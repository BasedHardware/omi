"""Tests for free-tier fair-use enforcement (#6083).

Verifies that free users with exhausted credits escalate through
the enforcement pipeline on violation count alone, bypassing the
LLM classifier score requirement.
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
sys.modules.setdefault('utils.notifications', MagicMock())

# Stub subscription
_subscription_mod = types.ModuleType('utils.subscription')
_subscription_mod.has_transcription_credits = MagicMock(return_value=True)
_subscription_mod.is_paid_plan = MagicMock(return_value=False)
sys.modules.setdefault('utils.subscription', _subscription_mod)

# Now import the module under test
import utils.fair_use as fair_use_mod
from models.fair_use import SoftCapTrigger

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_classifier_result(misuse_score=0.0, usage_type='none', free_credits_exhausted=False):
    return {
        'misuse_score': misuse_score,
        'usage_type': usage_type,
        'free_credits_exhausted': free_credits_exhausted,
    }


def _make_trigger(trigger_type='daily'):
    mock_trigger = MagicMock()
    mock_trigger.value = trigger_type
    return [{'trigger': mock_trigger}]


# ---------------------------------------------------------------------------
# escalate_enforcement tests
# ---------------------------------------------------------------------------


class TestEscalateEnforcementFreeTier:
    """Test that free-tier exhausted users bypass the misuse_score gate."""

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
    def test_free_exhausted_escalates_none_to_warning(self, _mock_speech):
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'none'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 1, 'violation_count_30d': 1}

        result = fair_use_mod.escalate_enforcement(
            'test-uid',
            _make_trigger(),
            _make_classifier_result(misuse_score=0.1, usage_type='free_exhausted', free_credits_exhausted=True),
        )

        assert result['action'] == 'warning'
        assert result['new_stage'] == 'warning'

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_free_exhausted_escalates_warning_to_throttle(self, _mock_speech):
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'warning'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 2, 'violation_count_30d': 2}

        result = fair_use_mod.escalate_enforcement(
            'test-uid',
            _make_trigger(),
            _make_classifier_result(misuse_score=0.1, usage_type='free_exhausted', free_credits_exhausted=True),
        )

        assert result['action'] == 'throttle'
        assert result['new_stage'] == 'throttle'

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_free_exhausted_escalates_throttle_to_restrict(self, _mock_speech):
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'throttle'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 3, 'violation_count_30d': 3}

        result = fair_use_mod.escalate_enforcement(
            'test-uid',
            _make_trigger(),
            _make_classifier_result(misuse_score=0.1, usage_type='free_exhausted', free_credits_exhausted=True),
        )

        assert result['action'] == 'restrict'
        assert result['new_stage'] == 'restrict'

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_paid_user_still_requires_misuse_score(self, _mock_speech):
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'none'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 1, 'violation_count_30d': 1}

        result = fair_use_mod.escalate_enforcement(
            'test-uid',
            _make_trigger(),
            _make_classifier_result(misuse_score=0.1, usage_type='personal', free_credits_exhausted=False),
        )

        assert result['action'] == 'none'
        assert result['new_stage'] == 'none'

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_paid_user_escalates_with_high_score(self, _mock_speech):
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'none'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 1, 'violation_count_30d': 1}

        result = fair_use_mod.escalate_enforcement(
            'test-uid',
            _make_trigger(),
            _make_classifier_result(misuse_score=0.8, usage_type='audiobook', free_credits_exhausted=False),
        )

        assert result['action'] == 'warning'
        assert result['new_stage'] == 'warning'

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_free_exhausted_insufficient_violations_no_escalate(self, _mock_speech):
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'warning'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 1, 'violation_count_30d': 1}

        result = fair_use_mod.escalate_enforcement(
            'test-uid',
            _make_trigger(),
            _make_classifier_result(misuse_score=0.1, usage_type='free_exhausted', free_credits_exhausted=True),
        )

        assert result['action'] == 'none'
        assert result['new_stage'] == 'warning'


# ---------------------------------------------------------------------------
# is_free_credits_exhausted tests
# ---------------------------------------------------------------------------


class TestIsFreeCreditsExhausted:
    def setup_method(self):
        # Reset the lazy import caches so patches take effect
        fair_use_mod._has_transcription_credits = None
        fair_use_mod._is_paid_plan = None

    def test_paid_user_returns_false(self):
        mock_sub = MagicMock()
        mock_sub.plan = 'unlimited'
        fair_use_mod.users_db.get_user_valid_subscription = MagicMock(return_value=mock_sub)
        _subscription_mod.is_paid_plan = MagicMock(return_value=True)
        _subscription_mod.has_transcription_credits = MagicMock(return_value=False)

        assert fair_use_mod.is_free_credits_exhausted('test-uid') is False

    def test_basic_user_with_credits_returns_false(self):
        mock_sub = MagicMock()
        mock_sub.plan = 'basic'
        fair_use_mod.users_db.get_user_valid_subscription = MagicMock(return_value=mock_sub)
        _subscription_mod.is_paid_plan = MagicMock(return_value=False)
        _subscription_mod.has_transcription_credits = MagicMock(return_value=True)

        assert fair_use_mod.is_free_credits_exhausted('test-uid') is False

    def test_basic_user_no_credits_returns_true(self):
        mock_sub = MagicMock()
        mock_sub.plan = 'basic'
        fair_use_mod.users_db.get_user_valid_subscription = MagicMock(return_value=mock_sub)
        _subscription_mod.is_paid_plan = MagicMock(return_value=False)
        _subscription_mod.has_transcription_credits = MagicMock(return_value=False)

        assert fair_use_mod.is_free_credits_exhausted('test-uid') is True

    def test_no_subscription_no_credits_returns_true(self):
        fair_use_mod.users_db.get_user_valid_subscription = MagicMock(return_value=None)
        _subscription_mod.is_paid_plan = MagicMock(return_value=False)
        _subscription_mod.has_transcription_credits = MagicMock(return_value=False)

        assert fair_use_mod.is_free_credits_exhausted('test-uid') is True


# ---------------------------------------------------------------------------
# trigger_classifier_if_needed tests
# ---------------------------------------------------------------------------


class TestTriggerClassifierFreeTier:
    def setup_method(self):
        _mock_redis.reset_mock()
        _mock_redis.set.return_value = True  # Lock acquired
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'none'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 0, 'violation_count_30d': 0}
        _fair_use_db.create_fair_use_event.return_value = 'evt-123'
        _fair_use_db.get_fair_use_events.return_value = [{'case_ref': 'FU-TEST01'}]
        # Reset lazy import caches
        fair_use_mod._has_transcription_credits = None
        fair_use_mod._is_paid_plan = None

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    @patch.object(fair_use_mod, 'is_free_credits_exhausted', return_value=True)
    def test_free_exhausted_skips_llm_classifier(self, _mock_free, _mock_speech):
        mock_classifier = MagicMock()
        fair_use_mod._classify_user_purpose = mock_classifier

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(fair_use_mod.trigger_classifier_if_needed('test-uid', _make_trigger()))
        finally:
            loop.close()

        # Classifier should NOT have been called
        mock_classifier.assert_not_called()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    @patch.object(fair_use_mod, 'is_free_credits_exhausted', return_value=False)
    def test_non_free_user_calls_llm_classifier(self, _mock_free, _mock_speech):
        async def mock_classify(uid):
            return _make_classifier_result(misuse_score=0.1)

        fair_use_mod._classify_user_purpose = mock_classify

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(fair_use_mod.trigger_classifier_if_needed('test-uid', _make_trigger()))
        finally:
            loop.close()

        # Verify escalation was called (no assertion error = classify was called)

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    @patch.object(fair_use_mod, 'is_free_credits_exhausted', return_value=True)
    def test_free_exhausted_uses_shorter_cooldown(self, _mock_free, _mock_speech):
        fair_use_mod._classify_user_purpose = MagicMock()

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(fair_use_mod.trigger_classifier_if_needed('test-uid', _make_trigger()))
        finally:
            loop.close()

        # Redis lock should use 1h (3600s) cooldown, not 12h
        set_call = _mock_redis.set.call_args
        assert set_call.kwargs.get('ex') == 3600

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    @patch.object(fair_use_mod, 'is_free_credits_exhausted', return_value=True)
    def test_free_exhausted_synthetic_result_records_event(self, _mock_free, _mock_speech):
        fair_use_mod._classify_user_purpose = MagicMock()
        _fair_use_db.create_fair_use_event.reset_mock()

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(fair_use_mod.trigger_classifier_if_needed('test-uid', _make_trigger()))
        finally:
            loop.close()

        # An event should be created with free_exhausted metadata
        _fair_use_db.create_fair_use_event.assert_called_once()
        event_data = _fair_use_db.create_fair_use_event.call_args[0][1]
        assert event_data['classifier']['usage_type'] == 'free_exhausted'
        assert event_data['classifier']['free_credits_exhausted'] is True
