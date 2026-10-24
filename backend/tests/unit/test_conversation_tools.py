"""Tests verifying conversation_tools.py validation, configurable resilience, and boundary handling.

Ensures that get_conversations_tool and search_conversations_tool safely handle None configurable
dictionaries, top-level user_id, coerce string limit/offset/segments, validate non-empty queries,
and render addressable conversations without unhandled exceptions.
"""

import os
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _module(name, **attrs):
    mod = ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


def _package(name):
    mod = _module(name)
    mod.__path__ = []  # type: ignore[attr-defined]
    return mod


def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn

    def dec(func):
        func.func = func
        return func

    return dec


@pytest.fixture(scope="module", autouse=True)
def _conversation_tools_module():
    """Load conversation_tools with isolated dependencies."""
    langchain_tools = _module("langchain_core.tools", tool=_tool_decorator)
    langchain_runnables = _module("langchain_core.runnables", RunnableConfig=dict)

    mock_db = _module(
        "database.conversations",
        get_conversations=MagicMock(return_value=[]),
        get_conversation=MagicMock(return_value={"id": "conv_1", "transcript_segments": []}),
    )
    mock_users = _module("database.users", get_person=MagicMock(return_value=None))
    mock_vector = _module("database.vector_db", find_similar_conversations=MagicMock(return_value=[]))
    mock_auth = _module("database.auth", get_user_name=MagicMock(return_value="Alex"))

    mock_factory = _module(
        "utils.conversations.factory",
        deserialize_conversation=lambda d: MagicMock(id=d.get("id", "c1"), get_person_ids=lambda: []),
    )
    mock_mcp = _module(
        "utils.conversations.mcp_transcript_search",
        ChatTranscriptSearch=MagicMock(),
        chat_transcript_coverage_note=MagicMock(return_value=""),
        chat_transcript_excerpts=MagicMock(return_value={}),
        merge_chat_conversation_ids=lambda a, b: a + b,
        search_chat_transcript_chunks=MagicMock(return_value=[]),
    )
    mock_render = _module(
        "utils.conversations.render",
        conversation_to_citation_card=lambda c: {"id": getattr(c, "id", "c1")},
        conversations_to_string=MagicMock(return_value="Conversation #1: Test"),
    )
    mock_search = _module(
        "utils.conversations.search",
        conversation_matches_date_range=lambda *a, **k: True,
        keyword_search_conversation_ids=MagicMock(return_value=[]),
        parse_exact_conversation_reference=lambda *a, **k: None,
    )
    mock_metrics = _module("utils.metrics", OMI_CHAT_SEARCH_TOOL_OUTCOMES_TOTAL=MagicMock(labels=MagicMock(return_value=MagicMock(inc=MagicMock()))))
    mock_obs = _module("utils.observability.fallback", record_fallback=MagicMock())
    mock_scope = _module(
        "utils.retrieval.chat_scope",
        apply_chat_scope_dates=lambda scope, start, end: (start, end, None),
        chat_scope_from_config=MagicMock(return_value=None),
    )
    mock_refs = _module("utils.retrieval.turn_refs", register_record_ref=MagicMock())
    mock_clock = _module("utils.user_clock", clock_for_turn=MagicMock(return_value=MagicMock()))
    mock_llm_txt = _module(
        "utils.conversations.transcript_for_llm",
        owner_safe_transcript_segments=lambda segs: (segs, None),
    )
    mock_model_text = _module(
        "utils.model_text",
        DisplayClock=MagicMock(),
        ELAPSED_LEGEND="ELAPSED",
        UNTRUSTED_LEGEND="UNTRUSTED",
        format_date=lambda *a: "2026-01-01",
        none_found=lambda *a, **k: "None found",
        truncation_note=lambda *a, **k: "Truncated",
        untrusted_block=lambda src, txt: txt,
        withheld_note=lambda *a, **k: "",
    )
    mock_embed = _module("utils.llm.clients", gemini_embed_query=MagicMock(return_value=[0.1, 0.2]))

    stubs = {
        "langchain_core": _package("langchain_core"),
        "langchain_core.tools": langchain_tools,
        "langchain_core.runnables": langchain_runnables,
        "database": _package("database"),
        "database.conversations": mock_db,
        "database.users": mock_users,
        "database.vector_db": mock_vector,
        "database.auth": mock_auth,
        "utils": _package("utils"),
        "utils.conversations": _package("utils.conversations"),
        "utils.conversations.factory": mock_factory,
        "utils.conversations.mcp_transcript_search": mock_mcp,
        "utils.conversations.render": mock_render,
        "utils.conversations.search": mock_search,
        "utils.conversations.transcript_for_llm": mock_llm_txt,
        "utils.metrics": mock_metrics,
        "utils.observability": _package("utils.observability"),
        "utils.observability.fallback": mock_obs,
        "utils.retrieval": _package("utils.retrieval"),
        "utils.retrieval.chat_scope": mock_scope,
        "utils.retrieval.turn_refs": mock_refs,
        "utils.user_clock": mock_clock,
        "utils.model_text": mock_model_text,
        "utils.llm": _package("utils.llm"),
        "utils.llm.clients": mock_embed,
    }

    with stub_modules(stubs):
        module = load_module_fresh(
            "utils.retrieval.tools._conversation_tools_test",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "conversation_tools.py"),
        )
        globals()["conv_mod"] = module
        globals()["mock_db"] = mock_db
        globals()["mock_search"] = mock_search
        yield
        globals().pop("conv_mod", None)
        globals().pop("mock_db", None)
        globals().pop("mock_search", None)


