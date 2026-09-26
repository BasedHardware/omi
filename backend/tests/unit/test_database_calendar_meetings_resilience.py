"""Tests for database.calendar_meetings resilience, parameter validation, and merge writes."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

import database.calendar_meetings as calendar_db


def test_update_meeting_uses_set_merge(monkeypatch):
    fake_doc = MagicMock()
    fake_coll = MagicMock()
    fake_coll.document.return_value = fake_doc

    monkeypatch.setattr(calendar_db, '_get_meetings_collection', lambda uid: fake_coll)

    update_payload = {'title': 'Updated Title', 'location': 'Room A'}
    calendar_db.update_meeting('user-1', 'meeting-123', update_payload)

    fake_coll.document.assert_called_once_with('meeting-123')
    fake_doc.set.assert_called_once()
    args, kwargs = fake_doc.set.call_args
    assert kwargs.get('merge') is True
    assert args[0]['title'] == 'Updated Title'
    assert args[0]['location'] == 'Room A'
    assert 'synced_at' in args[0]
    assert isinstance(args[0]['synced_at'], datetime)


def test_update_meeting_empty_id_raises_value_error():
    with pytest.raises(ValueError, match="meeting_id is required"):
        calendar_db.update_meeting('user-1', '', {'title': 'New Title'})


def test_create_meeting_missing_fields_raises_value_error():
    with pytest.raises(ValueError, match="meeting_data must include 'calendar_source' and 'calendar_event_id'"):
        calendar_db.create_meeting('user-1', {'calendar_source': 'google'})

    with pytest.raises(ValueError, match="meeting_data must include 'calendar_source' and 'calendar_event_id'"):
        calendar_db.create_meeting('user-1', {'calendar_event_id': 'evt-1'})


def test_delete_meeting_empty_id_raises_value_error():
    with pytest.raises(ValueError, match="meeting_id is required"):
        calendar_db.delete_meeting('user-1', '')


def test_to_utc_non_datetime_raises_type_error():
    with pytest.raises(TypeError, match="Expected datetime, got str"):
        calendar_db._to_utc('2026-09-24T12:00:00')

    with pytest.raises(TypeError, match="Expected datetime, got NoneType"):
        calendar_db._to_utc(None)


def test_to_utc_validates_timezone_conversion():
    naive = datetime(2026, 9, 24, 12, 0, 0)
    utc_res = calendar_db._to_utc(naive)
    assert utc_res.tzinfo == timezone.utc
    assert utc_res.hour == 12
