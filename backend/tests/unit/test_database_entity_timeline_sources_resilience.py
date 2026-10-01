"""Hermetic unit tests verifying defensive boundary guards in database.entity_timeline_sources."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest

from database.entity_timeline_sources import (
    _bounded_identity_segments,
    _normalize_timeline_datetime,
    list_entity_timeline_conversations,
    list_entity_timeline_meetings,
    list_entity_timeline_screen_activity,
)


def test_normalize_timeline_datetime_handles_iso_strings():
    """Verify ISO strings with Z and offsets are normalized to UTC."""
    res_z = _normalize_timeline_datetime("2026-09-30T10:00:00Z")
    assert res_z == datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)

    res_offset = _normalize_timeline_datetime("2026-09-30T12:00:00+02:00")
    assert res_offset == datetime(2026, 9, 30, 10, 0, 0, tzinfo=timezone.utc)


def test_normalize_timeline_datetime_coerces_naive_datetime():
    """Verify naive datetimes are coerced to timezone.utc."""
    naive_dt = datetime(2026, 9, 30, 10, 0, 0)
    res = _normalize_timeline_datetime(naive_dt)
    assert res is not None
    assert res.tzinfo == timezone.utc
    assert res.year == 2026
    assert res.hour == 10


def test_normalize_timeline_datetime_rejects_invalid_values():
    """Verify empty strings, malformed strings, and bad types raise ValueError or TypeError."""
    assert _normalize_timeline_datetime(None) is None

    with pytest.raises(ValueError, match="date string cannot be empty or whitespace"):
        _normalize_timeline_datetime("")
    with pytest.raises(ValueError, match="date string cannot be empty or whitespace"):
        _normalize_timeline_datetime("   ")
    with pytest.raises(ValueError, match="Invalid ISO timestamp string"):
        _normalize_timeline_datetime("not-a-timestamp")
    with pytest.raises(TypeError, match="date must be a datetime, ISO timestamp string, or None"):
        _normalize_timeline_datetime(12345)  # type: ignore[arg-type]


def test_bounded_identity_segments_fails_closed_on_corrupt_input():
    """Verify invalid uid or non-dict data fails closed returning empty list."""
    assert _bounded_identity_segments("", {"transcript_segments": []}) == []
    assert _bounded_identity_segments("   ", {"transcript_segments": []}) == []
    assert _bounded_identity_segments("usr-1", None) == []  # type: ignore[arg-type]
    assert _bounded_identity_segments("usr-1", "not-a-dict") == []  # type: ignore[arg-type]


def test_list_conversations_guards_uid_and_db_client():
    """Verify list_entity_timeline_conversations validates uid and db_client."""
    mock_db = MagicMock()
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        list_entity_timeline_conversations("", db_client=mock_db, limit=10)
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        list_entity_timeline_conversations("   ", db_client=mock_db, limit=10)
    with pytest.raises(ValueError, match="db_client must not be None"):
        list_entity_timeline_conversations("usr-1", db_client=None, limit=10)


def test_list_conversations_guards_limit_type_and_bounds():
    """Verify limit must be integer between 1 and 501."""
    mock_db = MagicMock()
    with pytest.raises(TypeError, match="limit must be an integer"):
        list_entity_timeline_conversations("usr-1", db_client=mock_db, limit="10")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="limit must be an integer"):
        list_entity_timeline_conversations("usr-1", db_client=mock_db, limit=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="limit must be between 1 and 501"):
        list_entity_timeline_conversations("usr-1", db_client=mock_db, limit=0)
    with pytest.raises(ValueError, match="limit must be between 1 and 501"):
        list_entity_timeline_conversations("usr-1", db_client=mock_db, limit=502)


def test_list_conversations_rejects_inverted_date_range():
    """Verify start_date > end_date raises ValueError."""
    mock_db = MagicMock()
    start = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
    end = datetime(2026, 9, 30, 10, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="start_date cannot be after end_date"):
        list_entity_timeline_conversations("usr-1", db_client=mock_db, limit=10, start_date=start, end_date=end)


def test_list_meetings_and_screen_activity_guards():
    """Verify list_entity_timeline_meetings and list_entity_timeline_screen_activity validate inputs."""
    mock_db = MagicMock()
    # meetings guards
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        list_entity_timeline_meetings("", db_client=mock_db, limit=10)
    with pytest.raises(ValueError, match="db_client must not be None"):
        list_entity_timeline_meetings("usr-1", db_client=None, limit=10)
    with pytest.raises(TypeError, match="limit must be an integer"):
        list_entity_timeline_meetings("usr-1", db_client=mock_db, limit=False)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="limit must be between 1 and 501"):
        list_entity_timeline_meetings("usr-1", db_client=mock_db, limit=0)

    # screen activity guards
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        list_entity_timeline_screen_activity("   ", db_client=mock_db, limit=10)
    with pytest.raises(ValueError, match="db_client must not be None"):
        list_entity_timeline_screen_activity("usr-1", db_client=None, limit=10)
    with pytest.raises(TypeError, match="limit must be an integer"):
        list_entity_timeline_screen_activity("usr-1", db_client=mock_db, limit="invalid")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="limit must be between 1 and 501"):
        list_entity_timeline_screen_activity("usr-1", db_client=mock_db, limit=600)
