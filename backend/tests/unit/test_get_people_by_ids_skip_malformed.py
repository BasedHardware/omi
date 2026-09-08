"""database.users.get_people_by_ids validates at the boundary so a malformed person doc is skipped.

Every caller builds [Person(**p) for p in get_people_by_ids(...)]. get_people_by_ids only setdefaults
the id field, while Person requires name, so one legacy or partially-written person doc missing name
raised ValidationError and 500'd the read (conversation list, trends, external integrations, chat
retrieval, ...). PR #9494 fixed one call site; this closes the class at the boundary: get_people_by_ids
now skips a Person-invalid doc (logging it) and returns only valid person dicts.
"""

import os

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

from unittest.mock import MagicMock

import database.users as users


def _doc(doc_id, data):
    d = MagicMock()
    d.exists = True
    d.id = doc_id
    d.to_dict.return_value = data
    return d


def _patch_db(monkeypatch, docs):
    fake = MagicMock()
    for attr in ('collection', 'document'):
        getattr(fake, attr).return_value = fake
    fake.get_all.return_value = docs
    monkeypatch.setattr(users, 'db', fake)


def test_get_people_by_ids_skips_malformed_and_keeps_valid(monkeypatch):
    _patch_db(
        monkeypatch,
        [
            _doc('p1', {'id': 'p1', 'name': 'Alice'}),  # valid
            _doc('p2', {'id': 'p2'}),  # missing required name -> Person invalid -> skipped
            _doc('legacy', {'name': 'Bob'}),  # missing id -> id falls back to doc.id, then valid
        ],
    )
    result = users.get_people_by_ids('u1', ['p1', 'p2', 'legacy'])
    assert sorted(p['id'] for p in result) == ['legacy', 'p1']  # malformed p2 skipped; legacy id filled


def test_get_people_by_ids_empty_returns_empty(monkeypatch):
    assert users.get_people_by_ids('u1', []) == []
