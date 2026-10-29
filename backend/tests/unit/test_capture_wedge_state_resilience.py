from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import pytest
from google.cloud import firestore

from database.capture_wedge_state import (
    CAPTURE_WEDGE_STATE_COLLECTION,
    WEDGE_NUDGE_COOLDOWN,
    _clean_day,
    _clean_id,
    claim_wedge_first_seen,
    claim_wedge_nudge_cooldown,
    get_wedge_state,
    reset_wedge_state,
)


@pytest.fixture(autouse=True)
def mock_transactional(monkeypatch):
    """Ensure firestore.transactional is a transparent pass-through during unit tests."""
    monkeypatch.setattr(firestore, "transactional", lambda fn: fn)


class FakeSnapshot:
    def __init__(self, exists: bool = True, data: dict[str, Any] | None = None):
        self.exists = exists
        self._data = dict(data) if data is not None else {}

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


class FakeDocRef:
    def __init__(self, doc_id: str, store: dict[str, dict[str, Any]]):
        self.id = doc_id
        self._store = store

    def get(self, transaction: Any = None) -> FakeSnapshot:
        if self.id in self._store:
            return FakeSnapshot(exists=True, data=self._store[self.id])
        return FakeSnapshot(exists=False, data={})

    def set(self, data: dict[str, Any], merge: bool = False) -> None:
        if merge and self.id in self._store:
            self._store[self.id].update(data)
        else:
            self._store[self.id] = dict(data)

    def delete(self) -> None:
        self._store.pop(self.id, None)


class FakeTransaction:
    def __init__(self):
        pass

    def set(self, doc_ref: FakeDocRef, data: dict[str, Any], merge: bool = False) -> None:
        doc_ref.set(data, merge=merge)


class FakeCollection:
    def __init__(self, store: dict[str, dict[str, Any]]):
        self._store = store

    def document(self, doc_id: str) -> FakeDocRef:
        return FakeDocRef(doc_id, self._store)


class FakeClient:
    def __init__(self):
        self._store: dict[str, dict[str, Any]] = {}

    def collection(self, name: str) -> FakeCollection:
        return FakeCollection(self._store)

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()


def test_clean_id_and_day_sanitization():
    assert _clean_id("user_123") == "user_123"
    assert _clean_id("  user_abc  ") == "user_abc"
    assert _clean_id("") == ""
    assert _clean_id("   ") == ""
    assert _clean_id(None) == ""
    assert _clean_id(12345) == ""
    assert _clean_id("../secret") == ""
    assert _clean_id("user/hack") == ""
    assert _clean_id("user\\hack") == ""
    assert _clean_id("user\x00null") == ""
    assert _clean_id("a" * 129) == ""

    assert _clean_day("2026-10-29") == "2026-10-29"
    assert _clean_day("  2026-10-29  ") == "2026-10-29"
    assert _clean_day("") == ""
    assert _clean_day("   ") == ""
    assert _clean_day(None) == ""
    assert _clean_day(20261029) == ""
    assert _clean_day("../day") == ""
    assert _clean_day("day/bad") == ""
    assert _clean_day("day\\bad") == ""
    assert _clean_day("day\x00bad") == ""
    assert _clean_day("d" * 33) == ""


def test_claim_wedge_first_seen_rejections():
    client = FakeClient()
    assert not claim_wedge_first_seen("", "2026-10-29", firestore_client=client)
    assert not claim_wedge_first_seen("uid_1", "", firestore_client=client)
    assert not claim_wedge_first_seen("../bad_uid", "2026-10-29", firestore_client=client)
    assert not claim_wedge_first_seen("uid_1", "../bad_day", firestore_client=client)
    assert not claim_wedge_nudge_cooldown("", firestore_client=client)
    assert not claim_wedge_nudge_cooldown("bad/uid", firestore_client=client)


def test_claim_wedge_first_seen_happy_path_and_dedup():
    client = FakeClient()
    uid = "test_user_42"
    day1 = "2026-10-29"
    day2 = "2026-10-30"

    assert claim_wedge_first_seen(uid, day1, firestore_client=client) is True
    assert claim_wedge_first_seen(uid, day1, firestore_client=client) is False
    assert claim_wedge_first_seen(uid, day2, firestore_client=client) is True


def test_claim_wedge_nudge_cooldown_and_naive_dt():
    client = FakeClient()
    uid = "test_user_nudge"
    base_time = datetime(2026, 10, 29, 12, 0, 0, tzinfo=timezone.utc)

    # First nudge claim succeeds
    assert claim_wedge_nudge_cooldown(uid, now=base_time, firestore_client=client) is True

    # Immediate next nudge within 24h fails
    later_1h = base_time + timedelta(hours=1)
    assert claim_wedge_nudge_cooldown(uid, now=later_1h, firestore_client=client) is False

    # Store a naive datetime into the document to verify naive datetime alignment
    doc = client.collection(CAPTURE_WEDGE_STATE_COLLECTION).document(uid)
    doc.set({"last_nudge_at": datetime(2026, 10, 29, 12, 0, 0)}, merge=True)

    # Nudge check with tz-aware now should not crash with TypeError
    assert claim_wedge_nudge_cooldown(uid, now=later_1h, firestore_client=client) is False

    # Nudge after cooldown (25h) succeeds
    later_25h = base_time + timedelta(hours=25)
    assert claim_wedge_nudge_cooldown(uid, now=later_25h, firestore_client=client) is True


def test_get_and_reset_wedge_state():
    client = FakeClient()
    uid = "test_user_mgmt"
    day = "2026-10-29"

    assert get_wedge_state(uid, firestore_client=client) is None
    assert reset_wedge_state(uid, firestore_client=client) is True

    claim_wedge_first_seen(uid, day, firestore_client=client)
    state = get_wedge_state(uid, firestore_client=client)
    assert state is not None
    assert state.get("first_seen_day") == day
    assert state.get("uid") == uid

    assert reset_wedge_state(uid, firestore_client=client) is True
    assert get_wedge_state(uid, firestore_client=client) is None


def test_transaction_exception_resilience():
    class BrokenClient:
        def collection(self, name: str):
            raise RuntimeError("Database unavailable")

    broken = BrokenClient()
    assert claim_wedge_first_seen("uid_1", "2026-10-29", firestore_client=broken) is False
    assert claim_wedge_nudge_cooldown("uid_1", firestore_client=broken) is False
    assert get_wedge_state("uid_1", firestore_client=broken) is None
    assert reset_wedge_state("uid_1", firestore_client=broken) is False
