import asyncio
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Iterator
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _module(name: str, **attributes) -> ModuleType:
    module = ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


@pytest.fixture
def calendar_route_harness() -> Iterator[SimpleNamespace]:
    """Load the import-bound route during fixture setup, outside test CPU timing."""
    users_db = _module("database.users", get_integration=MagicMock())
    endpoints = _module("utils.other.endpoints", get_current_user_uid=lambda: "uid")

    async def get_events(**_kwargs):
        return [
            {
                "id": "event-1",
                "summary": "Planning",
                "htmlLink": "https://calendar.example/event-1",
            }
        ]

    async def refresh_token(_uid, _integration):
        return None

    calendar_tools = _module("utils.retrieval.tools.calendar_tools", get_google_calendar_events=get_events)
    google_utils = _module("utils.retrieval.tools.google_utils", refresh_google_token=refresh_token)
    calendar_utils = _module(
        "utils.conversations.calendar_utils",
        extract_attendees=lambda _event: (["Ada"], ["ada@example.com"]),
        parse_event_times=lambda _event: (
            datetime(2026, 7, 11, 10, 0),
            datetime(2026, 7, 11, 11, 0),
        ),
    )
    telemetry = _module(
        "utils.integration_telemetry",
        GOOGLE_CALENDAR="google_calendar",
        IntegrationTelemetryContext=lambda **kwargs: SimpleNamespace(**kwargs),
        emit_sync_attempted=MagicMock(),
        emit_sync_failed=MagicMock(),
        emit_sync_succeeded=MagicMock(),
    )

    stubs = {
        "database.users": users_db,
        "utils.other.endpoints": endpoints,
        "utils.retrieval.tools.calendar_tools": calendar_tools,
        "utils.retrieval.tools.google_utils": google_utils,
        "utils.conversations.calendar_utils": calendar_utils,
        "utils.integration_telemetry": telemetry,
    }

    with stub_modules(stubs):
        route = load_module_fresh(
            "routers.google_calendar",
            str(BACKEND_DIR / "routers" / "google_calendar.py"),
        )

        route.users_db.get_integration.return_value = {
            "connected": True,
            "access_token": "calendar-token",
        }
        offloads = []

        async def run_blocking(executor, function, *args, **kwargs):
            offloads.append((executor, function, args, kwargs))
            return function(*args, **kwargs)

        route.run_blocking = run_blocking
        yield SimpleNamespace(route=route, offloads=offloads)


def test_calendar_route_offloads_token_lookup_and_preserves_response_behavior(calendar_route_harness):
    route = calendar_route_harness.route
    result = asyncio.run(
        route.list_google_calendar_events(
            time_min=None,
            time_max=None,
            q=None,
            max_results=20,
            x_app_platform=None,
            x_app_version=None,
            x_app_build=None,
            uid="uid-calendar",
        )
    )

    assert [event.event_id for event in result] == ["event-1"]
    offloads = calendar_route_harness.offloads
    assert len(offloads) == 1
    executor, function, args, kwargs = offloads[0]
    assert executor is route.db_executor
    assert function is route._get_google_calendar_token
    assert args == ("uid-calendar",)
    assert kwargs == {}
