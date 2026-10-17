"""Hermetic unit tests for announcements database resilience, TOCTOU handling, and client injection."""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

from unittest.mock import MagicMock
import pytest

import database.announcements as announcements_db


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
    mock_doc.update.side_effect = Exception("NotFound: Document concurrent deletion")
    mock_client.collection.return_value.document.return_value = mock_doc

    res = announcements_db.deactivate_announcement("ann-raced", firestore_client=mock_client)
    assert res is False


def test_deactivate_announcement_empty_id():
    res = announcements_db.deactivate_announcement("   ")
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
    mock_doc.delete.side_effect = Exception("Transient error")
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
    res1 = announcements_db.dismiss_announcement("", "ann-1")
    assert res1 is False
    res2 = announcements_db.dismiss_announcement("uid-1", "   ")
    assert res2 is False


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
    mock_client.collection.return_value.document.return_value.collection.return_value.stream.return_value = [doc1, doc2]

    ids = announcements_db.get_dismissed_announcement_ids("uid-1", firestore_client=mock_client)
    assert ids == {"ann-1", "ann-2"}


def test_get_dismissed_announcement_ids_empty_uid():
    ids = announcements_db.get_dismissed_announcement_ids("   ")
    assert ids == set()
