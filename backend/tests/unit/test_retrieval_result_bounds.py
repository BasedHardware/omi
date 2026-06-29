"""Tests for bounding agentic retrieval tool results (issue #4927).

A broad chat question can match a huge set ("what do you know about me" -> every memory), and
formatting all of it into one tool result floods the chat model's context so it freezes or
refuses. get_memories_tool now bounds its result via these shared helpers (the same fix already
applied to the conversations tool). These cover the pure bounding helpers directly.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _load(module_name, rel_path):
    # result_bounds.py imports nothing heavy, so load it directly without triggering the
    # utils.retrieval.tools package __init__ (which pulls in every tool's dependencies).
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_DIR / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


rb = _load("result_bounds_under_test", "utils/retrieval/tools/result_bounds.py")


class TestCapItemsForLlm:
    def test_caps_to_max_and_flags_truncation(self):
        capped, total, truncated = rb.cap_items_for_llm(list(range(500)), 300)
        assert total == 500
        assert truncated is True
        assert capped == list(range(300))  # most-relevant-first order preserved

    def test_under_cap_is_untouched(self):
        capped, total, truncated = rb.cap_items_for_llm(list(range(50)), 300)
        assert capped == list(range(50)) and total == 50 and truncated is False

    def test_exactly_at_cap_is_not_truncated(self):
        capped, total, truncated = rb.cap_items_for_llm(list(range(300)), 300)
        assert truncated is False and len(capped) == 300

    def test_empty_list(self):
        assert rb.cap_items_for_llm([], 300) == ([], 0, False)


class TestBoundedResult:
    def test_truncated_appends_summarize_and_narrow_note(self):
        out = rb.bounded_result("User Memories (300 shown):\n- a fact", True, noun="memories")
        # No definitive total is claimed (the page length is not the true total); it says more may exist.
        assert "more may exist" in out
        assert "most relevant memories" in out
        assert "Summarize what is shown" in out
        assert "narrower" in out

    def test_not_truncated_short_result_unchanged(self):
        body = "User Memories (3 shown):\n- a fact"
        assert rb.bounded_result(body, False, noun="memories") == body

    def test_oversized_result_is_clipped_to_budget_with_note(self):
        big = "x" * (rb.MAX_RESULT_CHARS + 5000)
        out = rb.bounded_result(big, False, noun="memories")
        assert len(out) <= rb.MAX_RESULT_CHARS + 400  # budget plus the appended note
        assert "Summarize what is shown" in out

    def test_default_noun(self):
        out = rb.bounded_result("body", True)
        assert "most relevant results" in out
