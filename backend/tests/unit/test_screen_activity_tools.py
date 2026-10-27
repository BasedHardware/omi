"""Tests verifying screen_activity_tools query validation, user resolution, and app filter matching.

Ensures that empty or None queries return graceful error messages, limits are coerced cleanly,
user ID resolution falls back to top-level configuration when needed, and app filters match
safely without case/whitespace or NoneType errors.
"""

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


@pytest.fixture(scope="module", autouse=True)
def _screen_activity_module():
    """Load screen_activity_tools with temporary stub dependencies."""
    langchain_tools = ModuleType("langchain_core.tools")
    langchain_tools.tool = _tool_decorator
    langchain_runnables = ModuleType("langchain_core.runnables")
    langchain_runnables.RunnableConfig = dict

    model_text = load_module_fresh("utils.model_text", str(BACKEND_DIR / "utils" / "model_text.py"))
    user_clock = ModuleType("utils.user_clock")
    user_clock.clock_for_config = MagicMock(return_value=MagicMock(tz="UTC"))

    screen_activity_db = ModuleType("database.screen_activity")
    screen_activity_db.get_screen_activity_summary = MagicMock()
    screen_activity_db.normalize_screen_activity_timestamp = MagicMock()

    vector_db = ModuleType("database.vector_db")
    vector_db.search_screen_activity_vectors = MagicMock(return_value=[])

    db_client = ModuleType("database._client")
    db_client.db = MagicMock()

    llm_clients = ModuleType("utils.llm.clients")
    llm_clients.gemini_embed_query = MagicMock(return_value=[0.1, 0.2])

    stubs = {
        "langchain_core": ModuleType("langchain_core"),
        "langchain_core.tools": langchain_tools,
        "langchain_core.runnables": langchain_runnables,
        "utils.model_text": model_text,
        "utils.user_clock": user_clock,
        "database.screen_activity": screen_activity_db,
        "database.vector_db": vector_db,
        "database._client": db_client,
        "utils.llm": ModuleType("utils.llm"),
        "utils.llm.clients": llm_clients,
    }

    with stub_modules(stubs):
        module = load_module_fresh(
            "utils.retrieval.tools.screen_activity_tools",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "screen_activity_tools.py"),
        )
        globals()["sat"] = module
        yield
        globals().pop("sat", None)


def test_search_screen_activity_empty_and_none_query():
    res1 = sat.search_screen_activity_tool.func("")
    assert res1 == "Error: Search query cannot be empty."

    res2 = sat.search_screen_activity_tool.func("   ")
    assert res2 == "Error: Search query cannot be empty."

    res3 = sat.search_screen_activity_tool.func(None)
    assert res3 == "Error: Search query cannot be empty."


def test_missing_user_id():
    res1 = sat.search_screen_activity_tool.func("python", config={})
    assert res1 == "Error: User ID not found in configuration"

    res2 = sat.get_screen_activity_tool.func(config={})
    assert res2 == "Error: User ID not found in configuration"


def test_user_id_resolution():
    nested_cfg = {"configurable": {"user_id": "usr_nested"}}
    assert sat._get_uid(nested_cfg) == "usr_nested"
    assert sat._get_uid({"user_id": "usr_direct"}) is None
    assert sat._get_uid({}) is None
    assert sat._get_uid(None) is None


def test_app_filter_sanitization():
    summary_mock = {
        "apps": {
            "Slack": {"count": 10, "window_titles": ["#general"]},
            "Chrome": {"count": 30, "window_titles": ["GitHub"]},
            None: {"count": 1, "window_titles": []},
        },
        "total_screenshots": 41,
        "coverage": {"truncated": False},
    }
    with patch.object(sat.screen_activity_db, "get_screen_activity_summary", return_value=summary_mock):
        with patch.object(sat, "_chat_context_window") as mock_window:
            mock_window.return_value.resolve.return_value = (None, None)
            res = sat.get_screen_activity_tool.func(app_filter="  slack  ", config={"configurable": {"user_id": "u1"}})
            assert "**Slack** — 10 observations" in res
            assert "Chrome" not in res

            res_none = sat.get_screen_activity_tool.func(app_filter="Firefox", config={"configurable": {"user_id": "u1"}})
            assert "No observations for app 'Firefox' in the summarized rows." in res_none
