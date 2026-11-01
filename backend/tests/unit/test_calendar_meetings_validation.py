"""#19757 — create_meeting validates meeting_data keys and retries transactions.

Before the fix a payload missing calendar_source/calendar_event_id raised a
bare KeyError (before any validation), and a plain db.transaction() abandoned
the write on Firestore Aborted contention. Now: ValueError at the boundary +
bounded contention retry.
"""

import os
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest

import database.calendar_meetings as meetings_db


def _fake_db(exists=False):
    written = []
    doc_ref = MagicMock()
    doc_ref.get.return_value = SimpleNamespace(exists=exists, to_dict=lambda: {})
    meetings_coll = MagicMock()
    meetings_coll.document.return_value = doc_ref
    user_ref = MagicMock()
    user_ref.collection.return_value = meetings_coll
    db = MagicMock()
    db.collection.return_value.document.return_value = user_ref
    txn = MagicMock()
    txn.set.side_effect = lambda *a, **kw: written.append((a, kw))
    db.transaction.return_value = txn
    return db, txn, written


def test_missing_calendar_source_raises_valueerror():
    db, _, _ = _fake_db()
    meetings_db.db = db
    with pytest.raises(ValueError, match='calendar_source'):
        meetings_db.create_meeting('u1', {'calendar_event_id': 'e1'})


def test_missing_event_id_raises_valueerror():
    db, _, _ = _fake_db()
    meetings_db.db = db
    with pytest.raises(ValueError, match='calendar_event_id'):
        meetings_db.create_meeting('u1', {'calendar_source': 'google'})


def test_create_writes_via_bounded_retry_helper(monkeypatch):
    db, txn, written = _fake_db()
    meetings_db.db = db
    used = {}
    monkeypatch.setattr(
        meetings_db,
        'run_with_transaction_contention_retry',
        lambda factory, op, *, operation_name: (used.__setitem__('name', operation_name), op(txn))[1],
    )
    meeting_id = meetings_db.create_meeting(
        'u1', {'calendar_source': 'google', 'calendar_event_id': 'evt-7', 'title': 'Sync'}
    )
    assert isinstance(meeting_id, str) and meeting_id
    assert used['name'] == 'calendar_meeting_create'
    assert written, 'the upsert ran inside the transaction'


def test_existing_doc_keeps_created_at(monkeypatch):
    db, txn, written = _fake_db(exists=True)
    meetings_db.db = db
    monkeypatch.setattr(
        meetings_db,
        'run_with_transaction_contention_retry',
        lambda factory, op, *, operation_name: op(txn),
    )
    meetings_db.create_meeting('u1', {'calendar_source': 'google', 'calendar_event_id': 'e1'})
    args, kwargs = written[0]
    assert 'created_at' not in args[1]  # merge-preserve: no first-created overwrite
    assert 'synced_at' in args[1]
