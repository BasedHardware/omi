"""Unit tests for calendar meetings TOCTOU deletion guard, update fallback, and client injection."""

from datetime import datetime, timezone
from unittest.mock import MagicMock
import pytest

import database.calendar_meetings as calendar_db
import routers.calendar_meetings as calendar_router


def test_delete_meeting_success_and_not_found():
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = True

    mock_col = MagicMock()
    mock_col.document.return_value = mock_doc

    mock_client = MagicMock()
    mock_client.collection.return_value.document.return_value.collection.return_value = mock_col

    # Case 1: Exists -> Returns True and calls delete
    res = calendar_db.delete_meeting("uid_1", "meeting_1", client=mock_client)
    assert res is True
    mock_doc.delete.assert_called_once()

    # Case 2: Does not exist -> Returns False, no delete
    mock_doc_missing = MagicMock()
    mock_doc_missing.get.return_value.exists = False
    mock_col.document.return_value = mock_doc_missing
    res_missing = calendar_db.delete_meeting("uid_1", "meeting_2", client=mock_client)
    assert res_missing is False


def test_update_meeting_toctou_guard():
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = True
    mock_doc.update.side_effect = Exception("NotFound: Document was deleted concurrently")

    mock_col = MagicMock()
    mock_col.document.return_value = mock_doc
    mock_client = MagicMock()
    mock_client.collection.return_value.document.return_value.collection.return_value = mock_col

    res = calendar_db.update_meeting("uid_1", "meeting_1", {"title": "Updated"}, client=mock_client)
    assert res is False


def test_store_calendar_meeting_update_fallback_to_create(monkeypatch):
    monkeypatch.setattr(calendar_db, 'get_meeting_id_by_calendar_event', lambda uid, eid, src: 'existing_m_id')

    # Simulate update failure (concurrently deleted)
    monkeypatch.setattr(calendar_db, 'update_meeting', lambda uid, mid, data, **kw: False)

    created_id = None

    def fake_create(uid, data):
        nonlocal created_id
        created_id = 'new_m_id'
        return 'new_m_id'

    monkeypatch.setattr(calendar_db, 'create_meeting', fake_create)

    req = calendar_router.StoreMeetingRequest(
        calendar_event_id='evt-123',
        calendar_source='google_calendar',
        title='Design Sync',
        start_time=datetime(2026, 10, 17, 10, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 10, 17, 10, 30, 0, tzinfo=timezone.utc),
    )
    res = calendar_router.store_calendar_meeting(req, uid='uid-1')
    assert res.meeting_id == 'new_m_id'
    assert created_id == 'new_m_id'
