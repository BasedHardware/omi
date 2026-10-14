"""Regression test for the pending-sync starvation fixed in #21214.

A task exported through the single-item ``PATCH /v1/action-items/{id}`` route
went through ``update_action_item``, which never cleared ``sync_requested``.
Every device export left the flag set; once 50 settled rows led the
sync_requested==True limit-50 query, genuinely pending tasks starved with no
error. The route now clears ``sync_requested`` whenever ``exported`` becomes
True — matching ``batch_sync_update_action_items``.
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import database.action_items as action_items_db


UID = "u1"
ITEM_ID = "item-1"


def _install_fake_db(monkeypatch):
    """Capture the update payload the single-item route writes."""
    writes = []

    doc_ref = MagicMock()
    doc_ref.get.return_value = SimpleNamespace(exists=True, to_dict=lambda: {})
    doc_ref.update.side_effect = lambda data: writes.append(data)

    items_collection = MagicMock()
    items_collection.document.return_value = doc_ref

    user_doc = MagicMock()
    user_doc.collection.return_value = items_collection
    users = MagicMock()
    users.document.return_value = user_doc

    fake_db = MagicMock()
    fake_db.collection.return_value = users

    monkeypatch.setattr(action_items_db, "db", fake_db)
    monkeypatch.setattr(action_items_db, "bump_action_items_list_version", lambda uid: None)
    return writes


def test_export_clears_sync_requested(monkeypatch):
    writes = _install_fake_db(monkeypatch)

    action_items_db.update_action_item(
        UID,
        ITEM_ID,
        {"exported": True, "export_platform": "apple_reminders", "apple_reminder_id": "r1"},
    )

    assert writes, "update_action_item should issue a doc update"
    assert writes[-1]["exported"] is True
    assert writes[-1]["sync_requested"] is False


def test_non_export_update_leaves_sync_requested_alone(monkeypatch):
    writes = _install_fake_db(monkeypatch)

    action_items_db.update_action_item(UID, ITEM_ID, {"description": "x"})

    assert "sync_requested" not in writes[-1]


def _install_fake_db_existing(monkeypatch, existing_completed, existing_completed_at):
    """Fake db whose doc already holds completed/completed_at."""
    writes = []

    doc_ref = MagicMock()
    doc_ref.get.return_value = SimpleNamespace(
        exists=True,
        to_dict=lambda: {"completed": existing_completed, "completed_at": existing_completed_at},
    )
    doc_ref.update.side_effect = lambda data: writes.append(data)

    items_collection = MagicMock()
    items_collection.document.return_value = doc_ref
    user_doc = MagicMock()
    user_doc.collection.return_value = items_collection
    users = MagicMock()
    users.document.return_value = user_doc
    fake_db = MagicMock()
    fake_db.collection.return_value = users

    monkeypatch.setattr(action_items_db, "db", fake_db)
    monkeypatch.setattr(action_items_db, "bump_action_items_list_version", lambda uid: None)
    return writes


def test_recompleting_preserves_completed_at(monkeypatch):
    """#21218 — a duplicate completion keeps the original timestamp."""
    from datetime import datetime, timezone

    original = datetime(2026, 1, 1, tzinfo=timezone.utc)
    replay = datetime(2026, 10, 14, tzinfo=timezone.utc)
    writes = _install_fake_db_existing(monkeypatch, True, original)

    action_items_db.update_action_item(UID, ITEM_ID, {"completed": True, "completed_at": replay})

    assert writes[-1]["completed_at"] == original


def test_first_completion_stamps_now(monkeypatch):
    """A genuinely-new completion still gets the fresh timestamp."""
    from datetime import datetime, timezone

    replay = datetime(2026, 10, 14, tzinfo=timezone.utc)
    writes = _install_fake_db_existing(monkeypatch, False, None)

    action_items_db.update_action_item(UID, ITEM_ID, {"completed": True, "completed_at": replay})

    assert writes[-1]["completed_at"] == replay
