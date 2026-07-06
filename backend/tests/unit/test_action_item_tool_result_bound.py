"""Tests for bounding the action items chat tool result (issue #4927).

Asking the chat to "show me all my tasks" can pull a full 500-item page and render each item over
several lines, which floods the chat model's context so it freezes or refuses ("that's quite a bit
of information to process at once") -- the same failure already fixed for the conversations tool in
#8503. get_action_items_tool now caps how many items (and how many characters) it returns and
appends a note telling the model to summarize what it has and offer to narrow. These tests cover the
two pure bounding helpers.
"""

import importlib.util
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.unit.memory_import_isolation import restore_sys_modules, snapshot_sys_modules

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


# Stub the heavy leaves action_item_tools imports; langchain_core is used for real (the @tool
# decorator needs it). None of these are exercised by the pure helpers under test.
_SYS_MODULE_NAMES = [
    "database",
    "database.action_items",
    "database.notifications",
    "utils",
    "utils.notifications",
    "utils.conversations",
    "utils.conversations.render",
    "utils.retrieval",
    "utils.retrieval.agentic",
    "utils.retrieval.tools",
    "utils.retrieval.tools.action_item_tools",
]
_SYS_MODULES_SNAPSHOT = snapshot_sys_modules(_SYS_MODULE_NAMES)

for _p in [
    "database",
    "utils",
    "utils.conversations",
    "utils.retrieval",
    "utils.retrieval.tools",
]:
    _pkg(_p)
for _name, _attrs in {
    "database.action_items": [],
    "database.notifications": ["get_user_time_zone"],
    "utils.notifications": [
        "send_action_item_completed_notification",
        "send_action_item_created_notification",
        "send_action_item_data_message",
        "sync_action_item_reminder",
    ],
    "utils.conversations.render": ["resolve_display_tz"],
    "utils.retrieval.agentic": ["agent_config_context"],
}.items():
    _m = _mod(_name)
    for _a in _attrs:
        setattr(_m, _a, MagicMock())

ai = _load("utils.retrieval.tools.action_item_tools", "utils/retrieval/tools/action_item_tools.py")

restore_sys_modules(_SYS_MODULES_SNAPSHOT)
del _SYS_MODULES_SNAPSHOT, _SYS_MODULE_NAMES


class TestCapActionItemsForLlm:
    def test_caps_and_flags_truncation(self):
        items = list(range(500))  # stand-ins; the database's ordering is preserved
        capped, truncated = ai._cap_action_items_for_llm(items)
        assert truncated is True
        assert len(capped) == ai.MAX_ACTION_ITEMS_FOR_LLM
        assert capped == items[: ai.MAX_ACTION_ITEMS_FOR_LLM]  # first (most relevant) kept

    def test_under_cap_is_untouched(self):
        items = list(range(50))
        capped, truncated = ai._cap_action_items_for_llm(items)
        assert capped == items and truncated is False

    def test_exactly_at_cap_is_not_truncated(self):
        items = list(range(ai.MAX_ACTION_ITEMS_FOR_LLM))
        capped, truncated = ai._cap_action_items_for_llm(items)
        assert truncated is False and len(capped) == ai.MAX_ACTION_ITEMS_FOR_LLM

    def test_empty_list(self):
        capped, truncated = ai._cap_action_items_for_llm([])
        assert capped == [] and truncated is False


class TestBoundedActionItemsResult:
    def test_truncated_appends_guidance_note_without_claiming_a_total(self):
        out = ai._bounded_action_items_result("1. [Pending] ship it\n   ID: a", truncated=True)
        assert "more may exist" in out
        assert "Summarize what is shown" in out
        assert "narrower" in out
        # No definitive total is claimed: the page is limit-capped, not necessarily the full set.
        assert "total" not in out.lower()

    def test_not_truncated_short_result_unchanged(self):
        body = "1. [Pending] ship it\n   ID: a"
        assert ai._bounded_action_items_result(body, truncated=False) == body

    def test_oversized_result_is_clipped_at_a_line_boundary_with_note(self):
        big = "1. [Pending] first\n" + ("x" * 30000) + "\n2. [Pending] second\n" + ("y" * 40000)
        out = ai._bounded_action_items_result(big, truncated=False)
        assert len(out) <= ai.MAX_RESULT_CHARS + 400  # budget plus the appended note
        assert "Summarize what is shown" in out
        # Clipped back to a line boundary, so the final record before the note is not sliced
        # mid-field (the trailing 40k-character run is dropped whole, not cut partway).
        note_idx = out.index("[Only the most relevant")
        body = out[:note_idx].rstrip("\n")
        assert not body.endswith("y")
