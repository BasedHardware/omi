"""Regression test for renaming a missing person.

PATCH /v1/users/people/{person_id}/name -> update_person did a bare Firestore .update(), which
raises NotFound on a missing/stale person id (e.g. after the idempotent DELETE removed it),
surfacing as HTTP 500. update_person now checks existence and returns False so the router can 404.
Pinned against a fake Firestore via patch.object on the db proxy, no live services.
"""

import os
from unittest.mock import MagicMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.users as users_db  # noqa: E402


def _person_ref(fake_db, exists):
    # db.collection('users').document(uid).collection('people').document(person_id)
    ref = fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value
    ref.get.return_value.exists = exists
    return ref


def test_update_person_missing_returns_false_without_updating():
    fake_db = MagicMock()
    ref = _person_ref(fake_db, exists=False)
    with patch.object(users_db, "db", fake_db):
        assert users_db.update_person("u1", "missing", "Alice") is False
    ref.update.assert_not_called()  # no .update() -> no NotFound -> no 500


def test_update_person_existing_updates_and_returns_true():
    fake_db = MagicMock()
    ref = _person_ref(fake_db, exists=True)
    with patch.object(users_db, "db", fake_db):
        assert users_db.update_person("u1", "p1", "Alice") is True
    ref.update.assert_called_once_with({"name": "Alice"})
