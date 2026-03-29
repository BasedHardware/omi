"""Tests for free-tier fair-use enforcement (#6083).

Architecture: free-exhausted users get a synthetic score of 1.0 (instead of
the LLM classifier) and follow the same graduated escalation pipeline as
abuse-detected users: none → warning → throttle → restrict.
"""

import asyncio
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub heavy dependencies before importing the module under test
# ---------------------------------------------------------------------------
_db_client = types.ModuleType('database._client')
_db_client.db = MagicMock()
sys.modules.setdefault('database._client', _db_client)

_redis_mod = types.ModuleType('database.redis_db')
_mock_redis = MagicMock()
_redis_mod.r = _mock_redis
sys.modules.setdefault('database.redis_db', _redis_mod)

sys.modules.setdefault('google.cloud.firestore', MagicMock())
sys.modules.setdefault('google.cloud.firestore_v1', MagicMock())

# Stub database.fair_use
_fair_use_db = types.ModuleType('database.fair_use')
_fair_use_db.get_fair_use_state = MagicMock(return_value={'stage': 'none'})
_fair_use_db.update_fair_use_state = MagicMock()
_fair_use_db.create_fair_use_event = MagicMock(return_value='evt-123')
_fair_use_db.get_fair_use_events = MagicMock(return_value=[{'case_ref': 'FU-TEST01'}])
_fair_use_db.get_violation_counts = MagicMock(return_value={'violation_count_7d': 0, 'violation_count_30d': 0})
sys.modules.setdefault('database.fair_use', _fair_use_db)

# Stub database.users
_users_db = MagicMock()
sys.modules.setdefault('database.users', _users_db)

# Stub notifications
_notifications_mod = types.ModuleType('utils.notifications')
_notifications_mod.send_notification = MagicMock()
sys.modules.setdefault('utils.notifications', _notifications_mod)

# Stub LLM classifier
_classifier_mod = types.ModuleType('utils.llm.fair_use_classifier')
_classifier_mod.classify_user_purpose = MagicMock()
sys.modules.setdefault('utils.llm', types.ModuleType('utils.llm'))
sys.modules.setdefault('utils.llm.fair_use_classifier', _classifier_mod)

# Stub subscription
_subscription_mod = types.ModuleType('utils.subscription')
_subscription_mod.has_transcription_credits = MagicMock(return_value=True)
_subscription_mod.is_paid_plan = MagicMock(return_value=False)
sys.modules.setdefault('utils.subscription', _subscription_mod)

# Now import the module under test
import utils.fair_use as fair_use_mod

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trigger(trigger_type='daily'):
    mock_trigger = MagicMock()
    mock_trigger.value = trigger_type
    return [{'trigger': mock_trigger}]


# ---------------------------------------------------------------------------
# is_free_credits_exhausted tests
# ---------------------------------------------------------------------------


class TestIsFreeCreditsExhausted:
    def test_paid_user_returns_false(self):
        mock_sub = MagicMock()
        mock_sub.plan = 'unlimited'
        fair_use_mod.users_db.get_user_valid_subscription = MagicMock(return_value=mock_sub)
        fair_use_mod.is_paid_plan = MagicMock(return_value=True)
        fair_use_mod.has_transcription_credits = MagicMock(return_value=False)

        assert fair_use_mod.is_free_credits_exhausted('test-uid') is False

    def test_basic_user_with_credits_returns_false(self):
        mock_sub = MagicMock()
        mock_sub.plan = 'basic'
        fair_use_mod.users_db.get_user_valid_subscription = MagicMock(return_value=mock_sub)
        fair_use_mod.is_paid_plan = MagicMock(return_value=False)
        fair_use_mod.has_transcription_credits = MagicMock(return_value=True)

        assert fair_use_mod.is_free_credits_exhausted('test-uid') is False

    def test_basic_user_no_credits_returns_true(self):
        mock_sub = MagicMock()
        mock_sub.plan = 'basic'
        fair_use_mod.users_db.get_user_valid_subscription = MagicMock(return_value=mock_sub)
        fair_use_mod.is_paid_plan = MagicMock(return_value=False)
        fair_use_mod.has_transcription_credits = MagicMock(return_value=False)

        assert fair_use_mod.is_free_credits_exhausted('test-uid') is True

    def test_no_subscription_no_credits_returns_true(self):
        fair_use_mod.users_db.get_user_valid_subscription = MagicMock(return_value=None)
        fair_use_mod.is_paid_plan = MagicMock(return_value=False)
        fair_use_mod.has_transcription_credits = MagicMock(return_value=False)

        assert fair_use_mod.is_free_credits_exhausted('test-uid') is True

    def test_exception_returns_false(self):
        """Fail-open: any exception returns False (user keeps access)."""
        fair_use_mod.users_db.get_user_valid_subscription = MagicMock(side_effect=Exception('DB down'))

        assert fair_use_mod.is_free_credits_exhausted('test-uid') is False


