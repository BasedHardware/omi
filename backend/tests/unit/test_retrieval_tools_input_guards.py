"""Hermetic unit tests for input validation and defensive guards in retrieval tools.

Covers:
- web_tools.fetch_url_tool: non-string, None, whitespace URL validation
- perplexity_tools.perplexity_web_search_tool: non-string, None, whitespace query validation
- calendar_tools.create_calendar_event_tool: title, start_time, end_time fast-fail validation
- calendar_tools.delete_calendar_event_tool: whitespace sanitization & titleless event resilience
- calendar_tools.update_calendar_event_tool: whitespace sanitization & titleless event resilience
"""

import asyncio
from pathlib import Path
from types import ModuleType
from typing import Iterator

import pytest

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parents[2]
TOOLS_DIR = BACKEND_DIR / "utils" / "retrieval" / "tools"


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
    def wrap(fn):
        fn.ainvoke = lambda args: fn(**args)
        return fn

    if func is not None:
        return wrap(func)
    return wrap


async def _run_blocking(_executor, function, *args, **kwargs):
    return function(*args, **kwargs)


class _GoogleAPIError(Exception):
    pass


@pytest.fixture
def calendar_tools_mod() -> Iterator[ModuleType]:
    """Load calendar_tools with integration dependencies stubbed via sanctioned import isolation."""
    stubs = {
        "langchain_core.tools": _module("langchain_core.tools", tool=_passthrough_tool),
        "langchain_core.runnables": _module("langchain_core.runnables", RunnableConfig=dict),
        "database.users": AutoMockModule("database.users"),
        "database.notifications": _module("database.notifications", get_user_time_zone=lambda _uid: "UTC"),
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
        load_module_fresh("utils.retrieval.tools.integration_base", str(TOOLS_DIR / "integration_base.py"))
        module = load_module_fresh("utils.retrieval.tools.calendar_tools", str(TOOLS_DIR / "calendar_tools.py"))
        module.prepare_access = lambda *_args: ("uid-test", {"connected": True, "access_token": "token-test"}, "token-test", None)
        yield module


@pytest.fixture
def web_tools_mod() -> Iterator[ModuleType]:
    """Load web_tools with minimal stubs."""
    stubs = {
        "langchain_core.tools": _module("langchain_core.tools", tool=_passthrough_tool),
        "utils.http_client": AutoMockModule("utils.http_client"),
        "utils.log_sanitizer": AutoMockModule("utils.log_sanitizer"),
        "utils.retrieval.tools": _package("utils.retrieval.tools"),
    }
    with stub_modules(stubs):
        yield load_module_fresh("utils.retrieval.tools.web_tools", str(TOOLS_DIR / "web_tools.py"))


@pytest.fixture
def perplexity_tools_mod() -> Iterator[ModuleType]:
    """Load perplexity_tools with minimal stubs."""
    stubs = {
        "langchain_core.tools": _module("langchain_core.tools", tool=_passthrough_tool),
        "utils.generated_compute": AutoMockModule("utils.generated_compute"),
        "utils.executors": _module("utils.executors", db_executor=object(), run_blocking=_run_blocking),
        "utils.http_client": AutoMockModule("utils.http_client"),
        "utils.llm.gateway_client": AutoMockModule("utils.llm.gateway_client"),
        "utils.log_sanitizer": AutoMockModule("utils.log_sanitizer"),
        "utils.retrieval.tools": _package("utils.retrieval.tools"),
    }
    with stub_modules(stubs):
        yield load_module_fresh("utils.retrieval.tools.perplexity_tools", str(TOOLS_DIR / "perplexity_tools.py"))


# ---------------------------------------------------------------------------
# web_tools.fetch_url_tool tests
# ---------------------------------------------------------------------------

def test_fetch_url_tool_none_and_empty_guards(web_tools_mod):
    res_none = asyncio.run(web_tools_mod.fetch_url_tool.ainvoke({"url": None}))
    assert "Error: URL is required and cannot be empty." in res_none

    res_empty = asyncio.run(web_tools_mod.fetch_url_tool.ainvoke({"url": "   "}))
    assert "Error: URL is required and cannot be empty." in res_empty

    res_num = asyncio.run(web_tools_mod.fetch_url_tool.ainvoke({"url": 12345}))
    assert "Error: URL is required and cannot be empty." in res_num

    res_invalid_scheme = asyncio.run(web_tools_mod.fetch_url_tool.ainvoke({"url": "ftp://example.com"}))
    assert "Error: URL must start with http:// or https://" in res_invalid_scheme


# ---------------------------------------------------------------------------
# perplexity_tools.perplexity_web_search_tool tests
# ---------------------------------------------------------------------------

def test_perplexity_web_search_tool_none_and_empty_guards(perplexity_tools_mod):
    res_none = asyncio.run(perplexity_tools_mod.perplexity_web_search_tool.ainvoke({"query": None}))
    assert "Error: query is required and cannot be empty." in res_none

    res_empty = asyncio.run(perplexity_tools_mod.perplexity_web_search_tool.ainvoke({"query": "   "}))
    assert "Error: query is required and cannot be empty." in res_empty

    res_num = asyncio.run(perplexity_tools_mod.perplexity_web_search_tool.ainvoke({"query": 9999}))
    assert "Error: query is required and cannot be empty." in res_num


# ---------------------------------------------------------------------------
# calendar_tools tests
# ---------------------------------------------------------------------------

def test_create_calendar_event_tool_fast_fail_guards(calendar_tools_mod):
    # None/empty title fast-fails before any DB lookup
    res_title_none = asyncio.run(
        calendar_tools_mod.create_calendar_event_tool.ainvoke({
            "title": None,
            "start_time": "2026-10-28T10:00:00Z",
            "end_time": "2026-10-28T11:00:00Z",
        })
    )
    assert "Error: title is required and cannot be empty." in res_title_none

    res_title_empty = asyncio.run(
        calendar_tools_mod.create_calendar_event_tool.ainvoke({
            "title": "   ",
            "start_time": "2026-10-28T10:00:00Z",
            "end_time": "2026-10-28T11:00:00Z",
        })
    )
    assert "Error: title is required and cannot be empty." in res_title_empty

    # None/empty start_time
    res_start_none = asyncio.run(
        calendar_tools_mod.create_calendar_event_tool.ainvoke({
            "title": "Sync Meeting",
            "start_time": None,
            "end_time": "2026-10-28T11:00:00Z",
        })
    )
    assert "Error: start_time is required in format" in res_start_none

    # None/empty end_time
    res_end_none = asyncio.run(
        calendar_tools_mod.create_calendar_event_tool.ainvoke({
            "title": "Sync Meeting",
            "start_time": "2026-10-28T10:00:00Z",
            "end_time": None,
        })
    )
    assert "Error: end_time is required in format" in res_end_none


def test_delete_calendar_event_tool_whitespace_sanitization(calendar_tools_mod):
    # Whitespace-only event_id is sanitized to None
    res = asyncio.run(
        calendar_tools_mod.delete_calendar_event_tool.ainvoke({
            "event_id": "   ",
            "event_title": None,
            "start_date": None,
        })
    )
    assert "Error: Please provide either event_id, event_title, or start_date" in res


def test_delete_calendar_event_tool_handles_titleless_events(calendar_tools_mod):
    # An event with summary: None should not crash with AttributeError when filtering
    titleless_event = {"id": "ev-1", "summary": None, "start": {"dateTime": "2026-10-28T10:00:00Z"}}
    matching_event = {"id": "ev-2", "summary": "Team Sync", "start": {"dateTime": "2026-10-28T11:00:00Z"}}

    async def _mock_get_events(**_kwargs):
        return [titleless_event, matching_event]

    async def _mock_delete_event(*_args, **_kwargs):
        return None

    calendar_tools_mod.get_google_calendar_events = _mock_get_events
    calendar_tools_mod.delete_google_calendar_event = _mock_delete_event

    res = asyncio.run(
        calendar_tools_mod.delete_calendar_event_tool.ainvoke({
            "event_id": None,
            "event_title": "Team Sync",
            "start_date": "2026-10-28T00:00:00Z",
        })
    )
    assert "Successfully deleted 1 calendar event" in res


def test_update_calendar_event_tool_whitespace_sanitization(calendar_tools_mod):
    # Both whitespace-only event_id and event_title are sanitized to None
    res = asyncio.run(
        calendar_tools_mod.update_calendar_event_tool.ainvoke({
            "event_id": "   ",
            "event_title": "   ",
        })
    )
    assert "Error: Please provide either event_id or event_title to identify which event to update." in res


def test_update_calendar_event_tool_handles_titleless_events(calendar_tools_mod):
    # An event with summary: None should not crash with AttributeError when filtering
    titleless_event = {"id": "ev-1", "summary": None, "start": {"dateTime": "2026-10-28T10:00:00Z"}}
    matching_event = {"id": "ev-2", "summary": "Team Sync", "start": {"dateTime": "2026-10-28T11:00:00Z"}}

    async def _mock_get_events(**_kwargs):
        return [titleless_event, matching_event]

    async def _mock_get_event(*_args, **_kwargs):
        return {"id": "ev-2", "summary": "Team Sync"}

    async def _mock_update_event(*_args, **_kwargs):
        return {"id": "ev-2", "summary": "Updated Team Sync"}

    calendar_tools_mod.get_google_calendar_events = _mock_get_events
    calendar_tools_mod.get_google_calendar_event = _mock_get_event
    calendar_tools_mod.update_google_calendar_event = _mock_update_event

    res = asyncio.run(
        calendar_tools_mod.update_calendar_event_tool.ainvoke({
            "event_id": None,
            "event_title": "Team Sync",
            "title": "Updated Team Sync",
        })
    )
    assert "Successfully updated calendar event: Updated Team Sync" in res
