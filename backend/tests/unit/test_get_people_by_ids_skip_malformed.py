"""database.users.get_people_by_ids validates at the boundary so a malformed person doc is skipped.

Every caller builds [Person(**p) for p in get_people_by_ids(...)]. get_people_by_ids only setdefaults
the id field, while Person requires name, so one legacy or partially-written person doc missing name
raised ValidationError and 500'd the read (conversation list, trends, external integrations, chat
retrieval, ...). PR #9494 fixed one call site; this closes the class at the boundary: get_people_by_ids
now skips a Person-invalid doc (logging it) and returns only valid person dicts.

Migrated to the WP2 storage port (ADR-0002): the test injects a document store instead of stubbing
the raw Firestore client. The store is the real Mongo adapter over a mongomock client — hermetic (no
server), so the migrated code path is exercised end to end. The read boundary parses the neutral
StoredDocument (.exists/.to_dict()/.id) unchanged.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import mongomock

import database.users as users
from database.store.adapters.mongo import MongoDocumentStore


def _store_with(*people):
    store = MongoDocumentStore(client=mongomock.MongoClient(), db_name='test')
    for person_id, data in people:
        store.set(f'users/u1/people/{person_id}', data)
    return store


def test_get_people_by_ids_skips_malformed_and_keeps_valid(monkeypatch):
    store = _store_with(
        ('p1', {'id': 'p1', 'name': 'Alice'}),  # valid
        ('p2', {'id': 'p2'}),  # missing required name -> Person invalid -> skipped
        ('legacy', {'name': 'Bob'}),  # missing id -> id falls back to doc.id, then valid
    )
    monkeypatch.setattr(users, '_store', lambda: store)
    result = users.get_people_by_ids('u1', ['p1', 'p2', 'legacy'])
    assert sorted(p['id'] for p in result) == ['legacy', 'p1']  # malformed p2 skipped; legacy id filled


def test_get_people_by_ids_empty_returns_empty():
    assert users.get_people_by_ids('u1', []) == []
