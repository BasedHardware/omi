from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest

from database.capture_wedge_state import (
    _clean_id,
    _clean_day,
    claim_wedge_first_seen,
    claim_wedge_nudge_cooldown,
    WEDGE_NUDGE_COOLDOWN,
)


def test_clean_id_valid():
    assert _clean_id("user_123-ABC") == "user_123-ABC"
    assert _clean_id("  clean_me  ") == "clean_me"


def test_clean_id_invalid_traversal():
    with pytest.raises(ValueError, match="forbidden traversal patterns"):
        _clean_id("../etc/passwd")
    with pytest.raises(ValueError, match="forbidden traversal patterns"):
        _clean_id("user/123")
    with pytest.raises(ValueError, match="forbidden traversal patterns"):
        _clean_id("user\\123")
    with pytest.raises(ValueError, match="forbidden traversal patterns"):
        _clean_id("user\0null")


def test_clean_id_length_and_type():
    with pytest.raises(ValueError):
        _clean_id("")
    with pytest.raises(ValueError):
        _clean_id("   ")
    with pytest.raises(ValueError):
        _clean_id("a" * 129)
    with pytest.raises(ValueError):
        _clean_id(None)  # type: ignore[arg-type]


def test_clean_day_valid():
    assert _clean_day("2026-09-29") == "2026-09-29"


def test_clean_day_invalid():
    with pytest.raises(ValueError):
        _clean_day("../day")
    with pytest.raises(ValueError):
        _clean_day("day/sub")
    with pytest.raises(ValueError):
        _clean_day("a" * 33)
    with pytest.raises(ValueError):
        _clean_day(123)  # type: ignore[arg-type]


def test_claim_wedge_first_seen_success():
    client = MagicMock()
    doc_ref = MagicMock()
    client.collection.return_value.document.return_value = doc_ref

    transaction = MagicMock()
    client.transaction.return_value = transaction
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = {'first_seen_day': '2026-09-28'}
    doc_ref.get.return_value = snapshot

    result = claim_wedge_first_seen("user-1", "2026-09-29", firestore_client=client)
    assert result is True
    transaction.set.assert_called_once()


def test_claim_wedge_first_seen_already_claimed():
    client = MagicMock()
    doc_ref = MagicMock()
    client.collection.return_value.document.return_value = doc_ref

    transaction = MagicMock()
    client.transaction.return_value = transaction
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = {'first_seen_day': '2026-09-29'}
    doc_ref.get.return_value = snapshot

    result = claim_wedge_first_seen("user-1", "2026-09-29", firestore_client=client)
    assert result is False
    transaction.set.assert_not_called()


def test_claim_wedge_nudge_cooldown_grants_claim():
    client = MagicMock()
    doc_ref = MagicMock()
    client.collection.return_value.document.return_value = doc_ref

    transaction = MagicMock()
    client.transaction.return_value = transaction
    snapshot = MagicMock()
    snapshot.exists = True
    snapshot.to_dict.return_value = {'last_nudge_at': None}
    doc_ref.get.return_value = snapshot

    result = claim_wedge_nudge_cooldown("user-1", firestore_client=client)
    assert result is True
    transaction.set.assert_called_once()


def test_claim_wedge_nudge_cooldown_active():
    client = MagicMock()
    doc_ref = MagicMock()
    client.collection.return_value.document.return_value = doc_ref

    transaction = MagicMock()
    client.transaction.return_value = transaction
    snapshot = MagicMock()
    snapshot.exists = True
    now = datetime.now(timezone.utc)
    snapshot.to_dict.return_value = {'last_nudge_at': now - timedelta(hours=1)}
    doc_ref.get.return_value = snapshot

    result = claim_wedge_nudge_cooldown("user-1", now=now, firestore_client=client)
    assert result is False
    transaction.set.assert_not_called()
