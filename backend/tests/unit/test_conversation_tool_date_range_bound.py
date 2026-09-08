"""Tests for bounding the conversations chat tool over wide date ranges (issue #4927).

Asking the chat about "my last 30 days" matched up to 5000 conversations and formatted all of
them into one tool result, which flooded the chat model's context so it froze or refused
("that's quite a bit of information to process at once"). get_conversations_tool now caps how
many conversations (and how many characters) it returns and appends a note telling the model to
summarize what it has and offer to narrow. These tests cover the two pure bounding helpers.
"""

import importlib
import importlib.util
import os
import sys
import types
from pathlib import Path
from types import SimpleNamespace
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


# Keep the real package namespaces importable for tests collected later in the same
# process. Only the heavy leaf modules are replaced below; replacing ``utils`` or
# ``utils.retrieval.tools`` here makes unrelated modules impossible to import.
for _p in [
    "database",
    "models",
    "utils",
    "utils.conversations",
    "utils.llm",
    "utils.retrieval",
    "utils.retrieval.tools",
]:
    importlib.import_module(_p)
for _name, _attrs in {
    "database.conversations": [],
    "database.notifications": ["get_user_time_zone"],
    "database.users": ["get_people_by_ids"],
    "database.vector_db": [],
    "models.conversation": ["Conversation"],
    "models.other": ["Person"],
    "utils.conversations.factory": ["deserialize_conversation"],
    "utils.conversations.render": ["conversation_to_citation_card", "conversations_to_string"],
    "utils.conversations.mcp_transcript_search": ["build_transcript_match_snippets"],
    "utils.conversations.search": [
        "keyword_search_conversation_ids",
        "merge_conversation_search_ids",
        "parse_exact_conversation_reference",
        "conversation_matches_date_range",
    ],
    "utils.llm.clients": ["embeddings"],
    "utils.retrieval.agentic": ["agent_config_context"],
}.items():
    _m = _mod(_name)
    for _a in _attrs:
        setattr(_m, _a, MagicMock())


def _apply_chat_scope_dates(scope, start_date, end_date):
    """Pass-through stub: date-range bound tests do not exercise hard-scope intersection."""
    return start_date, end_date, None


def _chat_scope_from_config(configurable):
    if not isinstance(configurable, dict):
        return None
    scope = configurable.get("chat_scope")
    return scope if isinstance(scope, dict) and scope else None


_chat_scope = _mod("utils.retrieval.chat_scope")
_chat_scope.apply_chat_scope_dates = _apply_chat_scope_dates
_chat_scope.chat_scope_from_config = _chat_scope_from_config

ct = _load(
    "utils.retrieval.tools._conversation_tools_date_range_test",
    "utils/retrieval/tools/conversation_tools.py",
)
jit = importlib.import_module("utils.retrieval.tools.conversation_jit")


class TestExactConversationReference:
    def test_exact_reference_skips_semantic_search(self):
        conversation_id = "e8c05000-52f0-4a95-951c-ccd715523429"
        ct.parse_exact_conversation_reference.return_value = conversation_id
        ct.conversation_matches_date_range.return_value = True
        # Rebind: sibling unit files may have already loaded conversation_tools with a real
        # keyword_search_conversation_ids (not a MagicMock), so reset_mock is unsafe here.
        ct.keyword_search_conversation_ids = MagicMock()
        ct.vector_db.query_vectors = MagicMock(return_value=[])
        ct.conversations_db.get_conversations_by_id = MagicMock(
            return_value=[{"id": conversation_id, "transcript_segments": [], "is_locked": False}]
        )
        ct.deserialize_conversation = MagicMock(
            return_value=SimpleNamespace(transcript_segments=[], model_dump=lambda: {"id": conversation_id})
        )
        ct.conversations_to_string = MagicMock(return_value="[formatted]")
        ct.notification_db.get_user_time_zone = MagicMock(return_value="UTC")

        result = ct.search_conversations_tool.invoke(
            {"query": conversation_id},
            config={"configurable": {"user_id": "test-uid", "conversations_collected": []}},
        )

        assert "matching exactly" in result
        assert "[formatted]" in result
        ct.keyword_search_conversation_ids.assert_not_called()
        ct.vector_db.query_vectors.assert_not_called()
        ct.conversations_db.get_conversations_by_id.assert_called_once_with("test-uid", [conversation_id])


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


class TestJITConversationRetrieval:
    def test_summary_card_is_transcript_free_and_has_stable_refs(self):
        raw = {
            "id": "conv-42",
            "created_at": "2026-08-23T12:00:00+00:00",
            "transcript_segments": [{"id": "secret", "text": "must not be in the card"}],
            "structured": {
                "title": "Planning",
                "overview": "A bounded overview",
                "category": "work",
                "action_items": [{"description": "Ship the plan"}],
            },
        }

        card = jit._summary_card_from_data(raw)
        result = jit.format_jit_results([raw])

        assert card["conversation_ref"] == "conversation:conv-42"
        assert card["summary_evidence_ref"] == "conversation:conv-42:summary"
        assert card["action_items"] == ["Ship the plan"]
        assert "A bounded overview" in result
        assert "conversation:conv-42:summary" in result
        assert "must not be in the card" not in result

    def test_bounded_window_caps_segments_and_uses_index_fallback_refs(self):
        segments = [{"id": f"s{i}", "start": i, "end": i + 1, "text": f"line {i}"} for i in range(40)]

        window = jit._bounded_transcript_window(
            segments,
            offset=5,
            limit=999,
            conversation_id="conv-42",
        )

        assert len(window) == jit.MAX_JIT_TRANSCRIPT_WINDOW_SEGMENTS
        assert window[0]["evidence_ref"] == "conversation:conv-42:segment:s5"
        assert window[-1]["evidence_ref"] == "conversation:conv-42:segment:s28"

    def test_unratified_jit_options_are_not_exposed_on_production_tools(self):
        for tool in (ct.get_conversations_tool, ct.search_conversations_tool):
            fields = tool.args_schema.model_fields
            assert "summary_card_only" not in fields
            assert "hydrate_transcript_windows" not in fields
