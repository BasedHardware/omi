"""Tests verifying defensive parameter guards, coercion, and config handling in file_tools.py.

Hermetic isolated unit test suite covering:
1. question validation: None, empty string, or whitespace returns clean error message.
2. config resolution: Top-level user_id/uid and chat_session_id fallbacks.
3. configurable uid alias resolution: Support for 'uid' key in configurable dict.
4. missing uid guard: When chat_session_id is present but user_id is missing.
5. missing chat_session_id guard: When user_id is present but chat_session_id is missing.
6. file_ids string normalization: Single string file_ids normalized without character iteration.
7. file_ids non-iterable handling: Integer or malformed file_ids does not crash.
8. video window bounds: Coercion of string start/end seconds, subtraction TypeError prevention,
   and clean rejection of booleans and non-numeric values.
"""

import contextvars
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

try:
    from tests.unit.memory_import_isolation import (
        restore_sys_modules,
        snapshot_sys_modules,
    )
except ImportError:
    try:
        from memory_import_isolation import (
            restore_sys_modules,
            snapshot_sys_modules,
        )
    except ImportError:
        def snapshot_sys_modules(names):
            return {name: sys.modules.get(name) for name in names}

        def restore_sys_modules(saved):
            for name, original in saved.items():
                if original is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = original

_SYS_MODULE_NAMES = [
    "langchain_core",
    "langchain_core.tools",
    "langchain_core.runnables",
    "database",
    "database.chat",
    "models",
    "models.chat",
    "utils",
    "utils.other",
    "utils.other.chat_file",
    "utils.retrieval",
    "utils.retrieval.agentic",
    "utils.retrieval.tools",
    "utils.retrieval.tools._file_tools_guards_test",
]

_SYS_MODULES_SNAPSHOT = snapshot_sys_modules(_SYS_MODULE_NAMES)


def tearDownModule():
    restore_sys_modules(_SYS_MODULES_SNAPSHOT)


def _pkg(name: str):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name: str):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


def _tool_decorator(func=None, **kwargs):
    if func is not None:
        func.func = func
        return func

    def dec(f):
        f.func = f
        return f

    return dec


for _p in [
    "langchain_core",
    "langchain_core.tools",
    "langchain_core.runnables",
    "database",
    "models",
    "utils",
    "utils.other",
    "utils.retrieval",
    "utils.retrieval.tools",
]:
    _pkg(_p)

_langchain_tools = _mod("langchain_core.tools")
_langchain_tools.tool = _tool_decorator

_lc_runnables = _mod("langchain_core.runnables")
_lc_runnables.RunnableConfig = dict

for _name, _attrs in {
    "database.chat": ["get_chat_session_by_id"],
    "models.chat": ["ChatSession"],
    "utils.other.chat_file": ["FileChatTool"],
}.items():
    _m = _mod(_name)
    for _a in _attrs:
        if not hasattr(_m, _a):
            setattr(_m, _a, MagicMock())

_agentic_stub = _mod("utils.retrieval.agentic")
_agentic_stub.agent_config_context = contextvars.ContextVar("agent_config", default=None)

_chat_file_stub = _mod("utils.other.chat_file")
_rejected = getattr(_chat_file_stub, "ProviderRejectedChatFileError", None)
if not (isinstance(_rejected, type) and issubclass(_rejected, BaseException)):

    class ProviderRejectedChatFileError(Exception):
        pass

    _chat_file_stub.ProviderRejectedChatFileError = ProviderRejectedChatFileError

ft_spec = importlib.util.spec_from_file_location(
    "utils.retrieval.tools._file_tools_guards_test",
    str(BACKEND_DIR / "utils/retrieval/tools/file_tools.py"),
)
ft = importlib.util.module_from_spec(ft_spec)
ft_spec.loader.exec_module(ft)


