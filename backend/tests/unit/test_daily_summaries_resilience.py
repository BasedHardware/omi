import os
from unittest.mock import MagicMock, patch
import pytest

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

from database.daily_summaries import (
    _clean_str,
    _clean_id,
    create_daily_summary,
    get_daily_summary,
    get_daily_summaries,
    delete_daily_summary,
    get_summaries_count,
    upsert_desktop_daily_usage,
)


def test_clean_str():
    assert _clean_str("  test  ") == "test"
    with pytest.raises(ValueError):
        _clean_str("")
    with pytest.raises(ValueError):
        _clean_str("   ")
    with pytest.raises(ValueError):
        _clean_str(None)


def test_clean_id():
    assert _clean_id("valid_id") == "valid_id"
    with pytest.raises(ValueError):
        _clean_id("")
    with pytest.raises(ValueError):
        _clean_id("invalid/path")
    with pytest.raises(ValueError):
        _clean_id("invalid\\path")
    with pytest.raises(ValueError):
        _clean_id("invalid..path")


@patch("database.daily_summaries.db")
def test_create_daily_summary_auto_uuid(mock_db):
    mock_summary_ref = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_summary_ref

    generated_id = create_daily_summary("user1", {"headline": "Great day"})
    assert isinstance(generated_id, str)
    assert len(generated_id) > 0
    mock_summary_ref.set.assert_called_once()
    payload = mock_summary_ref.set.call_args[0][0]
    assert payload["id"] == generated_id
    assert "created_at" in payload


@patch("database.daily_summaries.db")
def test_create_daily_summary_custom_id(mock_db):
    mock_summary_ref = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_summary_ref

    result = create_daily_summary("user1", {"id": "custom-uuid-123", "headline": "Productive"})
    assert result == "custom-uuid-123"
    mock_summary_ref.set.assert_called_once()


@patch("database.daily_summaries.db")
def test_get_daily_summaries_pagination_clamping(mock_db):
    mock_query = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.limit.return_value = mock_query
    mock_query.offset.return_value = mock_query
    mock_query.stream.return_value = []

    # Negative limit & offset clamped to limit=1, offset=0
    get_daily_summaries("user1", limit=-10, offset=-5)
    mock_query.limit.assert_called_with(1)
    mock_query.offset.assert_called_with(0)

    # Exorbitant limit clamped to 500
    get_daily_summaries("user1", limit=9999, offset=10)
    mock_query.limit.assert_called_with(500)
    mock_query.offset.assert_called_with(10)


@patch("database.daily_summaries.db")
@patch("database.daily_summaries.redis_db")
def test_delete_daily_summary_resilience(mock_redis_db, mock_db):
    mock_summary_ref = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_summary_ref
    mock_redis_db.remove_daily_summary_to_uid.side_effect = Exception("Redis connection refused")

    # Should succeed without raising exception despite redis failure
    deleted = delete_daily_summary("user1", "summary123")
    assert deleted is True
    mock_summary_ref.delete.assert_called_once()
    mock_redis_db.remove_daily_summary_to_uid.assert_called_once_with("summary123")


@patch("database.daily_summaries.db")
def test_get_summaries_count_fallback(mock_db):
    mock_count = MagicMock()
    mock_db.collection.return_value.document.return_value.collection.return_value.count.return_value = mock_count
    mock_count.get.side_effect = Exception("Firestore unavailable")

    # Resilient fallback returns 0
    assert get_summaries_count("user1") == 0


@patch("database.daily_summaries.firestore.transactional", lambda fn: fn)
@patch("database.daily_summaries.db")
def test_upsert_desktop_daily_usage_clamping(mock_db):
    mock_usage_ref = MagicMock()
    mock_snapshot = MagicMock()
    mock_snapshot.exists = True
    mock_snapshot.to_dict.return_value = {"watching_seconds": 100}
    mock_usage_ref.get.return_value = mock_snapshot
    mock_db.collection.return_value.document.return_value.collection.return_value.document.return_value = mock_usage_ref
    mock_tx = MagicMock()
    mock_db.transaction.return_value = mock_tx

    upsert_desktop_daily_usage(
        "user1",
        "2026-09-29",
        "UTC",
        "device1",
        {"watching_seconds": -50, "listening_seconds": 25}
    )

    # Clamping ensures negative counters become 0 and max is respected
    mock_tx.set.assert_called_once()
    payload = mock_tx.set.call_args[0][1]
    assert payload["watching_seconds"] == 100  # max(100, max(0, -50))
    assert payload["listening_seconds"] == 25   # max(0, max(0, 25))