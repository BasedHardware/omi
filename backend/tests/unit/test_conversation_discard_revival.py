"""A discard is the system's verdict about content, not a state to defend.

``discarded`` is set only by the system deciding a conversation held nothing —
there is no endpoint through which a user discards one; users delete, which is a
separate field. Every processor re-derives that verdict from the content in
front of it, so a write cannot resurrect something still empty.

Fencing writes on it stranded conversations a later sync had filled with speech:
transcribed, untitled, invisible to their owner, and beyond the reach of the
in-app reprocess that exists to recover them, because it hit the same fence.

The guards that remain are about generations, not verdicts.
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
        expected_statuses={'processing', 'merging', 'completed'},
    )
    return persisted, ref


def test_a_discarded_conversation_can_be_rewritten(monkeypatch):
    persisted, ref = _persist(monkeypatch, {'discarded': True, 'status': 'processing'})

    assert persisted is True
    assert ref.written is not None, 'a sync that filled it with speech must be able to land'
    assert ref.written['discarded'] is False, 'the write carries the fresh verdict, which is what unhides it'


def test_a_stale_generation_is_still_fenced(monkeypatch):
    # The status guard is what fences a stale processor, and it is untouched:
    # a generation that already reached a terminal state stays owned by it.
    persisted, ref = _persist(monkeypatch, {'discarded': False, 'status': 'failed'})

    assert persisted is False
    assert ref.written is None


def test_a_stale_generation_is_fenced_even_when_discarded(monkeypatch):
    persisted, ref = _persist(monkeypatch, {'discarded': True, 'status': 'failed'})

    assert persisted is False
    assert ref.written is None


def test_a_deleted_conversation_is_not_recreated(monkeypatch):
    persisted, ref = _persist(monkeypatch, None)

    assert persisted is False
    assert ref.written is None
