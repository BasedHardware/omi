"""Hermetic unit tests verifying defensive boundary guards in database.task_recommendations."""

from datetime import datetime, timezone
import pytest

from database.task_recommendations import (
    _decision_records,
    _normalize_task_datetime,
    _request_hash,
    _stable_id,
    _user_ref,
    _valid_evaluation_projection,
)


def test_normalize_task_datetime_handles_iso_strings():
    """Verify ISO strings with Z and offsets are normalized to UTC."""
    res_z = _normalize_task_datetime("2026-09-30T12:00:00Z")
    assert res_z == datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)

    res_offset = _normalize_task_datetime("2026-09-30T14:00:00+02:00")
    assert res_offset == datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)


def test_normalize_task_datetime_coerces_naive_datetime():
    """Verify naive datetimes are coerced to timezone.utc."""
    naive_dt = datetime(2026, 9, 30, 12, 0, 0)
    res = _normalize_task_datetime(naive_dt)
    assert res.tzinfo == timezone.utc
    assert res.year == 2026
    assert res.hour == 12


def test_normalize_task_datetime_rejects_invalid_values():
    """Verify empty strings, malformed strings, and bad types raise ValueError or TypeError."""
    with pytest.raises(ValueError, match="timestamp string cannot be empty or whitespace"):
        _normalize_task_datetime("")
    with pytest.raises(ValueError, match="timestamp string cannot be empty or whitespace"):
        _normalize_task_datetime("   ")
    with pytest.raises(ValueError, match="Invalid ISO timestamp string"):
        _normalize_task_datetime("invalid-iso-string")
    with pytest.raises(TypeError, match="timestamp must be a datetime, ISO timestamp string, or None"):
        _normalize_task_datetime(12345)  # type: ignore[arg-type]


def test_user_ref_rejects_empty_or_whitespace_uid():
    """Verify _user_ref validates uid against empty and whitespace-only strings."""
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        _user_ref("")
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        _user_ref("   ")


def test_stable_id_rejects_empty_identifiers():
    """Verify _stable_id validates prefix and parts."""
    with pytest.raises(ValueError, match="prefix must be a non-empty string"):
        _stable_id("", "part1")
    with pytest.raises(ValueError, match="prefix must be a non-empty string"):
        _stable_id("   ", "part1")
    with pytest.raises(ValueError, match="identifier parts must not be empty or whitespace"):
        _stable_id("prefix", "")
    with pytest.raises(ValueError, match="identifier parts must not be empty or whitespace"):
        _stable_id("prefix", "   ")
    with pytest.raises(ValueError, match="identifier parts must not be empty or whitespace"):
        _stable_id("prefix", None)

    sid = _stable_id("prefix", "usr-1", 123)
    assert sid.startswith("prefix_")
    assert len(sid) == len("prefix_") + 32


def test_request_hash_validates_dict():
    """Verify _request_hash requires a dictionary payload."""
    with pytest.raises(TypeError, match="payload must be a dictionary"):
        _request_hash("not-a-dict")  # type: ignore[arg-type]

    h = _request_hash({"key": "value"})
    assert isinstance(h, str)
    assert len(h) == 64


def test_decision_records_handles_corrupt_payloads_safely():
    """Verify _decision_records skips invalid records without raising exceptions."""
    # Non-list input returns empty list
    assert _decision_records(None, "eval-1") == []  # type: ignore[arg-type]
    assert _decision_records("not-a-list", "eval-1") == []  # type: ignore[arg-type]

    # Malformed record items skipped
    malformed = [{"invalid_field": 123}, "not-a-dict", 456]
    assert _decision_records(malformed, "eval-1") == []


def test_valid_evaluation_projection_handles_malformed_safely():
    """Verify _valid_evaluation_projection returns None for non-dict or malformed projections."""
    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    assert _valid_evaluation_projection(None, "eval-1", now) is None
    assert _valid_evaluation_projection("not-a-dict", "eval-1", now) is None
    assert _valid_evaluation_projection({"broken": "data"}, "eval-1", now) is None
