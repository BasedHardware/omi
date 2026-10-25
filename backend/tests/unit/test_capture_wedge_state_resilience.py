from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import database.capture_wedge_state as wedge_state
from database.capture_wedge_state import (
    CAPTURE_WEDGE_STATE_COLLECTION,
    WEDGE_NUDGE_COOLDOWN,
    _clean_day,
    _clean_id,
    _ensure_utc,
    claim_wedge_first_seen,
    claim_wedge_nudge_cooldown,
    get_wedge_state,
    reset_wedge_state,
)


class FakeSnapshot:
    def __init__(self, data: dict[str, Any] | None):
        self._data = data

    @property
    def exists(self) -> bool:
        return self._data is not None

    def to_dict(self) -> dict[str, Any] | None:
        if self._data is None:
            return None
        return dict(self._data)


class FakeDocRef:
    def __init__(self, path: str, store: dict[str, dict[str, Any]]):
        self.path = path
        self.store = store

    def get(self, transaction: Any = None) -> FakeSnapshot:
        return FakeSnapshot(self.store.get(self.path))

    def set(self, data: dict[str, Any], merge: bool = False) -> None:
        if merge and self.path in self.store:
            self.store[self.path].update(data)
        else:
            self.store[self.path] = dict(data)

    def delete(self) -> None:
        self.store.pop(self.path, None)


class FakeCollection:
    def __init__(self, name: str, store: dict[str, dict[str, Any]]):
        self.name = name
        self.store = store

    def document(self, doc_id: str) -> FakeDocRef:
        return FakeDocRef(f"{self.name}/{doc_id}", self.store)


class FakeTransaction:
    def __init__(self, store: dict[str, dict[str, Any]]):
        self.store = store

    def set(self, doc_ref: FakeDocRef, data: dict[str, Any], merge: bool = False) -> None:
        doc_ref.set(data, merge=merge)


class FakeFirestoreClient:
    def __init__(self):
        self.store: dict[str, dict[str, Any]] = {}

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(name, self.store)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self.store)


@pytest.fixture
def fake_client(monkeypatch):
    monkeypatch.setattr(wedge_state.firestore, 'transactional', lambda fn: fn)
    return FakeFirestoreClient()


def test_clean_id_and_day_helpers():
    assert _clean_id("user_123") == "user_123"
    assert _clean_id("  padded_user  ") == "padded_user"
    assert _clean_id("") is None
    assert _clean_id("   ") is None
    assert _clean_id(None) is None
    assert _clean_id(12345) is None
    assert _clean_id("a" * 129) is None
    assert _clean_id("../traversal") is None
    assert _clean_id("users/123") is None
    assert _clean_id("users\\123") is None
    assert _clean_id("null\x00byte") is None

    assert _clean_day("2026-10-25") == "2026-10-25"
    assert _clean_day("  2026-10-25  ") == "2026-10-25"
    assert _clean_day("") is None
    assert _clean_day("a" * 33) is None
    assert _clean_day("2026/10/25") is None
    assert _clean_day(None) is None


def test_ensure_utc_helper():
    now_res = _ensure_utc(None)
    assert now_res.tzinfo == timezone.utc

    naive = datetime(2026, 10, 25, 12, 0, 0)
    utc_dt = _ensure_utc(naive)
    assert utc_dt.tzinfo == timezone.utc
    assert utc_dt.year == 2026 and utc_dt.hour == 12

    offset_tz = timezone(timedelta(hours=2))
    aware = datetime(2026, 10, 25, 14, 0, 0, tzinfo=offset_tz)
    converted = _ensure_utc(aware)
    assert converted.tzinfo == timezone.utc
    assert converted.hour == 12


def test_claim_wedge_first_seen_winner_and_loser(fake_client):
    uid = "test-user-1"
    day = "2026-10-25"

    # First claim succeeds
    assert claim_wedge_first_seen(uid, day, firestore_client=fake_client) is True

    # Second claim for same day fails (winner took slot)
    assert claim_wedge_first_seen(uid, day, firestore_client=fake_client) is False

    # State was recorded
    state = get_wedge_state(uid, firestore_client=fake_client)
    assert state is not None
    assert state["uid"] == uid
    assert state["first_seen_day"] == day


def test_claim_wedge_first_seen_different_day(fake_client):
    uid = "test-user-2"
    day1 = "2026-10-25"
    day2 = "2026-10-26"

    assert claim_wedge_first_seen(uid, day1, firestore_client=fake_client) is True
    assert claim_wedge_first_seen(uid, day1, firestore_client=fake_client) is False

    # Rollover to day 2 succeeds
    assert claim_wedge_first_seen(uid, day2, firestore_client=fake_client) is True
    state = get_wedge_state(uid, firestore_client=fake_client)
    assert state["first_seen_day"] == day2


