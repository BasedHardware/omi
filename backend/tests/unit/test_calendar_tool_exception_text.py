"""Calendar chat tools must not return raw exception text (issue #15635)."""

import asyncio
import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_LEAK = "provider-secret-token"


class _AutoMockModule(ModuleType):
    def __init__(self, name):
        super().__init__(name)
        self.__path__ = []
        self.__file__ = f"<stub {name}>"

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


def _register(saved: dict, name: str):
    if name not in saved:
        saved[name] = sys.modules.get(name)
    mod = _AutoMockModule(name)
    sys.modules[name] = mod
    if "." in name:
        parent_name, attr = name.rsplit(".", 1)
        setattr(_register(saved, parent_name), attr, mod)
    return mod


def _load(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _parse_iso_with_tz(field_name, value, tz_required_msg):
    if not value:
        return None, None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None, f"Error: Invalid {field_name} format. Expected {tz_required_msg}: {value}"
    if parsed.tzinfo is None:
        return None, f"Error: {field_name} must include timezone {tz_required_msg}: {value}"
    return parsed, None


@pytest.fixture
def calendar_tools():
    saved: dict = {}
    for name in [
        "httpx",
        "langchain_core",
        "langchain_core.tools",
        "langchain_core.runnables",
        "database",
        "database.users",
        "database.notifications",
        "models",
        "utils",
        "utils.executors",
        "utils.http_client",
        "utils.integration_telemetry",
        "utils.log_sanitizer",
        "utils.model_text",
        "utils.user_clock",
        "utils.conversations",
        "utils.conversations.datetime_utils",
        "utils.retrieval",
        "utils.retrieval.tools",
        "utils.retrieval.tools.integration_base",
        "utils.retrieval.tools.google_utils",
        "utils.retrieval.tools.calendar_render",
    ]:
        _register(saved, name)
    sys.modules["langchain_core.tools"].tool = lambda func=None, **_kw: func if func is not None else (lambda f: f)

    mutation = _load(
        "models.calendar_mutation",
        BACKEND_DIR / "models" / "calendar_mutation.py",
    )
    tools = _load(
        "utils.retrieval.tools.calendar_tools",
        BACKEND_DIR / "utils" / "retrieval" / "tools" / "calendar_tools.py",
    )
    tools.CalendarMutationResult = mutation.CalendarMutationResult
    tools.format_deleted_calendar_events = mutation.format_deleted_calendar_events
    tools.calendar_event_title = mutation.event_title
    tools.parse_iso_with_tz = _parse_iso_with_tz

    async def run_blocking(*_args, **_kwargs):
        return ("uid-1", {"id": "cal"}, "token", None)

    tools.run_blocking = run_blocking
    tools.clock_for_config = lambda *_args, **_kwargs: object()
    try:
        yield tools
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
        sys.modules.pop("models.calendar_mutation", None)
        sys.modules.pop("utils.retrieval.tools.calendar_tools", None)


def _config():
    return {"configurable": {"user_id": "uid-1"}}


def test_bad_start_time_hides_parser_exception(calendar_tools):
    result = asyncio.run(
        calendar_tools.create_calendar_event_tool(
            "Meet",
            "not-a-time",
            "2024-01-20T15:00:00-08:00",
            config=_config(),
        )
    )

    assert result.startswith("Error: Invalid start_time format")
    assert "not-a-time" in result
    assert "Invalid isoformat string" not in result


def test_delete_failure_hides_provider_exception(calendar_tools):
    async def get_events(**_kwargs):
        return [{"id": "evt-1", "summary": "Standup", "start": {"dateTime": "2024-01-20T18:00:00-08:00"}}]

    async def delete_event(_token, _event_id):
        raise RuntimeError(f"{_LEAK}-abc")

    calendar_tools.get_google_calendar_events = get_events
    calendar_tools.delete_google_calendar_event = delete_event

    result = asyncio.run(
        calendar_tools.delete_calendar_event_tool(
            event_title="Standup",
            start_date="2024-01-20T00:00:00-08:00",
            end_date="2024-01-21T00:00:00-08:00",
            config=_config(),
        )
    )

    assert "could not delete this event" in result
    assert "Standup" in result
    assert _LEAK not in result


def test_update_search_failure_hides_provider_exception(calendar_tools):
    async def get_events(**_kwargs):
        raise RuntimeError(f"{_LEAK}-xyz")

    calendar_tools.get_google_calendar_events = get_events

    result = asyncio.run(
        calendar_tools.update_calendar_event_tool(
            event_title="Standup",
            config=_config(),
        )
    )

    assert result == "Error searching for calendar event. Please try again."
    assert _LEAK not in result
