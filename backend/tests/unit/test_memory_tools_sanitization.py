"""Tests verifying exception sanitization in memory_tools.py.

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


# Stub dependencies hermetically
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

_pkg("database")
_db_client_mod = _mod("database._client")
_db_client_mod.db = MagicMock()
_notif_mod = _mod("database.notifications")
_notif_mod.get_user_time_zone = MagicMock(return_value="UTC")

_pkg("models")
_mem_models_mod = _mod("models.memories")
_mem_models_mod.MemoryDB = MagicMock()

for p in [
    "utils",
    "utils.memory",
    "utils.memory.memory_service",
    "utils.memory.belief_model",
    "utils.conversations",
    "utils.conversations.render",
    "utils.retrieval",
    "utils.retrieval.chat_scope",
    "utils.retrieval.memory_evidence",
    "utils.retrieval.tools",
    "utils.retrieval.tools.result_bounds",
]:
    _pkg(p)

_mem_service_mod = _mod("utils.memory.memory_service")
_mem_service_mod.MemoryService = MagicMock()

_belief_mod = _mod("utils.memory.belief_model")
_belief_mod.belief_model_enabled = MagicMock(return_value=False)
_belief_mod.memory_use_suppressed = MagicMock(return_value=False)
_belief_mod.normalize_temporal_read_view = MagicMock(return_value="useful_now")

_conv_render_mod = _mod("utils.conversations.render")
_conv_render_mod.format_local_date = MagicMock(return_value="2026-09-28")
_conv_render_mod.resolve_display_tz = MagicMock(return_value=(None, None))

_chat_scope_mod = _mod("utils.retrieval.chat_scope")
_chat_scope_mod.apply_chat_scope_dates = MagicMock(return_value=(None, None, None))
_chat_scope_mod.chat_scope_from_config = MagicMock(return_value=None)

_mem_evidence_mod = _mod("utils.retrieval.memory_evidence")
_mem_evidence_mod.MAX_MEMORY_EVIDENCE_CHARS = 1000
_mem_evidence_mod.format_memory_evidence = MagicMock(return_value="evidence")
_mem_evidence_mod.render_memory_evidence = MagicMock(return_value="rendered_evidence")

_result_bounds_mod = _mod("utils.retrieval.tools.result_bounds")
_result_bounds_mod.cap_items_for_llm = MagicMock(return_value=([], 0, False))


def _load(module_name, rel_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_DIR / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


mt = _load(
    "utils.retrieval.tools._memory_tools_sanitization_test",
    "utils/retrieval/tools/memory_tools.py",
)


class TestMemoryToolsSanitization(unittest.TestCase):
    SENSITIVE = "sensitive_firestore_internal_credentials_xyz_777"

    def test_unexpected_exception_in_search_memories_tool_is_sanitized(self):
        mock_service_instance = MagicMock()
        mock_service_instance.search.side_effect = RuntimeError(f"Database query crash: {self.SENSITIVE}")

        with patch.object(mt, "MemoryService", return_value=mock_service_instance):
            result = mt.search_memories_tool.func(
                query="coffee preferences",
                config={"configurable": {"user_id": "user_123"}},
            )
            self.assertNotIn(self.SENSITIVE, result)
            self.assertNotIn("RuntimeError", result)
            self.assertEqual("Error searching memories. Please try again.", result)

    def test_traceback_print_exc_not_called_in_search_memories_tool(self):
        mock_service_instance = MagicMock()
        mock_service_instance.search.side_effect = RuntimeError("Crash")

        with patch.object(mt, "MemoryService", return_value=mock_service_instance), \
             patch("traceback.print_exc") as mock_print_exc:
            result = mt.search_memories_tool.func(
                query="coffee preferences",
                config={"configurable": {"user_id": "user_123"}},
            )
            self.assertFalse(mock_print_exc.called)
            self.assertEqual("Error searching memories. Please try again.", result)

    def test_config_not_available_returns_clean_error(self):
        result = mt.search_memories_tool.func(query="test", config=None)
        self.assertEqual("Error: Configuration not available", result)

    def test_missing_user_id_returns_clean_error(self):
        result = mt.search_memories_tool.func(
            query="test",
            config={"configurable": {}},
        )
        self.assertEqual("Error: User ID not found in configuration", result)

    def test_chat_scope_blocked_returns_clean_error(self):
        with patch.object(
            mt,
            "_memory_tools_blocked_by_chat_scope",
            return_value="Error: Chat is scoped to a single conversation.",
        ):
            result = mt.search_memories_tool.func(
                query="test",
                config={"configurable": {"user_id": "user_123"}},
            )
            self.assertEqual("Error: Chat is scoped to a single conversation.", result)


if __name__ == "__main__":
    unittest.main()
