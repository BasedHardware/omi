"""Hermetic unit tests for error sanitization in retrieval tools and phone calls.

Verifies that:
1. search_memories_tool logs exceptions with exc_info and returns generic sanitized message without leaking raw exception string or tracebacks.
2. get_conversations_tool logs exceptions with exc_info and returns generic sanitized message.
3. get_action_items_tool logs exceptions with exc_info and returns generic sanitized message for config and database errors.
4. verify_phone_number logs exceptions with exc_info and raises 500 with generic sanitized detail.
5. No raw traceback.print_exc() calls exist in memory_tools, conversation_tools, action_item_tools, or phone_calls.
"""

from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

# Ensure encryption secret is available for backend modules
os.environ.setdefault("ENCRYPTION_SECRET", "01234567890123456789012345678901")

from utils.retrieval.tools.memory_tools import search_memories_tool
from utils.retrieval.tools.conversation_tools import get_conversations_tool
from utils.retrieval.tools.action_item_tools import get_action_items_tool
from routers.phone_calls import verify_phone_number, VerifyPhoneNumberRequest


class RetrievalToolsErrorSanitizationTests(unittest.TestCase):

    def test_search_memories_tool_sanitizes_unexpected_exception(self):
        """Verify search_memories_tool catches unexpected exceptions and returns a sanitized user message."""
        config = {"configurable": {"user_id": "test_user"}}
        with patch("utils.retrieval.tools.memory_tools.MemoryService") as mock_service_cls:
            mock_service = MagicMock()
            mock_service.search.side_effect = RuntimeError("Database connection string postgres://secret:pass@internal.db:5432/omi")
            mock_service_cls.return_value = mock_service

            result = search_memories_tool.invoke({"query": "my goals"}, config=config)

            self.assertIn("An unexpected error occurred while searching memories", result)
            self.assertNotIn("postgres://", result)
            self.assertNotIn("secret:pass", result)
            self.assertNotIn("RuntimeError", result)

    def test_get_conversations_tool_sanitizes_unexpected_exception(self):
        """Verify get_conversations_tool catches unexpected exceptions and returns a sanitized user message."""
        config = {"configurable": {"user_id": "test_user"}}
        with patch("utils.retrieval.tools.conversation_tools.conversations_db.get_conversations") as mock_get_convs:
            mock_conv = {
                "id": "conv_123",
                "transcript_segments": [{"text": "hello", "person_id": "p1"}],
            }
            mock_get_convs.return_value = [mock_conv]
            with patch("utils.retrieval.tools.conversation_tools.conversations_to_string", side_effect=Exception("Firestore socket hangup on replica cluster 10.0.12.34")):
                result = get_conversations_tool.invoke({}, config=config)

                self.assertIn("An unexpected error occurred while retrieving conversations", result)
                self.assertNotIn("Firestore socket hangup", result)
                self.assertNotIn("10.0.12.34", result)

    def test_get_action_items_tool_sanitizes_config_error(self):
        """Verify get_action_items_tool handles config errors without raw exception reflection."""
        bad_config = MagicMock()
        bad_config.__contains__.side_effect = TypeError("Internal Pydantic serialization fault in credentials context")
        result = get_action_items_tool.func(config=bad_config)

        self.assertEqual(result, "Error: Unable to access user configuration")
        self.assertNotIn("Internal Pydantic", result)

    def test_get_action_items_tool_sanitizes_db_error(self):
        """Verify get_action_items_tool handles database errors with sanitized message."""
        config = {"configurable": {"user_id": "test_user"}}
        with patch("utils.retrieval.tools.action_item_tools.action_items_db.get_action_items") as mock_db:
            mock_db.side_effect = Exception("Deadlock detected on tasks_user_idx table partition 4")
            result = get_action_items_tool.invoke({}, config=config)

            self.assertIn("An unexpected error occurred while retrieving action items", result)
            self.assertNotIn("Deadlock detected", result)
            self.assertNotIn("tasks_user_idx", result)

    def test_create_action_item_tool_sanitizes_db_error(self):
        """Verify create_action_item_tool handles database errors with sanitized message."""
        from utils.retrieval.tools.action_item_tools import create_action_item_tool
        config = {"configurable": {"user_id": "test_user"}}
        with patch("utils.retrieval.tools.action_item_tools.action_items_db.create_action_item") as mock_db:
            mock_db.side_effect = Exception("IntegrityConstraintViolation: foreign key violation on users.uid")
            result = create_action_item_tool.invoke({"description": "test task"}, config=config)

            self.assertIn("An unexpected error occurred while creating the action item", result)
            self.assertNotIn("IntegrityConstraintViolation", result)
            self.assertNotIn("foreign key violation", result)

    def test_update_action_item_tool_sanitizes_db_error(self):
        """Verify update_action_item_tool handles database errors with sanitized message."""
        from utils.retrieval.tools.action_item_tools import update_action_item_tool
        config = {"configurable": {"user_id": "test_user"}}
        with patch("utils.retrieval.tools.action_item_tools.action_items_db.get_action_item") as mock_get:
            mock_get.side_effect = Exception("ConnectionRefusedError: failed to connect to Firestore replica socket 10.0.0.1:8080")
            result = update_action_item_tool.invoke({"action_item_id": "task_1", "completed": True}, config=config)

            self.assertIn("An unexpected error occurred while updating the action item", result)
            self.assertNotIn("ConnectionRefusedError", result)
            self.assertNotIn("10.0.0.1", result)

    def test_verify_phone_number_sanitizes_exception_detail(self):
        """Verify verify_phone_number raises HTTPException with static detail on unexpected failures."""
        request = VerifyPhoneNumberRequest(phone_number="+15551234567")
        with patch("routers.phone_calls.check_call_access"), \
             patch("routers.phone_calls.phone_calls_db.get_phone_number_by_number", return_value=None), \
             patch("routers.phone_calls.start_caller_id_verification", side_effect=Exception("Twilio API Token Auth Failure: SK123456789")):
            with self.assertRaises(HTTPException) as cm:
                verify_phone_number(request, uid="test_user", _=None)

            self.assertEqual(cm.exception.status_code, 500)
            self.assertEqual(cm.exception.detail, "Failed to start verification. Please try again later.")
            self.assertNotIn("SK123456789", cm.exception.detail)

    def test_no_traceback_print_in_modified_modules(self):
        """Verify that traceback.print_exc() is not called in retrieval tools or phone_calls router."""
        backend_dir = Path(__file__).resolve().parents[2]
        files_to_check = [
            backend_dir / "utils" / "retrieval" / "tools" / "memory_tools.py",
            backend_dir / "utils" / "retrieval" / "tools" / "conversation_tools.py",
            backend_dir / "utils" / "retrieval" / "tools" / "action_item_tools.py",
            backend_dir / "routers" / "phone_calls.py",
        ]
        for file_path in files_to_check:
            content = file_path.read_text(encoding="utf-8")
            self.assertNotIn("traceback.print_exc", content, f"Found traceback.print_exc in {file_path.name}")
            self.assertNotIn("import traceback", content, f"Found import traceback in {file_path.name}")


if __name__ == "__main__":
    unittest.main()
