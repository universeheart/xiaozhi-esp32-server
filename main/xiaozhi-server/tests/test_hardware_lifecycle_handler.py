import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from core.api.hardware_lifecycle_handler import HardwareLifecycleHandler, HardwareQrError


class _Request:
    def __init__(self, body, token="account-token"):
        self._body = body
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def json(self):
        return self._body


class HardwareLifecycleHandlerTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.logger_patch = patch("core.api.hardware_lifecycle_handler.setup_logging", return_value=MagicMock())
        self.logger_patch.start()
        self.temp = tempfile.TemporaryDirectory()
        self.secret = "factory-secret-for-tests"
        self.handler = HardwareLifecycleHandler({"hardware_activation": {
            "qr_secret": self.secret,
            "qr_max_age_seconds": 600,
            "memory_root": self.temp.name,
        }})

    def tearDown(self):
        self.temp.cleanup()
        self.logger_patch.stop()

    def qr(self, **overrides):
        data = {
            "productCode": "COMPANION_V1", "serialNumber": "SN000001",
            "macAddress": "FC-0C-70-20-83-A6", "issuedAt": int(time.time()),
            "nonce": "nonce-1", "board": "esp32", "appVersion": "1.0.1",
        }
        data.update(overrides)
        canonical = "|".join((data["productCode"], data["serialNumber"],
                self.handler.normalize_mac(data["macAddress"]), str(data["issuedAt"]), data["nonce"]))
        data["signature"] = hmac.new(self.secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        return data

    def test_valid_qr_and_replay_protection(self):
        qr = self.qr()
        verified = self.handler.verify_qr(qr, consume_nonce=True)
        self.assertEqual("fc:0c:70:20:83:a6", verified["macAddress"])
        with self.assertRaises(HardwareQrError):
            self.handler.verify_qr(qr, consume_nonce=True)

    def test_tampered_and_expired_qr_fail(self):
        qr = self.qr()
        qr["serialNumber"] = "TAMPERED"
        with self.assertRaises(HardwareQrError):
            self.handler.verify_qr(qr)
        expired = self.qr(issuedAt=int(time.time()) - 601, nonce="expired")
        with self.assertRaises(HardwareQrError):
            self.handler.verify_qr(expired)

    async def test_verify_requires_both_signature_and_factory_registry(self):
        with patch("core.api.hardware_lifecycle_handler.verify_hardware", new=AsyncMock(
                return_value={"verified": True, "status": "PROVISIONED"})) as call:
            response = await self.handler.verify(_Request({"qr": self.qr(nonce="verify")}))
            self.assertEqual(200, response.status)
            call.assert_awaited_once()
        with patch("core.api.hardware_lifecycle_handler.verify_hardware", new=AsyncMock(
                side_effect=RuntimeError("not in registry"))):
            response = await self.handler.verify(_Request({"qr": self.qr(nonce="unknown")}))
            self.assertEqual(502, response.status)

    async def test_activation_requires_account_and_forwards_verified_data(self):
        missing = await self.handler.activate(_Request({"qr": self.qr()}, token=""))
        self.assertEqual(401, missing.status)
        with patch("core.api.hardware_lifecycle_handler.activate_hardware", new=AsyncMock(
                return_value={"status": "ACTIVATED", "agentId": "agent-1"})) as call:
            response = await self.handler.activate(_Request({"qr": self.qr(nonce="activate"),
                    "activationCode": "123456", "agentName": "客厅小伴"}))
            self.assertEqual(200, response.status)
            payload = call.await_args.args[0]
            self.assertEqual("account-token", payload["accountToken"])
            self.assertEqual("fc:0c:70:20:83:a6", payload["macAddress"])
            self.assertEqual("123456", payload["activationCode"])

    async def test_unbind_purges_local_memory_only_after_manager_success(self):
        memory_dir = os.path.join(self.temp.name, "fc_0c_70_20_83_a6")
        os.makedirs(memory_dir)
        with open(os.path.join(memory_dir, "profile.md"), "w", encoding="utf-8") as stream:
            stream.write("private")
        with patch("core.api.hardware_lifecycle_handler.unbind_hardware", new=AsyncMock(
                return_value={"status": "UNBOUND", "memoryKey": "fc:0c:70:20:83:a6"})):
            response = await self.handler.unbind(_Request({"macAddress": "fc:0c:70:20:83:a6", "confirmation": "UNBIND"}))
            self.assertEqual(200, response.status)
            self.assertFalse(os.path.exists(memory_dir))

        retained = os.path.join(self.temp.name, "fc_0c_70_20_83_a6")
        os.makedirs(retained)
        with patch("core.api.hardware_lifecycle_handler.unbind_hardware", new=AsyncMock(side_effect=RuntimeError("db down"))):
            response = await self.handler.unbind(_Request({"macAddress": "fc:0c:70:20:83:a6", "confirmation": "UNBIND"}))
            self.assertEqual(502, response.status)
            self.assertTrue(os.path.isdir(retained))


if __name__ == "__main__":
    unittest.main()
