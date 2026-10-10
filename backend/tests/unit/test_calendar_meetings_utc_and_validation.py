"""Unit tests for calendar meetings UTC normalization, duration validation, and query filter ordering."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

import database.calendar_meetings as calendar_db
import routers.calendar_meetings as calendar_router


def test_store_calendar_meeting_normalizes_mixed_naive_and_offset_times_to_utc(monkeypatch):
    captured = {}

    monkeypatch.setattr(calendar_db, 'get_meeting_id_by_calendar_event', lambda uid, eid, src: None)

    def fake_create_meeting(uid, data):
        captured.update(data)
        return 'meeting-doc-1'

    monkeypatch.setattr(calendar_db, 'create_meeting', fake_create_meeting)

    plus_two = timezone(timedelta(hours=2))
    req = calendar_router.StoreMeetingRequest(
        calendar_event_id='evt-1',
        calendar_source='google_calendar',
        title='Sync Call',
        start_time=datetime(2026, 9, 24, 14, 0, 0, tzinfo=plus_two),  # 12:00 UTC
        end_time=datetime(2026, 9, 24, 12, 45, 0),  # naive -> 12:45 UTC
    )
    res = calendar_router.store_calendar_meeting(req, uid='uid-1')
    assert res.meeting_id == 'meeting-doc-1'
    assert captured['start_time'] == datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
    assert captured['end_time'] == datetime(2026, 9, 24, 12, 45, 0, tzinfo=timezone.utc)
    assert captured['duration_minutes'] == 45


def test_store_calendar_meeting_rejects_end_time_not_after_start_time():
    req = calendar_router.StoreMeetingRequest(
        calendar_event_id='evt-2',
        calendar_source='macos_calendar',
        title='Invalid Window',
        start_time=datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc),
    )
    with pytest.raises(HTTPException) as exc_info:
        calendar_router.store_calendar_meeting(req, uid='uid-1')
    assert exc_info.value.status_code == 422


def test_list_meetings_applies_where_filters_in_utc_before_limit(monkeypatch):
    calls = []

    class FakeQuery:
        def where(self, field, op, value):
            calls.append(('where', field, op, value))
            return self

        def order_by(self, field, direction=None):
            calls.append(('order_by', field))
            return self

        def limit(self, count):
            calls.append(('limit', count))
            return self

        def stream(self):
            doc = MagicMock()
            doc.id = 'm-1'
            doc.to_dict.return_value = {'title': 'Standup'}
            return [doc]

    monkeypatch.setattr(calendar_db, '_get_meetings_collection', lambda uid: FakeQuery())

    naive_start = datetime(2026, 9, 24, 9, 0, 0)
    naive_end = datetime(2026, 9, 24, 18, 0, 0)
    items = calendar_db.list_meetings('uid-1', start_date=naive_start, end_date=naive_end, limit=10)
    assert len(items) == 1
    assert calls[0] == ('where', 'start_time', '>=', datetime(2026, 9, 24, 9, 0, 0, tzinfo=timezone.utc))
    assert calls[1] == ('where', 'start_time', '<=', datetime(2026, 9, 24, 18, 0, 0, tzinfo=timezone.utc))
    assert calls[2] == ('order_by', 'start_time')
    assert calls[3] == ('limit', 10)


def test_store_meeting_request_rejects_empty_and_whitespace_only_fields():
    with pytest.raises(Exception):
        calendar_router.StoreMeetingRequest(
            calendar_event_id='',
            calendar_source='google_calendar',
            title='Valid Title',
            start_time=datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 9, 24, 12, 30, 0, tzinfo=timezone.utc),
        )

    with pytest.raises(Exception):
        calendar_router.StoreMeetingRequest(
            calendar_event_id='evt-1',
            calendar_source='   ',
            title='Valid Title',
            start_time=datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 9, 24, 12, 30, 0, tzinfo=timezone.utc),
        )

    with pytest.raises(Exception):
        calendar_router.StoreMeetingRequest(
            calendar_event_id='evt-1',
            calendar_source='google_calendar',
            title='  \t\n  ',
            start_time=datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc),
            end_time=datetime(2026, 9, 24, 12, 30, 0, tzinfo=timezone.utc),
        )


def test_store_meeting_request_strips_leading_and_trailing_whitespace():
    req = calendar_router.StoreMeetingRequest(
        calendar_event_id='  evt-clean-1  ',
        calendar_source='  macos_calendar  ',
        title='  Standup Discussion  ',
        start_time=datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 9, 24, 12, 30, 0, tzinfo=timezone.utc),
    )
    assert req.calendar_event_id == 'evt-clean-1'
    assert req.calendar_source == 'macos_calendar'
    assert req.title == 'Standup Discussion'


def test_clean_id_rejects_empty_whitespace_and_path_traversal():
    with pytest.raises(ValueError, match="cannot be empty or whitespace-only"):
        calendar_db._clean_id("", "uid")

    with pytest.raises(ValueError, match="cannot be empty or whitespace-only"):
        calendar_db._clean_id("   ", "uid")

    with pytest.raises(ValueError, match="cannot contain path separator"):
        calendar_db._clean_id("user/admin", "uid")

    with pytest.raises(ValueError, match="cannot contain path separator"):
        calendar_db._clean_id("..\\nested", "meeting_id")

    with pytest.raises(ValueError, match="must be a string"):
        calendar_db._clean_id(12345, "uid")  # type: ignore

    assert calendar_db._clean_id("  valid-id-123  ", "uid") == "valid-id-123"


def test_to_utc_strictly_raises_on_non_datetime_type():
    with pytest.raises(ValueError, match="Expected datetime instance"):
        calendar_db._to_utc("2026-09-24T12:00:00Z")  # string instead of datetime

    with pytest.raises(ValueError, match="Expected datetime instance"):
        calendar_db._to_utc(1727179200)  # integer timestamp instead of datetime


def test_list_meetings_clamps_limit_bounds(monkeypatch):
    calls = []

    class FakeQuery:
        def order_by(self, field, direction=None):
            return self

        def limit(self, count):
            calls.append(count)
            return self

        def stream(self):
            return []

    monkeypatch.setattr(calendar_db, '_get_meetings_collection', lambda uid, client=None: FakeQuery())

    # Underflow limit clamped to 1
    calendar_db.list_meetings('uid-1', limit=-5)
    assert calls[-1] == 1

    calendar_db.list_meetings('uid-1', limit=0)
    assert calls[-1] == 1

    # Overflow limit clamped to 500
    calendar_db.list_meetings('uid-1', limit=1000)
    assert calls[-1] == 500


def test_update_meeting_handles_not_found_with_merge_upsert():
    from google.api_core import exceptions

    doc_ref = MagicMock()
    doc_ref.update.side_effect = exceptions.NotFound("Document missing")

    fake_client = MagicMock()
    fake_client.collection.return_value.document.return_value.collection.return_value.document.return_value = doc_ref

    meeting_data = {'title': 'Updated Title'}
    calendar_db.update_meeting('uid-1', 'meeting-123', meeting_data, db_client=fake_client)

    # doc_ref.set must have been called with merge=True as fallback
    doc_ref.set.assert_called_once_with(meeting_data, merge=True)


def test_get_calendar_meeting_route_rejects_invalid_id_format():
    with pytest.raises(HTTPException) as exc_info:
        calendar_router.get_calendar_meeting(meeting_id="../traversal", uid="uid-1")
    assert exc_info.value.status_code == 400

    with pytest.raises(HTTPException) as exc_info:
        calendar_router.get_calendar_meeting(meeting_id="   ", uid="uid-1")
    assert exc_info.value.status_code == 400
