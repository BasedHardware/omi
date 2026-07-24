"""Only deletion refuses a processor's write.

Lifecycle state does not: a discard is the system's own verdict that a
conversation held nothing, and a status records which generation ran. Fencing on
either stranded conversations a later sync had filled with speech — transcribed,
untitled, invisible to their owner, and beyond the in-app reprocess meant to
recover them, which hit the same fence — to prevent races never observed in
production.

Deletion is different in kind. It is a decision its owner made, and a merge
write to a missing document would create it.
"""

import os
from unittest.mock import MagicMock

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import database.conversations as conversations_db


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
    def set(self, ref, data, merge=False):
        ref.written = data

    def update(self, ref, data):
        ref.written = data


def _persist(monkeypatch, existing):
    ref = _Ref(_Snapshot(existing))

    fake_db = MagicMock()
    fake_db.collection.return_value.document.return_value = ref
    fake_db.transaction.return_value = _Transaction()

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
    )
    return persisted, ref


def test_a_discarded_conversation_can_be_rewritten(monkeypatch):
    persisted, ref = _persist(monkeypatch, {'discarded': True, 'status': 'processing'})

    assert persisted is True
    assert ref.written is not None, 'a sync that filled it with speech must be able to land'
    assert ref.written['discarded'] is False, 'the write carries the fresh verdict, which is what unhides it'


def test_a_deleted_conversation_is_not_recreated(monkeypatch):
    persisted, ref = _persist(monkeypatch, None)

    assert persisted is False
    assert ref.written is None


def test_a_dead_lettered_conversation_can_be_rewritten(monkeypatch):
    # A finalization that exhausted its attempts leaves the conversation failed
    # and discarded. Fencing on either state made that terminal, so a later sync
    # carrying the speech it was missing could never revive it.
    persisted, ref = _persist(monkeypatch, {'discarded': True, 'status': 'failed'})

    assert persisted is True
    assert ref.written is not None
