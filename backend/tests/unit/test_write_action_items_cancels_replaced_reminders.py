"""Reprocessing a conversation replaces its tasks; the replaced rows' reminders must go.

`_write_action_items` deletes every task the conversation wrote before, creates the
new extraction (under fresh ids, scheduling a reminder for each dated one), but never
cancelled the replaced rows. The mobile client only cancels a scheduled reminder on
the backend's deletion data message, so after a reprocess the user kept the old
reminders: duplicates for the tasks that survived re-extraction, and stale reminders
for tasks the new extraction dropped.

Same class as #15041 (conversation delete), #15043 (developer API delete), #14983/#14984
(checking a task off inside a conversation) and #15028/#15029 (MCP task writes).
"""

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from utils.conversations import process_conversation

DUE = datetime(2026, 9, 21, 9, tzinfo=timezone.utc)


def _extracted_item(description="Send the budget"):
    return SimpleNamespace(
        description=description,
        completed=False,
        created_at=None,
        updated_at=None,
        due_at=DUE,
        completed_at=None,
    )


def _conversation():
    return SimpleNamespace(
        id="conv-1",
        is_locked=False,
        structured=SimpleNamespace(action_items=[_extracted_item()]),
    )


@pytest.fixture
def writer(monkeypatch):
    """Run the real replacement writer with every I/O seam recorded."""
    monkeypatch.setattr(process_conversation.conversation_capture, "canonical_conversation_fields", lambda *a, **k: {})
    monkeypatch.setattr(process_conversation, "delete_action_item_vectors_batch", MagicMock())
    monkeypatch.setattr(process_conversation, "upsert_action_item_vectors_batch", MagicMock())
    monkeypatch.setattr(process_conversation, "emit_product_event", MagicMock())
    monkeypatch.setattr(process_conversation, "send_action_item_data_message", MagicMock())
    monkeypatch.setattr(process_conversation, "submit_with_context", MagicMock())
    monkeypatch.setattr(process_conversation, "sync_action_item_reminder", MagicMock(), raising=False)
    monkeypatch.setattr(
        process_conversation.action_items_db, "create_action_items_batch", lambda uid, data: ["new-task"][: len(data)]
    )
    monkeypatch.setattr(process_conversation.action_items_db, "delete_action_items_for_conversation", MagicMock())
    return process_conversation


def _write(monkeypatch, writer, old_items):
    monkeypatch.setattr(writer.action_items_db, "get_action_items_by_conversation", lambda uid, cid: list(old_items))
    writer._write_action_items("uid-1", _conversation())


def test_replacing_a_conversation_task_cancels_the_replaced_reminder(monkeypatch, writer):
    _write(
        monkeypatch,
        writer,
        [
            {"id": "old-open", "description": "Send the budget", "due_at": DUE, "completed": False},
            {"id": "old-done", "description": "Already handled", "due_at": DUE, "completed": True},
            {"id": "old-undated", "description": "No deadline", "due_at": None, "completed": False},
        ],
    )

    writer.sync_action_item_reminder.assert_called_once_with(
        user_id="uid-1", action_item_id="old-open", description="", completed=True, due_at=None
    )


def test_a_first_processing_with_no_previous_tasks_cancels_nothing(monkeypatch, writer):
    _write(monkeypatch, writer, [])

    writer.sync_action_item_reminder.assert_not_called()


def test_a_failing_reminder_cancel_does_not_skip_the_new_tasks(monkeypatch, writer):
    """The old rows are already deleted at this point; the new extraction must still be written."""
    writer.sync_action_item_reminder.side_effect = RuntimeError("fcm unavailable")
    create = MagicMock(return_value=["new-task"])
    monkeypatch.setattr(writer.action_items_db, "create_action_items_batch", create)

    _write(
        monkeypatch,
        writer,
        [{"id": "old-open", "description": "Send the budget", "due_at": DUE, "completed": False}],
    )

    create.assert_called_once()
