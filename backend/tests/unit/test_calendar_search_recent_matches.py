"""Unit tests verifying chat calendar search returns recent matches when newest_first is set (#21573)."""

import asyncio
from datetime import datetime, timedelta, timezone
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


_httpx = _mod("httpx")


class TimeoutException(Exception):
    pass


class ConnectError(Exception):
    pass


_httpx.TimeoutException = TimeoutException
_httpx.ConnectError = ConnectError

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

_pkg("database")
_mod("database.notifications")

_pkg("models")
_cal_mut_mod = _mod("models.calendar_mutation")
_cal_mut_mod.CalendarMutationResult = MagicMock()
_cal_mut_mod.event_title = MagicMock(return_value="Event Title")
_cal_mut_mod.format_deleted_calendar_events = MagicMock(return_value="Deleted 1 event.")

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
    "utils.retrieval.tools._calendar_search_recent_matches_test",
    "utils/retrieval/tools/calendar_tools.py",
)
get_google_calendar_events = ct.get_google_calendar_events
get_calendar_events_tool = ct.get_calendar_events_tool


class TestCalendarSearchRecentMatches(unittest.IsolatedAsyncioTestCase):
    async def test_newest_first_true_returns_latest_matches_nearest_time_max(self):
        # 25 weekly occurrences of "1:1 with Andy"
        base_time = datetime(2025, 9, 1, 10, 0, tzinfo=timezone.utc)
        all_items = []
        for i in range(25):
            event_dt = base_time + timedelta(weeks=i)
            all_items.append({
                "id": f"event_{i:02d}",
                "summary": f"1:1 with Andy #{i}",
                "start": {"dateTime": event_dt.isoformat()},
                "end": {"dateTime": (event_dt + timedelta(hours=1)).isoformat()},
            })

        mock_api_request = AsyncMock(return_value={"items": all_items})
        with patch.object(ct, "google_api_request", mock_api_request):
            results = await get_google_calendar_events(
                access_token="fake_token",
                time_min=base_time,
                time_max=base_time + timedelta(weeks=26),
                max_results=10,
                search_query="Andy",
                newest_first=True,
            )

        # Must return the 10 events nearest time_max (the latest occurrences)
        assert len(results) == 10
        expected_ids = [f"event_{i:02d}" for i in range(15, 25)]
        actual_ids = [e["id"] for e in results]
        assert actual_ids == expected_ids
        # Specifically, the most recent meeting (event_24) is included
        assert actual_ids[-1] == "event_24"

    async def test_default_newest_first_false_preserves_earliest_first_with_search_query(self):
        """Regression test for maintainer feedback: other callers (mutation tools, event picker)
        must keep earliest-first by default even when search_query is supplied."""
        base_time = datetime(2025, 9, 1, 10, 0, tzinfo=timezone.utc)
        page1 = [
            {"id": f"event_{i:02d}", "summary": f"1:1 with Andy #{i}"}
            for i in range(15)
        ]
        page2 = [
            {"id": f"event_{i:02d}", "summary": f"1:1 with Andy #{i}"}
            for i in range(15, 25)
        ]

        mock_api_request = AsyncMock(
            side_effect=[
                {"items": page1, "nextPageToken": "token2"},
                {"items": page2},
            ]
        )
        with patch.object(ct, "google_api_request", mock_api_request):
            # newest_first defaults to False
            results = await get_google_calendar_events(
                access_token="fake_token",
                time_min=base_time,
                time_max=base_time + timedelta(weeks=26),
                max_results=10,
                search_query="Andy",
            )

        # Default must return earliest-first and stop on reaching max_results
        assert len(results) == 10
        expected_ids = [f"event_{i:02d}" for i in range(10)]
        actual_ids = [e["id"] for e in results]
        assert actual_ids == expected_ids
        # Page 2 was never fetched because max_results was reached on page 1
        assert mock_api_request.call_count == 1

    async def test_no_search_query_keeps_earliest_first(self):
        # 25 upcoming events
        base_time = datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc)
        page1 = [
            {"id": f"event_{i:02d}", "summary": f"Meeting #{i}"}
            for i in range(15)
        ]
        page2 = [
            {"id": f"event_{i:02d}", "summary": f"Meeting #{i}"}
            for i in range(15, 25)
        ]

        mock_api_request = AsyncMock(
            side_effect=[
                {"items": page1, "nextPageToken": "token2"},
                {"items": page2},
            ]
        )
        with patch.object(ct, "google_api_request", mock_api_request):
            results = await get_google_calendar_events(
                access_token="fake_token",
                time_min=base_time,
                time_max=base_time + timedelta(days=7),
                max_results=10,
                search_query=None,
            )

        # Without search_query, must keep earliest-first and stop on reaching max_results
        assert len(results) == 10
        expected_ids = [f"event_{i:02d}" for i in range(10)]
        actual_ids = [e["id"] for e in results]
        assert actual_ids == expected_ids
        assert mock_api_request.call_count == 1

    async def test_search_query_newest_first_with_fewer_than_max_results(self):
        all_items = [
            {"id": f"event_{i}", "summary": f"Andy Discussion {i}"}
            for i in range(4)
        ]

        mock_api_request = AsyncMock(return_value={"items": all_items})
        with patch.object(ct, "google_api_request", mock_api_request):
            results = await get_google_calendar_events(
                access_token="fake_token",
                max_results=10,
                search_query="Andy",
                newest_first=True,
            )

        assert len(results) == 4
        assert [e["id"] for e in results] == ["event_0", "event_1", "event_2", "event_3"]

    async def test_search_query_newest_first_collects_across_pages_before_tail_truncation(self):
        page1 = [{"id": f"event_{i:02d}", "summary": f"Andy #{i}"} for i in range(10)]
        page2 = [{"id": f"event_{i:02d}", "summary": f"Andy #{i}"} for i in range(10, 20)]

        mock_api_request = AsyncMock(
            side_effect=[
                {"items": page1, "nextPageToken": "token2"},
                {"items": page2},
            ]
        )
        with patch.object(ct, "google_api_request", mock_api_request):
            results = await get_google_calendar_events(
                access_token="fake_token",
                max_results=5,
                search_query="Andy",
                newest_first=True,
            )

        assert mock_api_request.call_count == 2
        assert len(results) == 5
        # The 5 nearest time_max (the latest events from page 2)
        assert [e["id"] for e in results] == ["event_15", "event_16", "event_17", "event_18", "event_19"]

    async def test_auth_error_retry_preserves_newest_first_with_search_query(self):
        """Verify that after an auth error and token refresh, the retry call still
        passes newest_first=True when search_query is set (catching regression noted by maintainer)."""
        all_items = [
            {
                "id": f"event_{i:02d}",
                "summary": f"1:1 with Andy #{i}",
                "start": {"dateTime": f"2026-03-{i+1:02d}T10:00:00Z"},
            }
            for i in range(20)
        ]

        auth_error = GoogleAPIError("Token expired", is_auth_error=True, status_code=401)
        mock_get_events = AsyncMock(
            side_effect=[
                auth_error,
                all_items[-10:],
            ]
        )

        with patch.object(ct, "prepare_access", return_value=("test-uid", {"connected": True}, "old-token", None)), \
             patch.object(ct, "refresh_google_token", new=AsyncMock(return_value="new-token")), \
             patch.object(ct, "_get_user_display_tz", new=AsyncMock(return_value=(timezone.utc, "UTC"))), \
             patch.object(ct, "get_google_calendar_events", mock_get_events):

            result = await get_calendar_events_tool(
                search_query="Andy",
                max_results=10,
            )

        assert mock_get_events.call_count == 2
        # First call passes newest_first=True
        assert mock_get_events.call_args_list[0].kwargs.get("newest_first") is True
        # Retry call after refresh MUST also pass newest_first=True
        assert mock_get_events.call_args_list[1].kwargs.get("newest_first") is True
        assert "1:1 with Andy #19" in result

