"""A calendar read over more than 30 days that reaches into the future starts at its soonest events.

``get_calendar_events_tool`` read any range over 30 days by walking backwards from its end
in 30-day windows and stopping once ``max_results`` events were found. That suits a range
that has already ended ("my meetings over the last two months"), but for "what's on my
calendar for the next two months" it returned events 30-60 days out, newest first, and
skipped everything in the next 30 days.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Iterator

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules
from utils.model_text import DisplayClock, format_span

BACKEND_DIR = Path(__file__).resolve().parents[2]
TOOLS_DIR = BACKEND_DIR / "utils" / "retrieval" / "tools"
GOOGLE_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _module(name: str, **attributes) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def _package(name: str) -> ModuleType:
    package = _module(name)
    package.__path__ = []
    return package


def _passthrough_tool(func=None, **_kwargs):
    return func if func is not None else (lambda inner: inner)


async def _run_blocking(_executor, function, *args, **kwargs):
    return function(*args, **kwargs)


class _GoogleAPIError(Exception):
    pass


def _event(summary: str, start: datetime) -> dict:
    return {
        "id": f"{summary}-{start.isoformat()}",
        "summary": summary,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": (start + timedelta(minutes=30)).isoformat()},
    }


def _start(event: dict) -> datetime:
    return datetime.fromisoformat(event["start"]["dateTime"])


def _parse_google_time(value: str) -> datetime:
    return datetime.strptime(value, GOOGLE_TIME_FORMAT).replace(tzinfo=timezone.utc)


class _FakeGoogleCalendar:
    """Lists events like the Calendar API: start in [timeMin, timeMax), ``q`` match, ascending."""

    def __init__(self, events: list[dict]):
        self.events = events
        self.requests: list[dict] = []

    async def request(self, method, url, access_token, params=None, body=None, allow_204=False):
        params = dict(params or {})
        self.requests.append(params)
        time_min = _parse_google_time(params["timeMin"])
        time_max = _parse_google_time(params["timeMax"])
        query = (params.get("q") or "").lower()
        matches = sorted(
            (
                event
                for event in self.events
                if time_min <= _start(event) < time_max and query in event["summary"].lower()
            ),
            key=_start,
        )
        return {"items": matches[: int(params["maxResults"])]}


@pytest.fixture
def calendar_tools() -> Iterator[ModuleType]:
    """Load the real calendar tool with its integration seams faked, restoring modules after."""
    stubs = {
        "langchain_core.tools": _module("langchain_core.tools", tool=_passthrough_tool),
        "langchain_core.runnables": _module("langchain_core.runnables", RunnableConfig=dict),
        "database.users": AutoMockModule("database.users"),
        "database.notifications": _module("database.notifications", get_user_time_zone=lambda _uid: "UTC"),
        "models.calendar_mutation": AutoMockModule("models.calendar_mutation"),
        "utils.executors": _module("utils.executors", db_executor=object(), run_blocking=_run_blocking),
        "utils.http_client": AutoMockModule("utils.http_client"),
        "utils.integration_telemetry": AutoMockModule("utils.integration_telemetry"),
        "utils.log_sanitizer": AutoMockModule("utils.log_sanitizer"),
        "utils.retrieval.agentic": AutoMockModule("utils.retrieval.agentic"),
        "utils.retrieval.tools": _package("utils.retrieval.tools"),
        "utils.retrieval.tools.google_utils": AutoMockModule("utils.retrieval.tools.google_utils"),
    }
    stubs["utils.retrieval.tools.google_utils"].GoogleAPIError = _GoogleAPIError

    with stub_modules(stubs):
        load_module_fresh("utils.retrieval.tools.calendar_render", str(TOOLS_DIR / "calendar_render.py"))
        # The real date parsing and max_results capping the tool relies on.
        load_module_fresh("utils.retrieval.tools.integration_base", str(TOOLS_DIR / "integration_base.py"))
        module = load_module_fresh("utils.retrieval.tools.calendar_tools", str(TOOLS_DIR / "calendar_tools.py"))
        module.prepare_access = lambda *_args: ("uid-1", {"connected": True, "access_token": "token"}, "token", None)
        yield module


def _use_calendar(calendar_tools: ModuleType, events: list[dict]) -> _FakeGoogleCalendar:
    calendar = _FakeGoogleCalendar(events)
    calendar_tools.google_api_request = calendar.request
    return calendar


def _shown(start: datetime) -> str:
    return f"When: {format_span(start, start + timedelta(minutes=30), DisplayClock.utc())}"


def _now_minute() -> datetime:
    return datetime.now(timezone.utc).replace(second=0, microsecond=0)


def test_range_into_the_future_lists_the_soonest_events_first(calendar_tools):
    now = _now_minute()
    starts = [now + timedelta(days=day, hours=1) for day in range(1, 60)]
    calendar = _use_calendar(calendar_tools, [_event("Standup", start) for start in starts])

    result = asyncio.run(
        calendar_tools.get_calendar_events_tool(
            start_date=(now - timedelta(hours=1)).isoformat(),
            end_date=(now + timedelta(days=60)).isoformat(),
        )
    )

    assert result.startswith("Calendar Events (10 shown; more may exist,")
    shown = [start for start in starts if _shown(start) in result]
    assert shown == starts[:10]
    positions = [result.index(_shown(start)) for start in shown]
    assert positions == sorted(positions)
    assert len(calendar.requests) == 1


def test_range_that_has_ended_still_walks_back_from_its_end(calendar_tools):
    end = _now_minute() - timedelta(hours=1)
    start = end - timedelta(days=60)
    calendar = _use_calendar(calendar_tools, [])

    asyncio.run(calendar_tools.get_calendar_events_tool(start_date=start.isoformat(), end_date=end.isoformat()))

    first_window = calendar.requests[0]
    assert _parse_google_time(first_window["timeMax"]) == end
    assert _parse_google_time(first_window["timeMin"]) == end - timedelta(days=30)


def test_mixed_naive_and_aware_event_starts_do_not_crash_the_sort(calendar_tools):
    """A floating-time/ICS-imported event (naive ``dateTime``) alongside a normal
    aware event used to raise TypeError when the >30-day walk-back sorted
    ``events_with_time`` by start, since one key was offset-naive and the rest
    (including the ``datetime.min`` fallback) were offset-aware.
    """
    end = _now_minute() - timedelta(hours=1)
    start = end - timedelta(days=60)

    naive_start = (end - timedelta(days=5)).replace(tzinfo=None)
    naive_event = {
        "id": "floating-time-import",
        "summary": "Floating",
        "start": {"dateTime": naive_start.isoformat()},
        "end": {"dateTime": (naive_start + timedelta(minutes=30)).isoformat()},
    }
    aware_event = _event("Standup", end - timedelta(days=10))

    async def _request(_method, _url, _access_token, params=None, body=None, allow_204=False):
        return {"items": [naive_event, aware_event]}

    calendar_tools.google_api_request = _request

    result = asyncio.run(
        calendar_tools.get_calendar_events_tool(start_date=start.isoformat(), end_date=end.isoformat())
    )

    assert "Floating" in result
    assert "Standup" in result
    assert result.index("Floating") < result.index("Standup")
