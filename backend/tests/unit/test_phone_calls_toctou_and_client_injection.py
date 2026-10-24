"""Unit tests for phone_calls TOCTOU deletion guard and client injection."""

from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

import database.phone_calls as phone_calls_db
import routers.phone_calls as phone_router


def test_delete_phone_number_success_and_missing():
    mock_doc = MagicMock()
    mock_doc.get.return_value.exists = True

    mock_col = MagicMock()
    mock_col.document.return_value = mock_doc

    mock_user_doc = MagicMock()
    mock_user_doc.collection.return_value = mock_col

    mock_client = MagicMock()
    mock_client.collection.return_value.document.return_value = mock_user_doc

    # Case 1: Exists -> returns True and deletes
    res = phone_calls_db.delete_phone_number("uid_1", "pn_123", client=mock_client)
    assert res is True
    mock_doc.delete.assert_called_once()

    # Case 2: Missing -> returns False, no delete
    mock_doc_missing = MagicMock()
    mock_doc_missing.get.return_value.exists = False
    mock_col.document.return_value = mock_doc_missing
    res_missing = phone_calls_db.delete_phone_number("uid_1", "pn_456", firestore_client=mock_client)
    assert res_missing is False


@patch("routers.phone_calls.phone_calls_db")
@patch("routers.phone_calls.delete_caller_id", return_value=True)
@patch("routers.phone_calls.check_call_access")
def test_remove_phone_number_toctou_not_found(mock_access, mock_delete_caller, mock_db):
    """When a phone number is concurrently deleted before delete_phone_number, raise clean 404."""
    mock_db.get_phone_number.return_value = {"id": "pn1", "phone_number": "+15551234567", "twilio_sid": "PN123"}
    mock_db.delete_phone_number.return_value = False

    with pytest.raises(HTTPException) as exc:
        phone_router.remove_phone_number("pn1", uid="uid_test")

    assert exc.value.status_code == 404
    assert exc.value.detail == "Phone number not found"


@patch("routers.phone_calls.phone_calls_db")
@patch("routers.phone_calls.delete_caller_id", return_value=True)
@patch("routers.phone_calls.check_call_access")
def test_remove_phone_number_success(mock_access, mock_delete_caller, mock_db):
    """Normal deletion deletes Twilio caller ID, then removes Firestore document."""
    mock_db.get_phone_number.return_value = {"id": "pn1", "phone_number": "+15551234567", "twilio_sid": "PN123"}
    mock_db.delete_phone_number.return_value = True

    res = phone_router.remove_phone_number("pn1", uid="uid_test")
    assert res == {"success": True}
    mock_delete_caller.assert_called_once_with("PN123")
    mock_db.delete_phone_number.assert_called_once_with("uid_test", "pn1")


def test_delete_pending_verification_with_client():
    mock_doc = MagicMock()
    mock_col = MagicMock()
    mock_col.document.return_value = mock_doc
    mock_client = MagicMock()
    mock_client.collection.return_value = mock_col

    phone_calls_db.delete_pending_verification("+15551234567", firestore_client=mock_client)
    mock_doc.delete.assert_called_once()


def test_upsert_phone_number_with_firestore_client():
    mock_phone_doc = MagicMock()
    mock_phone_col = MagicMock()
    mock_phone_col.document.return_value = mock_phone_doc

    mock_user_doc = MagicMock()
    mock_user_doc.collection.return_value = mock_phone_col
    # Support data_protection_level read in decorator via firestore_client
    mock_user_doc.get.return_value.exists = True
    mock_user_doc.get.return_value.to_dict.return_value = {"data_protection_level": "standard"}

    mock_client = MagicMock()
    mock_client.collection.return_value.document.return_value = mock_user_doc

    phone_data = {"id": "pn_test", "phone_number": "+15559876543"}
    phone_calls_db.upsert_phone_number("uid_test", phone_data, firestore_client=mock_client)
    mock_phone_doc.set.assert_called_once()


def test_client_injection_bypasses_global_db():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_client.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_doc
    mock_doc.get.return_value.exists = True

    # Direct attribute assignment avoids triggering unittest.mock inspect on LazyProxy
    original_db = phone_calls_db.db
    mock_global_db = MagicMock()
    phone_calls_db.db = mock_global_db
    try:
        res = phone_calls_db.delete_phone_number("uid_1", "pn_123", client=mock_client)
        assert res is True
        mock_global_db.collection.assert_not_called()
    finally:
        phone_calls_db.db = original_db
