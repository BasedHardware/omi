"""Hermetic unit tests for calendar meetings TOCTOU deletion guard, update fallback, and delete handling."""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
sys.path.insert(0, str(BACKEND_DIR))
from tests.unit.memory_import_isolation import install_database_client_stub

install_database_client_stub()

import database.calendar_meetings as calendar_db
import routers.calendar_meetings as calendar_router


def test_delete_meeting_success_and_not_found(monkeypatch):
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = True
    mock_col = MagicMock()
    mock_col.document.return_value = mock_doc
    monkeypatch.setattr(calendar_db, "_get_meetings_collection", lambda uid: mock_col)

    # Exists -> returns True and deletes
    res = calendar_db.delete_meeting("uid_1", "m_1")
    assert res is True
    mock_doc.delete.assert_called_once()

    # Not found -> returns False, no delete
    mock_doc_missing = MagicMock()
    mock_doc_missing.get.return_value.exists = False
    mock_col_missing = MagicMock()
    mock_col_missing.document.return_value = mock_doc_missing
    monkeypatch.setattr(calendar_db, "_get_meetings_collection", lambda uid: mock_col_missing)
    res_missing = calendar_db.delete_meeting("uid_1", "m_2")
    assert res_missing is False


def test_update_meeting_toctou_guard(monkeypatch):
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = True
    mock_doc.update.side_effect = Exception("NotFound: Document was deleted concurrently")
    mock_col = MagicMock()
    mock_col.document.return_value = mock_doc
    monkeypatch.setattr(calendar_db, "_get_meetings_collection", lambda uid: mock_col)

    res = calendar_db.update_meeting("uid_1", "m_1", {"title": "Updated"})
    assert res is False


def test_store_calendar_meeting_update_fallback_to_create(monkeypatch):
    monkeypatch.setattr(calendar_db, "get_meeting_id_by_calendar_event", lambda uid, eid, src: "existing_m_id")
    monkeypatch.setattr(calendar_db, "update_meeting", lambda uid, mid, data: False)

    created_id = None

    def fake_create(uid, data):
        nonlocal created_id
        created_id = "new_m_id"
        return "new_m_id"

    monkeypatch.setattr(calendar_db, "create_meeting", fake_create)

    req = calendar_router.StoreMeetingRequest(
        calendar_event_id="evt-123",
        calendar_source="google_calendar",
        title="Design Sync",
        start_time=datetime(2026, 10, 17, 10, 0, 0, tzinfo=timezone.utc),
        end_time=datetime(2026, 10, 17, 10, 30, 0, tzinfo=timezone.utc),
    )
    res = calendar_router.store_calendar_meeting(req, uid="uid-1")
    assert res.meeting_id == "new_m_id"
    assert created_id == "new_m_id"
