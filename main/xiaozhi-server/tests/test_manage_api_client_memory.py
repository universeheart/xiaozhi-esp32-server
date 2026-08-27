"""Contract tests for the SuperBrain profile manager-api request."""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock


SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))


try:
    import httpx  # noqa: F401
except ModuleNotFoundError:
    httpx_stub = types.ModuleType("httpx")

    class _HttpxError(Exception):
        pass

    class _HttpStatusError(_HttpxError):
        def __init__(self, *args, response=None, **kwargs):
            super().__init__(*args)
            self.response = response

    httpx_stub.ConnectError = _HttpxError
    httpx_stub.TimeoutException = _HttpxError
    httpx_stub.NetworkError = _HttpxError
    httpx_stub.HTTPStatusError = _HttpStatusError
    httpx_stub.Limits = object
    httpx_stub.AsyncClient = object
    sys.modules["httpx"] = httpx_stub

from config import manage_api_client as subject  # noqa: E402


class MemoryProfileApiContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_instance = subject.ManageApiClient._instance

    async def asyncTearDown(self):
        subject.ManageApiClient._instance = self.original_instance

    async def test_upsert_maps_internal_profile_to_java_dto_contract(self):
        fake_client = type("FakeClient", (), {})()
        fake_client._execute_async_request = AsyncMock(return_value={"saved": True})
        subject.ManageApiClient._instance = fake_client

        result = await subject.upsert_memory_profile(
            {
                "mac_address": "device-001",
                "member_id": "member-01",
                "username": "Alice",
                "occupation": "Engineer",
                "primary_occupation": "Architect",
                "interests": "tea,music",
                "favorite_role": "friend",
                "favorite_tv_show": "show",
                "chinese_name": "艾丽丝",
                "english_name": "Alice",
                "profile_md": "# Alice",
            }
        )

        self.assertEqual(result, {"saved": True})
        fake_client._execute_async_request.assert_awaited_once_with(
            "POST",
            "/memory/profile/upsert",
            json={
                "macAddress": "device-001",
                "memberId": "member-01",
                "username": "Alice",
                "occupation": "Engineer",
                "primaryOccupation": "Architect",
                "interests": "tea,music",
                "favoriteRole": "friend",
                "favoriteTvShow": "show",
                "chineseName": "艾丽丝",
                "englishName": "Alice",
                "profileMd": "# Alice",
            },
        )

    async def test_upsert_without_initialized_client_is_a_safe_noop(self):
        subject.ManageApiClient._instance = None
        result = await subject.upsert_memory_profile(
            {"mac_address": "device-001", "profile_md": "# Alice"}
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
