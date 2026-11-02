"""Regression test for completed_at preservation fixed in #21218.

A re-completion — duplicate tap, whole-object edit, or sync replay — used to
stamp a fresh ``completed_at`` on an already-completed row, moving "when the
task was done" every time. All three write paths now preserve the stored
timestamp: the plain ``update_action_item`` path, its transactional
``update_linked`` branch (goal/workstream links), and
``batch_sync_update_action_items``.
"""

import os
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import database.action_items as action_items_db

UID = "u1"
ITEM_ID = "item-1"
ORIGINAL = datetime(2026, 1, 1, tzinfo=timezone.utc)
REPLAY = datetime(2026, 10, 14, tzinfo=timezone.utc)


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
    """A duplicate completion keeps the original timestamp."""
    writes = _install_fake_db_existing(monkeypatch, True, ORIGINAL)

    action_items_db.update_action_item(UID, ITEM_ID, {"completed": True, "completed_at": REPLAY})

    assert writes[-1]["completed_at"] == ORIGINAL


def test_first_completion_stamps_now(monkeypatch):
    """A genuinely-new completion still gets the fresh timestamp."""
    writes = _install_fake_db_existing(monkeypatch, False, None)

    action_items_db.update_action_item(UID, ITEM_ID, {"completed": True, "completed_at": REPLAY})

    assert writes[-1]["completed_at"] == REPLAY


def test_update_linked_branch_preserves_completed_at(monkeypatch):
    """The goal/workstream transactional branch must preserve too — it reads
    the row inside the transaction, so the stored completed_at is available."""
    txn_writes = []
    snapshot = SimpleNamespace(
        exists=True,
        to_dict=lambda: {"completed": True, "completed_at": ORIGINAL, "goal_id": "g0"},
    )

    doc_ref = MagicMock()
    doc_ref.get.return_value = snapshot  # transaction=… get() lands here
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
    monkeypatch.setattr(action_items_db, "validate_task_relationship_in_transaction", lambda *a, **kw: None)
    monkeypatch.setattr(action_items_db, "_record_followup_completion", lambda *a: None)

    # Drive the real transactional body directly: firestore.transactional just
    # decorates the inner fn; calling update_action_item with goal_id routes
    # through run_with_transaction_contention_retry(db.transaction, update_linked).
    txn = MagicMock()
    txn.update.side_effect = lambda ref, data: txn_writes.append(data)
    monkeypatch.setattr(action_items_db, "run_with_transaction_contention_retry", lambda t, fn, **kw: fn(txn))

    action_items_db.update_action_item(UID, ITEM_ID, {"completed": True, "completed_at": REPLAY, "goal_id": "g0"})

    assert txn_writes and txn_writes[-1]["completed_at"] == ORIGINAL


def test_batch_sync_replay_preserves_completed_at(monkeypatch):
    """batch_sync_update_action_items is the sync-replay write path — a replay
    of an already-completed item must keep the stored completed_at."""
    writes = _install_fake_db_existing(monkeypatch, True, ORIGINAL)
    monkeypatch.setattr(action_items_db, "_record_followup_completion", lambda *a: None)

    action_items_db.batch_sync_update_action_items(
        UID, [{"id": ITEM_ID, "data": {"completed": True, "completed_at": REPLAY}}]
    )

    assert writes and writes[-1]["completed_at"] == ORIGINAL


def test_batch_sync_first_completion_stamps_now(monkeypatch):
    writes = _install_fake_db_existing(monkeypatch, False, None)
    monkeypatch.setattr(action_items_db, "_record_followup_completion", lambda *a: None)

    action_items_db.batch_sync_update_action_items(
        UID, [{"id": ITEM_ID, "data": {"completed": True, "completed_at": REPLAY}}]
    )

    assert writes and writes[-1]["completed_at"] == REPLAY


def test_batch_sync_missing_doc_reports_missing(monkeypatch):
    writes = _install_fake_db_existing(monkeypatch, True, ORIGINAL)
    # Flip the pre-read to a missing doc: replay on a deleted row stays missing.
    import database.action_items as mod

    doc_ref = mod.db.collection('users').document(UID).collection('action_items').document(ITEM_ID)
    doc_ref.get.return_value = SimpleNamespace(exists=False, to_dict=lambda: {})

    result = action_items_db.batch_sync_update_action_items(
        UID, [{"id": ITEM_ID, "data": {"completed": True, "completed_at": REPLAY}}]
    )

    assert result.missing_ids == [ITEM_ID]
    assert not writes
