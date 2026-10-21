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
