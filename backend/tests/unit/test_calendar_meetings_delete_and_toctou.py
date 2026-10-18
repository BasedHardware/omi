"""Hermetic unit tests for calendar meetings TOCTOU deletion guard, update fallback, and delete handling."""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from google.api_core.exceptions import NotFound as _NotFound
except (ImportError, ModuleNotFoundError):

    class _NotFound(Exception):
        pass


import database.calendar_meetings as calendar_db
from database.document_ids import calendar_meeting_doc_id


@pytest.fixture(autouse=True)
def isolate_database_client(monkeypatch):
    mock_db = MagicMock()
    monkeypatch.setattr(calendar_db, "db", mock_db)
    yield mock_db


def test_update_meeting_success(monkeypatch):
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = True
    mock_client.collection.return_value.document.return_value.collection.return_value.document.return_value = (
        mock_doc
    )
    monkeypatch.setattr(calendar_db, "db", mock_client)

    res = calendar_db.update_meeting("uid-1", "meet-1", {"title": "Updated Meeting"})
    assert res is True
    mock_doc.update.assert_called_once()


def test_update_meeting_missing():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = False
    mock_client.collection.return_value.document.return_value.collection.return_value.document.return_value = (
        mock_doc
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(calendar_db, "db", mock_client)
        res = calendar_db.update_meeting("uid-1", "meet-missing", {"title": "Test"})
        assert res is False


def test_update_meeting_toctou_not_found():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = True
    mock_doc.update.side_effect = _NotFound("Meeting deleted concurrently")
    mock_client.collection.return_value.document.return_value.collection.return_value.document.return_value = (
        mock_doc
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(calendar_db, "db", mock_client)
        res = calendar_db.update_meeting("uid-1", "meet-raced", {"title": "Test"})
        assert res is False


def test_delete_meeting_success():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = True
    mock_client.collection.return_value.document.return_value.collection.return_value.document.return_value = (
        mock_doc
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(calendar_db, "db", mock_client)
        res = calendar_db.delete_meeting("uid-1", "meet-1")
        assert res is True
        mock_doc.delete.assert_called_once()


def test_delete_meeting_missing():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = False
    mock_client.collection.return_value.document.return_value.collection.return_value.document.return_value = (
        mock_doc
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(calendar_db, "db", mock_client)
        res = calendar_db.delete_meeting("uid-1", "meet-missing")
        assert res is False
