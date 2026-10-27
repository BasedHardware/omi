"""Unit tests for file_tools input validation, timestamp parsing, and configuration fallbacks."""

from unittest.mock import MagicMock, patch
import pytest

import utils.retrieval.tools.file_tools as file_tools
from models.chat import ChatSession


class TestFileToolsCoercionAndGuards:
    mod = file_tools

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
        assert self.mod.search_files_tool.func("what is this?", config=cfg) == "No active chat session. Files are not available."

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