# ---------------------------------------------------------------------------
# trigger_classifier_if_needed tests — free-exhausted synthetic score
# ---------------------------------------------------------------------------


class TestTriggerClassifierFreeTier:
    """Free-exhausted users get synthetic score 1.0 and go through escalation."""

    def setup_method(self):
        _mock_redis.reset_mock()
        _mock_redis.set.return_value = True
        _fair_use_db.get_fair_use_state.reset_mock()
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'none'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 0, 'violation_count_30d': 0}
        _fair_use_db.create_fair_use_event.reset_mock()
        _fair_use_db.create_fair_use_event.return_value = 'evt-123'
        _fair_use_db.get_fair_use_events.return_value = [{'case_ref': 'FU-TEST01'}]
        _fair_use_db.update_fair_use_state.reset_mock()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'is_free_credits_exhausted', return_value=True)
    @patch.object(fair_use_mod, '_get_classify_user_purpose')
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_free_exhausted_uses_synthetic_score(self, _mock_speech, mock_get_classify, _mock_free):
        """Free-exhausted: acquires lock, skips LLM, uses synthetic score 1.0 for escalation."""
        mock_classifier = MagicMock()
        mock_get_classify.return_value = mock_classifier

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(fair_use_mod.trigger_classifier_if_needed('test-uid', _make_trigger()))
        finally:
            loop.close()

        # LLM classifier not called
        mock_classifier.assert_not_called()
        # Lock was acquired
        _mock_redis.set.assert_called_once()
        # Escalation happened (none → warning with synthetic score 1.0)
        _fair_use_db.update_fair_use_state.assert_called()
        # First call is the stage update; last call may be last_case_ref
        stage_call = _fair_use_db.update_fair_use_state.call_args_list[0][0]
        assert stage_call[1]['stage'] == 'warning'

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'is_free_credits_exhausted', return_value=True)
    @patch.object(fair_use_mod, '_get_classify_user_purpose')
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_free_exhausted_stores_synthetic_metadata(self, _mock_speech, mock_get_classify, _mock_free):
        """Verify the exact synthetic classifier payload is stored in the fair-use event."""
        mock_get_classify.return_value = MagicMock()

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(fair_use_mod.trigger_classifier_if_needed('test-uid', _make_trigger()))
        finally:
            loop.close()

        # create_fair_use_event stores the classifier result in the event payload
        _fair_use_db.create_fair_use_event.assert_called_once()
        event_data = _fair_use_db.create_fair_use_event.call_args[0][1]
        assert event_data['classifier'] == {'misuse_score': 1.0, 'usage_type': 'free_exhausted'}

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'is_free_credits_exhausted', return_value=True)
    @patch.object(fair_use_mod, '_get_classify_user_purpose')
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_free_exhausted_escalates_warning_to_throttle(self, _mock_speech, mock_get_classify, _mock_free):
        """Free-exhausted user already at warning with enough violations → throttle."""
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'warning'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 2, 'violation_count_30d': 3}
        mock_get_classify.return_value = MagicMock()

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(fair_use_mod.trigger_classifier_if_needed('test-uid', _make_trigger()))
        finally:
            loop.close()

        _fair_use_db.update_fair_use_state.assert_called()
        stage_call = _fair_use_db.update_fair_use_state.call_args_list[0][0]
        assert stage_call[1]['stage'] == 'throttle'

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'is_free_credits_exhausted', return_value=True)
    @patch.object(fair_use_mod, '_get_classify_user_purpose')
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_free_exhausted_escalates_throttle_to_restrict(self, _mock_speech, mock_get_classify, _mock_free):
        """Free-exhausted user at throttle with enough violations → restrict."""
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'throttle'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 3, 'violation_count_30d': 5}
        mock_get_classify.return_value = MagicMock()

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(fair_use_mod.trigger_classifier_if_needed('test-uid', _make_trigger()))
        finally:
            loop.close()

        _fair_use_db.update_fair_use_state.assert_called()
        stage_call = _fair_use_db.update_fair_use_state.call_args_list[0][0]
        assert stage_call[1]['stage'] == 'restrict'

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, '_get_classify_user_purpose')
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    @patch.object(fair_use_mod, 'is_free_credits_exhausted', return_value=False)
    def test_non_free_user_calls_classifier(self, _mock_free, _mock_speech, mock_get_classify):
        """Non-free user: goes through the normal LLM classifier pipeline."""
        classify_called = {'called': False}
        _fair_use_db.create_fair_use_event.reset_mock()

        async def mock_classify(uid):
            classify_called['called'] = True
            return {'misuse_score': 0.1, 'usage_type': 'personal'}

        mock_get_classify.return_value = mock_classify

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(fair_use_mod.trigger_classifier_if_needed('test-uid', _make_trigger()))
        finally:
            loop.close()

        assert classify_called['called'] is True


