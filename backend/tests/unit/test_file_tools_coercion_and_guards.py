"""Unit tests for file_tools input validation, timestamp parsing, and configuration fallbacks."""

from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn

    def dec(func):
        func.func = func
        return func

    return dec


@pytest.fixture(scope="class")
def file_tools_module():
    """Load utils.retrieval.tools.file_tools hermetically with isolated stubs."""
    db_chat = ModuleType("database.chat")
    db_chat.get_chat_session_by_id = MagicMock()

    class FakeChatSession:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
            self.file_ids = kwargs.get("file_ids", [])
            self.created_at = kwargs.get("created_at")

    models_chat = ModuleType("models.chat")
    models_chat.ChatSession = FakeChatSession

    class FakeProviderRejectedChatFileError(Exception):
        pass

    utils_chat_file = ModuleType("utils.other.chat_file")
    utils_chat_file.FileChatTool = MagicMock()
    utils_chat_file.ProviderRejectedChatFileError = FakeProviderRejectedChatFileError

    lc_tools = ModuleType("langchain_core.tools")
    lc_tools.tool = _tool_decorator

    lc_runnables = ModuleType("langchain_core.runnables")
    lc_runnables.RunnableConfig = dict

    stubs: dict[str, ModuleType | None] = {
        "database.chat": db_chat,
        "models.chat": models_chat,
        "utils.other.chat_file": utils_chat_file,
        "langchain_core.tools": lc_tools,
        "langchain_core.runnables": lc_runnables,
    }

    tool_path = BACKEND_DIR / "utils" / "retrieval" / "tools" / "file_tools.py"
    with stub_modules(stubs):
        mod = load_module_fresh("utils.retrieval.tools._file_tools_coercion_isolated", str(tool_path))
        yield mod


