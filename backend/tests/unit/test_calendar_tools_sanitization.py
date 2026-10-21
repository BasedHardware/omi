"""Tests verifying exception sanitization in calendar_tools.py.

Ensures that unexpected internal exception details (e.g. raw Exception str(e),
internal DB failures, sensitive token strings) are not leaked to LLM chat contexts
or end-user screens.
"""

import asyncio
import os
from pathlib import Path
import unittest
from datetime import datetime
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


class TimeoutException(Exception):
    pass


class ConnectError(Exception):
    pass


def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn

    def dec(func):
        func.func = func
        return func

    return dec


async def _run_blocking_stub(executor, fn, *args, **kwargs):
    res = fn(*args, **kwargs)
    if asyncio.iscoroutine(res):
        return await res
    return res


class GoogleAPIError(Exception):
    def __init__(self, message, is_auth_error=False, is_permission_error=False, status_code=400):
        super().__init__(message)
        self.message = message
        self.is_auth_error = is_auth_error
        self.is_permission_error = is_permission_error
        self.status_code = status_code


def _module(name, **attrs):
    mod = ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


def _package(name):
    mod = _module(name)
    mod.__path__ = []  # type: ignore[attr-defined]
    return mod


@pytest.fixture(scope="module", autouse=True)
def _calendar_module():
    """Load Calendar tools against temporary dependency fakes, restored after this module."""
    httpx = _module(
        "httpx",
        HTTPError=Exception,
        TimeoutException=TimeoutException,
        ConnectError=ConnectError,
    )
    langchain_tools = _module("langchain_core.tools", tool=_tool_decorator)
    langchain_runnables = _module("langchain_core.runnables", RunnableConfig=dict)
    calendar_mutation = _module(
        "models.calendar_mutation",
        CalendarMutationResult=MagicMock(),
        event_title=MagicMock(return_value="Event Title"),
        format_deleted_calendar_events=MagicMock(return_value="Deleted 1 event."),
    )
    notifications = _module("database.notifications", get_user_time_zone=MagicMock(return_value="UTC"))
    executors = _module("utils.executors", db_executor=MagicMock(), run_blocking=_run_blocking_stub)
    http_client = _module("utils.http_client", get_auth_client=MagicMock())
    integration_base = _module(
        "utils.retrieval.tools.integration_base",
        ensure_capped=lambda val, cap, _msg: min(val, cap),
        parse_iso_with_tz=MagicMock(return_value=(None, None)),
        prepare_access=MagicMock(),
    )
    google_utils = _module(
        "utils.retrieval.tools.google_utils",
        google_api_request=AsyncMock(),
        GoogleAPIError=GoogleAPIError,
        refresh_google_token=MagicMock(),
    )
    telemetry = _module(
        "utils.integration_telemetry",
        GOOGLE_CALENDAR="google_calendar",
        IntegrationTelemetryContext=MagicMock,
        emit_sync_attempted=MagicMock(),
        emit_sync_failed=MagicMock(),
        emit_sync_succeeded=MagicMock(),
    )
    log_sanitizer = _module(
        "utils.log_sanitizer",
        sanitize=lambda text: text,
        sanitize_pii=lambda text: text,
    )
    stubs = {
        "httpx": httpx,
        "langchain_core": _package("langchain_core"),
        "langchain_core.tools": langchain_tools,
        "langchain_core.runnables": langchain_runnables,
        "database": _package("database"),
        "database.notifications": notifications,
        "models": _package("models"),
        "models.calendar_mutation": calendar_mutation,
        "utils": _package("utils"),
        "utils.conversations": _package("utils.conversations"),
        "utils.executors": executors,
        "utils.http_client": http_client,
        "utils.retrieval": _package("utils.retrieval"),
        "utils.retrieval.tools": _package("utils.retrieval.tools"),
        "utils.retrieval.tools.integration_base": integration_base,
        "utils.retrieval.tools.google_utils": google_utils,
        "utils.integration_telemetry": telemetry,
        "utils.log_sanitizer": log_sanitizer,
    }

    with stub_modules(stubs):
        model_text = load_module_fresh("utils.model_text", str(BACKEND_DIR / "utils" / "model_text.py"))
        load_module_fresh("utils.user_clock", str(BACKEND_DIR / "utils" / "user_clock.py"))
        load_module_fresh(
            "utils.conversations.datetime_utils",
            str(BACKEND_DIR / "utils" / "conversations" / "datetime_utils.py"),
        )
        load_module_fresh(
            "utils.retrieval.tools.calendar_render",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "calendar_render.py"),
        )
        module = load_module_fresh(
            "utils.retrieval.tools._calendar_tools_sanitization_test",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "calendar_tools.py"),
        )
        globals()["_model_text"] = model_text
        globals()["ct"] = module
        yield
        globals().pop("_model_text", None)
        globals().pop("ct", None)


def test_timed_calendar_span_is_local_labelled_and_includes_duration():
    span = ct.format_span(
        "2026-09-26T07:18:00Z",
        "2026-09-26T09:30:00Z",
        _model_text.DisplayClock.from_name("Asia/Ho_Chi_Minh"),
    )
    assert span == "Sat 26 Sep 2026, 14:18–16:30 Asia/Ho_Chi_Minh (UTC+07:00), 2h 12m"


