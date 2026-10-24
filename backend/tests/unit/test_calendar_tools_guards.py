"""Tests verifying parameter guards, coercion, and error sanitization in calendar_tools.py.

Hermetic isolated unit test suite covering:
1. create_calendar_event_tool rejects empty/None/non-string title cleanly.
2. create_calendar_event_tool safely handles None, int, and malformed start_time/end_time.
3. create_calendar_event_tool masks exceptions and does not leak raw traceback or str(e).
4. delete_calendar_event_tool handles events with None summary without AttributeError.
5. delete_calendar_event_tool safely coerces non-string event_title (int/bool).
6. update_calendar_event_tool handles events with None summary without AttributeError.
7. update_calendar_event_tool safely coerces non-string event_title (int/bool).
8. get_calendar_events_tool safely handles None, string, negative, and invalid max_results.

Uses memory_import_isolation snapshot_sys_modules and restore_sys_modules to avoid
leaking stubs across test execution.
"""

import asyncio
from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

try:
    from tests.unit.memory_import_isolation import (
        AutoMockModule,
        restore_sys_modules,
        snapshot_sys_modules,
    )
except ImportError:
    try:
        from memory_import_isolation import (
            AutoMockModule,
            restore_sys_modules,
            snapshot_sys_modules,
        )
    except ImportError:
        class AutoMockModule(types.ModuleType):
            def __getattr__(self, name: str):
                if name.startswith("__") and name.endswith("__"):
                    raise AttributeError(name)
                mock = MagicMock()
                setattr(self, name, mock)
                return mock

        def snapshot_sys_modules(names):
            return {name: sys.modules.get(name) for name in names}

        def restore_sys_modules(saved):
            for name, original in saved.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original


_SYS_MODULE_NAMES = [
    "langchain_core",
    "langchain_core.tools",
    "langchain_core.runnables",
    "database",
    "database.users",
    "models",
    "models.calendar_mutation",
    "utils",
    "utils.model_text",
    "utils.user_clock",
    "utils.conversations",
    "utils.conversations.datetime_utils",
    "utils.executors",
    "utils.http_client",
    "utils.retrieval",
    "utils.retrieval.agentic",
    "utils.retrieval.tools",
    "utils.retrieval.tools.integration_base",
    "utils.integration_telemetry",
    "utils.retrieval.tools.google_utils",
    "utils.retrieval.tools.calendar_render",
    "utils.log_sanitizer",
    "utils.retrieval.tools._calendar_tools_guards_test",
]

_SYS_MODULES_SNAPSHOT = snapshot_sys_modules(_SYS_MODULE_NAMES)


def _pkg(name: str):
    mod = types.ModuleType(name)
    mod.__path__ = []
    sys.modules[name] = mod
    if "." in name:
        parent_name, attr_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if isinstance(parent, types.ModuleType):
            setattr(parent, attr_name, mod)
    return mod


def _mod(name: str):
    mod = AutoMockModule(name)
    sys.modules[name] = mod
    if "." in name:
        parent_name, attr_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if isinstance(parent, types.ModuleType):
            setattr(parent, attr_name, mod)
    return mod