class TestFileToolsGuards(unittest.TestCase):
    def test_question_validation(self):
        """None, empty, whitespace-only, or non-string question returns clear error."""
        for invalid_q in [None, "", "   ", 123, []]:
            res = ft.search_files_tool.func(question=invalid_q, config={"foo": "bar"})
            self.assertEqual("Error: Please provide a question to search the files.", res)

    def test_top_level_config_uid_and_session_id_resolution(self):
        """Config with top-level user_id and chat_session_id resolves cleanly."""
        config = {"user_id": "usr_top", "chat_session_id": "sess_top"}
        session_data = {"file_ids": ["f_1"]}

        mock_session = types.SimpleNamespace(file_ids=["f_1"])
        mock_fc = MagicMock()
        mock_fc.process_chat_with_file.return_value = "answer from file"

        with patch.object(ft.chat_db, "get_chat_session_by_id", return_value=session_data) as mock_get_sess, \
             patch.object(ft, "ChatSession", return_value=mock_session), \
             patch.object(ft, "FileChatTool", return_value=mock_fc):
            res = ft.search_files_tool.func(question="test question", config=config)
            self.assertEqual("answer from file", res)
            mock_get_sess.assert_called_once_with("usr_top", "sess_top")

    def test_configurable_uid_alias_resolution(self):
        """Config with 'uid' instead of 'user_id' in configurable resolves cleanly."""
        config = {"configurable": {"uid": "usr_alias", "chat_session_id": "sess_alias"}}
        session_data = {"file_ids": ["f_1"]}

        mock_session = types.SimpleNamespace(file_ids=["f_1"])
        mock_fc = MagicMock()
        mock_fc.process_chat_with_file.return_value = "answer from file"

        with patch.object(ft.chat_db, "get_chat_session_by_id", return_value=session_data) as mock_get_sess, \
             patch.object(ft, "ChatSession", return_value=mock_session), \
             patch.object(ft, "FileChatTool", return_value=mock_fc):
            res = ft.search_files_tool.func(question="test question", config=config)
            self.assertEqual("answer from file", res)
            mock_get_sess.assert_called_once_with("usr_alias", "sess_alias")

    def test_missing_uid_guard(self):
        """When chat_session_id is present but user_id is missing, returns user ID error."""
        config = {"configurable": {"chat_session_id": "sess_1"}}
        res = ft.search_files_tool.func(question="test question", config=config)
        self.assertEqual("Error: User ID not found in configuration", res)

    def test_missing_chat_session_id_guard(self):
        """When user_id is present but chat_session_id is missing, returns session unavailable."""
        config = {"configurable": {"user_id": "u1"}}
        res = ft.search_files_tool.func(question="test question", config=config)
        self.assertEqual("No active chat session. Files are not available.", res)

    def test_file_ids_single_string_normalization(self):
        """Passing a single string for file_ids normalizes to a single-element list."""
        config = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        mock_session = types.SimpleNamespace(file_ids=["f_single"])
        mock_fc = MagicMock()
        mock_fc.process_chat_with_file.return_value = "file answer"

        with patch.object(ft.chat_db, "get_chat_session_by_id", return_value={"file_ids": ["f_single"]}), \
             patch.object(ft, "ChatSession", return_value=mock_session), \
             patch.object(ft, "FileChatTool", return_value=mock_fc):
            # Passing file_ids="f_single" as a string
            res = ft.search_files_tool.func(question="test", file_ids="f_single", config=config)
            self.assertEqual("file answer", res)
            args, _ = mock_fc.process_chat_with_file.call_args
            self.assertEqual(["f_single"], args[1])

    def test_file_ids_non_iterable_safe_handling(self):
        """Non-iterable file_ids (e.g. int) does not crash and searches all session files."""
        config = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        mock_session = types.SimpleNamespace(file_ids=["f_default"])
        mock_fc = MagicMock()
        mock_fc.process_chat_with_file.return_value = "file answer"

        with patch.object(ft.chat_db, "get_chat_session_by_id", return_value={"file_ids": ["f_default"]}), \
             patch.object(ft, "ChatSession", return_value=mock_session), \
             patch.object(ft, "FileChatTool", return_value=mock_fc):
            # Passing file_ids=123 (int)
            res = ft.search_files_tool.func(question="test", file_ids=123, config=config)
            self.assertEqual("file answer", res)
            args, _ = mock_fc.process_chat_with_file.call_args
            self.assertEqual(["f_default"], args[1])

    def test_video_window_string_seconds_no_typeerror(self):
        """Passing string end_seconds without start_seconds does not raise string-int subtraction TypeError."""
        config = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        mock_session = types.SimpleNamespace(file_ids=["f1"])
        mock_fc = MagicMock()
        mock_fc.process_chat_with_file.return_value = "file answer"

        with patch.object(ft.chat_db, "get_chat_session_by_id", return_value={"file_ids": ["f1"]}), \
             patch.object(ft, "ChatSession", return_value=mock_session), \
             patch.object(ft, "FileChatTool", return_value=mock_fc):
            res = ft.search_files_tool.func(
                question="test", end_seconds="10", config=config
            )
            self.assertEqual("file answer", res)
            args, _ = mock_fc.process_chat_with_file.call_args
            window = args[2]
            self.assertEqual((5.0, 10.0), window)

    def test_video_window_rejection_of_boolean_and_malformed(self):
        """Boolean or non-numeric seconds are rejected cleanly with session error."""
        config = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        mock_session = types.SimpleNamespace(file_ids=["f1"])

        with patch.object(ft.chat_db, "get_chat_session_by_id", return_value={"file_ids": ["f1"]}), \
             patch.object(ft, "ChatSession", return_value=mock_session):
            for bad_sec in [True, False, "not_a_number"]:
                res1 = ft.search_files_tool.func(
                    question="test", start_seconds=bad_sec, config=config
                )
                self.assertEqual("Session error: Invalid session parameters.", res1)

                res2 = ft.search_files_tool.func(
                    question="test", end_seconds=bad_sec, config=config
                )
                self.assertEqual("Session error: Invalid session parameters.", res2)


if __name__ == "__main__":
    unittest.main()
