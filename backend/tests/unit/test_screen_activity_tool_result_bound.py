"""Tests for bounding the screen activity chat tool result (issue #4927).

get_screen_activity_tool summarizes every app the user touched in a date range, each with up to
five uncapped-length window titles, with no row cap and no character budget. A wide range on a busy
machine ("what did I do last month") can therefore format tens of thousands of characters into one
tool result, flooding the chat model's context so it freezes or refuses -- the same failure already
fixed for the conversations, memories, and action items tools. It now caps how many apps (and how
many characters) it returns and appends a note telling the model to summarize and narrow. These
tests cover the two pure bounding helpers.

The production module imports heavy database/llm leaves at module scope (database.screen_activity,
database.vector_db, utils.llm.clients, ...) and the parent package's ``__init__`` pulls in chains
with import-time side effects (typesense client construction). So the fake leaves must be active
before the module is exec'd by file path: the sanctioned Tier-2 "fake must precede import" case
(see backend/docs/test_isolation.md and testing/import_isolation.load_module_fresh).
"""

import os
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
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
        # Packages the module is nested under / imports from.
        "database": _pkg("database"),
        "utils": _pkg("utils"),
        "utils.llm": _pkg("utils.llm"),
        "utils.retrieval": _pkg("utils.retrieval"),
        "utils.retrieval.tools": _pkg("utils.retrieval.tools"),
        # Leaf modules screen_activity_tools binds at import.
        "database.screen_activity": _leaf("database.screen_activity", []),
        "database.vector_db": _leaf("database.vector_db", []),
        "database.notifications": _leaf("database.notifications", ["get_user_time_zone"]),
        "database._client": _leaf("database._client", ["db"]),
        "utils.llm.clients": _leaf("utils.llm.clients", ["gemini_embed_query"]),
        "utils.retrieval.agentic": _leaf("utils.retrieval.agentic", ["agent_config_context"]),
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "utils.retrieval.tools.screen_activity_tools",
            os.path.join(str(_BACKEND), "utils", "retrieval", "tools", "screen_activity_tools.py"),
        )
        yield module


class TestCapAppsForLlm:
    def test_caps_and_flags_truncation(self, sa):
        apps = list(range(60))  # stand-ins; most-used-first order is preserved
        capped, truncated = sa._cap_apps_for_llm(apps)
        assert truncated is True
        assert len(capped) == sa.MAX_APPS_FOR_LLM
        assert capped == apps[: sa.MAX_APPS_FOR_LLM]

    def test_under_cap_is_untouched(self, sa):
        apps = list(range(20))
        capped, truncated = sa._cap_apps_for_llm(apps)
        assert capped == apps and truncated is False

    def test_exactly_at_cap_is_not_truncated(self, sa):
        apps = list(range(sa.MAX_APPS_FOR_LLM))
        capped, truncated = sa._cap_apps_for_llm(apps)
        assert truncated is False and len(capped) == sa.MAX_APPS_FOR_LLM

    def test_empty_list(self, sa):
        capped, truncated = sa._cap_apps_for_llm([])
        assert capped == [] and truncated is False


class TestBoundedScreenActivityResult:
    def test_truncated_appends_guidance_note(self, sa):
        out = sa._bounded_screen_activity_result("**Chrome** ~5 min", truncated=True)
        assert "more may exist" in out
        assert "Summarize what is shown" in out
        assert "specific app" in out
        assert "narrower date range" in out

    def test_not_truncated_short_result_unchanged(self, sa):
        body = "**Chrome** ~5 min (100 screenshots)"
        assert sa._bounded_screen_activity_result(body, truncated=False) == body

    # The summary header precedes the first app record in real output, so the first record is itself
    # preceded by a "\n**" boundary (mirrored here so the clipping logic is exercised faithfully).
    HEADER = "Screen Activity Summary (999 screenshots, ~50 min total):\n\n"

    def test_oversized_result_is_clipped_at_a_record_boundary_with_note(self, sa):
        rec1 = "**Chrome** ~5 min (100 screenshots)\n  Top windows: a, b\n"
        rec2 = "**Slack** ~3 min (50 screenshots)\n  Top windows: " + ("x" * 70000) + "\n"
        big = self.HEADER + rec1 + "\n" + rec2 + "\n"  # rec2 overflows the budget
        out = sa._bounded_screen_activity_result(big, truncated=False)
        assert len(out) <= sa.MAX_RESULT_CHARS + 400  # budget plus the appended note
        assert "Summarize what is shown" in out
        # Clipped at the app-record boundary: the first complete record is kept and the oversized
        # second record is dropped whole, never left as a partial "**Slack**" block.
        note_idx = out.index("[Only the most-used apps")
        body = out[:note_idx].rstrip("\n")
        assert "Chrome" in body
        assert "Slack" not in body
        assert not body.endswith("x")

    def test_single_oversized_record_keeps_truncated_data_not_just_header(self, sa):
        # A single app whose window titles alone exceed the budget must still return its (truncated)
        # data, not collapse to just the header (cubic on #8530).
        only = "**Chrome** ~5 min (100 screenshots)\n  Top windows: " + ("x" * 70000) + "\n"
        big = self.HEADER + only
        out = sa._bounded_screen_activity_result(big, truncated=False)
        assert len(out) <= sa.MAX_RESULT_CHARS + 400
        note_idx = out.index("[Only the most-used apps")
        body = out[:note_idx]
        assert "**Chrome**" in body  # the app record is present, not dropped down to the header
