"""Unit tests verifying defensive resilience and validation in sync_dead_letters."""

from __future__ import annotations

from datetime import datetime, timezone
import pytest

from database.sync_dead_letters import (
    DEAD_LETTER_LANE,
    DEAD_LETTERS_COLLECTION,
    STATUS_DEAD_LETTER,
    STATUS_PENDING,
    confirm_dead_letter,
    dead_letter_failure_code,
    ensure_dead_letter_confirmed,
    get_dead_letter,
    record_dead_letter_pending,
    _validate_dead_letter_identity,
)
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.sync import stage as sync_stage


@pytest.fixture(autouse=True)
def _patch_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMI_ENV_STAGE", "prod")


def _get_collection_name() -> str:
    return sync_stage.collection_name(DEAD_LETTERS_COLLECTION)


def test_dead_letter_failure_code_maps_expected_values() -> None:
    """Verify failure code normalizes invalid or arbitrary inputs to unknown."""
    assert dead_letter_failure_code("stt_failed") == "stt_failed"
    assert dead_letter_failure_code("llm_failed") == "llm_failed"
    assert dead_letter_failure_code("arbitrary_error") == "unknown"
    assert dead_letter_failure_code(None) == "unknown"
    assert dead_letter_failure_code(12345) == "unknown"


def test_record_dead_letter_pending_rejects_invalid_job_id() -> None:
    """Verify record_dead_letter_pending raises ValueError on invalid job_id types/values."""
    mock_client = StrictFirestore()
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
    mock_client = StrictFirestore()
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


def test_record_dead_letter_pending_coerces_naive_created_at() -> None:
    """Verify naive failure timestamps in existing records are coerced to UTC."""
    mock_client = StrictFirestore()
    coll = _get_collection_name()
    naive_dt = datetime(2026, 9, 30, 12, 0, 0)
    mock_client.rows[(coll, "job-naive")] = {
        "job_id": "job-naive",
        "uid": "user-naive",
        "created_at": naive_dt,
        "attempt_count": 1,
        "status": STATUS_PENDING,
    }

    updated = record_dead_letter_pending(
        job_id="job-naive",
        uid="user-naive",
        failure_code="stt_failed",
        firestore_client=mock_client,
    )
    assert updated["attempt_count"] == 2
    assert updated["created_at"].tzinfo == timezone.utc
    assert updated["created_at"] == naive_dt.replace(tzinfo=timezone.utc)


def test_get_dead_letter_validates_job_id() -> None:
    """Verify get_dead_letter validates job_id argument."""
    mock_client = StrictFirestore()
    with pytest.raises(ValueError, match="job_id must be a non-empty string without slashes"):
        get_dead_letter("", firestore_client=mock_client)

    with pytest.raises(ValueError, match="job_id must be a non-empty string without slashes"):
        get_dead_letter("job/slash", firestore_client=mock_client)


def test_confirm_dead_letter_validates_job_id_and_transitions() -> None:
    """Verify confirm_dead_letter validates job_id and updates status."""
    mock_client = StrictFirestore()
    with pytest.raises(ValueError, match="job_id must be a non-empty string without slashes"):
        confirm_dead_letter("", firestore_client=mock_client)

    # Missing doc returns None
    assert confirm_dead_letter("job-nonexistent", firestore_client=mock_client) is None

    # Existing pending doc transitions to dead_letter
    coll = _get_collection_name()
    mock_client.rows[(coll, "job-abc")] = {"job_id": "job-abc", "uid": "u1", "status": STATUS_PENDING}
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

    # Blank normalized UID rejected as mismatch
    with pytest.raises(RuntimeError, match="sync dead-letter identity mismatch"):
        _validate_dead_letter_identity({"job_id": "job-1", "uid": "u1"}, "job-1", "   ")

    # Optional None uid passes without error
    _validate_dead_letter_identity({"job_id": "job-1", "uid": "u1"}, "job-1", None)

    # Matching values pass without error
    _validate_dead_letter_identity({"job_id": "job-1", "uid": "u1"}, "job-1", "u1")
    _validate_dead_letter_identity({"job_id": "job-1", "uid": "u1"}, "  job-1  ", "  u1  ")


def test_ensure_dead_letter_confirmed_handles_missing_and_existing() -> None:
    """Verify ensure_dead_letter_confirmed handles missing and existing records."""
    mock_client = StrictFirestore()

    # Missing without uid raises RuntimeError
    with pytest.raises(RuntimeError, match="sync dead-letter missing and uid unavailable"):
        ensure_dead_letter_confirmed("job-fresh", firestore_client=mock_client)

    # Missing with blank uid raises RuntimeError
    with pytest.raises(RuntimeError, match="sync dead-letter missing and uid unavailable"):
        ensure_dead_letter_confirmed("job-fresh", uid="   ", firestore_client=mock_client)

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

    # Existing pending doc: confirming reuses it and validates identity against stored record
    coll = _get_collection_name()
    mock_client.rows[(coll, "job-existing")] = {
        "job_id": "job-existing",
        "uid": "u-orig",
        "failure_code": "stt_failed",
        "status": STATUS_PENDING,
        "attempt_count": 1,
    }

    # Wrong uid fails closed and cannot rewrite stored record
    with pytest.raises(RuntimeError, match="sync dead-letter identity mismatch"):
        ensure_dead_letter_confirmed("job-existing", uid="u-wrong", firestore_client=mock_client)

    # Blank uid fails closed
    with pytest.raises(RuntimeError, match="sync dead-letter identity mismatch"):
        ensure_dead_letter_confirmed("job-existing", uid="   ", firestore_client=mock_client)

    # Correct uid confirms existing pending record without overwriting failure_code
    confirmed_existing = ensure_dead_letter_confirmed(
        "job-existing",
        uid="u-orig",
        failure_code="llm_failed",  # should not rewrite original failure_code
        firestore_client=mock_client,
    )
    assert confirmed_existing["status"] == STATUS_DEAD_LETTER
    assert confirmed_existing["job_id"] == "job-existing"
    assert confirmed_existing["uid"] == "u-orig"
    assert confirmed_existing["failure_code"] == "stt_failed"
    assert confirmed_existing["attempt_count"] == 1
    assert "dead_lettered_at" in confirmed_existing
