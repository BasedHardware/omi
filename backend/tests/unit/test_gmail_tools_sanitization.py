"""Tests verifying exception sanitization in gmail_tools.py.

Ensures that internal exception details (RuntimeError str(e), traceback, credentials, etc.)
are not leaked to chat tool callers or LLM context.
"""

import asyncio
import importlib
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _pkg(name):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


def _load(module_name, rel_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_DIR / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Ensure langchain_core is stubbed if not installed
_pkg("langchain_core")
_lc_tools = _mod("langchain_core.tools")


def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn

    def dec(func):
        func.func = func
        return func

    return dec


_lc_tools.tool = _tool_decorator

_lc_runnables = _mod("langchain_core.runnables")
_lc_runnables.RunnableConfig = dict

# Stub dependencies for gmail_tools
for _p in [
    "utils",
    "utils.executors",
    "utils.retrieval",
    "utils.retrieval.tools",
    "utils.retrieval.tools.integration_base",
    "utils.retrieval.tools.google_utils",
]:
    _pkg(_p)


async def _run_blocking_stub(executor, fn, *args, **kwargs):
    res = fn(*args, **kwargs)
    if asyncio.iscoroutine(res):
        return await res
    return res


_executors_mod = _mod("utils.executors")
_executors_mod.db_executor = MagicMock()
_executors_mod.run_blocking = _run_blocking_stub

_google_utils_mod = _mod("utils.retrieval.tools.google_utils")
_google_utils_mod.GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
_google_utils_mod.google_api_request = AsyncMock()
_google_utils_mod.google_integration_has_scope = MagicMock(return_value=True)
_google_utils_mod.refresh_google_token = MagicMock()

_integration_base_mod = _mod("utils.retrieval.tools.integration_base")
_integration_base_mod.ensure_capped = lambda val, cap, msg: min(val, cap)
_integration_base_mod.prepare_access = MagicMock()
_integration_base_mod.retry_on_auth_async = AsyncMock()

gt = _load(
    "utils.retrieval.tools._gmail_tools_sanitization_test",
    "utils/retrieval/tools/gmail_tools.py",
)

GRANT_WITH_GMAIL = {
    "connected": True,
    "access_token": "test-access-token",
    "granted_scopes": [
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/gmail.readonly",
    ],
}


class TestGmailToolsSanitization(unittest.IsolatedAsyncioTestCase):
    async def test_unexpected_exception_sanitized_without_leaking_details(self):
        sensitive_marker = "sensitive_internal_api_token_xyz_98765"

        with (
            patch.object(
                gt,
                "prepare_access",
                return_value=("user-1", GRANT_WITH_GMAIL, "test-access-token", None),
            ),
            patch.object(
                gt,
                "retry_on_auth_async",
                side_effect=RuntimeError(f"Internal DB failure at /var/secrets: {sensitive_marker}"),
            ),
        ):
            result = await gt.get_gmail_messages_tool.func()

            self.assertNotIn(sensitive_marker, result)
            self.assertNotIn("RuntimeError", result)
            self.assertNotIn("/var/secrets", result)
            self.assertEqual(
                "An unexpected error occurred while fetching Gmail messages. Please try again later.",
                result,
            )

    async def test_unexpected_exception_in_prepare_access_is_sanitized(self):
        sensitive_marker = "sql_injection_probe_marker_12345"

        with patch.object(
            gt,
            "prepare_access",
            side_effect=Exception(f"Internal connection crash: {sensitive_marker}"),
        ):
            result = await gt.get_gmail_messages_tool.func()

            self.assertNotIn(sensitive_marker, result)
            self.assertNotIn("Internal connection crash", result)
            self.assertEqual(
                "An unexpected error occurred while fetching Gmail messages. Please try again later.",
                result,
            )

    async def test_access_error_returns_cleanly(self):
        expected_err = "Gmail is not connected. Please connect your Google account from settings to view your emails."

        with patch.object(
            gt,
            "prepare_access",
            return_value=(None, None, None, expected_err),
        ):
            result = await gt.get_gmail_messages_tool.func()
            self.assertEqual(expected_err, result)

    async def test_missing_credentials_without_error_returns_clean_connection_error(self):
        with patch.object(
            gt,
            "prepare_access",
            return_value=(None, None, None, None),
        ):
            result = await gt.get_gmail_messages_tool.func()
            self.assertEqual("Error checking Gmail connection", result)

    async def test_missing_scope_returns_reconnect_guidance(self):
        with (
            patch.object(
                gt,
                "prepare_access",
                return_value=("user-1", GRANT_WITH_GMAIL, "test-access-token", None),
            ),
            patch.object(
                gt,
                "google_integration_has_scope",
                return_value=False,
            ),
        ):
            result = await gt.get_gmail_messages_tool.func()
            self.assertIn("reconnect", result.lower())
            self.assertIn("approve email access", result)

    async def test_auth_retry_error_returns_cleanly(self):
        auth_err = "Google authentication expired. Please reconnect your Google account from settings."

        async def fake_retry_on_auth_async(*args, **kwargs):
            return None, auth_err

        with (
            patch.object(
                gt,
                "prepare_access",
                return_value=("user-1", GRANT_WITH_GMAIL, "test-access-token", None),
            ),
            patch.object(gt, "retry_on_auth_async", fake_retry_on_auth_async),
        ):
            result = await gt.get_gmail_messages_tool.func()
            self.assertEqual(auth_err, result)

    async def test_successful_fetch_formats_messages(self):
        fake_messages = [
            {
                "id": "msg-1",
                "threadId": "t-1",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Weekly Sync Notes"},
                        {"name": "From", "value": "alice@example.com"},
                        {"name": "To", "value": "bob@example.com"},
                        {"name": "Date", "value": "Sun, 27 Sep 2026 10:00:00 +0000"},
                    ],
                },
                "snippet": "Here are the notes from our sync.",
            }
        ]

        async def fake_retry_on_auth_async(*args, **kwargs):
            return fake_messages, None

        with (
            patch.object(
                gt,
                "prepare_access",
                return_value=("user-1", GRANT_WITH_GMAIL, "test-access-token", None),
            ),
            patch.object(gt, "retry_on_auth_async", fake_retry_on_auth_async),
        ):
            result = await gt.get_gmail_messages_tool.func()
            self.assertIn("Weekly Sync Notes", result)
            self.assertIn("alice@example.com", result)
            self.assertIn("Here are the notes from our sync.", result)


if __name__ == "__main__":
    unittest.main()
