"""Tests for bounding the conversations chat tool over wide date ranges (issue #4927).

Asking the chat about "my last 30 days" matched up to 5000 conversations and formatted all of
them into one tool result, which flooded the chat model's context so it froze or refused
("that's quite a bit of information to process at once"). get_conversations_tool now caps how
many conversations (and how many characters) it returns and appends a note telling the model to
summarize what it has and offer to narrow. These tests cover the two pure bounding helpers.
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


# Stub the heavy leaves conversation_tools imports; langchain_core is used for real (the @tool
# decorator needs it). None of these are exercised by the pure helpers under test.
for _p in [
    "database",
    "models",
    "utils",
    "utils.conversations",
    "utils.llm",
    "utils.retrieval",
    "utils.retrieval.tools",
]:
    _pkg(_p)
for _name, _attrs in {
    "database.conversations": [],
    "database.notifications": ["get_user_time_zone"],
    "database.users": ["get_people_by_ids"],
    "database.vector_db": [],
    "models.conversation": ["Conversation"],
    "models.other": ["Person"],
    "utils.conversations.factory": ["deserialize_conversation"],
    "utils.conversations.render": ["conversations_to_string"],
    "utils.conversations.search": ["keyword_search_conversation_ids", "merge_conversation_search_ids"],
    "utils.llm.clients": ["embeddings"],
    "utils.retrieval.agentic": ["agent_config_context"],
}.items():
    _m = _mod(_name)
    for _a in _attrs:
        setattr(_m, _a, MagicMock())

ct = _load("utils.retrieval.tools.conversation_tools", "utils/retrieval/tools/conversation_tools.py")


class TestCapConversationsForLlm:
    def test_caps_to_most_recent_and_flags_truncation(self):
        items = list(range(150))  # stand-ins; newest-first order is preserved
        capped, total, truncated = ct._cap_conversations_for_llm(items)
        assert total == 150
        assert truncated is True
        assert len(capped) == ct.MAX_CONVERSATIONS_FOR_LLM
        assert capped == items[: ct.MAX_CONVERSATIONS_FOR_LLM]  # most recent kept

    def test_under_cap_is_untouched(self):
        items = list(range(50))
        capped, total, truncated = ct._cap_conversations_for_llm(items)
        assert capped == items and total == 50 and truncated is False

    def test_exactly_at_cap_is_not_truncated(self):
        items = list(range(ct.MAX_CONVERSATIONS_FOR_LLM))
        capped, total, truncated = ct._cap_conversations_for_llm(items)
        assert truncated is False and len(capped) == ct.MAX_CONVERSATIONS_FOR_LLM

    def test_empty_list(self):
        capped, total, truncated = ct._cap_conversations_for_llm([])
        assert capped == [] and total == 0 and truncated is False


class TestBoundedResult:
    def test_truncated_appends_guidance_note(self):
        out = ct._bounded_result("Conversation #1\nsome summary", total_found=150, truncated=True)
        assert "150 conversations" in out
        assert "Summarize what is shown" in out
        assert "narrow" in out

    def test_not_truncated_short_result_unchanged(self):
        body = "Conversation #1\nshort"
        assert ct._bounded_result(body, total_found=5, truncated=False) == body

    def test_oversized_result_is_clipped_at_a_conversation_boundary(self):
        big = "Conversation #1\n" + ("x" * 30000) + "\nConversation #2\n" + ("y" * 40000)
        out = ct._bounded_result(big, total_found=2, truncated=False)
        # Clipped under the budget, cut before the second record, and noted.
        assert "Conversation #2" not in out
        assert "yyyy" not in out
        assert len(out) <= ct.MAX_RESULT_CHARS + 400  # budget plus the appended note
        assert "Summarize what is shown" in out
