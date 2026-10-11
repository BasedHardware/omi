"""Tests verifying exception sanitization in calendar_tools.py.

Ensures that unexpected internal exception details (e.g. raw Exception str(e),
internal DB failures, sensitive token strings) are not leaked to LLM chat contexts
or end-user screens.
"""

import asyncio
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


# Stub httpx
_httpx = _mod("httpx")


class TimeoutException(Exception):
    pass


class ConnectError(Exception):
    pass


_httpx.TimeoutException = TimeoutException
_httpx.ConnectError = ConnectError

# Stub langchain_core
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

# Stub database.notifications
_pkg("database")
_notif_mod = _mod("database.notifications")

# Stub models.calendar_mutation
_pkg("models")
_cal_mut_mod = _mod("models.calendar_mutation")
_cal_mut_mod.CalendarMutationResult = MagicMock()
_cal_mut_mod.event_title = MagicMock(return_value="Event Title")
_cal_mut_mod.format_deleted_calendar_events = MagicMock(return_value="Deleted 1 event.")

# Stub utils packages
for _p in [
    "utils",
    "utils.executors",
    "utils.http_client",
    "utils.retrieval",
    "utils.retrieval.tools",
    "utils.retrieval.tools.integration_base",
    "utils.retrieval.tools.google_utils",
    "utils.integration_telemetry",
    "utils.log_sanitizer",
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

_http_client_mod = _mod("utils.http_client")
_http_client_mod.get_auth_client = MagicMock()

_telemetry_mod = _mod("utils.integration_telemetry")
_telemetry_mod.GOOGLE_CALENDAR = "google_calendar"
_telemetry_mod.IntegrationTelemetryContext = MagicMock
_telemetry_mod.emit_sync_attempted = MagicMock()
_telemetry_mod.emit_sync_failed = MagicMock()
_telemetry_mod.emit_sync_succeeded = MagicMock()

_log_sanitizer_mod = _mod("utils.log_sanitizer")
_log_sanitizer_mod.sanitize = lambda text: text
_log_sanitizer_mod.sanitize_pii = lambda text: text

_google_utils_mod = _mod("utils.retrieval.tools.google_utils")
_google_utils_mod.google_api_request = AsyncMock()


class GoogleAPIError(Exception):
    def __init__(self, message, is_auth_error=False, is_permission_error=False, status_code=400):
        super().__init__(message)
        self.message = message
        self.is_auth_error = is_auth_error
        self.is_permission_error = is_permission_error
        self.status_code = status_code


_google_utils_mod.GoogleAPIError = GoogleAPIError
_google_utils_mod.refresh_google_token = MagicMock()

_integration_base_mod = _mod("utils.retrieval.tools.integration_base")
_integration_base_mod.ensure_capped = lambda val, cap, msg: min(val, cap)
_integration_base_mod.parse_iso_with_tz = MagicMock(return_value=(None, None))
_integration_base_mod.prepare_access = MagicMock()


def _load(module_name, rel_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_DIR / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


ct = _load(
    "utils.retrieval.tools._calendar_tools_sanitization_test",
    "utils/retrieval/tools/calendar_tools.py",
)

GRANT_WITH_CALENDAR = {
    "connected": True,
    "access_token": "test-access-token",
    "granted_scopes": [
        "https://www.googleapis.com/auth/calendar",
    ],
}


class TestCalendarToolsSanitization(unittest.IsolatedAsyncioTestCase):
    SENSITIVE = "sensitive_internal_api_token_xyz_98765"

    async def test_unexpected_exception_in_get_calendar_events_tool_is_sanitized(self):
        with patch.object(
            ct,
            "prepare_access",
            side_effect=RuntimeError(f"Internal connection crash: {self.SENSITIVE}"),
        ):
            result = await ct.get_calendar_events_tool.func()
            self.assertNotIn(self.SENSITIVE, result)
            self.assertNotIn("RuntimeError", result)
            self.assertEqual(
                "An unexpected error occurred while fetching calendar events. Please try again later.",
                result,
            )

    async def test_unexpected_exception_in_create_calendar_event_tool_is_sanitized(self):
        with patch.object(
            ct,
            "prepare_access",
            side_effect=RuntimeError(f"Internal DB fault: {self.SENSITIVE}"),
        ):
            result = await ct.create_calendar_event_tool.func(
                title="Design Sync",
                start_time="2026-09-28T10:00:00Z",
                end_time="2026-09-28T11:00:00Z",
            )
            self.assertNotIn(self.SENSITIVE, result)
            self.assertNotIn("RuntimeError", result)
            self.assertEqual(
                "An unexpected error occurred while creating the calendar event. Please try again later.",
                result,
            )

    async def test_unexpected_exception_in_delete_calendar_event_tool_is_sanitized(self):
        with patch.object(
            ct,
            "prepare_access",
            side_effect=RuntimeError(f"Failed to query backend: {self.SENSITIVE}"),
        ):
            result = await ct.delete_calendar_event_tool.func(event_title="Design Sync")
            self.assertNotIn(self.SENSITIVE, result)
            self.assertNotIn("RuntimeError", result)
            self.assertEqual(
                "An unexpected error occurred while deleting calendar events. Please try again later.",
                result,
            )

    async def test_unexpected_exception_in_update_calendar_event_tool_is_sanitized(self):
        with patch.object(
            ct,
            "prepare_access",
            side_effect=RuntimeError(f"Mutation failure: {self.SENSITIVE}"),
        ):
            result = await ct.update_calendar_event_tool.func(event_id="evt_123")
            self.assertNotIn(self.SENSITIVE, result)
            self.assertNotIn("RuntimeError", result)
            self.assertEqual(
                "An unexpected error occurred while updating the calendar event. Please try again later.",
                result,
            )

    async def test_access_error_returns_cleanly(self):
        expected_err = (
            "Google Calendar is not connected. "
            "Please connect your Google Calendar from settings to view your events."
        )
        with patch.object(
            ct,
            "prepare_access",
            return_value=(None, None, None, expected_err),
        ):
            result = await ct.get_calendar_events_tool.func()
            self.assertEqual(expected_err, result)

    async def test_missing_credentials_returns_clean_error(self):
        with patch.object(
            ct,
            "prepare_access",
            return_value=(None, None, None, None),
        ):
            result = await ct.get_calendar_events_tool.func()
            self.assertEqual("Google Calendar access token not found.", result)

    async def test_inner_unexpected_exception_in_get_calendar_events_tool_is_sanitized(self):
        with patch.object(
            ct,
            "prepare_access",
            return_value=("uid_123", {"access_token": "token"}, "token", None),
        ), patch.object(
            ct,
            "get_google_calendar_events",
            side_effect=RuntimeError(f"API parse crash: {self.SENSITIVE}"),
        ):
            result = await ct.get_calendar_events_tool.func()
            self.assertNotIn(self.SENSITIVE, result)
            self.assertNotIn("RuntimeError", result)
            self.assertEqual("Error fetching calendar events. Please try again.", result)

    async def test_retry_error_in_get_calendar_events_tool_is_sanitized(self):
        auth_err = GoogleAPIError("Token expired", is_auth_error=True)
        with patch.object(
            ct,
            "prepare_access",
            return_value=("uid_123", {"access_token": "token"}, "token", None),
        ), patch.object(
            ct,
            "get_google_calendar_events",
            side_effect=[auth_err, RuntimeError(f"Retry crash: {self.SENSITIVE}")],
        ), patch.object(
            ct,
            "refresh_google_token",
            new=AsyncMock(return_value="new_token"),
        ):
            result = await ct.get_calendar_events_tool.func()
            self.assertNotIn(self.SENSITIVE, result)
            self.assertNotIn("RuntimeError", result)
            self.assertEqual("Error fetching calendar events. Please try again.", result)

    async def test_inner_unexpected_exception_in_delete_calendar_event_tool_is_sanitized(self):
        with patch.object(
            ct,
            "prepare_access",
            return_value=("uid_123", {"access_token": "token"}, "token", None),
        ), patch.object(
            ct,
            "delete_google_calendar_event",
            side_effect=RuntimeError(f"Delete event crash: {self.SENSITIVE}"),
        ):
            result = await ct.delete_calendar_event_tool.func(event_id="evt_123")
            self.assertNotIn(self.SENSITIVE, result)
            self.assertNotIn("RuntimeError", result)
            self.assertEqual("Error deleting calendar event. Please try again.", result)

    async def test_inner_unexpected_exception_in_update_calendar_event_tool_is_sanitized(self):
        with patch.object(
            ct,
            "prepare_access",
            return_value=("uid_123", {"access_token": "token"}, "token", None),
        ), patch.object(
            ct,
            "get_google_calendar_event",
            side_effect=RuntimeError(f"Get event crash: {self.SENSITIVE}"),
        ):
            result = await ct.update_calendar_event_tool.func(event_id="evt_123")
            self.assertNotIn(self.SENSITIVE, result)
            self.assertNotIn("RuntimeError", result)
            self.assertEqual("Error getting calendar event. Please try again.", result)


if __name__ == "__main__":
    unittest.main()