class TestFileToolsCoercionAndGuards:
    @pytest.fixture(autouse=True)
    def _setup_mod(self, file_tools_module):
        self.mod = file_tools_module

    def test_parse_seconds(self):
        assert self.mod._parse_seconds(10) == 10.0
        assert self.mod._parse_seconds("15.5") == 15.5
        assert self.mod._parse_seconds("0") == 0.0
        assert self.mod._parse_seconds(-5) == 0.0  # clamped to 0.0
        assert self.mod._parse_seconds(None) is None
        assert self.mod._parse_seconds(True) is None  # booleans rejected
        assert self.mod._parse_seconds(False) is None
        assert self.mod._parse_seconds("invalid") is None
        assert self.mod._parse_seconds(float("nan")) is None
        assert self.mod._parse_seconds(float("inf")) is None

    def test_empty_question_rejection(self):
        cfg = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        assert self.mod.search_files_tool.func("", config=cfg) == "Please provide a question about the files."
        assert self.mod.search_files_tool.func("   ", config=cfg) == "Please provide a question about the files."
        assert self.mod.search_files_tool.func(None, config=cfg) == "Please provide a question about the files."

    def test_no_active_chat_session(self):
        cfg = {"configurable": {"user_id": "u1"}}
        result = self.mod.search_files_tool.func("what is this?", config=cfg)
        assert result == "No active chat session. Files are not available."

    def test_top_level_config_resolution(self):
        cfg = {"user_id": "top_u1", "chat_session_id": "top_s1"}
        mock_session = {"id": "top_s1", "file_ids": ["f1"]}

        with (
            patch.object(self.mod.chat_db, "get_chat_session_by_id", return_value=mock_session),
            patch.object(self.mod, "FileChatTool") as mock_fc_class,
        ):
            mock_fc = MagicMock()
            mock_fc.process_chat_with_file.return_value = "Answer about file"
            mock_fc_class.return_value = mock_fc

            res = self.mod.search_files_tool.func("summarize", config=cfg)
            assert res == "Answer about file"
            mock_fc_class.assert_called_once_with("top_u1", "top_s1")

    def test_string_end_seconds_coercion_without_type_error(self):
        cfg = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        mock_session = {"id": "s1", "file_ids": ["vid1"]}

        with (
            patch.object(self.mod.chat_db, "get_chat_session_by_id", return_value=mock_session),
            patch.object(self.mod, "FileChatTool") as mock_fc_class,
        ):
            mock_fc = MagicMock()
            mock_fc.process_chat_with_file.return_value = "Video frame answer"
            mock_fc_class.return_value = mock_fc

            # Passing end_seconds="15" with start_seconds=None previously caused TypeError in ("15" or 0) - 5
            res = self.mod.search_files_tool.func(
                "what happens here?",
                start_seconds=None,
                end_seconds="15",
                config=cfg,
            )
            assert res == "Video frame answer"
            called_window = mock_fc.process_chat_with_file.call_args.args[2]
            assert called_window == (10.0, 15.0)

    def test_string_start_seconds_coercion(self):
        cfg = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        mock_session = {"id": "s1", "file_ids": ["vid1"]}

        with (
            patch.object(self.mod.chat_db, "get_chat_session_by_id", return_value=mock_session),
            patch.object(self.mod, "FileChatTool") as mock_fc_class,
        ):
            mock_fc = MagicMock()
            mock_fc.process_chat_with_file.return_value = "Video frame answer"
            mock_fc_class.return_value = mock_fc

            res = self.mod.search_files_tool.func(
                "what happens here?",
                start_seconds="10.5",
                end_seconds=None,
                config=cfg,
            )
            assert res == "Video frame answer"
            called_window = mock_fc.process_chat_with_file.call_args.args[2]
            assert called_window == (10.5, 15.5)

    def test_invalid_seconds_does_not_raise_value_error(self):
        cfg = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        mock_session = {"id": "s1", "file_ids": ["doc1"]}

        with (
            patch.object(self.mod.chat_db, "get_chat_session_by_id", return_value=mock_session),
            patch.object(self.mod, "FileChatTool") as mock_fc_class,
        ):
            mock_fc = MagicMock()
            mock_fc.process_chat_with_file.return_value = "Document summary"
            mock_fc_class.return_value = mock_fc

            # Non-numeric seconds should not crash with session error
            res = self.mod.search_files_tool.func(
                "read doc",
                start_seconds="not_a_number",
                config=cfg,
            )
            assert res == "Document summary"
            called_window = mock_fc.process_chat_with_file.call_args.args[2]
            assert called_window is None

    def test_single_string_file_id_coercion(self):
        cfg = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        mock_session = {"id": "s1", "file_ids": ["target_file_id"]}

        with (
            patch.object(self.mod.chat_db, "get_chat_session_by_id", return_value=mock_session),
            patch.object(self.mod, "FileChatTool") as mock_fc_class,
        ):
            mock_fc = MagicMock()
            mock_fc.process_chat_with_file.return_value = "Target file content"
            mock_fc_class.return_value = mock_fc

            # Passing single string instead of list
            res = self.mod.search_files_tool.func(
                "read target",
                file_ids="target_file_id",
                config=cfg,
            )
            assert res == "Target file content"
            called_files = mock_fc.process_chat_with_file.call_args.args[1]
            assert called_files == ["target_file_id"]

    def test_created_at_fallback_injected_for_legacy_session(self):
        cfg = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        mock_session = {"id": "s1", "file_ids": ["f1"]}  # no created_at

        with (
            patch.object(self.mod.chat_db, "get_chat_session_by_id", return_value=mock_session),
            patch.object(self.mod, "ChatSession") as mock_cs_class,
            patch.object(self.mod, "FileChatTool") as mock_fc_class,
        ):
            mock_cs = MagicMock()
            mock_cs.file_ids = ["f1"]
            mock_cs_class.return_value = mock_cs

            mock_fc = MagicMock()
            mock_fc.process_chat_with_file.return_value = "Answer"
            mock_fc_class.return_value = mock_fc

            res = self.mod.search_files_tool.func("summarize", config=cfg)
            assert res == "Answer"
            call_kwargs = mock_cs_class.call_args.kwargs
            assert "created_at" in call_kwargs
            assert call_kwargs["created_at"] is not None
            assert isinstance(call_kwargs["created_at"], datetime)
            assert call_kwargs["created_at"].tzinfo is not None
    def test_whitespace_or_empty_after_cleaning_file_ids_falls_through_to_all_files(self):
        """Empty-after-cleaning file_ids (e.g. whitespace only) intentionally falls through to search all session files."""
        cfg = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        mock_session = {"id": "s1", "file_ids": ["session_f1", "session_f2"]}

        with (
            patch.object(self.mod.chat_db, "get_chat_session_by_id", return_value=mock_session),
            patch.object(self.mod, "FileChatTool") as mock_fc_class,
        ):
            mock_fc = MagicMock()
            mock_fc.process_chat_with_file.return_value = "Searched all session files"
            mock_fc_class.return_value = mock_fc

            res = self.mod.search_files_tool.func(
                "query files",
                file_ids=["   ", "\t", None, 12345],  # type: ignore[arg-type]
                config=cfg,
            )
            assert res == "Searched all session files"
            called_files = mock_fc.process_chat_with_file.call_args.args[1]
            assert called_files == ["session_f1", "session_f2"]

    def test_uid_unresolved_while_chat_session_id_present(self):
        """Verify behavior when uid is unresolved but chat_session_id is present."""
        # 1. In configurable dictionary: uid is None, chat_session_id is present -> proceeds with None uid
        cfg_configurable = {"configurable": {"chat_session_id": "s1"}}
        mock_session = {"id": "s1", "file_ids": ["f1"]}

        with (
            patch.object(self.mod.chat_db, "get_chat_session_by_id", return_value=mock_session) as mock_get_session,
            patch.object(self.mod, "FileChatTool") as mock_fc_class,
        ):
            mock_fc = MagicMock()
            mock_fc.process_chat_with_file.return_value = "Answer with null uid"
            mock_fc_class.return_value = mock_fc

            res = self.mod.search_files_tool.func("summarize", config=cfg_configurable)
            assert res == "Answer with null uid"
            mock_get_session.assert_called_once_with(None, "s1")
            mock_fc_class.assert_called_once_with(None, "s1")

        # 2. In top-level dictionary (without configurable key): missing uid fails closed
        cfg_top_level_no_uid = {"chat_session_id": "top_s1"}
        res2 = self.mod.search_files_tool.func("summarize", config=cfg_top_level_no_uid)
        assert res2 == "Error: Configuration error"

