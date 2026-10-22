"""Hermetic unit tests for file_tools resilience, input validation, and config fallback."""

import importlib.util
import math
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

_chat_file_stub = _mod("utils.other.chat_file")
_rejected = getattr(_chat_file_stub, "ProviderRejectedChatFileError", None)
if not (isinstance(_rejected, type) and issubclass(_rejected, BaseException)):

    class ProviderRejectedChatFileError(Exception):
        pass

    _chat_file_stub.ProviderRejectedChatFileError = ProviderRejectedChatFileError

ft = _load(
    "utils.retrieval.tools._file_tools_resilience_test",
    "utils/retrieval/tools/file_tools.py",
)


class FakeChatSession:
    def __init__(self, file_ids=None):
        self.file_ids = file_ids or []


class TestFileToolsResilience(unittest.TestCase):
    def test_empty_or_invalid_question_returns_error(self):
        config = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        for invalid_q in [None, "", "   ", 123, []]:
            res = ft.search_files_tool.func(question=invalid_q, config=config)
            self.assertEqual("Error: A non-empty question is required to search files.", res)

    def test_missing_or_invalid_config_returns_error(self):
        res1 = ft.search_files_tool.func(question="test", config=None)
        self.assertEqual("Error: Configuration not available", res1)

        res2 = ft.search_files_tool.func(question="test", config="not_a_dict")
        self.assertEqual("Error: Configuration not available", res2)

    def test_missing_uid_and_session_id_returns_config_error(self):
        res1 = ft.search_files_tool.func(question="test", config={"foo": "bar"})
        self.assertEqual("Error: Configuration error", res1)

        res2 = ft.search_files_tool.func(question="test", config={"configurable": {}})
        self.assertEqual("Error: Configuration error", res2)

    def test_missing_user_id_returns_user_id_error(self):
        config = {"configurable": {"chat_session_id": "s1"}}
        res = ft.search_files_tool.func(question="test", config=config)
        self.assertEqual("Error: User ID not found in configuration.", res)

    def test_missing_chat_session_id_returns_no_session(self):
        config = {"configurable": {"user_id": "u1"}}
        res = ft.search_files_tool.func(question="test", config=config)
        self.assertEqual("No active chat session. Files are not available.", res)

    def test_top_level_config_and_uid_alias_fallback(self):
        # Fallback to top-level user_id and chat_session_id
        config_top = {"user_id": "u1", "chat_session_id": "s1"}
        with patch.object(ft.chat_db, "get_chat_session_by_id", return_value=None):
            res = ft.search_files_tool.func(question="test", config=config_top)
            self.assertEqual("Chat session not found.", res)

        # Fallback to uid alias
        config_uid = {"configurable": {"uid": "u2", "chat_session_id": "s2"}}
        with patch.object(ft.chat_db, "get_chat_session_by_id", return_value=None):
            res = ft.search_files_tool.func(question="test", config=config_uid)
            self.assertEqual("Chat session not found.", res)

    def test_file_ids_string_and_tuple_coercion(self):
        config = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        fake_session = FakeChatSession(file_ids=["file_100", "file_200"])

        mock_tool_instance = MagicMock()
        mock_tool_instance.process_chat_with_file.return_value = "file answer"

        with patch.object(ft.chat_db, "get_chat_session_by_id", return_value={"file_ids": ["file_100", "file_200"]}):
            with patch.object(ft, "ChatSession", return_value=fake_session):
                with patch.object(ft, "FileChatTool", return_value=mock_tool_instance):
                    # Passing single string instead of list
                    res_str = ft.search_files_tool.func(question="test", file_ids="file_100", config=config)
                    self.assertEqual("file answer", res_str)
                    mock_tool_instance.process_chat_with_file.assert_called_with("test", ["file_100"], None)

                    # Passing tuple with whitespace and None
                    res_tuple = ft.search_files_tool.func(
                        question="test", file_ids=(" file_100 ", None, ""), config=config
                    )
                    self.assertEqual("file answer", res_tuple)
                    mock_tool_instance.process_chat_with_file.assert_called_with("test", ["file_100"], None)

    def test_file_ids_non_iterable_safe_handling(self):
        config = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        fake_session = FakeChatSession(file_ids=["file_100"])

        mock_tool_instance = MagicMock()
        mock_tool_instance.process_chat_with_file.return_value = "file answer"

        with patch.object(ft.chat_db, "get_chat_session_by_id", return_value={"file_ids": ["file_100"]}):
            with patch.object(ft, "ChatSession", return_value=fake_session):
                with patch.object(ft, "FileChatTool", return_value=mock_tool_instance):
                    # Passing non-iterable int (should safely search all session files)
                    res = ft.search_files_tool.func(question="test", file_ids=123, config=config)
                    self.assertEqual("file answer", res)
                    mock_tool_instance.process_chat_with_file.assert_called_with("test", ["file_100"], None)

    def test_specified_files_not_available_in_session(self):
        config = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        fake_session = FakeChatSession(file_ids=["file_100"])

        with patch.object(ft.chat_db, "get_chat_session_by_id", return_value={"file_ids": ["file_100"]}):
            with patch.object(ft, "ChatSession", return_value=fake_session):
                res = ft.search_files_tool.func(question="test", file_ids=["file_999"], config=config)
                self.assertEqual("The specified files are not available in this chat session.", res)

    def test_no_files_uploaded_yet(self):
        config = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        fake_session = FakeChatSession(file_ids=[])

        with patch.object(ft.chat_db, "get_chat_session_by_id", return_value={"file_ids": []}):
            with patch.object(ft, "ChatSession", return_value=fake_session):
                res = ft.search_files_tool.func(question="test", file_ids=None, config=config)
                self.assertEqual(
                    "No files have been uploaded to this chat session yet. Ask the user to upload files first.", res
                )

    def test_start_and_end_seconds_coercion_and_window(self):
        config = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        fake_session = FakeChatSession(file_ids=["file_100"])

        mock_tool_instance = MagicMock()
        mock_tool_instance.process_chat_with_file.return_value = "video answer"

        with patch.object(ft.chat_db, "get_chat_session_by_id", return_value={"file_ids": ["file_100"]}):
            with patch.object(ft, "ChatSession", return_value=fake_session):
                with patch.object(ft, "FileChatTool", return_value=mock_tool_instance):
                    # String numeric values
                    res = ft.search_files_tool.func(
                        question="test", start_seconds="12.5", end_seconds="18.5", config=config
                    )
                    self.assertEqual("video answer", res)
                    mock_tool_instance.process_chat_with_file.assert_called_with("test", ["file_100"], (12.5, 18.5))

                    # Non-numeric string should not crash
                    res_bad = ft.search_files_tool.func(
                        question="test", start_seconds="invalid", end_seconds="nan", config=config
                    )
                    self.assertEqual("video answer", res_bad)
                    mock_tool_instance.process_chat_with_file.assert_called_with("test", ["file_100"], None)

                    # Negative start_seconds clamped to 0.0
                    res_neg = ft.search_files_tool.func(question="test", start_seconds=-10, config=config)
                    self.assertEqual("video answer", res_neg)
                    mock_tool_instance.process_chat_with_file.assert_called_with("test", ["file_100"], (0.0, 5.0))


if __name__ == "__main__":
    unittest.main()
