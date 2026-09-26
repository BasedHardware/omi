"""Tests verifying exception sanitization in file_tools.py.

Ensures that internal exception details (ValueError str(e), traceback, etc.)
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
    "models.chat",
    "utils",
    "utils.other",
    "utils.retrieval",
    "utils.retrieval.tools",
]:
    _pkg(_p)

for _name, _attrs in {
    "database.chat": ["get_chat_session_by_id"],
    "models.chat": ["ChatSession"],
    "utils.other.chat_file": ["FileChatTool"],
    "utils.retrieval.agentic": ["agent_config_context"],
}.items():
    _m = _mod(_name)
    for _a in _attrs:
        if not hasattr(_m, _a):
            setattr(_m, _a, MagicMock())

ft = _load(
    "utils.retrieval.tools._file_tools_sanitization_test",
    "utils/retrieval/tools/file_tools.py",
)


class TestFileToolsSanitization(unittest.TestCase):
    def test_search_files_config_error_sanitized(self):
        # Missing configurable causes AttributeError on configurable.get('user_id')
        result = ft.search_files_tool.func(question="test", config={"invalid": 123})
        self.assertEqual("Error: Configuration error", result)

    def test_search_files_value_error_sanitized(self):
        config = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        with patch.object(ft.chat_db, "get_chat_session_by_id", side_effect=ValueError("internal database secret")):
            result = ft.search_files_tool.func(question="test", config=config)
            self.assertEqual("Session error: Invalid session parameters.", result)
            self.assertNotIn("internal database secret", result)

    def test_search_files_unexpected_exception_sanitized(self):
        config = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        with patch.object(ft.chat_db, "get_chat_session_by_id", side_effect=RuntimeError("redis pool exhausted")):
            result = ft.search_files_tool.func(question="test", config=config)
            self.assertEqual(
                "I encountered an error while searching the files. Please try again or rephrase your question.", result
            )
            self.assertNotIn("redis pool exhausted", result)


if __name__ == "__main__":
    unittest.main()
