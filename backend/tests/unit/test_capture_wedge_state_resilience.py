import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from google.cloud import firestore

from database.capture_wedge_state import (
    _clean_id,
    _clean_day,
    _client,
    claim_wedge_first_seen,
    claim_wedge_nudge_cooldown,
    get_wedge_state,
    reset_wedge_state,
    CAPTURE_WEDGE_STATE_COLLECTION,
    WEDGE_NUDGE_COOLDOWN,
    MAX_ID_LENGTH,
    MAX_DAY_LENGTH,
)


@pytest.fixture(autouse=True)
def mock_transactional(monkeypatch):
    """Ensure firestore.transactional is a transparent pass-through during unit tests."""
    monkeypatch.setattr(firestore, "transactional", lambda fn: fn)


class FakeSnapshot:
    def __init__(self, exists=True, data=None):
        self.exists = exists
        self._data = data or {}

    def to_dict(self):
        return dict(self._data)


class FakeDocRef:
    def __init__(self, doc_id):
        self.doc_id = doc_id
        self.data = None
        self.deleted = False

    def get(self, transaction=None):
        if self.data is not None and not self.deleted:
            return FakeSnapshot(exists=True, data=self.data)
        return FakeSnapshot(exists=False, data=None)

    def set(self, data, merge=False):
        self.deleted = False
        if merge and self.data is not None:
            merged = dict(self.data)
            merged.update(data)
            self.data = merged
        else:
            self.data = dict(data) if isinstance(data, dict) else data

    def delete(self):
        self.deleted = True
        self.data = None


class FakeCollection:
    def __init__(self):
        self.docs = {}

    def document(self, doc_id):
        if doc_id not in self.docs:
            self.docs[doc_id] = FakeDocRef(doc_id)
        return self.docs[doc_id]


class FakeFirestoreClient:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        if name not in self.collections:
            self.collections[name] = FakeCollection()
        return self.collections[name]

    def transaction(self):
        class FakeTxn:
            def set(self, ref, data, merge=False):
                ref.set(data, merge=merge)

        return FakeTxn()


# --- Unit Tests ---


def test_clean_id_validates_and_normalizes():
    assert _clean_id("user_123") == "user_123"
    assert _clean_id("  user-abc  ") == "user-abc"
    assert _clean_id("") == ""
    assert _clean_id("   ") == ""
    assert _clean_id(None) == ""
    assert _clean_id(1234) == ""  # type: ignore[arg-type]
    # Path traversal and control sequences
    assert _clean_id("../bad") == ""
    assert _clean_id("users/123") == ""
    assert _clean_id("users\\123") == ""
    assert _clean_id("uid\x00null") == ""
    # Length boundaries
    assert _clean_id("u" * (MAX_ID_LENGTH + 1)) == ""
    assert _clean_id("u" * MAX_ID_LENGTH) == "u" * MAX_ID_LENGTH


def test_clean_day_validates_and_normalizes():
    assert _clean_day("2026-09-30") == "2026-09-30"
    assert _clean_day("  2026-09-30  ") == "2026-09-30"
    assert _clean_day("") == ""
    assert _clean_day("   ") == ""
    assert _clean_day(None) == ""
    assert _clean_day(20260930) == ""  # type: ignore[arg-type]
    # Path traversal rejection
    assert _clean_day("../day") == ""
    assert _clean_day("day/01") == ""
    assert _clean_day("day\\01") == ""
    assert _clean_day("day\x0001") == ""
    # Length boundaries
    assert _clean_day("d" * (MAX_DAY_LENGTH + 1)) == ""
    assert _clean_day("d" * MAX_DAY_LENGTH) == "d" * MAX_DAY_LENGTH


def test_claim_wedge_first_seen_success_and_idempotency():
    client = FakeFirestoreClient()
    uid = "test-uid-1"
    day1 = "2026-09-30"
    now_stamp = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)

    # First claim for day1 succeeds
    assert claim_wedge_first_seen(uid, day1, now=now_stamp, firestore_client=client) is True

    state = get_wedge_state(uid, firestore_client=client)
    assert state is not None
    assert state["uid"] == uid
    assert state["first_seen_day"] == day1
    assert state["updated_at"] == now_stamp

    # Second claim for the SAME day returns False (already claimed)
    assert claim_wedge_first_seen(uid, day1, now=now_stamp, firestore_client=client) is False

    # Claim for a NEW day succeeds
    day2 = "2026-10-01"
    assert claim_wedge_first_seen(uid, day2, now=now_stamp, firestore_client=client) is True
    updated_state = get_wedge_state(uid, firestore_client=client)
    assert updated_state is not None
    assert updated_state["first_seen_day"] == day2


