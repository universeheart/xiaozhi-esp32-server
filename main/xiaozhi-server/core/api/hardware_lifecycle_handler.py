import hashlib
import hmac
import os
import re
import shutil
import time
import uuid

from aiohttp import web

from config.logger import setup_logging
from config.manage_api_client import activate_hardware, unbind_hardware, verify_hardware

TAG = __name__


class HardwareQrError(ValueError):
    pass


class HardwareLifecycleHandler:
    """Validates signed factory QR data before delegating atomic persistence to manager-api."""

    def __init__(self, config: dict):
        self.logger = setup_logging()
        settings = config.get("hardware_activation", {})
        self.secret = str(settings.get("qr_secret", ""))
        self.max_age = int(settings.get("qr_max_age_seconds", 600))
        self.memory_root = os.path.abspath(
            settings.get("memory_root", os.path.join(os.getcwd(), ".superbrain_mem"))
        )
        self._seen_nonces = {}

    @staticmethod
    def normalize_mac(value: str) -> str:
        compact = re.sub(r"[^0-9a-fA-F]", "", str(value or "")).lower()
        if not re.fullmatch(r"[0-9a-f]{12}", compact):
            raise HardwareQrError("invalid mac address")
        return ":".join(compact[i : i + 2] for i in range(0, 12, 2))

    def verify_qr(self, qr: dict, consume_nonce: bool = False) -> dict:
        if not self.secret or "你" in self.secret:
            raise HardwareQrError("hardware qr secret is not configured")
        required = ("productCode", "serialNumber", "macAddress", "issuedAt", "nonce", "signature")
        if not isinstance(qr, dict) or any(not qr.get(key) for key in required):
            raise HardwareQrError("incomplete hardware qr payload")
        mac = self.normalize_mac(qr["macAddress"])
        try:
            issued_at = int(qr["issuedAt"])
        except (TypeError, ValueError) as exc:
            raise HardwareQrError("invalid qr issue time") from exc
        now = int(time.time())
        if issued_at > now + 60 or now - issued_at > self.max_age:
            raise HardwareQrError("hardware qr has expired")
        nonce = str(qr["nonce"])
        self._seen_nonces = {key: expiry for key, expiry in self._seen_nonces.items() if expiry > now}
        if consume_nonce and nonce in self._seen_nonces:
            raise HardwareQrError("hardware qr has already been used")
        canonical = "|".join((str(qr["productCode"]), str(qr["serialNumber"]), mac, str(issued_at), nonce))
        expected = hmac.new(self.secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(qr["signature"]).lower()):
            raise HardwareQrError("hardware qr signature is invalid")
        if consume_nonce:
            self._seen_nonces[nonce] = now + self.max_age
        return {
            "productCode": str(qr["productCode"]),
            "serialNumber": str(qr["serialNumber"]),
            "macAddress": mac,
            "board": qr.get("board"),
            "appVersion": qr.get("appVersion"),
        }

    async def verify(self, request):
        try:
            data = await request.json()
            hardware = self.verify_qr(data.get("qr", data), consume_nonce=False)
            registry = await verify_hardware({key: hardware[key] for key in ("productCode", "serialNumber", "macAddress")})
            return web.json_response({"code": 0, "msg": "success", "data": {**hardware, **registry}})
        except (HardwareQrError, ValueError) as exc:
            return web.json_response({"code": 10223, "msg": str(exc)}, status=400)
        except Exception as exc:
            self.logger.bind(tag=TAG).error(f"硬件可信清单校验失败: {exc}")
            return web.json_response({"code": 502, "msg": "hardware registry verification failed"}, status=502)

    async def activate(self, request):
        token = self._account_token(request)
        if not token:
            return web.json_response({"code": 401, "msg": "account token is required"}, status=401)
        try:
            data = await request.json()
            activation_code = str(data.get("activationCode") or "")
            if not re.fullmatch(r"\d{6}", activation_code):
                raise HardwareQrError("a live six-digit device activation code is required")
            hardware = self.verify_qr(data.get("qr", data), consume_nonce=True)
            result = await activate_hardware({
                **hardware,
                "requestId": str(data.get("requestId") or uuid.uuid4()),
                "accountToken": token,
                "activationCode": activation_code,
                "agentName": data.get("agentName"),
            })
            return web.json_response({"code": 0, "msg": "success", "data": result})
        except (HardwareQrError, ValueError) as exc:
            return web.json_response({"code": 10226, "msg": str(exc)}, status=400)
        except Exception as exc:
            self.logger.bind(tag=TAG).error(f"硬件激活失败: {exc}")
            return web.json_response({"code": 502, "msg": "hardware activation failed"}, status=502)

    async def unbind(self, request):
        token = self._account_token(request)
        if not token:
            return web.json_response({"code": 401, "msg": "account token is required"}, status=401)
        try:
            data = await request.json()
            mac = self.normalize_mac(data.get("macAddress"))
            result = await unbind_hardware({
                "requestId": str(data.get("requestId") or uuid.uuid4()),
                "accountToken": token,
                "macAddress": mac,
                "confirmation": data.get("confirmation"),
            })
            removed = self.purge_local_memory(result.get("memoryKey", mac))
            return web.json_response({"code": 0, "msg": "success", "data": {**result, "localMemoryPurged": removed}})
        except (HardwareQrError, ValueError) as exc:
            return web.json_response({"code": 10227, "msg": str(exc)}, status=400)
        except Exception as exc:
            self.logger.bind(tag=TAG).error(f"硬件解绑失败: {exc}")
            return web.json_response({"code": 502, "msg": "hardware unbind failed"}, status=502)

    async def options(self, _request):
        return web.Response(headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, OPTIONS",
            "Access-Control-Allow-Headers": "authorization, content-type",
        })

    def purge_local_memory(self, memory_key: str) -> bool:
        compact = re.sub(r"[^0-9a-zA-Z]", "", str(memory_key)).lower()
        if not compact or not os.path.isdir(self.memory_root):
            return False
        removed = False
        root = os.path.realpath(self.memory_root)
        for entry in os.listdir(root):
            candidate = os.path.realpath(os.path.join(root, entry))
            entry_compact = re.sub(r"[^0-9a-zA-Z]", "", entry).lower()
            if entry_compact == compact and candidate.startswith(root + os.sep) and os.path.isdir(candidate):
                shutil.rmtree(candidate)
                removed = True
        return removed

    @staticmethod
    def _account_token(request) -> str:
        authorization = request.headers.get("Authorization", "")
        return authorization[7:].strip() if authorization.startswith("Bearer ") else ""
