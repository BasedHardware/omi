"""Hermetic unit tests for backend/database/phone_call_usage.py resilience, validation, and DI."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

import database.phone_call_usage as usage_db


def test_clean_uid_validates_and_rejects_pathological_uids():
    # Valid UIDs
    assert usage_db._clean_uid("user-123") == "user-123"
    assert usage_db._clean_uid("  user-abc  ") == "user-abc"
    assert usage_db._clean_uid("0x1234567890abcdef") == "0x1234567890abcdef"

    # Pathological UIDs (key injection, colons, whitespaces, newlines, traversal)
    assert usage_db._clean_uid("") == ""
    assert usage_db._clean_uid("   ") == ""
    assert usage_db._clean_uid(None) == ""
    assert usage_db._clean_uid(12345) == ""  # type: ignore
    assert usage_db._clean_uid("user:inject") == ""
    assert usage_db._clean_uid("user\ninject") == ""
    assert usage_db._clean_uid("user\rinject") == ""
    assert usage_db._clean_uid("user with space") == ""
    assert usage_db._clean_uid("a" * 129) == ""


def test_get_current_month_count_with_invalid_uid_returns_zero():
    mock_redis = MagicMock()
    for bad in ["", "   ", None, "bad:uid", "uid with space"]:
        count, reset_at = usage_db.get_current_month_count(bad, redis_client=mock_redis)  # type: ignore
        assert count == 0
        assert reset_at > 0
    assert not mock_redis.get.called


def test_get_current_month_count_normal_and_di():
    mock_redis = MagicMock()
    mock_redis.get.return_value = b"7"

    count, reset_at = usage_db.get_current_month_count("  user-prod  ", redis_client=mock_redis)
    assert count == 7
    assert reset_at > 0

    now = datetime.now(timezone.utc)
    expected_key = f"phone_call_usage:user-prod:{now.year}-{now.month:02d}"
    mock_redis.get.assert_called_once_with(expected_key)


def test_get_current_month_count_handles_redis_read_exception_gracefully():
    mock_redis = MagicMock()
    mock_redis.get.side_effect = Exception("Redis connection refused")

    count, reset_at = usage_db.get_current_month_count("user-1", redis_client=mock_redis)
    assert count == 0
    assert reset_at > 0


def test_get_current_month_count_handles_corrupt_non_int_gracefully():
    mock_redis = MagicMock()
    mock_redis.get.return_value = b"corrupted-string-data"

    count, reset_at = usage_db.get_current_month_count("user-1", redis_client=mock_redis)
    assert count == 0
    assert reset_at > 0


def test_get_current_month_count_clamps_negative_to_zero():
    mock_redis = MagicMock()
    mock_redis.get.return_value = b"-10"

    count, reset_at = usage_db.get_current_month_count("user-1", redis_client=mock_redis)
    assert count == 0
    assert reset_at > 0


def test_reserve_current_month_slot_rejects_invalid_uid():
    mock_redis = MagicMock()
    for bad in ["", "   ", None, "bad:colons"]:
        reserved, used_before, reset_at = usage_db.reserve_current_month_slot(bad, 5, redis_client=mock_redis)  # type: ignore
        assert reserved is False
        assert used_before == 0
        assert reset_at > 0
    assert not mock_redis.incr.called


def test_reserve_current_month_slot_rejects_invalid_or_non_positive_limit():
    mock_redis = MagicMock()
    for bad_limit in [0, -1, -100, "invalid", None]:  # type: ignore
        reserved, used_before, reset_at = usage_db.reserve_current_month_slot(
            "user-1", bad_limit, redis_client=mock_redis  # type: ignore
        )
        assert reserved is False
        assert used_before == 0
        assert reset_at > 0
    assert not mock_redis.incr.called


def test_reserve_current_month_slot_success_flow():
    mock_redis = MagicMock()
    mock_redis.incr.return_value = 1

    reserved, used_before, reset_at = usage_db.reserve_current_month_slot("  user-1  ", 5, redis_client=mock_redis)
    assert reserved is True
    assert used_before == 0
    assert reset_at > 0

    now = datetime.now(timezone.utc)
    expected_key = f"phone_call_usage:user-1:{now.year}-{now.month:02d}"
    mock_redis.incr.assert_called_once_with(expected_key, 1)
    mock_redis.expire.assert_called_once_with(expected_key, 40 * 24 * 3600)
    assert not mock_redis.decr.called


def test_reserve_current_month_slot_over_limit_rollback_success():
    mock_redis = MagicMock()
    mock_redis.incr.return_value = 6

    reserved, used_before, reset_at = usage_db.reserve_current_month_slot("user-1", 5, redis_client=mock_redis)
    assert reserved is False
    assert used_before == 5
    assert reset_at > 0

    now = datetime.now(timezone.utc)
    expected_key = f"phone_call_usage:user-1:{now.year}-{now.month:02d}"
    mock_redis.decr.assert_called_once_with(expected_key, 1)


def test_reserve_current_month_slot_over_limit_rollback_handles_decr_error():
    mock_redis = MagicMock()
    mock_redis.incr.return_value = 10
    mock_redis.decr.side_effect = Exception("Transient redis decr error")

    reserved, used_before, reset_at = usage_db.reserve_current_month_slot("user-1", 5, redis_client=mock_redis)
    assert reserved is False
    assert used_before == 9
    assert reset_at > 0


def test_reserve_current_month_slot_fails_open_on_redis_error():
    mock_redis = MagicMock()
    mock_redis.incr.side_effect = Exception("Cluster node unreachable")

    # Fail-open posture: allows call when quota backend is unreachable
    reserved, used_before, reset_at = usage_db.reserve_current_month_slot("user-1", 5, redis_client=mock_redis)
    assert reserved is True
    assert used_before == 0
    assert reset_at > 0


def test_increment_current_month_pipeline_execution():
    mock_redis = MagicMock()
    mock_pipe = MagicMock()
    mock_redis.pipeline.return_value = mock_pipe

    usage_db.increment_current_month("  user-1  ", redis_client=mock_redis)

    now = datetime.now(timezone.utc)
    expected_key = f"phone_call_usage:user-1:{now.year}-{now.month:02d}"
    mock_pipe.incr.assert_called_once_with(expected_key, 1)
    mock_pipe.expire.assert_called_once_with(expected_key, 40 * 24 * 3600)
    mock_pipe.execute.assert_called_once()


def test_increment_current_month_handles_pipeline_exception():
    mock_redis = MagicMock()
    mock_pipe = MagicMock()
    mock_pipe.execute.side_effect = Exception("Write permission denied")
    mock_redis.pipeline.return_value = mock_pipe

    # Should not raise
    usage_db.increment_current_month("user-1", redis_client=mock_redis)


def test_increment_current_month_noop_on_invalid_uid():
    mock_redis = MagicMock()
    usage_db.increment_current_month("", redis_client=mock_redis)
    usage_db.increment_current_month("   ", redis_client=mock_redis)
    usage_db.increment_current_month("user:inject", redis_client=mock_redis)
    assert not mock_redis.pipeline.called


def test_reset_current_month_usage_clears_counter():
    mock_redis = MagicMock()
    res = usage_db.reset_current_month_usage("  user-1  ", redis_client=mock_redis)
    assert res is True

    now = datetime.now(timezone.utc)
    expected_key = f"phone_call_usage:user-1:{now.year}-{now.month:02d}"
    mock_redis.delete.assert_called_once_with(expected_key)

    # Error handling
    mock_redis.delete.side_effect = Exception("Redis error")
    assert usage_db.reset_current_month_usage("user-1", redis_client=mock_redis) is False

    # Invalid UID
    assert usage_db.reset_current_month_usage("", redis_client=mock_redis) is False


def test_period_reset_epoch_month_rollover_calculation():
    # Regular month: June 15, 2026 -> July 1, 2026 00:00:00 UTC
    dt_june = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    epoch_july = int(datetime(2026, 7, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    assert usage_db._period_reset_epoch(dt_june) == epoch_july

    # Year boundary rollover: Dec 31, 2026 -> Jan 1, 2027 00:00:00 UTC
    dt_dec = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    epoch_jan = int(datetime(2027, 1, 1, 0, 0, 0, tzinfo=timezone.utc).timestamp())
    assert usage_db._period_reset_epoch(dt_dec) == epoch_jan