def test_claim_wedge_first_seen_invalid_inputs(fake_client):
    assert claim_wedge_first_seen("", "2026-10-25", firestore_client=fake_client) is False
    assert claim_wedge_first_seen("user", "", firestore_client=fake_client) is False
    assert claim_wedge_first_seen("user/traversal", "2026-10-25", firestore_client=fake_client) is False
    assert claim_wedge_first_seen("user", "2026/10/25", firestore_client=fake_client) is False


def test_claim_wedge_nudge_cooldown_window(fake_client):
    uid = "test-user-3"
    t0 = datetime(2026, 10, 25, 10, 0, 0, tzinfo=timezone.utc)

    # Initial claim succeeds
    assert claim_wedge_nudge_cooldown(uid, now=t0, firestore_client=fake_client) is True

    # Claim 1 hour later fails (within 24h cooldown)
    t1 = t0 + timedelta(hours=1)
    assert claim_wedge_nudge_cooldown(uid, now=t1, firestore_client=fake_client) is False

    # Claim 23h 59m later fails
    t2 = t0 + timedelta(hours=23, minutes=59)
    assert claim_wedge_nudge_cooldown(uid, now=t2, firestore_client=fake_client) is False

    # Claim 24h 1s later succeeds
    t3 = t0 + timedelta(hours=24, seconds=1)
    assert claim_wedge_nudge_cooldown(uid, now=t3, firestore_client=fake_client) is True


def test_claim_wedge_nudge_cooldown_naive_and_aware_datetimes(fake_client):
    uid = "test-user-4"
    # Provide naive datetime as now
    naive_t0 = datetime(2026, 10, 25, 12, 0, 0)

    # Does not raise TypeError
    assert claim_wedge_nudge_cooldown(uid, now=naive_t0, firestore_client=fake_client) is True

    # Stored record is aware UTC
    state = get_wedge_state(uid, firestore_client=fake_client)
    assert state["last_nudge_at"].tzinfo == timezone.utc

    # Simulate legacy Firestore document having naive timestamp
    fake_client.store[f"{CAPTURE_WEDGE_STATE_COLLECTION}/{uid}"]["last_nudge_at"] = datetime(2026, 10, 25, 12, 0, 0)

    # Calling with aware UTC now does not raise TypeError
    aware_now = datetime(2026, 10, 25, 13, 0, 0, tzinfo=timezone.utc)
    assert claim_wedge_nudge_cooldown(uid, now=aware_now, firestore_client=fake_client) is False


def test_claim_wedge_nudge_cooldown_invalid_uid(fake_client):
    assert claim_wedge_nudge_cooldown("", firestore_client=fake_client) is False
    assert claim_wedge_nudge_cooldown("   ", firestore_client=fake_client) is False
    assert claim_wedge_nudge_cooldown("../traversal", firestore_client=fake_client) is False


def test_get_wedge_state_and_reset(fake_client):
    uid = "test-user-5"
    assert get_wedge_state(uid, firestore_client=fake_client) is None
    assert reset_wedge_state(uid, firestore_client=fake_client) is True

    claim_wedge_first_seen(uid, "2026-10-25", firestore_client=fake_client)
    state = get_wedge_state(uid, firestore_client=fake_client)
    assert state is not None
    assert state["uid"] == uid

    # Reset removes document
    assert reset_wedge_state(uid, firestore_client=fake_client) is True
    assert get_wedge_state(uid, firestore_client=fake_client) is None

    # Invalid uid returns None / False
    assert get_wedge_state("", firestore_client=fake_client) is None
    assert reset_wedge_state("", firestore_client=fake_client) is False


def test_client_resolution_failure_fails_safe():
    with patch("database.capture_wedge_state.get_firestore_client", side_effect=RuntimeError("no creds")):
        assert claim_wedge_first_seen("u1", "2026-10-25", firestore_client=None) is False
        assert claim_wedge_nudge_cooldown("u1", firestore_client=None) is False
        assert get_wedge_state("u1", firestore_client=None) is None
        assert reset_wedge_state("u1", firestore_client=None) is False


def test_firestore_transaction_error_logged_and_fails_safe(fake_client):
    uid = "test-user-6"
    broken_client = MagicMock()
    broken_client.collection.side_effect = RuntimeError("network partition")

    assert claim_wedge_first_seen(uid, "2026-10-25", firestore_client=broken_client) is False
    assert claim_wedge_nudge_cooldown(uid, firestore_client=broken_client) is False
    assert get_wedge_state(uid, firestore_client=broken_client) is None
    assert reset_wedge_state(uid, firestore_client=broken_client) is False
