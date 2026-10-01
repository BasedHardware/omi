"""Hermetic unit tests verifying defensive boundary guards in database.memory_non_active_routes."""

from datetime import datetime, timezone
import pytest

from database.memory_non_active_routes import (
    NonActiveRoute,
    NonActiveRouteOutcome,
    _payload_fingerprint,
    _stable_outcome_id,
    persist_non_active_route_outcome,
)


def _valid_outcome_dict(**overrides) -> dict:
    base = {
        "uid": "usr-123",
        "route": NonActiveRoute.archive,
        "idempotency_key": "idem-123",
        "source_ids": ["src-1", "src-2"],
        "reason": "Routine archive of inactive memory",
        "run_id": "run-456",
        "patch_id": "patch-789",
        "created_at": datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc),
    }
    base.update(overrides)
    return base


def test_persist_rejects_non_outcome_instance():
    """Verify persist_non_active_route_outcome raises TypeError on non-outcome input."""
    with pytest.raises(TypeError, match="outcome must be an instance of NonActiveRouteOutcome"):
        persist_non_active_route_outcome(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="outcome must be an instance of NonActiveRouteOutcome"):
        persist_non_active_route_outcome({"uid": "usr-123"})  # type: ignore[arg-type]


def test_persist_rejects_none_db_client():
    """Verify persist_non_active_route_outcome raises ValueError when db_client is None."""
    outcome = NonActiveRouteOutcome(**_valid_outcome_dict())
    with pytest.raises(ValueError, match="db_client must not be None"):
        persist_non_active_route_outcome(outcome, db_client=None)


def test_outcome_rejects_empty_or_whitespace_identifiers():
    """Verify empty or whitespace-only identifiers raise ValueError."""
    for field in ("uid", "idempotency_key", "reason", "run_id"):
        data_empty = _valid_outcome_dict(**{field: ""})
        with pytest.raises(ValueError, match="required fields must not be blank"):
            NonActiveRouteOutcome(**data_empty)

        data_whitespace = _valid_outcome_dict(**{field: "   "})
        with pytest.raises(ValueError, match="required fields must not be blank"):
            NonActiveRouteOutcome(**data_whitespace)


def test_outcome_rejects_empty_source_ids():
    """Verify source_ids with no valid non-blank strings raises ValueError."""
    with pytest.raises(ValueError, match="source_ids must not be empty"):
        NonActiveRouteOutcome(**_valid_outcome_dict(source_ids=[]))
    with pytest.raises(ValueError, match="source_ids must not be empty"):
        NonActiveRouteOutcome(**_valid_outcome_dict(source_ids=["", "   "]))


def test_outcome_coerces_naive_datetime_to_utc():
    """Verify naive datetime in created_at is coerced to timezone.utc."""
    naive_dt = datetime(2026, 9, 30, 12, 0, 0)
    outcome = NonActiveRouteOutcome(**_valid_outcome_dict(created_at=naive_dt))
    assert outcome.created_at.tzinfo == timezone.utc
    assert outcome.created_at.year == 2026
    assert outcome.created_at.hour == 12


def test_outcome_parses_iso_string_to_utc():
    """Verify ISO strings with Z or offsets are normalized to UTC."""
    outcome_z = NonActiveRouteOutcome(**_valid_outcome_dict(created_at="2026-09-30T12:00:00Z"))
    assert outcome_z.created_at.tzinfo == timezone.utc
    assert outcome_z.created_at == datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)

    outcome_offset = NonActiveRouteOutcome(**_valid_outcome_dict(created_at="2026-09-30T14:00:00+02:00"))
    assert outcome_offset.created_at.tzinfo == timezone.utc
    assert outcome_offset.created_at == datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)


def test_outcome_rejects_invalid_created_at():
    """Verify malformed strings or invalid types in created_at raise ValueError or TypeError."""
    with pytest.raises(ValueError, match="created_at string cannot be empty or whitespace"):
        NonActiveRouteOutcome(**_valid_outcome_dict(created_at="   "))
    with pytest.raises(ValueError, match="Invalid ISO timestamp string"):
        NonActiveRouteOutcome(**_valid_outcome_dict(created_at="not-a-valid-timestamp"))


def test_stable_outcome_id_guards():
    """Verify _stable_outcome_id validates uid and idempotency_key."""
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        _stable_outcome_id("", "idem-1")
    with pytest.raises(ValueError, match="idempotency_key must be a non-empty string"):
        _stable_outcome_id("usr-1", "")

    oid = _stable_outcome_id("usr-1", "idem-1")
    assert oid.startswith("nar_")
    assert len(oid) == 36


def test_payload_fingerprint_rejects_non_dict():
    """Verify _payload_fingerprint raises TypeError if non-dict passed."""
    with pytest.raises(TypeError, match="data must be a dictionary"):
        _payload_fingerprint("not-a-dict")  # type: ignore[arg-type]
