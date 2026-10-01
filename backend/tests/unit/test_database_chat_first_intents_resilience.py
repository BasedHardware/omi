"""Unit tests verifying defensive boundary guards in chat_first_intents."""

from datetime import datetime, timezone
import pytest

from database.chat_first_intents import (
    fetch_ready_intent_batch,
    fetch_ready_intents,
    release_due_deferrals,
)


def test_fetch_ready_intent_batch_rejects_empty_uid():
    """Verify fetch_ready_intent_batch strictly rejects empty or non-string uid."""
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        fetch_ready_intent_batch("", account_generation=1)
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        fetch_ready_intent_batch("   ", account_generation=1)
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        fetch_ready_intent_batch(None, account_generation=1)  # type: ignore[arg-type]


def test_fetch_ready_intent_batch_rejects_invalid_generation():
    """Verify fetch_ready_intent_batch rejects boolean or negative account_generation."""
    with pytest.raises(ValueError, match="account_generation must be a non-negative integer"):
        fetch_ready_intent_batch("user_123", account_generation=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="account_generation must be a non-negative integer"):
        fetch_ready_intent_batch("user_123", account_generation=-1)
    with pytest.raises(ValueError, match="account_generation must be a non-negative integer"):
        fetch_ready_intent_batch("user_123", account_generation="1")  # type: ignore[arg-type]


def test_fetch_ready_intent_batch_rejects_invalid_now_type():
    """Verify fetch_ready_intent_batch rejects non-datetime now argument."""
    with pytest.raises(ValueError, match="now must be a datetime"):
        fetch_ready_intent_batch("user_123", account_generation=1, now="2026-09-30")  # type: ignore[arg-type]


def test_fetch_ready_intent_batch_limit_clamping(monkeypatch):
    """Verify limit parameter is clamped within [1, 64] and non-int/bool/below-1 defaults to 8."""
    observed_limits = []

    def mock_require_control(*args, **kwargs):
        pass

    class MockQuery:
        def stream(self):
            return []

    class MockCollection:
        def where(self, filter=None):
            return MockQuery()

    class MockUserRef:
        def collection(self, name):
            return MockCollection()

    class MockClient:
        def collection(self, name):
            return self
        def document(self, doc_id):
            return MockUserRef()

    def mock_repair_transient_dead_letters(uid, account_generation, limit, now, firestore_client, requeue):
        observed_limits.append(limit)
        return False

    monkeypatch.setattr("database.chat_first_intents._require_current_control", mock_require_control)
    monkeypatch.setattr("database.chat_first_intents.delivery_attempts.repair_transient_dead_letters", mock_repair_transient_dead_letters)

    client = MockClient()

    # limit > 64 clamped to 64
    fetch_ready_intent_batch("user_123", account_generation=1, limit=100, firestore_client=client)
    assert observed_limits[-1] == 64

    # limit < 1 clamped/defaulted to 8
    fetch_ready_intent_batch("user_123", account_generation=1, limit=0, firestore_client=client)
    assert observed_limits[-1] == 8

    fetch_ready_intent_batch("user_123", account_generation=1, limit=-5, firestore_client=client)
    assert observed_limits[-1] == 8

    # boolean limit defaulted to 8
    fetch_ready_intent_batch("user_123", account_generation=1, limit=True, firestore_client=client)  # type: ignore[arg-type]
    assert observed_limits[-1] == 8

    # valid limits preserved
    fetch_ready_intent_batch("user_123", account_generation=1, limit=1, firestore_client=client)
    assert observed_limits[-1] == 1

    fetch_ready_intent_batch("user_123", account_generation=1, limit=32, firestore_client=client)
    assert observed_limits[-1] == 32


def test_release_due_deferrals_rejects_empty_uid_and_invalid_generation():
    """Verify release_due_deferrals validates uid and generation boundaries."""
    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        release_due_deferrals("", account_generation=1, now=now)
    with pytest.raises(ValueError, match="account_generation must be a non-negative integer"):
        release_due_deferrals("user_123", account_generation=-1, now=now)
    with pytest.raises(ValueError, match="account_generation must be a non-negative integer"):
        release_due_deferrals("user_123", account_generation=True, now=now)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="now must be a datetime"):
        release_due_deferrals("user_123", account_generation=1, now="not-a-dt")  # type: ignore[arg-type]


def test_release_due_deferrals_coerces_naive_now(monkeypatch):
    """Verify release_due_deferrals cleanly coerces naive datetime without offset mismatch."""
    def mock_require_control(*args, **kwargs):
        pass

    observed_due_ats = []

    class MockQuery:
        def limit(self, count):
            return self
        def stream(self):
            return []

    def mock_build(self, collection, params, field_filter_factory=None):
        observed_due_ats.append(params.get("due_at"))
        return MockQuery()

    monkeypatch.setattr("database.chat_first_intents._require_current_control", mock_require_control)
    monkeypatch.setattr("database.firestore_index_registry.FirestoreQuerySpec.build", mock_build)

    class MockUserRef:
        def collection(self, name):
            return self

    class MockClient:
        def collection(self, name):
            return self
        def document(self, doc_id):
            return MockUserRef()

    naive_now = datetime(2026, 9, 30, 12, 0, 0)
    batch = release_due_deferrals("user_123", account_generation=1, now=naive_now, firestore_client=MockClient())
    assert len(observed_due_ats) == 1
    assert observed_due_ats[0].tzinfo == timezone.utc
    assert batch.intents == []