class TestConversationTools(unittest.TestCase):
    def setUp(self):
        self.config = {"configurable": {"user_id": "test_uid"}}
        mock_db.get_conversations.reset_mock()
        mock_search.keyword_search_conversation_ids.reset_mock()

    def test_get_conversations_handles_top_level_uid(self):
        res = conv_mod.get_conversations_tool.func(config={"user_id": "top_uid"})
        self.assertIn("No conversations found", res)
        mock_db.get_conversations.assert_called()

    def test_get_conversations_handles_configurable_none(self):
        res = conv_mod.get_conversations_tool.func(config={"configurable": None})
        self.assertEqual(res, "Error: User ID not found in configuration")

    def test_get_conversations_coerces_string_limit_and_segments(self):
        res = conv_mod.get_conversations_tool.func(
            limit="25",
            offset="3",
            max_transcript_segments="50",
            config=self.config
        )
        self.assertIn("No conversations found", res)
        mock_db.get_conversations.assert_called_with(
            "test_uid",
            limit=25,
            offset=3,
            start_date=None,
            end_date=None,
            include_discarded=False,
            statuses=["processing", "completed"],
        )

    def test_search_conversations_handles_top_level_uid(self):
        res = conv_mod.search_conversations_tool.func(
            query="AI project discussion",
            config={"user_id": "top_uid"}
        )
        self.assertIn("None found", res)

    def test_search_conversations_guards_empty_query(self):
        res_empty = conv_mod.search_conversations_tool.func(query="   ", config=self.config)
        self.assertEqual(res_empty, "Error: Query is required to search conversations.")

        res_none = conv_mod.search_conversations_tool.func(query=None, config=self.config)
        self.assertEqual(res_none, "Error: Query is required to search conversations.")

    def test_search_conversations_coerces_string_limit_and_segments(self):
        res = conv_mod.search_conversations_tool.func(
            query="meeting with Bob",
            limit="15",
            max_transcript_segments="100",
            config=self.config
        )
        self.assertIn("None found", res)

    def test_render_addressable_conversations_handles_none_configurable(self):
        res = conv_mod._render_addressable_conversations([], configurable=None)
        self.assertEqual(res, "")


if __name__ == "__main__":
    unittest.main()
