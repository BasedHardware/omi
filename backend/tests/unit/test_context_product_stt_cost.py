"""Context STT cost buckets are tagged by product, not last_active_platform."""

from unittest.mock import patch

from utils.analytics import record_usage


def test_context_product_writes_stt_cost_bucket():
    with patch('utils.analytics.user_usage_db') as usage_db, patch('utils.analytics.record_llm_usage_bucket') as bucket:
        record_usage('uid-1', transcription_seconds=120, app_product='context-for-claude')

    usage_db.update_hourly_usage.assert_called_once()
    bucket.assert_called_once()
    args, kwargs = bucket.call_args
    assert args[0] == 'uid-1'
    assert kwargs['bucket'] == 'context_for_claude_stt'
    assert kwargs['cost_usd'] == 0.0086  # 2 minutes * $0.0043


def test_non_context_product_skips_stt_cost_bucket():
    with patch('utils.analytics.user_usage_db') as usage_db, patch('utils.analytics.record_llm_usage_bucket') as bucket:
        record_usage('uid-1', transcription_seconds=120, app_product='omi-desktop')

    usage_db.update_hourly_usage.assert_called_once()
    bucket.assert_not_called()


def test_missing_product_skips_stt_cost_bucket():
    with patch('utils.analytics.user_usage_db'), patch('utils.analytics.record_llm_usage_bucket') as bucket:
        record_usage('uid-1', transcription_seconds=120)
    bucket.assert_not_called()