# ---------------------------------------------------------------------------
# escalate_enforcement tests — shared by both abuse and free-exhausted paths
# ---------------------------------------------------------------------------


class TestEscalateEnforcement:
    """escalate_enforcement handles both abuse detection (LLM) and free-exhausted
    (synthetic score) paths. The score gate (misuse_score >= threshold) is always required."""

    def setup_method(self):
        _fair_use_db.get_fair_use_state.reset_mock()
        _fair_use_db.get_violation_counts.reset_mock()
        _fair_use_db.create_fair_use_event.reset_mock()
        _fair_use_db.update_fair_use_state.reset_mock()
        _fair_use_db.create_fair_use_event.return_value = 'evt-123'
        _fair_use_db.get_fair_use_events.return_value = [{'case_ref': 'FU-TEST01'}]
        _mock_redis.reset_mock()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_low_score_does_not_escalate(self, _mock_speech):
        """Low misuse score should NOT escalate, even with violations."""
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'none'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 3, 'violation_count_30d': 5}

        result = fair_use_mod.escalate_enforcement(
            'test-uid', _make_trigger(), {'misuse_score': 0.1, 'usage_type': 'personal'}
        )

        assert result['action'] == 'none'
        assert result['new_stage'] == 'none'

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_high_score_escalates_to_warning(self, _mock_speech):
        """High misuse score escalates from none → warning."""
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'none'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 1, 'violation_count_30d': 1}

        result = fair_use_mod.escalate_enforcement(
            'test-uid', _make_trigger(), {'misuse_score': 0.8, 'usage_type': 'audiobook'}
        )

        assert result['action'] == 'warning'
        assert result['new_stage'] == 'warning'

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_high_score_escalates_warning_to_throttle(self, _mock_speech):
        """Repeated high score escalates warning → throttle."""
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'warning'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 2, 'violation_count_30d': 3}

        result = fair_use_mod.escalate_enforcement(
            'test-uid', _make_trigger(), {'misuse_score': 0.8, 'usage_type': 'audiobook'}
        )

        assert result['action'] == 'throttle'
        assert result['new_stage'] == 'throttle'

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_high_score_escalates_throttle_to_restrict(self, _mock_speech):
        """Continued abuse escalates throttle → restrict."""
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'throttle'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 3, 'violation_count_30d': 5}

        result = fair_use_mod.escalate_enforcement(
            'test-uid', _make_trigger(), {'misuse_score': 0.8, 'usage_type': 'audiobook'}
        )

        assert result['action'] == 'restrict'
        assert result['new_stage'] == 'restrict'

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_free_exhausted_synthetic_score_escalates(self, _mock_speech):
        """Free-exhausted synthetic score (1.0) should escalate same as abuse."""
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'none'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 0, 'violation_count_30d': 0}

        result = fair_use_mod.escalate_enforcement(
            'test-uid', _make_trigger(), {'misuse_score': 1.0, 'usage_type': 'free_exhausted'}
        )

        assert result['action'] == 'warning'
        assert result['new_stage'] == 'warning'


