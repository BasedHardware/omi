"""Unit tests for database/calendar_meetings.py input validation and resilience guards."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from google.api_core.exceptions import GoogleAPICallError
import pytest

import database.calendar_meetings as calendar_db


def test_validate_uid_rejects_empty_whitespace_or_path_traversal():
    for bad in ["", "   ", None, "users/admin", "../evil", "/root"]:
        with pytest.raises(ValueError, match="Invalid user ID"):
            calendar_db._validate_uid(bad)

    assert calendar_db._validate_uid("user-123") == "user-123"
    assert calendar_db._validate_uid("  user-abc  ") == "user-abc"


def test_validate_meeting_id_rejects_empty_whitespace_or_path_traversal():
    for bad in ["", "   ", None, "meetings/sub", "../evil"]:
        with pytest.raises(ValueError, match="Invalid meeting ID"):
            calendar_db._validate_meeting_id(bad)

    assert calendar_db._validate_meeting_id("meeting-123") == "meeting-123"
    assert calendar_db._validate_meeting_id("  mtg-456  ") == "mtg-456"


def test_to_utc_handles_various_datetime_representations():
    utc_now = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
    naive = datetime(2026, 9, 29, 12, 0, 0)
    assert calendar_db._to_utc(naive) == utc_now

    offset_time = datetime(2026, 9, 29, 14, 0, 0, tzinfo=timezone(timedelta(hours=2)))
    assert calendar_db._to_utc(offset_time) == utc_now

    iso_str = "2026-09-29T12:00:00Z"
    assert calendar_db._to_utc(iso_str) == utc_now

    iso_offset_str = "2026-09-29T14:00:00+02:00"
    assert calendar_db._to_utc(iso_offset_str) == utc_now


def test_to_utc_raises_on_unparseable_inputs():
    for bad in [None, "", "   ", "not-a-datetime", 12345, [], {}]:
        with pytest.raises(ValueError, match="Cannot convert|Invalid ISO datetime"):
            calendar_db._to_utc(bad)


def test_create_meeting_validates_inputs_and_upserts(monkeypatch):
    mock_db = MagicMock()
    mock_coll = MagicMock()
    mock_doc = MagicMock()
    mock_tx = MagicMock()

    mock_db.collection.return_value.document.return_value.collection.return_value = mock_coll
    mock_coll.document.return_value = mock_doc
    mock_doc.get.return_value.exists = False
    mock_db.transaction.return_value = mock_tx

    monkeypatch.setattr(calendar_db, "db", mock_db)
    monkeypatch.setattr(calendar_db, "calendar_meeting_doc_id", lambda uid, src, eid: f"deterministic-{src}-{eid}")

    # Missing fields
    with pytest.raises(ValueError, match="meeting_data must be a dictionary"):
        calendar_db.create_meeting("uid1", "not-a-dict")  # type: ignore

    with pytest.raises(ValueError, match="calendar_source and calendar_event_id are required"):
        calendar_db.create_meeting("uid1", {"title": "No source"})

    with pytest.raises(ValueError, match="calendar_source and calendar_event_id are required"):
        calendar_db.create_meeting("uid1", {"calendar_source": "", "calendar_event_id": "e1"})

    # Valid call
    meeting_data = {
        "calendar_source": "google_calendar",
        "calendar_event_id": "evt-999",
        "title": "Strategy Sync",
        "start_time": datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc),
        "end_time": datetime(2026, 9, 29, 11, 0, 0, tzinfo=timezone.utc),
    }

    meeting_id = calendar_db.create_meeting("uid1", meeting_data)
    assert meeting_id == "deterministic-google_calendar-evt-999"
    mock_tx.set.assert_called_once()
    payload = mock_tx.set.call_args[0][1]
    assert payload["title"] == "Strategy Sync"
    assert payload["start_time"] == datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc)
    assert "synced_at" in payload
    assert "created_at" in payload


def test_update_meeting_handles_existence_and_bad_times(monkeypatch):
    mock_db = MagicMock()
    mock_coll = MagicMock()
    mock_doc = MagicMock()

    mock_db.collection.return_value.document.return_value.collection.return_value = mock_coll
    mock_coll.document.return_value = mock_doc

    monkeypatch.setattr(calendar_db, "db", mock_db)

    # Invalid uid or meeting_id
    assert calendar_db.update_meeting("", "m1", {"title": "T"}) is False
    assert calendar_db.update_meeting("uid1", "", {"title": "T"}) is False
    assert calendar_db.update_meeting("uid1", "m1", None) is False

    # Document not found
    mock_doc.get.return_value.exists = False
    assert calendar_db.update_meeting("uid1", "m1", {"title": "T"}) is False

    # Document found, valid update
    mock_doc.get.return_value.exists = True
    assert calendar_db.update_meeting("uid1", "m1", {"title": "Updated"}) is True
    mock_doc.update.assert_called_once()
    updated_payload = mock_doc.update.call_args[0][0]
    assert updated_payload["title"] == "Updated"
    assert "synced_at" in updated_payload

    # Document found, unparseable start_time returns False (does not write bad time)
    mock_doc.update.reset_mock()
    assert calendar_db.update_meeting("uid1", "m1", {"start_time": "invalid-datetime-string"}) is False
    mock_doc.update.assert_not_called()


def test_get_meeting_guards_and_returns(monkeypatch):
    mock_db = MagicMock()
    mock_coll = MagicMock()
    mock_doc = MagicMock()

    mock_db.collection.return_value.document.return_value.collection.return_value = mock_coll
    mock_coll.document.return_value = mock_doc

    monkeypatch.setattr(calendar_db, "db", mock_db)

    assert calendar_db.get_meeting("", "m1") is None
    assert calendar_db.get_meeting("uid1", "") is None

    # Missing doc
    mock_doc.get.return_value.exists = False
    assert calendar_db.get_meeting("uid1", "m1") is None

    # Existing doc
    mock_doc.get.return_value.exists = True
    mock_doc.get.return_value.to_dict.return_value = {"title": "Planning"}
    mock_doc.get.return_value.id = "m1"
    res = calendar_db.get_meeting("uid1", "m1")
    assert res == {"title": "Planning", "id": "m1"}


def test_get_meeting_id_by_calendar_event_guards_inputs(monkeypatch):
    mock_db = MagicMock()
    mock_coll = MagicMock()
    mock_query = MagicMock()

    mock_db.collection.return_value.document.return_value.collection.return_value = mock_coll
    mock_coll.where.return_value.where.return_value.limit.return_value = mock_query

    monkeypatch.setattr(calendar_db, "db", mock_db)

    # Empty inputs return None without query
    assert calendar_db.get_meeting_id_by_calendar_event("", "evt-1", "src-1") is None
    assert calendar_db.get_meeting_id_by_calendar_event("uid1", "", "src-1") is None
    assert calendar_db.get_meeting_id_by_calendar_event("uid1", "evt-1", "") is None
    mock_coll.where.assert_not_called()

    # Found
    fake_doc = MagicMock()
    fake_doc.id = "doc-found-1"
    mock_query.stream.return_value = [fake_doc]
    assert calendar_db.get_meeting_id_by_calendar_event("uid1", "evt-1", "src-1") == "doc-found-1"

    # Not found
    mock_query.stream.return_value = []
    assert calendar_db.get_meeting_id_by_calendar_event("uid1", "evt-2", "src-1") is None


def test_list_meetings_bounds_clamping_and_date_inversion(monkeypatch):
    mock_db = MagicMock()
    mock_coll = MagicMock()
    mock_query = MagicMock()

    mock_db.collection.return_value.document.return_value.collection.return_value = mock_coll
    mock_coll.where.return_value = mock_query
    mock_query.where.return_value = mock_query
    mock_query.order_by.return_value.limit.return_value.stream.return_value = []
    mock_coll.order_by.return_value.limit.return_value.stream.return_value = []

    monkeypatch.setattr(calendar_db, "db", mock_db)

    # Invalid uid
    assert calendar_db.list_meetings("") == []

    # Inverted date range
    t_start = datetime(2026, 9, 29, 15, 0, 0, tzinfo=timezone.utc)
    t_end = datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc)
    assert calendar_db.list_meetings("uid1", start_date=t_start, end_date=t_end) == []

    # Unparseable dates fail safe to empty list
    assert calendar_db.list_meetings("uid1", start_date="unparseable-date") == []  # type: ignore[arg-type]

    # Limit clamping: negative limit clamped to 1, huge limit clamped to 500
    calendar_db.list_meetings("uid1", limit=-10)
    mock_coll.order_by.return_value.limit.assert_called_with(1)

    calendar_db.list_meetings("uid1", limit=99999)
    mock_coll.order_by.return_value.limit.assert_called_with(500)


def test_delete_meeting_and_delete_old_meetings(monkeypatch):
    mock_db = MagicMock()
    mock_coll = MagicMock()
    mock_doc = MagicMock()
    mock_batch = MagicMock()

    mock_db.collection.return_value.document.return_value.collection.return_value = mock_coll
    mock_coll.document.return_value = mock_doc
    mock_db.batch.return_value = mock_batch

    monkeypatch.setattr(calendar_db, "db", mock_db)

    # delete_meeting
    assert calendar_db.delete_meeting("", "m1") is False
    assert calendar_db.delete_meeting("uid1", "") is False
    assert calendar_db.delete_meeting("uid1", "m1") is True
    mock_doc.delete.assert_called_once()

    # delete_old_meetings invalid
    assert calendar_db.delete_old_meetings("", datetime.now(timezone.utc)) == 0
    assert calendar_db.delete_old_meetings("uid1", "not-a-datetime") == 0  # type: ignore
    assert calendar_db.delete_old_meetings("uid1", None) == 0

    # delete_old_meetings valid batch
    mock_doc1 = MagicMock()
    mock_doc2 = MagicMock()
    mock_coll.where.return_value.stream.return_value = [mock_doc1, mock_doc2]
    deleted = calendar_db.delete_old_meetings("uid1", datetime.now(timezone.utc))
    assert deleted == 2
    assert mock_batch.delete.call_count == 2
    mock_batch.commit.assert_called_once()


def test_get_meetings_in_time_range_with_fallback(monkeypatch):
    mock_db = MagicMock()
    mock_coll = MagicMock()
    mock_query = MagicMock()

    mock_db.collection.return_value.document.return_value.collection.return_value = mock_coll
    mock_coll.where.return_value.where.return_value.order_by.return_value.limit.return_value = mock_query

    monkeypatch.setattr(calendar_db, "db", mock_db)

    # Invalid range: start >= end
    t1 = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 9, 29, 10, 0, 0, tzinfo=timezone.utc)
    assert calendar_db.get_meetings_in_time_range("uid1", t1, t2) == []

    # Successful composite query
    doc1 = MagicMock()
    doc1.id = "m1"
    doc1.to_dict.return_value = {"title": "Meeting 1"}
    mock_query.stream.return_value = [doc1]
    res = calendar_db.get_meetings_in_time_range("uid1", t2, t1)
    assert len(res) == 1
    assert res[0]["id"] == "m1"

    # Fallback when composite query raises GoogleAPICallError (missing composite index)
    mock_query.stream.side_effect = GoogleAPICallError("Inequality query on multiple properties unsupported")
    fallback_query = MagicMock()
    mock_coll.where.return_value.order_by.return_value.limit.return_value = fallback_query

    doc_fallback = MagicMock()
    doc_fallback.id = "m-fallback"
    doc_fallback.to_dict.return_value = {
        "title": "Fallback Meeting",
        "end_time": datetime(2026, 9, 29, 11, 0, 0, tzinfo=timezone.utc),
    }
    fallback_query.stream.return_value = [doc_fallback]

    res_fallback = calendar_db.get_meetings_in_time_range("uid1", t2, t1)
    assert len(res_fallback) == 1
    assert res_fallback[0]["id"] == "m-fallback"
