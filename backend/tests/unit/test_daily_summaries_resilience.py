import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime
from backend.database.daily_summaries import (
    create_daily_summary, get_daily_summary, update_daily_summary,
    delete_daily_summary, set_daily_summary_visibility, get_daily_summaries,
    get_summaries_count, upsert_desktop_daily_usage, _clean_str, _clean_id
)

@pytest.fixture
def mock_firestore():
    with patch('backend.database.daily_summaries.firestore_client') as mock:
        mock.collection.return_value.document.return_value = MagicMock()
        yield mock

@pytest.fixture
def mock_redis():
    with patch('backend.database.daily_summaries.redis_client') as mock:
        yield mock

def test_clean_str():
    assert _clean_str("  test  ") == "test"
    with pytest.raises(ValueError):
        _clean_str("")
    with pytest.raises(ValueError):
        _clean_str("   ")

def test_clean_id():
    assert _clean_id("valid_id") == "valid_id"
    with pytest.raises(ValueError):
        _clean_id("")
    with pytest.raises(ValueError):
        _clean_id("invalid/path")

def test_create_daily_summary(mock_firestore):
    result = create_daily_summary("user1", {"test": "data"})
    assert isinstance(result, str)
    assert len(result) > 0

def test_create_daily_summary_with_id(mock_firestore):
    result = create_daily_summary("user1", {"id": "custom_id", "test": "data"})
    assert result == "custom_id"

def test_get_daily_summaries_pagination_clamping():
    assert get_daily_summaries("user1", limit=-10, offset=-5) == []
    assert get_daily_summaries("user1", limit=1000, offset=1000) == []

def test_upsert_desktop_daily_usage_clamping(mock_firestore):
    with patch('backend.database.daily_summaries.run_with_transaction_contention_retry') as mock_retry:
        upsert_desktop_daily_usage("user1", "device1", {"counter": -5})
        mock_retry.assert_called_once()

def test_delete_daily_summary_resilience(mock_firestore, mock_redis):
    mock_redis.delete.side_effect = Exception("Redis error")
    delete_daily_summary("user1", "summary1")
    # Should not raise exception despite Redis failure

def test_get_summaries_count_fallback(mock_firestore):
    mock_firestore.collection().stream.side_effect = Exception("Query error")
    assert get_summaries_count("user1") == 0