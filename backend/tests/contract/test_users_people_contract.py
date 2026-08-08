"""database.users people CRUD, proven on BOTH backends (WP2 rollout pilot, ADR-0002).

The migrated people functions are thin path-based wrappers over the storage port; this runs them
through the live Firestore emulator and a real Mongo replica set, asserting identical behavior — the
domain-level counterpart of test_document_store_contract. Injection is via the module ``_store``
seam (the WP2 analogue of the old ``users.db`` stub).

Live services required (skipped when absent): ``FIRESTORE_EMULATOR_HOST``, ``MONGO_URI``.
Not hermetic; lives in tests/contract/, not run by backend/test.sh.
"""

from __future__ import annotations

import os
import uuid

import pytest

import database.users as users


@pytest.fixture(params=["firestore", "mongo"])
def bind_store(request, monkeypatch):
    """Point database.users at each live adapter in turn via the _store seam."""
    backend = request.param
    if backend == "firestore":
        if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
            pytest.skip("FIRESTORE_EMULATOR_HOST not set")
        from database.store.adapters.firestore import FirestoreDocumentStore

        store = FirestoreDocumentStore()
    else:
        uri = os.environ.get("MONGO_URI")
        if not uri:
            pytest.skip("MONGO_URI not set")
        from database.store.adapters.mongo import MongoDocumentStore

        store = MongoDocumentStore(uri=uri, db_name="omi_contract")
    monkeypatch.setattr(users, "_store", lambda: store)
    return store


@pytest.fixture
def uid() -> str:
    return f"u_{uuid.uuid4().hex}"


def test_create_get_delete(bind_store, uid):
    assert users.get_person(uid, "p1") is None
    users.create_person(uid, {"id": "p1", "name": "Alice"})
    assert users.get_person(uid, "p1") == {"id": "p1", "name": "Alice"}
    users.delete_person(uid, "p1")
    assert users.get_person(uid, "p1") is None


def test_get_people_scoped_and_by_name(bind_store, uid):
    other = f"u_{uuid.uuid4().hex}"
    users.create_person(uid, {"id": "p1", "name": "Alice"})
    users.create_person(uid, {"id": "p2", "name": "Bob"})
    users.create_person(other, {"id": "p9", "name": "Intruder"})  # different user, must not leak

    assert sorted(p["name"] for p in users.get_people(uid)) == ["Alice", "Bob"]
    assert users.get_person_by_name(uid, "Bob")["id"] == "p2"
    assert users.get_person_by_name(uid, "Nobody") is None


def test_get_people_by_ids_skips_missing_and_fills_id(bind_store, uid):
    users.create_person(uid, {"id": "p1", "name": "Alice"})
    users.create_person(uid, {"id": "legacy", "name": "Bob"})
    result = users.get_people_by_ids(uid, ["p1", "missing", "legacy"])
    assert sorted(p["id"] for p in result) == ["legacy", "p1"]


def test_update_person_is_transactional(bind_store, uid):
    users.create_person(uid, {"id": "p1", "name": "Alice"})
    assert users.update_person(uid, "p1", "Alicia") is True
    assert users.get_person(uid, "p1")["name"] == "Alicia"
    # Missing person -> False (atomic existence check inside the transaction), never a raised error.
    assert users.update_person(uid, "missing", "X") is False