def test_claim_wedge_first_seen_invalid_inputs():
    client = FakeFirestoreClient()
    # Invalid UID
    assert claim_wedge_first_seen("", "2026-09-30", firestore_client=client) is False
    assert claim_wedge_first_seen("   ", "2026-09-30", firestore_client=client) is False
    assert claim_wedge_first_seen("../traversal", "2026-09-30", firestore_client=client) is False
    assert claim_wedge_first_seen("u/slash", "2026-09-30", firestore_client=client) is False

    # Invalid Day
    assert claim_wedge_first_seen("valid-uid", "", firestore_client=client) is False
    assert claim_wedge_first_seen("valid-uid", "../day", firestore_client=client) is False
    assert claim_wedge_first_seen("valid-uid", "day/01", firestore_client=client) is False


def test_claim_wedge_first_seen_error_handling():
    # If client is None
    assert claim_wedge_first_seen("uid", "2026-09-30", firestore_client=None) is False

    # If client transaction raises unexpected exception
    mock_client = MagicMock()
    mock_client.transaction.side_effect = Exception("Transport timeout")
    assert claim_wedge_first_seen("uid", "2026-09-30", firestore_client=mock_client) is False


def test_claim_wedge_nudge_cooldown_first_time():
    client = FakeFirestoreClient()
    uid = "test-uid-2"
    now_stamp = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)

    # First nudge claim succeeds
    assert claim_wedge_nudge_cooldown(uid, now=now_stamp, firestore_client=client) is True

    state = get_wedge_state(uid, firestore_client=client)
    assert state is not None
    assert state["last_nudge_at"] == now_stamp


def test_claim_wedge_nudge_cooldown_within_window_rejected():
    client = FakeFirestoreClient()
    uid = "test-uid-3"
    t0 = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)

    # First claim
    assert claim_wedge_nudge_cooldown(uid, now=t0, firestore_client=client) is True

    # 1 hour later (well within 24h window) -> rejected
    t_1h = t0 + timedelta(hours=1)
    assert claim_wedge_nudge_cooldown(uid, now=t_1h, firestore_client=client) is False

    # 23 hours later -> still within window -> rejected
    t_23h = t0 + timedelta(hours=23)
    assert claim_wedge_nudge_cooldown(uid, now=t_23h, firestore_client=client) is False


def test_claim_wedge_nudge_cooldown_after_window_accepted():
    client = FakeFirestoreClient()
    uid = "test-uid-4"
    t0 = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)

    assert claim_wedge_nudge_cooldown(uid, now=t0, firestore_client=client) is True

    # 25 hours later (past 24h cooldown) -> accepted
    t_25h = t0 + timedelta(hours=25)
    assert claim_wedge_nudge_cooldown(uid, now=t_25h, firestore_client=client) is True

    state = get_wedge_state(uid, firestore_client=client)
    assert state is not None
    assert state["last_nudge_at"] == t_25h


def test_claim_wedge_nudge_cooldown_naive_datetime():
    client = FakeFirestoreClient()
    uid = "test-uid-5"
    doc_ref = client.collection(CAPTURE_WEDGE_STATE_COLLECTION).document(uid)
    # Stored timestamp is legacy naive datetime
    t_naive = datetime(2026, 9, 29, 12, 0)
    doc_ref.set({"uid": uid, "last_nudge_at": t_naive})

    # Query with aware datetime 2 hours later
    now_aware = datetime(2026, 9, 29, 14, 0, tzinfo=timezone.utc)
    # Within 24h window -> should correctly compare and return False without TypeError
    assert claim_wedge_nudge_cooldown(uid, now=now_aware, firestore_client=client) is False


def test_claim_wedge_nudge_cooldown_invalid_inputs_and_errors():
    client = FakeFirestoreClient()
    assert claim_wedge_nudge_cooldown("", firestore_client=client) is False
    assert claim_wedge_nudge_cooldown("../bad", firestore_client=client) is False
    assert claim_wedge_nudge_cooldown("bad/uid", firestore_client=client) is False

    # If client is None
    assert claim_wedge_nudge_cooldown("valid-uid", firestore_client=None) is False

    # Transaction failure
    mock_client = MagicMock()
    mock_client.transaction.side_effect = Exception("Firestore unavailable")
    assert claim_wedge_nudge_cooldown("valid-uid", firestore_client=mock_client) is False


def test_get_and_reset_wedge_state():
    client = FakeFirestoreClient()
    uid = "test-uid-6"
    assert get_wedge_state(uid, firestore_client=client) is None
    assert get_wedge_state("", firestore_client=client) is None
    assert get_wedge_state("../bad", firestore_client=client) is None

    # Populate state
    claim_wedge_first_seen(uid, "2026-09-30", firestore_client=client)
    assert get_wedge_state(uid, firestore_client=client) is not None

    # Reset state
    assert reset_wedge_state(uid, firestore_client=client) is True
    assert get_wedge_state(uid, firestore_client=client) is None

    # Reset invalid inputs
    assert reset_wedge_state("", firestore_client=client) is False
    assert reset_wedge_state("../bad", firestore_client=client) is False


def test_client_fallback_resolution():
    mock_client = MagicMock()
    assert _client(mock_client) is mock_client
