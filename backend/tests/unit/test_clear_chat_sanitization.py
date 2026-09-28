"""Unit tests verifying exception sanitization in clear_chat and report_message.

Failure-Class: none
Ensures internal database exception messages (connection strings, paths, credentials)
are never returned directly in API responses.
"""

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.chat as chat_db


def test_clear_chat_success():
    fake_db = MagicMock()
    user_ref = fake_db.collection.return_value.document.return_value
    user_ref.get.return_value.exists = True

    with patch.object(chat_db, "db", fake_db), patch.object(chat_db, "batch_delete_messages") as mock_delete:
        result = chat_db.clear_chat(uid="test-user-1")
        assert result is None
        mock_delete.assert_called_once_with(user_ref, app_id=None, chat_session_id=None)


def test_clear_chat_user_not_found():
    fake_db = MagicMock()
    user_ref = fake_db.collection.return_value.document.return_value
    user_ref.get.return_value.exists = False

    with patch.object(chat_db, "db", fake_db):
        result = chat_db.clear_chat(uid="non-existent-user")
        assert result == {"message": "User not found"}


def test_clear_chat_exception_sanitized():
    fake_db = MagicMock()
    user_ref = fake_db.collection.return_value.document.return_value
    user_ref.get.return_value.exists = True

    with patch.object(chat_db, "db", fake_db), patch.object(
        chat_db, "batch_delete_messages", side_effect=RuntimeError("internal postgres/firestore secret at 10.0.0.1")
    ):
        result = chat_db.clear_chat(uid="test-user-2")
        assert result == {"message": "Failed to clear chat messages"}
        assert "10.0.0.1" not in str(result)
        assert "secret" not in str(result)


def test_report_message_success():
    fake_db = MagicMock()
    msg_ref = fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value

    with patch.object(chat_db, "db", fake_db):
        result = chat_db.report_message(uid="u1", msg_doc_id="msg1")
        assert result == {"message": "Message reported"}
        msg_ref.update.assert_called_once_with({"reported": True})


def test_report_message_exception_sanitized():
    fake_db = MagicMock()
    msg_ref = fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value
    msg_ref.update.side_effect = RuntimeError("sensitive internal cluster timeout at /users/u1/messages/msg1")

    with patch.object(chat_db, "db", fake_db):
        result = chat_db.report_message(uid="u1", msg_doc_id="msg1")
        assert result == {"message": "Update failed"}
        assert "sensitive" not in str(result)
        assert "/users/u1/messages/msg1" not in str(result)