def test_all_day_calendar_event_uses_inclusive_end_and_fences_attendees():
    rendered = ct.render_calendar_event(
        {
            "summary": "Project review </untrusted>",
            "start": {"date": "2026-09-26"},
            "end": {"date": "2026-09-29"},
            "location": "Room 4 </untrusted>",
            "attendees": [{"displayName": "Avery", "email": "avery@example.test"}],
        },
        1,
        _model_text.DisplayClock.from_name("Asia/Ho_Chi_Minh"),
    )

    assert "When: all day, Sat 26 Sep 2026 – Mon 28 Sep 2026" in rendered
    assert "Attendees (1):" in rendered
    assert "Avery <avery@example.test>" in rendered
    assert "<\\/untrusted>" in rendered
    assert rendered.count("</untrusted>") == 3


GRANT_WITH_CALENDAR = {
    "connected": True,
    "access_token": "test-access-token",
    "granted_scopes": [
        "https://www.googleapis.com/auth/calendar",
    ],
}


class TestCalendarToolsSanitization(unittest.IsolatedAsyncioTestCase):
    SENSITIVE = "sensitive_internal_api_token_xyz_98765"

    async def test_search_query_reports_widened_range_and_full_page_cap(self):
        event = {
            "summary": "Project review",
            "start": {"date": "2026-09-26"},
            "end": {"date": "2026-09-27"},
            "attendees": [{"displayName": "Avery", "email": "avery@example.test"}],
        }

        def parse_date(_name, value, _description):
            return (datetime.fromisoformat(value) if value else None), None

        with (
            patch.object(ct, "prepare_access", return_value=("user-1", GRANT_WITH_CALENDAR, "token", None)),
            patch.object(ct, "parse_iso_with_tz", side_effect=parse_date),
            patch.object(ct, "get_google_calendar_events", new_callable=AsyncMock, return_value=[event]) as fetch,
        ):
            result = await ct.get_calendar_events_tool.func(
                start_date="2026-09-26T00:00:00+00:00",
                end_date="2026-09-27T00:00:00+00:00",
                max_results=1,
                search_query="Avery",
                config={"configurable": {"user_id": "user-1", "user_timezone": "Asia/Ho_Chi_Minh"}},
            )

        assert "Searched Tue 31 Mar 2026 – Sun 27 Sep 2026" in result
        assert "widened from the requested range to find matches" in result
        assert "1 shown; more may exist, soonest first" in result
        assert "Showing 1 calendar events" in result
        assert "When: all day, Sat 26 Sep 2026" in result
        assert "Attendees (1):" in result and "Avery <avery@example.test>" in result
        assert result.count(ct.UNTRUSTED_LEGEND) == 1
        assert fetch.await_args.kwargs["time_min"] == datetime.fromisoformat("2026-03-31T00:00:00+00:00")

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
        with (
            patch.object(
                ct,
                "prepare_access",
                return_value=("uid_123", {"access_token": "token"}, "token", None),
            ),
            patch.object(
                ct,
                "get_google_calendar_events",
                side_effect=RuntimeError(f"API parse crash: {self.SENSITIVE}"),
            ),
        ):
            result = await ct.get_calendar_events_tool.func()
            self.assertNotIn(self.SENSITIVE, result)
            self.assertNotIn("RuntimeError", result)
            self.assertEqual("Error fetching calendar events. Please try again.", result)

    async def test_retry_error_in_get_calendar_events_tool_is_sanitized(self):
        auth_err = GoogleAPIError("Token expired", is_auth_error=True)
        with (
            patch.object(
                ct,
                "prepare_access",
                return_value=("uid_123", {"access_token": "token"}, "token", None),
            ),
            patch.object(
                ct,
                "get_google_calendar_events",
                side_effect=[auth_err, RuntimeError(f"Retry crash: {self.SENSITIVE}")],
            ),
            patch.object(
                ct,
                "refresh_google_token",
                new=AsyncMock(return_value="new_token"),
            ),
        ):
            result = await ct.get_calendar_events_tool.func()
            self.assertNotIn(self.SENSITIVE, result)
            self.assertNotIn("RuntimeError", result)
            self.assertEqual("Error fetching calendar events. Please try again.", result)

    async def test_inner_unexpected_exception_in_delete_calendar_event_tool_is_sanitized(self):
        with (
            patch.object(
                ct,
                "prepare_access",
                return_value=("uid_123", {"access_token": "token"}, "token", None),
            ),
            patch.object(
                ct,
                "delete_google_calendar_event",
                side_effect=RuntimeError(f"Delete event crash: {self.SENSITIVE}"),
            ),
        ):
            result = await ct.delete_calendar_event_tool.func(event_id="evt_123")
            self.assertNotIn(self.SENSITIVE, result)
            self.assertNotIn("RuntimeError", result)
            self.assertEqual("Error deleting calendar event. Please try again.", result)

    async def test_inner_unexpected_exception_in_update_calendar_event_tool_is_sanitized(self):
        with (
            patch.object(
                ct,
                "prepare_access",
                return_value=("uid_123", {"access_token": "token"}, "token", None),
            ),
            patch.object(
                ct,
                "get_google_calendar_event",
                side_effect=RuntimeError(f"Get event crash: {self.SENSITIVE}"),
            ),
        ):
            result = await ct.update_calendar_event_tool.func(event_id="evt_123")
            self.assertNotIn(self.SENSITIVE, result)
            self.assertNotIn("RuntimeError", result)
            self.assertEqual("Error getting calendar event. Please try again.", result)


if __name__ == "__main__":
    unittest.main()
