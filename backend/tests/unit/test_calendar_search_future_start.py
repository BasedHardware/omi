"""A calendar search with only a future start date searches forward from it.

``get_calendar_events_tool`` defaulted a missing ``end_date`` to *now* whenever a
``search_query`` was set. With a future ``start_date`` ("Do I have anything with Andy
coming up?") the window then ended before it started, the widening step padded it
backwards from now, and the upcoming meetings were never requested at all.
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


def test_search_with_future_start_and_no_end_finds_the_upcoming_meeting(calendar_tools):
    now = _now_minute()
    start = now + timedelta(days=3)
    upcoming = start + timedelta(days=1, hours=2)
    past = now - timedelta(days=30)
    calendar = _use_calendar(
        calendar_tools,
        [_event("1:1 with Andy", upcoming), _event("1:1 with Andy", past)],
    )

    result = asyncio.run(calendar_tools.get_calendar_events_tool(start_date=start.isoformat(), search_query="Andy"))

    assert _shown(upcoming) in result
    # The requested window has to reach past the start date, not stop at the moment of the call.
    assert _parse_google_time(calendar.requests[0]["timeMax"]) > start


def test_search_with_past_start_and_no_end_still_ends_now(calendar_tools):
    # "Meetings with Andy since June": an old start keeps the window ending at the time of the call.
    start = _now_minute() - timedelta(days=60)
    calendar = _use_calendar(calendar_tools, [_event("1:1 with Andy", start + timedelta(days=1))])

    before = datetime.now(timezone.utc).replace(microsecond=0)
    asyncio.run(calendar_tools.get_calendar_events_tool(start_date=start.isoformat(), search_query="Andy"))
    after = datetime.now(timezone.utc)

    time_max = _parse_google_time(calendar.requests[0]["timeMax"])
    assert before <= time_max <= after
