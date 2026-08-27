"""Offline regression tests for the native SuperBrain memory provider.

The production module has imports for logging and manager-api integration.  These
tests replace those boundaries before importing the provider so they can run with
the Python standard library only and never contact a model, database, or network.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock


SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))


class _NullLogger:
    def bind(self, **_kwargs):
        return self

    def debug(self, *_args, **_kwargs):
        return None

    info = debug
    warning = debug
    error = debug


def _install_import_stubs() -> None:
    config_package = types.ModuleType("config")
    config_package.__path__ = [str(SERVER_ROOT / "config")]
    sys.modules.setdefault("config", config_package)

    logger_module = types.ModuleType("config.logger")
    logger_module.setup_logging = lambda: _NullLogger()
    sys.modules["config.logger"] = logger_module

    loader_module = types.ModuleType("config.config_loader")
    loader_module.get_project_dir = lambda: str(SERVER_ROOT)
    sys.modules["config.config_loader"] = loader_module

    api_module = types.ModuleType("config.manage_api_client")

    async def _unused_async(*_args, **_kwargs):
        return None

    api_module.generate_and_save_chat_summary = _unused_async
    api_module.upsert_memory_profile = _unused_async
    sys.modules["config.manage_api_client"] = api_module

    util_module = types.ModuleType("core.utils.util")
    util_module.check_model_key = lambda *_args, **_kwargs: None
    sys.modules["core.utils.util"] = util_module


_install_import_stubs()

from core.providers.memory.superbrain_native import superbrain_native as subject  # noqa: E402


class _FakeLlm:
    api_key = "test-only-key"
    model_name = "fake-memory-llm"

    def __init__(self, response: str | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls = 0

    def response_no_stream(self, *_args, **_kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response


def _message(role: str, content: str) -> SimpleNamespace:
    return SimpleNamespace(role=role, content=content)


class SuperBrainHelperTests(unittest.TestCase):
    def test_extract_json_payload_accepts_plain_fenced_and_embedded_json(self):
        expected = {"username": "Alice"}
        self.assertEqual(subject._extract_json_payload(json.dumps(expected)), expected)
        self.assertEqual(
            subject._extract_json_payload("```json\n{\"username\": \"Alice\"}\n```"),
            expected,
        )
        self.assertEqual(
            subject._extract_json_payload("prefix {\"username\": \"Alice\"} suffix"),
            expected,
        )
        self.assertEqual(subject._extract_json_payload("not json"), {})

    def test_as_working_memory_normalizes_values_and_drops_unknown_keys(self):
        normalized = subject._as_working_memory(
            {
                "active_tasks": [" first ", "", 2],
                "open_topics": " topic ",
                "unknown": ["ignored"],
            }
        )
        self.assertEqual(normalized["active_tasks"], ["first", "2"])
        self.assertEqual(normalized["open_topics"], ["topic"])
        self.assertNotIn("unknown", normalized)
        self.assertEqual(normalized["pending_confirmations"], [])


class SuperBrainFileTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def _provider(self, role_id: str = "AA:BB:CC:DD:EE:FF", llm=None):
        provider = subject.MemoryProvider({})
        provider.memory_root = self.temp_dir.name
        provider.init_memory(role_id, llm or _FakeLlm("{}"))
        return provider

    def test_user_directories_are_isolated_and_stay_under_memory_root(self):
        first = self._provider("AA:BB:CC:DD:EE:01")
        second = self._provider("AA:BB:CC:DD:EE:02")
        self.assertNotEqual(first.user_memory_dir, second.user_memory_dir)
        root = os.path.realpath(self.temp_dir.name)
        self.assertEqual(os.path.commonpath([root, first.user_memory_dir]), root)
        self.assertEqual(os.path.commonpath([root, second.user_memory_dir]), root)

        first._write_text(first._path("profile"), "first-user")
        second._write_text(second._path("profile"), "second-user")
        self.assertEqual(first._read_text(first._path("profile")), "first-user")
        self.assertEqual(second._read_text(second._path("profile")), "second-user")

    def test_atomic_text_and_json_writes_leave_no_temp_file(self):
        provider = self._provider()
        text_path = provider._path("profile")
        json_path = provider._path("semantic")
        provider._write_text(text_path, "new profile")
        provider._write_json(json_path, {"name": "Alice"})
        self.assertEqual(provider._read_text(text_path), "new profile")
        self.assertEqual(provider._read_json(json_path, {}), {"name": "Alice"})
        self.assertFalse(os.path.exists(f"{text_path}.tmp"))
        self.assertFalse(os.path.exists(f"{json_path}.tmp"))

    def test_profile_update_preserves_known_fields_and_pins_device_identity(self):
        provider = self._provider("device-001")
        provider._write_json(
            provider._path("semantic"),
            {"username": "Alice", "occupation": "Engineer", "profile_md": "old"},
        )
        profile = provider._apply_profile_update(
            {"username": None, "occupation": "Architect", "profile_md": "updated"}
        )
        self.assertEqual(profile["mac_address"], "device-001")
        self.assertEqual(profile["username"], "Alice")
        self.assertEqual(profile["occupation"], "Architect")
        self.assertEqual(provider._read_text(provider._path("profile")), "updated")

    def test_dialogue_snapshot_is_idempotent(self):
        provider = self._provider()
        provider._now = lambda: "2026-08-25 12:00:00"
        messages = [_message("user", "I like tea"), _message("assistant", "Noted")]
        provider._record_dialogue_snapshots(messages)
        provider._record_dialogue_snapshots(messages)

        working = provider._read_json(
            provider._daily_path("working"), subject.DEFAULT_WORKING_MEMORY
        )
        monthly = provider._read_text(provider._monthly_path("episodic"))
        self.assertEqual(len(working["recent_dialogues"]), 1)
        self.assertEqual(monthly.count("I like tea"), 1)


class SuperBrainSaveTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addAsyncCleanup(self._cleanup_temp_dir)

    async def _cleanup_temp_dir(self):
        self.temp_dir.cleanup()

    def _provider(self, llm):
        provider = subject.MemoryProvider({})
        provider.memory_root = self.temp_dir.name
        provider.init_memory("device-001", llm)
        provider._now = lambda: "2026-08-25 12:00:00"
        return provider

    async def test_duplicate_dialogue_calls_llm_and_api_only_once(self):
        response = json.dumps(
            {
                "username": "Alice",
                "interests": ["tea", "music"],
                "profile_md": "Alice likes tea and music.",
            }
        )
        llm = _FakeLlm(response)
        provider = self._provider(llm)
        messages = [_message("user", "I like tea"), _message("assistant", "Noted")]
        original_upsert = subject.upsert_memory_profile
        upsert = AsyncMock(return_value={"ok": True})
        subject.upsert_memory_profile = upsert
        self.addAsyncCleanup(self._restore_upsert, original_upsert)

        await provider.save_memory(messages, "session-1")
        await provider.save_memory(messages, "session-1")

        self.assertEqual(llm.calls, 1)
        upsert.assert_awaited_once()

    async def _restore_upsert(self, original):
        subject.upsert_memory_profile = original

    async def test_llm_failure_keeps_dialogue_snapshot_and_returns_without_raising(self):
        provider = self._provider(_FakeLlm(error=RuntimeError("model unavailable")))
        messages = [_message("user", "Remember this"), _message("assistant", "Okay")]
        result = await provider.save_memory(messages, "session-2")
        working = provider._read_json(
            provider._daily_path("working"), subject.DEFAULT_WORKING_MEMORY
        )
        self.assertIsInstance(result, str)
        self.assertEqual(len(working["recent_dialogues"]), 1)


if __name__ == "__main__":
    unittest.main()
