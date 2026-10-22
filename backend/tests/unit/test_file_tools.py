"""Unit tests verifying search_files_tool behavior, question validation, file_id coercion, and config handling."""

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from utils.retrieval.tools.file_tools import (
    _names_request_field,
    search_files_tool,
)
import utils.retrieval.tools.file_tools as file_tools


def _valid_session_fixture(file_ids=None):
    return {
        "id": "s1",
        "created_at": datetime.now(timezone.utc),
        "file_ids": file_ids or [],
    }


class TestFileTools(unittest.TestCase):

    def test_names_request_field(self):
        self.assertTrue(_names_request_field("model", None))
        self.assertTrue(_names_request_field("messages[0]", None))
        self.assertFalse(_names_request_field("messages[0].file.file_id", None))
        self.assertTrue(_names_request_field(None, "model_not_found"))
        self.assertFalse(_names_request_field("other_param", "other_code"))

    def test_empty_or_none_question(self):
        config = {"configurable": {"user_id": "u1", "chat_session_id": "s1"}}
        # None tested via func directly (bypassing pydantic input validation)
        res_none = search_files_tool.func(question=None, config=config)
        self.assertEqual(res_none, "Error: Question cannot be empty.")

        # Whitespace tested via invoke
        res_empty = search_files_tool.invoke({"question": "   "}, config=config)
        self.assertEqual(res_empty, "Error: Question cannot be empty.")

    def test_missing_config_or_session(self):
        res_no_cfg = search_files_tool.func(question="Summary", config=None)
        self.assertEqual(res_no_cfg, "Error: Configuration not available")

        res_no_session = search_files_tool.invoke(
            {"question": "Summary"}, config={"configurable": {"user_id": "u1"}}
        )
        self.assertEqual(res_no_session, "No active chat session. Files are not available.")

    def test_missing_configurable_error_preserved(self):
        res = search_files_tool.func(question="Summary", config={"foo": "bar"})
        self.assertEqual(res, "Error: Configuration error")

    def test_top_level_config_fallback_func(self):
        with patch.object(file_tools.chat_db, "get_chat_session_by_id", return_value=None) as mock_get:
            res = search_files_tool.func(
                question="Summary",
                config={"configurable": {}, "user_id": "u1", "chat_session_id": "s1"},
            )
            self.assertEqual(res, "Chat session not found.")
            mock_get.assert_called_with("u1", "s1")

    def test_session_not_found(self):
        with patch.object(file_tools.chat_db, "get_chat_session_by_id", return_value=None):
            res = search_files_tool.invoke(
                {"question": "Summary"},
                config={"configurable": {"user_id": "u1", "chat_session_id": "s1"}},
            )
            self.assertEqual(res, "Chat session not found.")

    def test_no_files_uploaded_to_session(self):
        fixture = _valid_session_fixture(file_ids=[])
        with patch.object(file_tools.chat_db, "get_chat_session_by_id", return_value=fixture):
            res = search_files_tool.invoke(
                {"question": "Summary"},
                config={"configurable": {"user_id": "u1", "chat_session_id": "s1"}},
            )
            self.assertIn("No files have been uploaded to this chat session yet", res)

    def test_search_specified_file_found(self):
        fixture = _valid_session_fixture(file_ids=["f1", "f2"])
        mock_fc = MagicMock()
        mock_fc.process_chat_with_file.return_value = "File summary content"
        with patch.object(file_tools.chat_db, "get_chat_session_by_id", return_value=fixture), \
             patch.object(file_tools, "FileChatTool", return_value=mock_fc):
            res = search_files_tool.invoke(
                {
                    "question": "What is in f1?",
                    "file_ids": ["f1"],
                },
                config={"configurable": {"user_id": "u1", "chat_session_id": "s1"}},
            )
            self.assertEqual(res, "File summary content")
            mock_fc.process_chat_with_file.assert_called_with("What is in f1?", ["f1"], None)

    def test_search_single_string_file_id_coercion_func(self):
        fixture = _valid_session_fixture(file_ids=["f2"])
        mock_fc = MagicMock()
        mock_fc.process_chat_with_file.return_value = "Coerced file content"
        with patch.object(file_tools.chat_db, "get_chat_session_by_id", return_value=fixture), \
             patch.object(file_tools, "FileChatTool", return_value=mock_fc):
            res = search_files_tool.func(
                question="Search single file",
                file_ids="f2",
                config={"configurable": {"user_id": "u1", "chat_session_id": "s1"}},
            )
            self.assertEqual(res, "Coerced file content")
            mock_fc.process_chat_with_file.assert_called_with("Search single file", ["f2"], None)


if __name__ == "__main__":
    unittest.main()
