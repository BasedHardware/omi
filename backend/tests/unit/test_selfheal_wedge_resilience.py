import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from database.capture_wedge_state import (
    _clean_id,
    _clean_day,
    claim_wedge_first_seen,
    claim_wedge_nudge_cooldown,
)


def test_clean_id_validations():
    assert _clean_id("valid_uid_123", "uid") == "valid_uid_123"

    with pytest.raises(ValueError, match="uid cannot be empty"):
        _clean_id("", "uid")

    with pytest.raises(ValueError, match="uid must be a string"):
        _clean_id(12345, "uid")

    with pytest.raises(ValueError, match="uid contains prohibited path-traversal"):
        _clean_id("../admin_uid", "uid")

    with pytest.raises(ValueError, match="uid exceeds maximum allowable length"):
        _clean_id("a" * 257, "uid")


def test_clean_day_validations():
    assert _clean_day("2026-09-30") == "2026-09-30"

    with pytest.raises(ValueError, match="day must be a string"):
        _clean_day(20260930)

    with pytest.raises(ValueError, match="valid calendar date in YYYY-MM-DD format"):
        _clean_day("2026-13-45")

    with pytest.raises(ValueError, match="valid calendar date in YYYY-MM-DD format"):
        _clean_day("invalid-date")


def test_claim_wedge_first_seen_success_and_duplicate():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_snapshot = MagicMock()
    mock_snapshot.exists = False
    mock_snapshot.to_dict.return_value = {}
    mock_doc.get.return_value = mock_snapshot

    mock_client.collection.return_value.document.return_value = mock_doc
    with patch("google.cloud.firestore.transactional", lambda fn: lambda txn: fn(txn)):
        # First claim succeeds
        res = claim_wedge_first_seen("user_123", "2026-09-30", firestore_client=mock_client)
        assert res is True

        # Duplicate claim for same day returns False
        mock_snapshot.exists = True
        mock_snapshot.to_dict.return_value = {"first_seen_day": "2026-09-30"}
        res2 = claim_wedge_first_seen("user_123", "2026-09-30", firestore_client=mock_client)
        assert res2 is False


def test_claim_wedge_nudge_cooldown_error_fallback():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.get.side_effect = RuntimeError("Firestore connection lost")
    mock_client.collection.return_value.document.return_value = mock_doc

    with patch("google.cloud.firestore.transactional", lambda fn: lambda txn: fn(txn)):
        res = claim_wedge_nudge_cooldown("user_123", firestore_client=mock_client)
        assert res is False


def test_claim_wedge_first_seen_error_fallback():
    mock_client = MagicMock()
    mock_doc = MagicMock()
    mock_doc.get.side_effect = RuntimeError("Firestore connection lost")
    mock_client.collection.return_value.document.return_value = mock_doc

    with patch("google.cloud.firestore.transactional", lambda fn: lambda txn: fn(txn)):
        res = claim_wedge_first_seen("user_123", "2026-09-30", firestore_client=mock_client)
        assert res is False
