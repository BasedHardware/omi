"""Unit tests verifying defensive resilience and validation in sync_dead_letters."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
import pytest

from database.sync_dead_letters import (
    DEAD_LETTER_LANE,
    DEAD_LETTERS_COLLECTION,
    FAILURE_CODES,
    STATUS_DEAD_LETTER,
    STATUS_PENDING,
    confirm_dead_letter,
    dead_letter_failure_code,
    ensure_dead_letter_confirmed,
    get_dead_letter,
    record_dead_letter_pending,
    _validate_dead_letter_identity,
)


class _MockDocRef:
    def __init__(self, data: dict[str, Any] | None = None):
        self.data = data
        self.exists = data is not None

    def get(self, transaction: Any = None) -> Any:
        return self

    def to_dict(self) -> dict[str, Any] | None:
        return dict(self.data) if self.data is not None else None

    def set(self, payload: dict[str, Any], merge: bool = False) -> None:
        if self.data is None or not merge:
            self.data = dict(payload)
        else:
            self.data.update(payload)
        self.exists = True


class _MockTransaction:
    def set(self, doc_ref: _MockDocRef, payload: dict[str, Any], merge: bool = False) -> None:
        doc_ref.set(payload, merge=merge)


class _MockClient:
    def __init__(self, docs: dict[str, _MockDocRef] | None = None):
        self.docs = docs if docs is not None else {}

    def collection(self, name: str) -> Any:
        return self

    def document(self, doc_id: str) -> Any:
        if doc_id not in self.docs:
            self.docs[doc_id] = _MockDocRef(None)
        return self.docs[doc_id]

    def transaction(self) -> Any:
        return _MockTransaction()


@pytest.fixture(autouse=True)
def _patch_transactional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMI_ENV_STAGE", "prod")
    monkeypatch.setattr("google.cloud.firestore.transactional", lambda fn: fn)


def test_dead_letter_failure_code_maps_expected_values() -> None:
    """Verify failure code normalizes invalid or arbitrary inputs to unknown."""
    assert dead_letter_failure_code("stt_failed") == "stt_failed"
    assert dead_letter_failure_code("llm_failed") == "llm_failed"
    assert dead_letter_failure_code("arbitrary_error") == "unknown"
    assert dead_letter_failure_code(None) == "unknown"
    assert dead_letter_failure_code(12345) == "unknown"


def test_record_dead_letter_pending_rejects_invalid_job_id() -> None:
    """Verify record_dead_letter_pending raises ValueError on invalid job_id types/values."""
    mock_client = _MockClient()
    with pytest.raises(ValueError, match="job_id must be a non-empty string without slashes"):
        record_dead_letter_pending(job_id="", uid="user-1", firestore_client=mock_client)

    with pytest.raises(ValueError, match="job_id must be a non-empty string without slashes"):
        record_dead_letter_pending(job_id="   ", uid="user-1", firestore_client=mock_client)

    with pytest.raises(ValueError, match="job_id must be a non-empty string without slashes"):
        record_dead_letter_pending(job_id="job/invalid", uid="user-1", firestore_client=mock_client)

    with pytest.raises(ValueError, match="job_id must be a non-empty string without slashes"):
        record_dead_letter_pending(job_id=None, uid="user-1", firestore_client=mock_client)  # type: ignore[arg-type]


def test_record_dead_letter_pending_normalizes_and_stores() -> None:
    """Verify record_dead_letter_pending strips whitespace and stores expected schema."""
    mock_client = _MockClient()
    doc = record_dead_letter_pending(
        job_id="  job-123  ",
        uid="  user-456  ",
        conversation_id="  conv-789  ",
        failure_code="stt_failed",
        firestore_client=mock_client,
    )
    assert doc["job_id"] == "job-123"
    assert doc["uid"] == "user-456"
    assert doc["conversation_id"] == "conv-789"
    assert doc["status"] == STATUS_PENDING
    assert doc["lane"] == DEAD_LETTER_LANE
    assert doc["attempt_count"] == 1
    assert isinstance(doc["created_at"], datetime)
    assert doc["created_at"].tzinfo == timezone.utc


def test_get_dead_letter_validates_job_id() -> None:
    """Verify get_dead_letter validates job_id argument."""
    mock_client = _MockClient()
    with pytest.raises(ValueError, match="job_id must be a non-empty string without slashes"):
        get_dead_letter("", firestore_client=mock_client)

    with pytest.raises(ValueError, match="job_id must be a non-empty string without slashes"):
        get_dead_letter("job/slash", firestore_client=mock_client)


def test_confirm_dead_letter_validates_job_id_and_transitions() -> None:
    """Verify confirm_dead_letter validates job_id and updates status."""
    mock_client = _MockClient()
    with pytest.raises(ValueError, match="job_id must be a non-empty string without slashes"):
        confirm_dead_letter("", firestore_client=mock_client)

    # Missing doc returns None
    assert confirm_dead_letter("job-nonexistent", firestore_client=mock_client) is None

    # Existing pending doc transitions to dead_letter
    mock_client.docs["job-abc"] = _MockDocRef({"job_id": "job-abc", "uid": "u1", "status": STATUS_PENDING})
    confirmed = confirm_dead_letter("job-abc", firestore_client=mock_client)
    assert confirmed is not None
    assert confirmed["status"] == STATUS_DEAD_LETTER
    assert isinstance(confirmed["dead_lettered_at"], datetime)
    assert confirmed["dead_lettered_at"].tzinfo == timezone.utc


def test_validate_dead_letter_identity_checks() -> None:
    """Verify _validate_dead_letter_identity rejects non-dict and mismatches."""
    with pytest.raises(ValueError, match="ledger doc must be a dictionary"):
        _validate_dead_letter_identity(None, "job-1", "u1")  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="job_id must be a non-empty string without slashes"):
        _validate_dead_letter_identity({"job_id": "job-1", "uid": "u1"}, "", "u1")

    with pytest.raises(RuntimeError, match="sync dead-letter identity mismatch"):
        _validate_dead_letter_identity({"job_id": "job-1", "uid": "u1"}, "job-2", "u1")

    with pytest.raises(RuntimeError, match="sync dead-letter identity mismatch"):
        _validate_dead_letter_identity({"job_id": "job-1", "uid": "u1"}, "job-1", "u2")

    # Matching values pass without error
    _validate_dead_letter_identity({"job_id": "job-1", "uid": "u1"}, "job-1", "u1")


def test_ensure_dead_letter_confirmed_handles_missing_and_existing() -> None:
    """Verify ensure_dead_letter_confirmed requires valid uid when missing, and enforces identity."""
    mock_client = _MockClient()

    # Missing without uid raises RuntimeError
    with pytest.raises(RuntimeError, match="sync dead-letter missing and uid unavailable"):
        ensure_dead_letter_confirmed("job-fresh", firestore_client=mock_client)

    # Missing with valid uid creates and confirms
    confirmed = ensure_dead_letter_confirmed(
        "job-fresh",
        uid="u-fresh",
        failure_code="llm_failed",
        firestore_client=mock_client,
    )
    assert confirmed["status"] == STATUS_DEAD_LETTER
    assert confirmed["job_id"] == "job-fresh"
    assert confirmed["uid"] == "u-fresh"
    assert confirmed["failure_code"] == "llm_failed"
