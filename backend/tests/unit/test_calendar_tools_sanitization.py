"""Tests verifying exception sanitization in calendar_tools.py.

Ensures that internal exception details (ValueError str(e), database secrets, etc.)
are not leaked to chat tool callers or plugin logs.
"""

import asyncio
import importlib
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
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

for _p in [
    "database",
    "models",
    "utils",
    "utils.retrieval",
    "utils.retrieval.tools",
]:
    _pkg(_p)

for _name, _attrs in {
    "database.notifications": ["get_user_time_zone"],
    "database.users": ["get_people_by_ids"],
    "models.calendar_mutation": [
        "CalendarMutationResult",
        "event_title",
        "format_deleted_calendar_events",
    ],
    "utils.executors": ["db_executor", "run_blocking"],
    "utils.http_client": ["get_auth_client"],
    "utils.integration_telemetry": [
        "GOOGLE_CALENDAR",
        "IntegrationTelemetryContext",
        "emit_sync_attempted",
        "emit_sync_failed",
        "emit_sync_succeeded",
        "sync_telemetry_context",
    ],
    "utils.log_sanitizer": ["sanitize", "sanitize_pii"],
    "utils.retrieval.agentic": ["agent_config_context"],
    "utils.retrieval.tools.google_utils": [
        "GoogleAPIError",
        "create_google_calendar_event",
        "delete_google_calendar_event",
        "get_google_calendar_event",
        "get_google_calendar_events",
        "google_api_request",
        "refresh_google_token",
        "update_google_calendar_event",
    ],
    "utils.retrieval.tools.integration_base": [
        "ensure_capped",
        "parse_iso_with_tz",
        "prepare_access",
    ],
}.items():
    _m = _mod(_name)
    for _a in _attrs:
        if not hasattr(_m, _a):
            setattr(_m, _a, MagicMock())

_telemetry = sys.modules["utils.integration_telemetry"]
_telemetry.emit_sync_failed = MagicMock()
_telemetry.emit_sync_succeeded = MagicMock()
_telemetry.emit_sync_attempted = MagicMock()
_telemetry.sync_telemetry_context = MagicMock()

_executors = sys.modules["utils.executors"]
async def _async_run_blocking(executor, fn, *args, **kwargs):
    return fn(*args, **kwargs)
_executors.run_blocking = _async_run_blocking

_log_sanitizer = sys.modules["utils.log_sanitizer"]
_log_sanitizer.sanitize = lambda s: str(s)
_log_sanitizer.sanitize_pii = lambda s: str(s)

cal = _load(
    "utils.retrieval.tools._calendar_tools_sanitization_test",
    "utils/retrieval/tools/calendar_tools.py",
)


class TestCalendarToolsSanitization(unittest.TestCase):
    def test_create_calendar_event_invalid_start_time(self):
        async def _run():
            config = {"configurable": {"user_id": "u1"}}
            with patch.object(cal, "prepare_access", return_value=("u1", {}, "tok", None)):
                result = await cal.create_calendar_event_tool.func(
                    title="Meeting",
                    start_time="bad-start-time",
                    end_time="2026-09-22T12:00:00+00:00",
                    config=config,
                )
                self.assertIn("Error: Invalid start_time format", result)
                self.assertIn("bad-start-time", result)
                self.assertNotIn("ValueError", result)

        asyncio.run(_run())

    def test_create_calendar_event_invalid_end_time(self):
        async def _run():
            config = {"configurable": {"user_id": "u1"}}
            with patch.object(cal, "prepare_access", return_value=("u1", {}, "tok", None)):
                result = await cal.create_calendar_event_tool.func(
                    title="Meeting",
                    start_time="2026-09-22T11:00:00+00:00",
                    end_time="bad-end-time",
                    config=config,
                )
                self.assertIn("Error: Invalid end_time format", result)
                self.assertIn("bad-end-time", result)
                self.assertNotIn("ValueError", result)

        asyncio.run(_run())

    def test_create_calendar_event_unexpected_exception(self):
        async def _run():
            config = {"configurable": {"user_id": "u1"}}
            with patch.object(cal, "prepare_access", side_effect=RuntimeError("internal calendar secret leak")):
                result = await cal.create_calendar_event_tool.func(
                    title="Meeting",
                    start_time="2026-09-22T11:00:00+00:00",
                    end_time="2026-09-22T12:00:00+00:00",
                    config=config,
                )
                self.assertEqual("Unexpected error creating calendar event. Please try again later.", result)
                self.assertNotIn("internal calendar secret leak", result)
                self.assertNotIn("RuntimeError", result)

        asyncio.run(_run())

    def test_get_calendar_events_unexpected_exception(self):
        async def _run():
            config = {"configurable": {"user_id": "u1"}}
            with patch.object(cal, "prepare_access", side_effect=RuntimeError("internal calendar db leak")):
                result = await cal.get_calendar_events_tool.func(config=config)
                self.assertEqual("Unexpected error fetching calendar events. Please try again later.", result)
                self.assertNotIn("internal calendar db leak", result)
                self.assertNotIn("RuntimeError", result)

        asyncio.run(_run())

    def test_delete_calendar_event_unexpected_exception(self):
        async def _run():
            config = {"configurable": {"user_id": "u1"}}
            with patch.object(cal, "prepare_access", side_effect=RuntimeError("internal calendar delete leak")):
                result = await cal.delete_calendar_event_tool.func(event_title="Meeting", config=config)
                self.assertEqual("Unexpected error deleting calendar events. Please try again later.", result)
                self.assertNotIn("internal calendar delete leak", result)
                self.assertNotIn("RuntimeError", result)

        asyncio.run(_run())

    def test_update_calendar_event_unexpected_exception(self):
        async def _run():
            config = {"configurable": {"user_id": "u1"}}
            with patch.object(cal, "prepare_access", side_effect=RuntimeError("internal calendar update leak")):
                result = await cal.update_calendar_event_tool.func(event_title="Meeting", config=config)
                self.assertEqual("Unexpected error updating calendar event. Please try again later.", result)
                self.assertNotIn("internal calendar update leak", result)
                self.assertNotIn("RuntimeError", result)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
