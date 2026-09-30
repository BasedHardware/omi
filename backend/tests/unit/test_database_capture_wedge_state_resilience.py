"""Hermetic unit tests for backend/database/capture_wedge_state.py resilience guards."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import pytest

from database.capture_wedge_state import (
    CAPTURE_WEDGE_STATE_COLLECTION,
    WEDGE_NUDGE_COOLDOWN,
    claim_wedge_first_seen,
    claim_wedge_nudge_cooldown,
)


class FakeSnapshot:
    def __init__(self, data: dict[str, Any] | None = None, exists: bool = True):
        self._data = data
        self.exists = exists

    def to_dict(self) -> dict[str, Any] | None:
        return self._data


class FakeDocRef:
    def __init__(self, path: str, store: dict[str, dict[str, Any]]):
        self.path = path
        self.store = store

    def get(self, transaction: Any = None) -> FakeSnapshot:
        if self.path in self.store:
            return FakeSnapshot(dict(self.store[self.path]), exists=True)
        return FakeSnapshot(None, exists=False)


class FakeCollection:
    def __init__(self, name: str, store: dict[str, dict[str, Any]]):
        self.name = name
        self.store = store

    def document(self, doc_id: str) -> FakeDocRef:
        return FakeDocRef(f"{self.name}/{doc_id}", self.store)


class FakeTransaction:
    def __init__(self, store: dict[str, dict[str, Any]]):
        self.store = store
        self.sets: list[tuple[FakeDocRef, dict[str, Any], bool]] = []

    def set(self, doc_ref: FakeDocRef, data: dict[str, Any], merge: bool = False):
        self.sets.append((doc_ref, data, merge))
        if merge and doc_ref.path in self.store:
            self.store[doc_ref.path].update(data)
        else:
            self.store[doc_ref.path] = dict(data)


class FakeFirestoreClient:
    def __init__(self):
        self.store: dict[str, dict[str, Any]] = {}

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(name, self.store)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self.store)


@pytest.fixture
def fake_client(monkeypatch):
    client = FakeFirestoreClient()
    # Mock firestore.transactional to immediately execute the decorated fn with the transaction
    def fake_transactional(fn):
        def wrapper(txn):
            return fn(txn)
        return wrapper

    monkeypatch.setattr("google.cloud.firestore.transactional", fake_transactional)
    return client


# --- Tests for claim_wedge_first_seen ---

@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, [], {}])
def test_claim_wedge_first_seen_rejects_invalid_uid(fake_client, invalid_uid):
    assert claim_wedge_first_seen(invalid_uid, "2026-09-30", firestore_client=fake_client) is False


@pytest.mark.parametrize("invalid_day", [None, "", "   ", 123, []])
def test_claim_wedge_first_seen_rejects_invalid_day(fake_client, invalid_day):
    assert claim_wedge_first_seen("user-1", invalid_day, firestore_client=fake_client) is False


def test_claim_wedge_first_seen_claims_new_slot(fake_client):
    now = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
    res = claim_wedge_first_seen("  user-1  ", "  2026-09-30  ", now=now, firestore_client=fake_client)
    assert res is True
    doc = fake_client.store.get(f"{CAPTURE_WEDGE_STATE_COLLECTION}/user-1")
    assert doc is not None
    assert doc["uid"] == "user-1"
    assert doc["first_seen_day"] == "2026-09-30"
    assert doc["updated_at"] == now


def test_claim_wedge_first_seen_normalizes_naive_datetime(fake_client):
    naive_now = datetime(2026, 9, 30, 10, 0, 0)
    res = claim_wedge_first_seen("user-1", "2026-09-30", now=naive_now, firestore_client=fake_client)
    assert res is True
    doc = fake_client.store.get(f"{CAPTURE_WEDGE_STATE_COLLECTION}/user-1")
    assert doc["updated_at"].tzinfo == timezone.utc


def test_claim_wedge_first_seen_rejects_duplicate_day(fake_client):
    now = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
    fake_client.store[f"{CAPTURE_WEDGE_STATE_COLLECTION}/user-1"] = {
        "uid": "user-1",
        "first_seen_day": "2026-09-30",
        "updated_at": now,
    }
    res = claim_wedge_first_seen("user-1", "2026-09-30", now=now, firestore_client=fake_client)
    assert res is False


def test_claim_wedge_first_seen_wins_new_day(fake_client):
    yesterday = datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc)
    today = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
    fake_client.store[f"{CAPTURE_WEDGE_STATE_COLLECTION}/user-1"] = {
        "uid": "user-1",
        "first_seen_day": "2026-09-29",
        "updated_at": yesterday,
    }
    res = claim_wedge_first_seen("user-1", "2026-09-30", now=today, firestore_client=fake_client)
    assert res is True
    doc = fake_client.store.get(f"{CAPTURE_WEDGE_STATE_COLLECTION}/user-1")
    assert doc["first_seen_day"] == "2026-09-30"
    assert doc["updated_at"] == today


# --- Tests for claim_wedge_nudge_cooldown ---

@pytest.mark.parametrize("invalid_uid", [None, "", "   ", 123, []])
def test_claim_wedge_nudge_cooldown_rejects_invalid_uid(fake_client, invalid_uid):
    assert claim_wedge_nudge_cooldown(invalid_uid, firestore_client=fake_client) is False


def test_claim_wedge_nudge_cooldown_wins_when_unseen(fake_client):
    now = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
    res = claim_wedge_nudge_cooldown("  user-1  ", now=now, firestore_client=fake_client)
    assert res is True
    doc = fake_client.store.get(f"{CAPTURE_WEDGE_STATE_COLLECTION}/user-1")
    assert doc["uid"] == "user-1"
    assert doc["last_nudge_at"] == now


def test_claim_wedge_nudge_cooldown_rejects_during_cooldown(fake_client):
    last_nudge = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 30, 14, 0, 0, tzinfo=timezone.utc)  # only 4 hours later
    fake_client.store[f"{CAPTURE_WEDGE_STATE_COLLECTION}/user-1"] = {
        "uid": "user-1",
        "last_nudge_at": last_nudge,
    }
    res = claim_wedge_nudge_cooldown("user-1", now=now, firestore_client=fake_client)
    assert res is False


def test_claim_wedge_nudge_cooldown_wins_after_cooldown_expires(fake_client):
    last_nudge = datetime(2026, 9, 29, 9, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)  # 25 hours later
    fake_client.store[f"{CAPTURE_WEDGE_STATE_COLLECTION}/user-1"] = {
        "uid": "user-1",
        "last_nudge_at": last_nudge,
    }
    res = claim_wedge_nudge_cooldown("user-1", now=now, firestore_client=fake_client)
    assert res is True
    doc = fake_client.store.get(f"{CAPTURE_WEDGE_STATE_COLLECTION}/user-1")
    assert doc["last_nudge_at"] == now


def test_claim_wedge_nudge_cooldown_prevents_timezone_type_error_with_naive_now(fake_client):
    # Aware stored timestamp, naive now passed in
    last_nudge = datetime(2026, 9, 29, 9, 0, 0, tzinfo=timezone.utc)
    naive_now = datetime(2026, 9, 30, 10, 0, 0)  # naive
    fake_client.store[f"{CAPTURE_WEDGE_STATE_COLLECTION}/user-1"] = {
        "uid": "user-1",
        "last_nudge_at": last_nudge,
    }
    # Must not raise TypeError: can't subtract offset-naive and offset-aware datetimes
    res = claim_wedge_nudge_cooldown("user-1", now=naive_now, firestore_client=fake_client)
    assert res is True


def test_claim_wedge_nudge_cooldown_prevents_timezone_type_error_with_naive_stored(fake_client):
    # Naive stored timestamp, aware now passed in
    naive_last_nudge = datetime(2026, 9, 29, 9, 0, 0)
    aware_now = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)
    fake_client.store[f"{CAPTURE_WEDGE_STATE_COLLECTION}/user-1"] = {
        "uid": "user-1",
        "last_nudge_at": naive_last_nudge,
    }
    res = claim_wedge_nudge_cooldown("user-1", now=aware_now, firestore_client=fake_client)
    assert res is True


def test_claim_wedge_nudge_cooldown_clamps_negative_cooldown(fake_client):
    last_nudge = datetime(2026, 9, 30, 9, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)  # 1 hour later
    fake_client.store[f"{CAPTURE_WEDGE_STATE_COLLECTION}/user-1"] = {
        "uid": "user-1",
        "last_nudge_at": last_nudge,
    }
    # Passing negative cooldown is clamped to 24h default, so 1 hr later is blocked
    res = claim_wedge_nudge_cooldown(
        "user-1",
        cooldown=timedelta(seconds=-10),
        now=now,
        firestore_client=fake_client,
    )
    assert res is False
