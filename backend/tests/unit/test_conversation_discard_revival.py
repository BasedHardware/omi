"""A discard is reconsidered by reprocessing and by nothing else.

A conversation discarded while it held nothing, then filled with speech by a
later sync, is revived by reprocessing it. Fencing that left the recording
transcribed, untitled, and invisible to its owner with no path back, because the
in-app reprocess reached the same fence. These pin the reopening to reprocessing
alone, so an ordinary finalizer still cannot overwrite a discard it never
inspected.
"""

import os
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import database.conversations as conversations_db
import utils.conversations.lifecycle as lifecycle_service


class _Snapshot:
    def __init__(self, data):
        self.exists = data is not None
        self._data = data

    def to_dict(self):
        return self._data


class _Ref:
    def __init__(self, snapshot):
        self._snapshot = snapshot
        self.written = None

    def get(self, transaction=None):
        return self._snapshot

    def collection(self, _name):
        return self

    def document(self, _name):
        return self


class _Transaction:
    def __init__(self, ref):
        self._ref = ref

    def set(self, ref, data, merge=False):
        ref.written = data

    def update(self, ref, data):
        ref.written = data


def _run(monkeypatch, existing, *, revive_discarded):
    ref = _Ref(_Snapshot(existing))
    transaction = _Transaction(ref)

    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value = ref
    fake_db.transaction.return_value = transaction

    monkeypatch.setattr(conversations_db, 'db', fake_db)
    monkeypatch.setattr(conversations_db.firestore, 'transactional', lambda fn: fn)

    persisted = conversations_db.persist_processing_result_with_lifecycle(
        'uid-1',
        {
            'id': 'conv-1',
            'status': 'completed',
            'discarded': False,
            'structured': {'title': 'Recovered'},
            # Present so the protection-level decorator skips its user lookup.
            'data_protection_level': 'standard',
        },
        expected_statuses={'processing', 'merging', 'completed'},
        revive_discarded=revive_discarded,
    )
    return persisted, ref


def test_reprocessing_revives_a_discarded_conversation(monkeypatch):
    existing = {'discarded': True, 'status': 'processing'}

    persisted, ref = _run(monkeypatch, existing, revive_discarded=True)

    assert persisted is True
    assert ref.written is not None, 'a revival must reach the document'
    assert ref.written['discarded'] is False, 'the write is what makes it visible again'


def test_a_run_that_is_not_reprocessing_stays_fenced(monkeypatch):
    existing = {'discarded': True, 'status': 'processing'}

    persisted, ref = _run(monkeypatch, existing, revive_discarded=False)

    assert persisted is False
    assert ref.written is None, 'a discard an ordinary finalizer never inspected must survive'


def test_revival_does_not_reopen_a_stale_generation(monkeypatch):
    # Reconsidering a discard is not licence to overwrite a generation that
    # already moved on; the status guard is independent of the discard guard.
    existing = {'discarded': True, 'status': 'failed'}

    persisted, ref = _run(monkeypatch, existing, revive_discarded=True)

    assert persisted is False
    assert ref.written is None


def test_revival_does_not_recreate_a_deleted_conversation(monkeypatch):
    persisted, ref = _run(monkeypatch, None, revive_discarded=True)

    assert persisted is False
    assert ref.written is None


@pytest.mark.parametrize('revive_discarded', [True, False])
def test_lifecycle_forwards_the_reprocess_intent(monkeypatch, revive_discarded):
    captured = {}

    def _capture(uid, conversation_data, *, expected_statuses, revive_discarded=False):
        captured['revive_discarded'] = revive_discarded
        return True

    monkeypatch.setattr(conversations_db, 'persist_processing_result_with_lifecycle', _capture)
    monkeypatch.setattr(lifecycle_service.conversations_db, 'persist_processing_result_with_lifecycle', _capture)

    lifecycle_service.persist_processed_conversation(
        'uid-1',
        {'id': 'conv-1', 'status': 'completed'},
        revive_discarded=revive_discarded,
    )

    assert captured['revive_discarded'] is revive_discarded
