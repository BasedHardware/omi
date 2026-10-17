"""Tests that get_screen_activity_tool keeps parser and database error text out of its tool result (issue #15643).

The tool's return value goes straight into the chat model's context, so a raw ``ValueError`` from the date
parser or a raw Firestore error (index URLs, project ids) must never be part of it.

The production module imports heavy database/llm leaves at module scope, so the fakes must be active before
the module is exec'd by file path: the sanctioned Tier-2 "fake must precede import" case (see
backend/docs/test_isolation.md and testing/import_isolation.load_module_fresh).
"""

import logging
import os
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]

_CONFIG = {"configurable": {"user_id": "u1"}}
_VALID_START = "2026-09-01T00:00:00+00:00"
_VALID_END = "2026-09-02T00:00:00+00:00"
_FIRESTORE_INDEX_ERROR = (
    "400 The query requires an index. You can create it here: "
    "https://console.firebase.google.com/v1/r/project/based-hardware/firestore/indexes?create_composite=abc"
)


@pytest.fixture
def sa():
    """Load a fresh screen_activity_tools against stubbed heavy leaves.

    langchain_core is left real (the @tool decorator needs it); only the database/llm
    leaves that screen_activity_tools imports at module scope are faked.
    """

    def _pkg(name):
        mod = ModuleType(name)
        mod.__path__ = []  # type: ignore[attr-defined]
        return mod

    def _leaf(name, attrs):
        mod = ModuleType(name)
        for a in attrs:
            setattr(mod, a, MagicMock())
        return mod

    fakes = {
        "database": _pkg("database"),
        "utils": _pkg("utils"),
        "utils.llm": _pkg("utils.llm"),
        "utils.retrieval": _pkg("utils.retrieval"),
        "utils.retrieval.tools": _pkg("utils.retrieval.tools"),
        "database.screen_activity": _leaf("database.screen_activity", ["get_screen_activity_summary"]),
        "database.vector_db": _leaf("database.vector_db", []),
        "database.notifications": _leaf("database.notifications", ["get_user_time_zone"]),
        "database._client": _leaf("database._client", ["db"]),
        "utils.llm.clients": _leaf("utils.llm.clients", ["gemini_embed_query"]),
        "utils.retrieval.agentic": _leaf("utils.retrieval.agentic", ["agent_config_context"]),
    }
    with stub_modules(fakes):
        # screen_activity_tools imports utils.model_text and utils.user_clock at module
        # scope; the stubbed "utils" package has an empty path, so load the real (stdlib-only)
        # model_text first, then user_clock (its database.notifications import hits the fake
        # above). Same sanctioned pattern as test_calendar_tools_sanitization.
        load_module_fresh(
            "utils.model_text",
            os.path.join(str(_BACKEND), "utils", "model_text.py"),
        )
        load_module_fresh(
            "utils.user_clock",
            os.path.join(str(_BACKEND), "utils", "user_clock.py"),
        )
        yield load_module_fresh(
            "utils.retrieval.tools.screen_activity_tools",
            os.path.join(str(_BACKEND), "utils", "retrieval", "tools", "screen_activity_tools.py"),
        )


def _fail_summary_query(sa, monkeypatch):
    monkeypatch.setattr(
        sa.screen_activity_db,
        "get_screen_activity_summary",
        MagicMock(side_effect=RuntimeError(_FIRESTORE_INDEX_ERROR)),
    )


@pytest.mark.parametrize(
    "start_date, end_date",
    [
        pytest.param("not-a-date", _VALID_END, id="bad_start"),
        pytest.param(_VALID_START, "2026-13-45T00:00:00+00:00", id="bad_end"),
    ],
)
def test_invalid_date_returns_fixed_hint_without_parser_text(sa, start_date, end_date):
    result = sa.get_screen_activity_tool.invoke({"start_date": start_date, "end_date": end_date}, config=_CONFIG)

    assert result == "Error: Invalid date format. Use YYYY-MM-DDTHH:MM:SS+HH:MM."


def test_summary_query_failure_returns_fixed_error_without_exception_text(sa, monkeypatch):
    _fail_summary_query(sa, monkeypatch)

    result = sa.get_screen_activity_tool.invoke({"start_date": _VALID_START, "end_date": _VALID_END}, config=_CONFIG)

    assert result == "Error retrieving screen activity summary. Please try again."


def test_summary_query_failure_is_still_logged_with_traceback(sa, monkeypatch, caplog):
    _fail_summary_query(sa, monkeypatch)

    with caplog.at_level(logging.ERROR, logger=sa.logger.name):
        sa.get_screen_activity_tool.invoke({"start_date": _VALID_START, "end_date": _VALID_END}, config=_CONFIG)

    error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
    assert len(error_records) == 1
    assert error_records[0].exc_info[0] is RuntimeError
