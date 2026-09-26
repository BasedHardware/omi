"""Tests verifying exception sanitization in conversation_tools.py.

Ensures that internal exception details (ValueError str(e), formatting traces, etc.)
are not leaked to chat tool callers or plugin logs.
"""

import importlib
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    mod = sys.modules.get(name)
    if mod is None:
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


# Ensure langchain_core is stubbed if not installed
_pkg("langchain_core")
_lc_tools = _mod("langchain_core.tools")


def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn

    def dec(func):
        func.func = func
        return func

    return dec


_lc_tools.tool = _tool_decorator

_lc_runnables = _mod("langchain_core.runnables")
_lc_runnables.RunnableConfig = dict

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
    "database.conversations": ["get_conversations", "get_conversations_by_id"],
    "database.notifications": ["get_user_time_zone"],
    "database.users": ["get_people_by_ids"],
    "database.vector_db": ["query_vectors_by_metadata"],
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
    "utils.retrieval.chat_scope": ["apply_chat_scope_dates", "chat_scope_from_config"],
    "utils.retrieval.tools.conversation_jit": [
        "MAX_JIT_CONVERSATIONS",
        "format_active_jit_conversations",
        "is_jit_conversation_retrieval_enabled",
    ],
}.items():
    _m = _mod(_name)
    for _a in _attrs:
        if not hasattr(_m, _a):
            setattr(_m, _a, MagicMock())

_chat_scope = sys.modules["utils.retrieval.chat_scope"]
_chat_scope.apply_chat_scope_dates = lambda scope, s, e: (s, e, None)
_chat_scope.chat_scope_from_config = lambda configurable: None

_jit = sys.modules["utils.retrieval.tools.conversation_jit"]
_jit.MAX_JIT_CONVERSATIONS = 10
_jit.format_active_jit_conversations = MagicMock()
_jit.is_jit_conversation_retrieval_enabled = lambda configurable: False

ct = _load(
    "utils.retrieval.tools._conversation_tools_sanitization_test",
    "utils/retrieval/tools/conversation_tools.py",
)


class TestConversationToolsSanitization(unittest.TestCase):
    def test_get_conversations_invalid_start_date_sanitized(self):
        config = {"configurable": {"user_id": "test_user"}}
        result = ct.get_conversations_tool.func(start_date="not-a-date", config=config)
        self.assertIn("Error: Invalid start_date format", result)
        self.assertIn("not-a-date", result)
        self.assertNotIn("ValueError", result)
        self.assertNotIn("ISO format", result)

    def test_get_conversations_invalid_end_date_sanitized(self):
        config = {"configurable": {"user_id": "test_user"}}
        result = ct.get_conversations_tool.func(end_date="not-a-date", config=config)
        self.assertIn("Error: Invalid end_date format", result)
        self.assertIn("not-a-date", result)
        self.assertNotIn("ValueError", result)
        self.assertNotIn("ISO format", result)

    def test_get_conversations_formatting_exception_sanitized(self):
        config = {"configurable": {"user_id": "test_user"}}
        with patch.object(ct.conversations_db, "get_conversations", return_value=[{"id": "conv1"}]), patch.object(
            ct, "deserialize_conversation", return_value=MagicMock()
        ), patch.object(ct, "conversations_to_string", side_effect=RuntimeError("internal secret connection leak")):
            result = ct.get_conversations_tool.func(config=config)
            self.assertEqual("Found 1 conversations but encountered an error formatting them.", result)
            self.assertNotIn("internal secret connection leak", result)
            self.assertNotIn("RuntimeError", result)

    def test_search_conversations_invalid_start_date_sanitized(self):
        config = {"configurable": {"user_id": "test_user"}}
        result = ct.search_conversations_tool.func(query="test", start_date="bad-date", config=config)
        self.assertIn("Error: Invalid start_date format", result)
        self.assertIn("bad-date", result)
        self.assertNotIn("ValueError", result)

    def test_search_conversations_invalid_end_date_sanitized(self):
        config = {"configurable": {"user_id": "test_user"}}
        result = ct.search_conversations_tool.func(query="test", end_date="bad-date", config=config)
        self.assertIn("Error: Invalid end_date format", result)
        self.assertIn("bad-date", result)
        self.assertNotIn("ValueError", result)


if __name__ == "__main__":
    unittest.main()