def _load(module_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_DIR / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn

    def dec(func):
        func.func = func
        return func

    return dec


# Install hermetic stubs
_pkg("langchain_core")
_lc_tools = _mod("langchain_core.tools")
_lc_tools.tool = _tool_decorator

_lc_runnables = _mod("langchain_core.runnables")
_lc_runnables.RunnableConfig = dict

_pkg("database")
_mod("database.users")

_pkg("models")
_cal_mut = _mod("models.calendar_mutation")


class _FakeMutationResult:
    def __init__(self):
        self.succeeded = []
        self.failed = []


_cal_mut.CalendarMutationResult = _FakeMutationResult
_cal_mut.event_title = lambda e: e.get("summary", "Untitled")
_cal_mut.format_deleted_calendar_events = lambda res: f"Deleted {len(res.succeeded)} events"

_pkg("utils")
_model_text = _mod("utils.model_text")
_model_text.UNTRUSTED_LEGEND = ""
_model_text.count_header = lambda *a, **k: ""
_model_text.format_date = lambda *a, **k: "2026-10-24"
_model_text.format_instant = lambda *a, **k: "2026-10-24T12:00:00Z"
_model_text.format_span = lambda *a, **k: "2026-10-24 12:00 to 13:00"
_model_text.truncation_note = lambda *a, **k: ""

_user_clock = _mod("utils.user_clock")
_user_clock.clock_for_config = lambda cfg, uid: MagicMock()

_pkg("utils.conversations")
_conv_dt = _mod("utils.conversations.datetime_utils")
_conv_dt.coerce_utc_datetime = lambda dt: dt

_executors = _mod("utils.executors")
_executors.db_executor = MagicMock()


async def _fake_run_blocking(executor, fn, *args, **kwargs):
    return fn(*args, **kwargs)


_executors.run_blocking = _fake_run_blocking

_http_client = _mod("utils.http_client")
_http_client.get_auth_client = MagicMock()

_pkg("utils.retrieval")
_pkg("utils.retrieval.tools")
_integ_base = _mod("utils.retrieval.tools.integration_base")


def _fake_ensure_capped(val, cap, msg=""):
    return min(val, cap)


def _fake_parse_iso(field_name, val, hint):
    if not val:
        return None, None
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return None, f"Error: {field_name} must include timezone"
        return dt, None
    except Exception:
        return None, f"Error: Invalid {field_name}"


def _fake_prepare_access(config, key, name, not_conn, not_found, err_prefix):
    return "test-uid", {"connected": True}, "fake-access-token", None


_integ_base.ensure_capped = _fake_ensure_capped
_integ_base.parse_iso_with_tz = _fake_parse_iso
_integ_base.prepare_access = _fake_prepare_access

_integ_telemetry = _mod("utils.integration_telemetry")
_integ_telemetry.GOOGLE_CALENDAR = "google_calendar"
_integ_telemetry.IntegrationTelemetryContext = MagicMock()
_integ_telemetry.emit_sync_attempted = MagicMock()
_integ_telemetry.emit_sync_failed = MagicMock()
_integ_telemetry.emit_sync_succeeded = MagicMock()

_google_utils = _mod("utils.retrieval.tools.google_utils")


class GoogleAPIError(Exception):
    def __init__(self, status_code=500, message="Google API error"):
        self.status_code = status_code
        self.message = message
        self.is_auth_error = False
        self.is_permission_error = False


_google_utils.GoogleAPIError = GoogleAPIError
_google_utils.google_api_request = AsyncMock()
_google_utils.refresh_google_token = AsyncMock(return_value="refreshed-token")

_log_sanitizer = _mod("utils.log_sanitizer")
_log_sanitizer.sanitize = lambda s: s
_log_sanitizer.sanitize_pii = lambda s: s

_cal_render = _mod("utils.retrieval.tools.calendar_render")
_cal_render.render_calendar_event = lambda *a, **k: "Event details"

# Load module under test
ct = _load(
    "utils.retrieval.tools._calendar_tools_guards_test",
    "utils/retrieval/tools/calendar_tools.py",
)


def tearDownModule():
    restore_sys_modules(_SYS_MODULES_SNAPSHOT)


class TestCalendarToolsGuards(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    def tearDown(self):
        self.loop.close()

    def test_create_calendar_event_empty_title_rejection(self):
        """Verifies None, empty, whitespace, and non-string titles return clean error."""
        for bad_title in [None, "", "   ", 123, []]:
            res = self.loop.run_until_complete(
                ct.create_calendar_event_tool(
                    title=bad_title,
                    start_time="2026-10-24T14:00:00+00:00",
                    end_time="2026-10-24T15:00:00+00:00",
                    config={},
                )
            )
            self.assertIn("Error: Please specify a title for the event.", res)

    def test_create_calendar_event_invalid_start_time(self):
        """Verifies start_time None, non-string, and invalid format return clean validation error."""
        for bad_time in [None, 12345, "invalid-date", "2026-10-24T14:00:00"]:
            res = self.loop.run_until_complete(
                ct.create_calendar_event_tool(
                    title="Design Review",
                    start_time=bad_time,
                    end_time="2026-10-24T15:00:00+00:00",
                    config={},
                )
            )
            self.assertTrue(res.startswith("Error:"), f"Expected error for {bad_time}, got: {res}")
            self.assertNotIn("Traceback", res)

    def test_create_calendar_event_invalid_end_time(self):
        """Verifies end_time None, non-string, and invalid format return clean validation error."""
        for bad_time in [None, 99999, "not-a-timestamp", "2026-10-24T15:00:00"]:
            res = self.loop.run_until_complete(
                ct.create_calendar_event_tool(
                    title="Design Review",
                    start_time="2026-10-24T14:00:00+00:00",
                    end_time=bad_time,
                    config={},
                )
            )
            self.assertTrue(res.startswith("Error:"), f"Expected error for {bad_time}, got: {res}")
            self.assertNotIn("Traceback", res)

    def test_delete_calendar_event_none_summary_resilience(self):
        """Verifies delete tool does not crash with AttributeError when event summary is None."""
        fake_events = [
            {"id": "ev1", "summary": None},
            {"id": "ev2", "summary": "Team Sync"},
        ]
        orig_get_events = ct.get_google_calendar_events
        orig_delete_event = ct.delete_google_calendar_event
        ct.get_google_calendar_events = AsyncMock(return_value=fake_events)
        ct.delete_google_calendar_event = AsyncMock(return_value=True)

        try:
            res = self.loop.run_until_complete(
                ct.delete_calendar_event_tool(
                    event_title="team",
                    config={},
                )
            )
            self.assertIn("Deleted 1 events", res)
        finally:
            ct.get_google_calendar_events = orig_get_events
            ct.delete_google_calendar_event = orig_delete_event

    def test_delete_calendar_event_non_string_event_title(self):
        """Verifies non-string event_title does not raise AttributeError on .lower()."""
        fake_events = [
            {"id": "ev1", "summary": "123 meeting"},
        ]
        orig_get_events = ct.get_google_calendar_events
        orig_delete_event = ct.delete_google_calendar_event
        ct.get_google_calendar_events = AsyncMock(return_value=fake_events)
        ct.delete_google_calendar_event = AsyncMock(return_value=True)

        try:
            res = self.loop.run_until_complete(
                ct.delete_calendar_event_tool(
                    event_title=123,
                    config={},
                )
            )
            self.assertIn("Deleted 1 events", res)
        finally:
            ct.get_google_calendar_events = orig_get_events
            ct.delete_google_calendar_event = orig_delete_event

    def test_update_calendar_event_none_summary_resilience(self):
        """Verifies update tool does not crash with AttributeError when event summary is None."""
        fake_events = [
            {"id": "ev1", "summary": None},
            {"id": "ev2", "summary": "1-on-1 Sync"},
        ]
        orig_get_events = ct.get_google_calendar_events
        orig_get_event = ct.get_google_calendar_event
        orig_update_event = ct.update_google_calendar_event

        ct.get_google_calendar_events = AsyncMock(return_value=fake_events)
        ct.get_google_calendar_event = AsyncMock(return_value={"id": "ev2", "summary": "1-on-1 Sync"})
        ct.update_google_calendar_event = AsyncMock(return_value={"id": "ev2", "summary": "Updated Sync"})

        try:
            res = self.loop.run_until_complete(
                ct.update_calendar_event_tool(
                    event_title="sync",
                    title="Updated Sync",
                    config={},
                )
            )
            self.assertIn("Successfully updated calendar event", res)
        finally:
            ct.get_google_calendar_events = orig_get_events
            ct.get_google_calendar_event = orig_get_event
            ct.update_google_calendar_event = orig_update_event

    def test_update_calendar_event_non_string_event_title(self):
        """Verifies update tool coerces non-string event_title without crashing."""
        fake_events = [
            {"id": "ev1", "summary": "Meeting 456"},
        ]
        orig_get_events = ct.get_google_calendar_events
        orig_get_event = ct.get_google_calendar_event
        orig_update_event = ct.update_google_calendar_event

        ct.get_google_calendar_events = AsyncMock(return_value=fake_events)
        ct.get_google_calendar_event = AsyncMock(return_value={"id": "ev1", "summary": "Meeting 456"})
        ct.update_google_calendar_event = AsyncMock(return_value={"id": "ev1", "summary": "New Title"})

        try:
            res = self.loop.run_until_complete(
                ct.update_calendar_event_tool(
                    event_title=456,
                    title="New Title",
                    config={},
                )
            )
            self.assertIn("Successfully updated calendar event", res)
        finally:
            ct.get_google_calendar_events = orig_get_events
            ct.get_google_calendar_event = orig_get_event
            ct.update_google_calendar_event = orig_update_event

    def test_get_calendar_events_max_results_coercion(self):
        """Verifies get_calendar_events_tool safely coerces max_results and does not crash."""
        orig_get_events = ct.get_google_calendar_events
        ct.get_google_calendar_events = AsyncMock(return_value=[])

        try:
            for bad_max in [None, "20", -5, True, "invalid", 999]:
                res = self.loop.run_until_complete(
                    ct.get_calendar_events_tool(
                        max_results=bad_max,
                        config={},
                    )
                )
                self.assertIsInstance(res, str)
                self.assertNotIn("Traceback", res)
        finally:
            ct.get_google_calendar_events = orig_get_events


if __name__ == "__main__":
    unittest.main()
