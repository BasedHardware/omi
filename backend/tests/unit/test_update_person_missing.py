"""Regression: renaming a missing person returns False (so the router 404s), never a 500.

update_person now runs the existence check and the rename inside a storage-port transaction (WP2,
ADR-0002), so a missing or stale person id returns False atomically — there is no read-then-write
window and no backend exception to translate into a 404. Pinned hermetically against the in-memory
FakeDocumentStore; real-backend parity (Firestore emulator + Mongo replica set), including this
transactional path, is covered by tests/contract/test_users_people_contract.py.
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import database.users as users
from tests.store_fakes import FakeDocumentStore


def _bind(monkeypatch) -> FakeDocumentStore:
    store = FakeDocumentStore()
    monkeypatch.setattr(users, "_store", lambda: store)
    return store


def test_update_person_missing_returns_false(monkeypatch):
    _bind(monkeypatch)
    assert users.update_person("u1", "missing", "Alice") is False


def test_update_person_existing_updates_and_returns_true(monkeypatch):
    store = _bind(monkeypatch)
    users.create_person("u1", {"id": "p1", "name": "Old"})
    assert users.update_person("u1", "p1", "Alice") is True
    assert store.get("users/u1/people/p1").to_dict()["name"] == "Alice"
