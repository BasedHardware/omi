from datetime import datetime, timezone
import unittest

from pydantic import ValidationError

from models.chat_session import (
    ChatSessionResponse,
    DeleteMessagesResponse,
    GenerateTitleResponse,
    InitialMessageResponse,
    SaveMessageResponse,
)


class TestChatSessionModelValidation(unittest.TestCase):
    def test_chat_session_response_valid(self):
        now = datetime.now(timezone.utc)
        session = ChatSessionResponse(
            id="s1",
            title="Project Planning",
            created_at=now,
            updated_at=now,
            message_count=5,
            starred=True,
        )
        self.assertEqual(session.message_count, 5)

    def test_chat_session_response_negative_message_count_rejected(self):
        now = datetime.now(timezone.utc)
        with self.assertRaises(ValidationError):
            ChatSessionResponse(
                id="s1",
                title="Project Planning",
                created_at=now,
                updated_at=now,
                message_count=-1,
                starred=True,
            )

    def test_save_message_response_valid(self):
        resp = SaveMessageResponse(
            id="m1",
            created_at="2026-01-01T00:00:00Z",
            created=True,
            journal_revision=10,
        )
        self.assertEqual(resp.journal_revision, 10)

    def test_save_message_response_negative_journal_revision_rejected(self):
        with self.assertRaises(ValidationError):
            SaveMessageResponse(
                id="m1",
                created_at="2026-01-01T00:00:00Z",
                created=True,
                journal_revision=-1,
            )

    def test_delete_messages_response_valid(self):
        resp = DeleteMessagesResponse(status="ok", deleted_count=12)
        self.assertEqual(resp.deleted_count, 12)

    def test_delete_messages_response_negative_deleted_count_rejected(self):
        with self.assertRaises(ValidationError):
            DeleteMessagesResponse(status="ok", deleted_count=-1)

    def test_initial_message_response_empty_message_rejected(self):
        with self.assertRaises(ValidationError):
            InitialMessageResponse(message="", message_id="m1")

    def test_generate_title_response_empty_title_rejected(self):
        with self.assertRaises(ValidationError):
            GenerateTitleResponse(title="")


if __name__ == "__main__":
    unittest.main()