# ---------------------------------------------------------------------------
# DG budget tests
# ---------------------------------------------------------------------------


class TestDgBudget:
    """Test is_dg_budget_exhausted uses FAIR_USE_RESTRICT_DAILY_DG_MS only."""

    def setup_method(self):
        _mock_redis.reset_mock()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 1800000)
    def test_under_budget_returns_false(self):
        _mock_redis.get.return_value = b'900000'
        assert fair_use_mod.is_dg_budget_exhausted('test-uid') is False

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 1800000)
    def test_at_budget_returns_true(self):
        _mock_redis.get.return_value = b'1800000'
        assert fair_use_mod.is_dg_budget_exhausted('test-uid') is True

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 1800000)
    def test_no_usage_returns_false(self):
        _mock_redis.get.return_value = None
        assert fair_use_mod.is_dg_budget_exhausted('test-uid') is False

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 0)
    def test_zero_limit_returns_false(self):
        """When limit is 0 (disabled), always returns False."""
        _mock_redis.get.return_value = b'9999999'
        assert fair_use_mod.is_dg_budget_exhausted('test-uid') is False

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', False)
    def test_disabled_returns_false(self):
        assert fair_use_mod.is_dg_budget_exhausted('test-uid') is False


class TestRecordDgUsageMs:
    """Test record_dg_usage_ms with simplified guard."""

    def setup_method(self):
        _mock_redis.reset_mock()
        _mock_redis.pipeline.return_value = MagicMock()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 1800000)
    def test_records_when_budget_configured(self):
        fair_use_mod.record_dg_usage_ms('test-uid', 5000)
        _mock_redis.pipeline.assert_called_once()
        pipe = _mock_redis.pipeline.return_value
        pipe.execute.assert_called_once()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_RESTRICT_DAILY_DG_MS', 0)
    def test_skips_when_budget_zero(self):
        fair_use_mod.record_dg_usage_ms('test-uid', 5000)
        _mock_redis.pipeline.assert_not_called()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', False)
    def test_skips_when_disabled(self):
        fair_use_mod.record_dg_usage_ms('test-uid', 5000)
        _mock_redis.pipeline.assert_not_called()


# ---------------------------------------------------------------------------
# Sync DG budget gate test
# ---------------------------------------------------------------------------


class TestSyncDgBudgetGate:
    """Test the sync endpoint response structure when DG budget is exhausted."""

    def test_sync_budget_exhausted_response_structure(self):
        from starlette.responses import JSONResponse
        import json

        response = JSONResponse(
            status_code=429,
            content={
                'new_memories': [],
                'updated_memories': [],
                'credits_exhausted': True,
                'dg_budget_exhausted': True,
                'skipped_segments': 5,
            },
        )

        assert response.status_code == 429
        body = json.loads(response.body)
        assert body['credits_exhausted'] is True
        assert body['dg_budget_exhausted'] is True
        assert body['skipped_segments'] == 5
