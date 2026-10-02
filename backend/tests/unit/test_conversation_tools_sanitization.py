"""Tests verifying exception sanitization in conversation_tools.py.

Ensures that unexpected internal exception details (e.g. raw Exception str(e),
internal DB failures, sensitive token strings) and inline traceback printing
are not leaked to LLM chat contexts or end-user screens.
"""

import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
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


# Stub httpx
_mod("httpx")

# Stub langchain_core
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

# Stub packages
for _p in [
    "database",
    "models",
    "utils",
    "utils.conversations",
    "utils.retrieval",
    "utils.retrieval.tools",
]:
    _pkg(_p)

# Stub database modules
_conv_db_mod = _mod("database.conversations")
_conv_db_mod.get_conversations = MagicMock(return_value=[])

_notif_db_mod = _mod("database.notifications")
_notif_db_mod.get_user_time_zone = MagicMock(return_value="UTC")

_users_db_mod = _mod("database.users")
_users_db_mod.get_people_by_ids = MagicMock(return_value=[])

_vector_db_mod = _mod("database.vector_db")

# Stub models.other
_models_other_mod = _mod("models.other")
_models_other_mod.Person = MagicMock

# Stub utils.conversations modules
_conv_factory_mod = _mod("utils.conversations.factory")
_conv_factory_mod.deserialize_conversation = MagicMock(return_value=MagicMock(transcript_segments=[]))

_conv_render_mod = _mod("utils.conversations.render")
_conv_render_mod.conversation_to_citation_card = MagicMock(return_value={})
_conv_render_mod.conversations_to_string = MagicMock(return_value="Formatted conversations")

_conv_search_mod = _mod("utils.conversations.search")
_conv_search_mod.conversation_matches_date_range = MagicMock(return_value=True)
_conv_search_mod.keyword_search_conversation_ids = MagicMock(return_value=[])
_conv_search_mod.merge_conversation_search_ids = MagicMock(return_value=[])
_conv_search_mod.parse_exact_conversation_reference = MagicMock(return_value=None)

# Stub utils.retrieval.chat_scope
_chat_scope_mod = _mod("utils.retrieval.chat_scope")
_chat_scope_mod.apply_chat_scope_dates = lambda scope, s, e: (s, e, None)
_chat_scope_mod.chat_scope_from_config = lambda cfg: None

# Stub utils.retrieval.tools.conversation_jit
_conv_jit_mod = _mod("utils.retrieval.tools.conversation_jit")
_conv_jit_mod.MAX_JIT_CONVERSATIONS = 10
_conv_jit_mod.format_active_jit_conversations = MagicMock(return_value="JIT conversations")
_conv_jit_mod.is_jit_conversation_retrieval_enabled = MagicMock(return_value=False)


def _load(module_name, rel_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_DIR / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


conv_tools = _load(
    "utils.retrieval.tools._conversation_tools_sanitization_test",
    "utils/retrieval/tools/conversation_tools.py",
)


class TestConversationToolsSanitization(unittest.TestCase):
    SENSITIVE = "sensitive_internal_token_secret_12345"
    EXPECTED_SANITIZED = "An unexpected error occurred while fetching conversations. Please try again later."

    def test_formatting_exception_is_sanitized_without_leaking_details(self):
        fake_convs = [{"id": "conv-1", "transcript_segments": []}]
        with (
            patch.object(conv_tools.conversations_db, "get_conversations", return_value=fake_convs),
            patch.object(
                conv_tools,
                "conversations_to_string",
                side_effect=RuntimeError(f"Internal crash at /var/secrets: {self.SENSITIVE}"),
            ),
        ):
            config = {"configurable": {"user_id": "test_user"}}
            result = conv_tools.get_conversations_tool.func(config=config)

            self.assertNotIn(self.SENSITIVE, result)
            self.assertNotIn("RuntimeError", result)
            self.assertEqual(self.EXPECTED_SANITIZED, result)

    def test_database_query_exception_is_sanitized(self):
        with patch.object(
            conv_tools.conversations_db,
            "get_conversations",
            side_effect=RuntimeError(f"Firestore query timeout: {self.SENSITIVE}"),
        ):
            config = {"configurable": {"user_id": "test_user"}}
            result = conv_tools.get_conversations_tool.func(config=config)

            self.assertNotIn(self.SENSITIVE, result)
            self.assertNotIn("RuntimeError", result)
            self.assertEqual(self.EXPECTED_SANITIZED, result)

    def test_scoped_fetch_exception_is_sanitized(self):
        with (
            patch.object(
                conv_tools,
                "chat_scope_from_config",
                return_value={"conversation_id": "conv_999"},
            ),
            patch.object(
                conv_tools,
                "_scoped_conversation_fetch",
                side_effect=RuntimeError(f"Scoped fetch failure: {self.SENSITIVE}"),
            ),
        ):
            config = {"configurable": {"user_id": "test_user"}}
            result = conv_tools.get_conversations_tool.func(config=config)

            self.assertNotIn(self.SENSITIVE, result)
            self.assertNotIn("RuntimeError", result)
            self.assertEqual(self.EXPECTED_SANITIZED, result)

    def test_missing_user_id_returns_clean_error(self):
        config = {"configurable": {}}
        result = conv_tools.get_conversations_tool.func(config=config)
        self.assertEqual("Error: User ID not found in configuration", result)

    def test_invalid_start_date_returns_validation_error(self):
        config = {"configurable": {"user_id": "test_user"}}
        result = conv_tools.get_conversations_tool.func(start_date="not-a-date", config=config)
        self.assertIn("Error: Invalid start_date format", result)

    def test_successful_fetch_returns_formatted_string(self):
        fake_convs = [{"id": "conv-1", "transcript_segments": []}]
        with patch.object(conv_tools.conversations_db, "get_conversations", return_value=fake_convs):
            config = {"configurable": {"user_id": "test_user"}}
            result = conv_tools.get_conversations_tool.func(config=config)
            self.assertEqual("Formatted conversations", result)


if __name__ == "__main__":
    unittest.main()
