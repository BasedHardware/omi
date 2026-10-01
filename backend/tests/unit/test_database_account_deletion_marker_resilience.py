"""Unit tests verifying resilience and defensive guards in account_deletion_marker."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
from google.api_core.exceptions import GoogleAPICallError, NotFound

from database.account_deletion_marker import (
    ACCOUNT_DELETION_COLLECTION,
    account_deletion_collection,
    account_deletion_document,
    account_deletion_firestore_client,
    get_user_deletion_wipe_status,
    _validate_uid,
)
from database.account_deletion_policy import ACCOUNT_DELETION_INVALID_STATUS
from database.firestore_read_metrics import FirestoreReadOutcome, FirestoreReadSite


def test_validate_uid_rejects_invalid_types_and_empty():
    """Verify _validate_uid rejects non-string, empty, and whitespace strings."""
    with pytest.raises(ValueError, match="uid must be a non-empty string without whitespace"):
        _validate_uid(None)
    with pytest.raises(ValueError, match="uid must be a non-empty string without whitespace"):
        _validate_uid("")
    with pytest.raises(ValueError, match="uid must be a non-empty string without whitespace"):
        _validate_uid("   ")
    with pytest.raises(ValueError, match="uid must be a non-empty string without whitespace"):
        _validate_uid(12345)


def test_validate_uid_rejects_path_delimiters():
    """Verify _validate_uid rejects path traversal / delimiter characters."""
    with pytest.raises(ValueError, match="uid cannot contain path delimiters"):
        _validate_uid("user/123")
    with pytest.raises(ValueError, match="uid cannot contain path delimiters"):
        _validate_uid("/root")


def test_validate_uid_normalizes_valid_string():
    """Verify _validate_uid strips surrounding whitespace on valid uids."""
    assert _validate_uid("  user-xyz  ") == "user-xyz"
    assert _validate_uid("valid_user_1") == "valid_user_1"


def test_account_deletion_collection_requires_client(monkeypatch):
    """Verify account_deletion_collection fails fast when firestore client is None."""
    monkeypatch.setattr("database.account_deletion_marker.get_data_plane_firestore_client", lambda: None)
    with pytest.raises(ValueError, match="firestore client is required"):
        account_deletion_collection(firestore_client=None)


def test_account_deletion_document_delegates_to_collection():
    """Verify account_deletion_document validates uid and accesses document."""
    mock_coll = MagicMock()
    mock_client = MagicMock()
    mock_client.collection.return_value = mock_coll

    account_deletion_document("  user-abc  ", firestore_client=mock_client)

    mock_client.collection.assert_called_once_with(ACCOUNT_DELETION_COLLECTION)
    mock_coll.document.assert_called_once_with("user-abc")


def test_get_user_deletion_wipe_status_validates_uid_early():
    """Verify get_user_deletion_wipe_status rejects empty/invalid uid."""
    with pytest.raises(ValueError, match="uid must be a non-empty string without whitespace"):
        get_user_deletion_wipe_status("")
    with pytest.raises(ValueError, match="uid must be a non-empty string without whitespace"):
        get_user_deletion_wipe_status("  ")
    with pytest.raises(ValueError, match="uid must be a non-empty string without whitespace"):
        get_user_deletion_wipe_status(None)  # type: ignore[arg-type]


def test_get_user_deletion_wipe_status_handles_not_found(monkeypatch):
    """Verify NotFound exception degrades cleanly to None and records MISS."""
    mock_doc = MagicMock()
    mock_doc.get.side_effect = NotFound("Document not found")
    mock_coll = MagicMock()
    mock_coll.document.return_value = mock_doc
    mock_client = MagicMock()
    mock_client.collection.return_value = mock_coll

    recorded = []
    monkeypatch.setattr(
        "database.account_deletion_marker.record_document_read",
        lambda site, outcome: recorded.append((site, outcome)),
    )

    status = get_user_deletion_wipe_status("user-missing", firestore_client=mock_client)
    assert status is None
    assert recorded == [(FirestoreReadSite.USER_DELETION_WIPE_STATUS, FirestoreReadOutcome.MISS)]


def test_get_user_deletion_wipe_status_handles_missing_document(monkeypatch):
    """Verify snapshot.exists=False returns None and records MISS."""
    mock_snapshot = MagicMock()
    mock_snapshot.exists = False
    mock_doc = MagicMock()
    mock_doc.get.return_value = mock_snapshot
    mock_coll = MagicMock()
    mock_coll.document.return_value = mock_doc
    mock_client = MagicMock()
    mock_client.collection.return_value = mock_coll

    recorded = []
    monkeypatch.setattr(
        "database.account_deletion_marker.record_document_read",
        lambda site, outcome: recorded.append((site, outcome)),
    )

    status = get_user_deletion_wipe_status("user-not-existing", firestore_client=mock_client)
    assert status is None
    assert recorded == [(FirestoreReadSite.USER_DELETION_WIPE_STATUS, FirestoreReadOutcome.MISS)]


def test_get_user_deletion_wipe_status_handles_hit(monkeypatch):
    """Verify existing snapshot returns normalized wipe_status and records HIT."""
    mock_snapshot = MagicMock()
    mock_snapshot.exists = True
    mock_snapshot.to_dict.return_value = {"wipe_status": "in_progress"}
    mock_doc = MagicMock()
    mock_doc.get.return_value = mock_snapshot
    mock_coll = MagicMock()
    mock_coll.document.return_value = mock_doc
    mock_client = MagicMock()
    mock_client.collection.return_value = mock_coll

    recorded = []
    monkeypatch.setattr(
        "database.account_deletion_marker.record_document_read",
        lambda site, outcome: recorded.append((site, outcome)),
    )

    status = get_user_deletion_wipe_status("user-active", firestore_client=mock_client)
    assert status == "in_progress"
    assert recorded == [(FirestoreReadSite.USER_DELETION_WIPE_STATUS, FirestoreReadOutcome.HIT)]


def test_get_user_deletion_wipe_status_handles_malformed_data(monkeypatch):
    """Verify corrupted non-dict snapshot data is handled safely."""
    mock_snapshot = MagicMock()
    mock_snapshot.exists = True
    mock_snapshot.to_dict.return_value = None  # Non-dict corrupt payload
    mock_doc = MagicMock()
    mock_doc.get.return_value = mock_snapshot
    mock_coll = MagicMock()
    mock_coll.document.return_value = mock_doc
    mock_client = MagicMock()
    mock_client.collection.return_value = mock_coll

    monkeypatch.setattr(
        "database.account_deletion_marker.record_document_read",
        lambda site, outcome: None,
    )

    status = get_user_deletion_wipe_status("user-corrupt", firestore_client=mock_client)
    assert status == ACCOUNT_DELETION_INVALID_STATUS


def test_get_user_deletion_wipe_status_reraises_google_api_call_error():
    """Verify unexpected GoogleAPICallError is not swallowed."""
    mock_doc = MagicMock()
    mock_doc.get.side_effect = GoogleAPICallError("Internal backend failure")
    mock_coll = MagicMock()
    mock_coll.document.return_value = mock_doc
    mock_client = MagicMock()
    mock_client.collection.return_value = mock_coll

    with pytest.raises(GoogleAPICallError, match="Internal backend failure"):
        get_user_deletion_wipe_status("user-crash", firestore_client=mock_client)
