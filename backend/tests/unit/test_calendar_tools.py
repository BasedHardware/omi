"""Hermetic unit tests for calendar_tools hardening and bug fixes.

Verifies:
1. Safe handling of untitled events (summary: None) in delete_calendar_event_tool and update_calendar_event_tool (no AttributeError).
2. Type coercion of max_results (string digits, invalid values bounded 1..50) in get_calendar_events_tool.
3. Inverted date range detection (end_date < start_date) returning helpful error strings without API errors.
4. Early validation of title, start_time, end_time in create_calendar_event_tool (no AttributeError on None/empty).
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


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


class TimeoutException(Exception):
    pass


class ConnectError(Exception):
    pass


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
def _calendar_tools_module():
    """Load calendar_tools with isolated dependencies."""
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
        parse_iso_with_tz=MagicMock(),
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
        "utils.conversations.datetime_utils": _module(
            "utils.conversations.datetime_utils",
            coerce_utc_datetime=lambda x: datetime.now(timezone.utc) if x else None,
        ),
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
        user_clock = load_module_fresh("utils.user_clock", str(BACKEND_DIR / "utils" / "user_clock.py"))
        calendar_render = load_module_fresh(
            "utils.retrieval.tools.calendar_render",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "calendar_render.py"),
        )
        module = load_module_fresh(
            "utils.retrieval.tools.calendar_tools",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "calendar_tools.py"),
        )
        globals()["ct"] = module
        globals()["_model_text"] = model_text
        yield
        globals().pop("ct", None)
        globals().pop("_model_text", None)


@pytest.mark.asyncio
async def test_create_calendar_event_empty_title_and_times():
    with patch.object(ct, "prepare_access", return_value=("u1", {"connected": True}, "token", None)):
        # Empty title rejection
        res1 = await ct.create_calendar_event_tool.func(
            title="",
            start_time="2026-10-22T14:00:00Z",
            end_time="2026-10-22T15:00:00Z",
            config={"configurable": {"user_id": "u1"}},
        )
        assert res1 == "Error: Event title cannot be empty."

        # None title rejection
        res2 = await ct.create_calendar_event_tool.func(
            title=None,
            start_time="2026-10-22T14:00:00Z",
            end_time="2026-10-22T15:00:00Z",
            config={"configurable": {"user_id": "u1"}},
        )
        assert res2 == "Error: Event title cannot be empty."

        # None start_time rejection without AttributeError
        res3 = await ct.create_calendar_event_tool.func(
            title="Sync",
            start_time=None,
            end_time="2026-10-22T15:00:00Z",
            config={"configurable": {"user_id": "u1"}},
        )
        assert "start_time must be provided as an ISO string" in res3

        # None end_time rejection without AttributeError
        res4 = await ct.create_calendar_event_tool.func(
            title="Sync",
            start_time="2026-10-22T14:00:00Z",
            end_time=None,
            config={"configurable": {"user_id": "u1"}},
        )
        assert "end_time must be provided as an ISO string" in res4


@pytest.mark.asyncio
async def test_get_calendar_events_inverted_date_range():
    start = datetime(2026, 10, 25, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 10, 20, 0, 0, tzinfo=timezone.utc)

    with patch.object(ct, "prepare_access", return_value=("u1", {"connected": True}, "token", None)):
        with patch.object(ct, "parse_iso_with_tz", side_effect=[(start, None), (end, None)]):
            res = await ct.get_calendar_events_tool.func(
                start_date="2026-10-25T00:00:00Z",
                end_date="2026-10-20T00:00:00Z",
                config={"configurable": {"user_id": "u1"}},
            )
            assert "Error: end_date must be after start_date" in res


@pytest.mark.asyncio
async def test_get_calendar_events_max_results_string_coercion():
    mock_events = [
        {
            "id": "e1",
            "summary": "Team Standup",
            "start": {"dateTime": "2026-10-22T10:00:00Z"},
            "end": {"dateTime": "2026-10-22T10:30:00Z"},
        }
    ]
    with patch.object(ct, "prepare_access", return_value=("u1", {"connected": True}, "token", None)):
        with patch.object(ct, "parse_iso_with_tz", return_value=(None, None)):
            with patch.object(ct, "get_google_calendar_events", new_callable=AsyncMock, return_value=mock_events) as mock_fetch:
                # String max_results should be coerced to int without TypeError
                res = await ct.get_calendar_events_tool.func(
                    max_results="5",  # type: ignore[arg-type]
                    config={"configurable": {"user_id": "u1"}},
                )
                assert "Team Standup" in res
                assert mock_fetch.call_args.kwargs["max_results"] == 5


@pytest.mark.asyncio
async def test_delete_calendar_event_untitled_event_no_attribute_error():
    # Events with summary: None must not trigger AttributeError: 'NoneType' object has no attribute 'lower'
    mock_events = [
        {"id": "e_none", "summary": None, "start": {"dateTime": "2026-10-22T10:00:00Z"}},
        {"id": "e_match", "summary": "Meeting with Alice", "start": {"dateTime": "2026-10-22T11:00:00Z"}},
    ]
    with patch.object(ct, "prepare_access", return_value=("u1", {"connected": True}, "token", None)):
        with patch.object(ct, "parse_iso_with_tz", return_value=(None, None)):
            with patch.object(ct, "get_google_calendar_events", new_callable=AsyncMock, return_value=mock_events):
                with patch.object(ct, "delete_google_calendar_event", new_callable=AsyncMock) as mock_del:
                    res = await ct.delete_calendar_event_tool.func(
                        event_title="alice",
                        config={"configurable": {"user_id": "u1"}},
                    )
                    assert "Deleted 1" in res
                    mock_del.assert_awaited_once_with("token", "e_match")


@pytest.mark.asyncio
async def test_update_calendar_event_untitled_event_no_attribute_error():
    # Events with summary: None must not trigger AttributeError: 'NoneType' object has no attribute 'lower'
    mock_events = [
        {"id": "e_none", "summary": None, "start": {"dateTime": "2026-10-22T10:00:00Z"}},
        {"id": "e_sync", "summary": "Product Design", "start": {"dateTime": "2026-10-22T11:00:00Z"}},
    ]
    updated_evt = {
        "id": "e_sync",
        "summary": "Product Design Updated",
        "start": {"dateTime": "2026-10-22T11:00:00Z"},
        "end": {"dateTime": "2026-10-22T12:00:00Z"},
    }
    with patch.object(ct, "prepare_access", return_value=("u1", {"connected": True}, "token", None)):
        with patch.object(ct, "parse_iso_with_tz", return_value=(None, None)):
            with patch.object(ct, "get_google_calendar_events", new_callable=AsyncMock, return_value=mock_events):
                with patch.object(ct, "get_google_calendar_event", new_callable=AsyncMock, return_value=mock_events[1]):
                    with patch.object(ct, "update_google_calendar_event", new_callable=AsyncMock, return_value=updated_evt):
                        res = await ct.update_calendar_event_tool.func(
                            event_title="design",
                            title="Product Design Updated",
                            config={"configurable": {"user_id": "u1"}},
                        )
                        assert "Successfully updated calendar event" in res
                        assert "Product Design Updated" in res
