"""Only deletion refuses a processor's write.

Lifecycle state does not: a discard is the system's own verdict that a conversation held nothing,
and a status records which generation ran. Deletion is different in kind — a merge write to a
missing document would recreate what the owner removed. Migrated to the WP2 storage port: the test
injects a FakeDocumentStore and drives persist_processing_result_with_lifecycle through the neutral
transaction seam.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import database.conversations as conversations_db
from tests.store_fakes import FakeDocumentStore

CONV = 'users/uid-1/conversations/conv-1'


def _persist(monkeypatch, existing):
    store = FakeDocumentStore()
    if existing is not None:
        store.set(CONV, existing)
    monkeypatch.setattr(conversations_db, '_store', lambda: store)

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
    written = store.get(CONV).to_dict() if store.exists(CONV) else None
    return persisted, written


def test_a_discarded_conversation_can_be_rewritten(monkeypatch):
    persisted, written = _persist(monkeypatch, {'discarded': True, 'status': 'processing'})

    assert persisted is True
    assert written is not None, 'a sync that filled it with speech must be able to land'
    assert written['discarded'] is False, 'the write carries the fresh verdict, which is what unhides it'


def test_a_deleted_conversation_is_not_recreated(monkeypatch):
    persisted, written = _persist(monkeypatch, None)

    assert persisted is False
    assert written is None


def test_a_dead_lettered_conversation_can_be_rewritten(monkeypatch):
    # A finalization that exhausted its attempts leaves the conversation failed and discarded.
    # Fencing on either state made that terminal, so a later sync carrying the speech it was
    # missing could never revive it.
    persisted, written = _persist(monkeypatch, {'discarded': True, 'status': 'failed'})

    assert persisted is True
    assert written is not None
