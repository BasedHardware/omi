"""Tests for bounding the screen activity chat tool result (issue #4927).

get_screen_activity_tool summarizes every app the user touched in a date range, each with up to
five uncapped-length window titles, with no row cap and no character budget. A wide range on a busy
machine ("what did I do last month") can therefore format tens of thousands of characters into one
tool result, flooding the chat model's context so it freezes or refuses -- the same failure already
fixed for the conversations, memories, and action items tools. It now caps how many apps (and how
many characters) it returns and appends a note telling the model to summarize and narrow. These
tests cover the two pure bounding helpers.
"""

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

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
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _load(module_name, rel_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_DIR / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Stub the heavy leaves screen_activity_tools imports; langchain_core is used for real (the @tool
# decorator needs it). None of these are exercised by the pure helpers under test.
for _p in [
    "database",
    "utils",
    "utils.llm",
    "utils.retrieval",
    "utils.retrieval.tools",
]:
    _pkg(_p)
for _name, _attrs in {
    "database.screen_activity": [],
    "database.vector_db": [],
    "database._client": ["db"],
    "utils.llm.clients": ["gemini_embed_query"],
    "utils.retrieval.agentic": ["agent_config_context"],
}.items():
    _m = _mod(_name)
    for _a in _attrs:
        setattr(_m, _a, MagicMock())

sa = _load("utils.retrieval.tools.screen_activity_tools", "utils/retrieval/tools/screen_activity_tools.py")


class TestCapAppsForLlm:
    def test_caps_and_flags_truncation(self):
        apps = list(range(60))  # stand-ins; most-used-first order is preserved
        capped, truncated = sa._cap_apps_for_llm(apps)
        assert truncated is True
        assert len(capped) == sa.MAX_APPS_FOR_LLM
        assert capped == apps[: sa.MAX_APPS_FOR_LLM]

    def test_under_cap_is_untouched(self):
        apps = list(range(20))
        capped, truncated = sa._cap_apps_for_llm(apps)
        assert capped == apps and truncated is False

    def test_exactly_at_cap_is_not_truncated(self):
        apps = list(range(sa.MAX_APPS_FOR_LLM))
        capped, truncated = sa._cap_apps_for_llm(apps)
        assert truncated is False and len(capped) == sa.MAX_APPS_FOR_LLM

    def test_empty_list(self):
        capped, truncated = sa._cap_apps_for_llm([])
        assert capped == [] and truncated is False


class TestBoundedScreenActivityResult:
    def test_truncated_appends_guidance_note(self):
        out = sa._bounded_screen_activity_result("**Chrome** ~5 min", truncated=True)
        assert "more may exist" in out
        assert "Summarize what is shown" in out
        assert "specific app" in out
        assert "narrower date range" in out

    def test_not_truncated_short_result_unchanged(self):
        body = "**Chrome** ~5 min (100 screenshots)"
        assert sa._bounded_screen_activity_result(body, truncated=False) == body

    # The summary header precedes the first app record in real output, so the first record is itself
    # preceded by a "\n**" boundary (mirrored here so the clipping logic is exercised faithfully).
    HEADER = "Screen Activity Summary (999 screenshots, ~50 min total):\n\n"

    def test_oversized_result_is_clipped_at_a_record_boundary_with_note(self):
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

    def test_single_oversized_record_keeps_truncated_data_not_just_header(self):
        # A single app whose window titles alone exceed the budget must still return its (truncated)
        # data, not collapse to just the header (cubic on #8530).
        only = "**Chrome** ~5 min (100 screenshots)\n  Top windows: " + ("x" * 70000) + "\n"
        big = self.HEADER + only
        out = sa._bounded_screen_activity_result(big, truncated=False)
        assert len(out) <= sa.MAX_RESULT_CHARS + 400
        note_idx = out.index("[Only the most-used apps")
        body = out[:note_idx]
        assert "**Chrome**" in body  # the app record is present, not dropped down to the header
