"""Hermetic unit tests for announcements database resilience, TOCTOU handling, and client injection."""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from google.api_core.exceptions import NotFound

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.memory_import_isolation import install_database_client_stub

install_database_client_stub()

import database.announcements as announcements_db


def test_update_announcement_success():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = True
    mock_client.collection.return_value.document.return_value = mock_doc

    mock_ann = MagicMock()
    mock_ann.id = "ann-1"

    with patch.object(announcements_db, "get_announcement_by_id", return_value=mock_ann):
        res = announcements_db.update_announcement("ann-1", {"active": False}, firestore_client=mock_client)
        assert res == mock_ann
        mock_doc.update.assert_called_once_with({"active": False})


def test_update_announcement_missing_doc():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = False
    mock_client.collection.return_value.document.return_value = mock_doc

    res = announcements_db.update_announcement("ann-missing", {"active": False}, firestore_client=mock_client)
    assert res is None


def test_update_announcement_toctou_exception_returns_none():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = True
    mock_doc.update.side_effect = NotFound("Concurrent deletion")
    mock_client.collection.return_value.document.return_value = mock_doc

    res = announcements_db.update_announcement("ann-raced", {"active": False}, firestore_client=mock_client)
    assert res is None


def test_update_announcement_empty_id():
    mock_client = MagicMock()
    res = announcements_db.update_announcement("   ", {"active": False}, firestore_client=mock_client)
    assert res is None


def test_deactivate_announcement_success():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = True
    mock_client.collection.return_value.document.return_value = mock_doc

    res = announcements_db.deactivate_announcement("ann-1", firestore_client=mock_client)
    assert res is True
    mock_doc.update.assert_called_once_with({"active": False})


def test_deactivate_announcement_missing_doc():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = False
    mock_client.collection.return_value.document.return_value = mock_doc

    res = announcements_db.deactivate_announcement("ann-missing", firestore_client=mock_client)
    assert res is False


def test_deactivate_announcement_toctou_race_guard():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = True
    mock_doc.update.side_effect = NotFound("Document concurrent deletion")
    mock_client.collection.return_value.document.return_value = mock_doc

    res = announcements_db.deactivate_announcement("ann-raced", firestore_client=mock_client)
    assert res is False


def test_deactivate_announcement_empty_id():
    mock_client = MagicMock()
    res = announcements_db.deactivate_announcement("   ", firestore_client=mock_client)
    assert res is False


def test_delete_announcement_success():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = True
    mock_client.collection.return_value.document.return_value = mock_doc

    res = announcements_db.delete_announcement("ann-del", firestore_client=mock_client)
    assert res is True
    mock_doc.delete.assert_called_once()


def test_delete_announcement_toctou_race():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = True
    mock_doc.delete.side_effect = NotFound("Concurrent deletion")
    mock_client.collection.return_value.document.return_value = mock_doc

    res = announcements_db.delete_announcement("ann-err", firestore_client=mock_client)
    assert res is False


def test_dismiss_announcement_success():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_client.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_doc

    res = announcements_db.dismiss_announcement("uid-1", "ann-1", cta_clicked=True, firestore_client=mock_client)
    assert res is True
    mock_doc.set.assert_called_once()
    payload = mock_doc.set.call_args[0][0]
    assert payload["cta_clicked"] is True
    assert "dismissed_at" in payload


def test_dismiss_announcement_empty_inputs():
    mock_client = MagicMock()
    with pytest.raises(ValueError, match="uid cannot be empty"):
        announcements_db.dismiss_announcement("", "ann-1", firestore_client=mock_client)
    with pytest.raises(ValueError, match="announcement_id cannot be empty"):
        announcements_db.dismiss_announcement("uid-1", "   ", firestore_client=mock_client)


def test_is_announcement_dismissed_true():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = True
    mock_client.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_doc

    res = announcements_db.is_announcement_dismissed("uid-1", "ann-1", firestore_client=mock_client)
    assert res is True


def test_is_announcement_dismissed_false():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = False
    mock_client.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_doc

    res = announcements_db.is_announcement_dismissed("uid-1", "ann-missing", firestore_client=mock_client)
    assert res is False


def test_get_dismissed_announcement_ids():
    mock_client = MagicMock()
    doc1 = MagicMock()
    doc1.id = "ann-1"
    doc2 = MagicMock()
    doc2.id = "ann-2"
    mock_client.collection.return_value.document.return_value.collection.return_value.stream.return_value = [
        doc1,
        doc2,
    ]

    ids = announcements_db.get_dismissed_announcement_ids("uid-1", firestore_client=mock_client)
    assert ids == {"ann-1", "ann-2"}


def test_get_dismissed_announcement_ids_empty_uid():
    mock_client = MagicMock()
    ids = announcements_db.get_dismissed_announcement_ids("   ", firestore_client=mock_client)
    assert ids == set()


def test_get_pending_announcements_with_injected_client():
    mock_client = MagicMock()
    # Mock stream for active announcements
    mock_client.collection.return_value.where.return_value.where.return_value.stream.return_value = []
    # Mock stream for dismissed announcements
    mock_client.collection.return_value.document.return_value.collection.return_value.stream.return_value = []

    res = announcements_db.get_pending_announcements(
        "uid-1", "1.0.0", "ios", "app_launch", firestore_client=mock_client
    )
    assert res == []
