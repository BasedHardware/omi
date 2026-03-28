"""Tests for free-tier fair-use enforcement (#6083).

Architecture: free-exhausted users go directly to 'restrict' stage via
ensure_free_exhausted_restrict(). This skips the LLM classifier and
graduated escalation. The restrict stage activates the daily DG budget
(FAIR_USE_RESTRICT_DAILY_DG_MS). When credits return, the restriction
auto-clears.
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trigger(trigger_type='daily'):
    mock_trigger = MagicMock()
    mock_trigger.value = trigger_type
    return [{'trigger': mock_trigger}]


# ---------------------------------------------------------------------------
# ensure_free_exhausted_restrict tests
# ---------------------------------------------------------------------------


class TestEnsureFreeExhaustedRestrict:
    """Core function: free-exhausted → restrict directly, auto-clear on credits return."""

    def setup_method(self):
        _fair_use_db.get_fair_use_state.reset_mock()
        _fair_use_db.update_fair_use_state.reset_mock()
        _mock_redis.reset_mock()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'is_free_credits_exhausted', return_value=True)
    @patch.object(fair_use_mod, 'get_enforcement_stage', return_value='none')
    def test_free_exhausted_sets_restrict(self, _mock_stage, _mock_free):
        """Free-exhausted user at stage 'none' should jump directly to 'restrict'."""
        result = fair_use_mod.ensure_free_exhausted_restrict('test-uid')

        assert result == 'restrict'
        _fair_use_db.update_fair_use_state.assert_called_once()
        call_args = _fair_use_db.update_fair_use_state.call_args[0]
        assert call_args[0] == 'test-uid'
        assert call_args[1]['stage'] == 'restrict'
        assert call_args[1]['restrict_reason'] == 'free_exhausted'
        assert call_args[1]['previous_stage'] == 'none'

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'is_free_credits_exhausted', return_value=True)
    @patch.object(fair_use_mod, 'get_enforcement_stage', return_value='warning')
    def test_free_exhausted_from_warning_sets_restrict(self, _mock_stage, _mock_free):
        """Free-exhausted user at any non-restrict stage should be set to 'restrict'."""
        result = fair_use_mod.ensure_free_exhausted_restrict('test-uid')
        assert result == 'restrict'
        _fair_use_db.update_fair_use_state.assert_called_once()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'is_free_credits_exhausted', return_value=True)
    @patch.object(fair_use_mod, 'get_enforcement_stage', return_value='restrict')
    def test_free_exhausted_already_restrict_noop(self, _mock_stage, _mock_free):
        """Free-exhausted user already at 'restrict' should not update state."""
        result = fair_use_mod.ensure_free_exhausted_restrict('test-uid')
        assert result == 'restrict'
        _fair_use_db.update_fair_use_state.assert_not_called()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'is_free_credits_exhausted', return_value=False)
    @patch.object(fair_use_mod, 'get_enforcement_stage', return_value='restrict')
    def test_credits_restored_clears_free_exhausted_restrict(self, _mock_stage, _mock_free):
        """When credits return and restrict_reason is 'free_exhausted', restore to previous stage."""
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'restrict_reason': 'free_exhausted',
            'previous_stage': 'none',
        }

        result = fair_use_mod.ensure_free_exhausted_restrict('test-uid')

        assert result == 'none'
        _fair_use_db.update_fair_use_state.assert_called_once()
        call_args = _fair_use_db.update_fair_use_state.call_args[0]
        assert call_args[1]['stage'] == 'none'
        assert call_args[1]['restrict_reason'] is None

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'is_free_credits_exhausted', return_value=False)
    @patch.object(fair_use_mod, 'get_enforcement_stage', return_value='restrict')
    def test_credits_restored_restores_previous_abuse_stage(self, _mock_stage, _mock_free):
        """When credits return and user was in 'warning' before, restore to 'warning' not 'none'."""
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'restrict_reason': 'free_exhausted',
            'previous_stage': 'warning',
        }

        result = fair_use_mod.ensure_free_exhausted_restrict('test-uid')

        assert result == 'warning'
        call_args = _fair_use_db.update_fair_use_state.call_args[0]
        assert call_args[1]['stage'] == 'warning'

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'is_free_credits_exhausted', return_value=False)
    @patch.object(fair_use_mod, 'get_enforcement_stage', return_value='restrict')
    def test_credits_restored_does_not_clear_abuse_restrict(self, _mock_stage, _mock_free):
        """When restrict_reason is NOT 'free_exhausted' (abuse), don't clear."""
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'restrict_reason': None,  # Abuse-based restrict has no reason or different reason
        }

        result = fair_use_mod.ensure_free_exhausted_restrict('test-uid')

        assert result == 'restrict'
        _fair_use_db.update_fair_use_state.assert_not_called()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'is_free_credits_exhausted', return_value=False)
    @patch.object(fair_use_mod, 'get_enforcement_stage', return_value='none')
    def test_non_exhausted_non_restricted_noop(self, _mock_stage, _mock_free):
        """Non-exhausted user at 'none' — no changes."""
        result = fair_use_mod.ensure_free_exhausted_restrict('test-uid')
        assert result == 'none'
        _fair_use_db.update_fair_use_state.assert_not_called()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', False)
    def test_disabled_returns_none(self):
        """When fair-use is disabled, always returns 'none'."""
        result = fair_use_mod.ensure_free_exhausted_restrict('test-uid')
        assert result == 'none'

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', True)
    def test_kill_switch_returns_none(self):
        """When kill switch is active, always returns 'none'."""
        result = fair_use_mod.ensure_free_exhausted_restrict('test-uid')
        assert result == 'none'
        _fair_use_db.update_fair_use_state.assert_not_called()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', {'test-uid'})
    def test_exempt_uid_returns_none(self):
        """Exempt UIDs are never restricted."""
        result = fair_use_mod.ensure_free_exhausted_restrict('test-uid')
        assert result == 'none'
        _fair_use_db.update_fair_use_state.assert_not_called()


# ---------------------------------------------------------------------------
# is_hard_restricted interaction with free-exhausted
# ---------------------------------------------------------------------------


class TestIsHardRestrictedFreeExhausted:
    """Free-exhausted users in restrict stage should NOT be hard-blocked."""

    def setup_method(self):
        _fair_use_db.get_fair_use_state.reset_mock()
        _mock_redis.reset_mock()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(
        fair_use_mod,
        'get_rolling_speech_ms',
        return_value={'daily_ms': 999999999, 'three_day_ms': 999999999, 'weekly_ms': 999999999},
    )
    def test_free_exhausted_restrict_not_hard_blocked(self, _mock_speech):
        """Free-exhausted restrict users should not be hard-blocked even with high speech."""
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'restrict_reason': 'free_exhausted',
        }
        assert fair_use_mod.is_hard_restricted('test-uid') is False

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(
        fair_use_mod,
        'get_rolling_speech_ms',
        return_value={'daily_ms': 999999999, 'three_day_ms': 999999999, 'weekly_ms': 999999999},
    )
    def test_abuse_restrict_still_hard_blocked(self, _mock_speech):
        """Abuse-restricted users with high speech should still be hard-blocked."""
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'restrict_reason': None,
        }
        assert fair_use_mod.is_hard_restricted('test-uid') is True


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


# ---------------------------------------------------------------------------
# trigger_classifier_if_needed tests
# ---------------------------------------------------------------------------


class TestTriggerClassifierFreeTier:
    """Free-exhausted users skip the LLM classifier entirely."""

    def setup_method(self):
        _mock_redis.reset_mock()
        _mock_redis.set.return_value = True
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'none'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 0, 'violation_count_30d': 0}
        _fair_use_db.create_fair_use_event.return_value = 'evt-123'
        _fair_use_db.get_fair_use_events.return_value = [{'case_ref': 'FU-TEST01'}]

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'is_free_credits_exhausted', return_value=True)
    @patch.object(fair_use_mod, 'ensure_free_exhausted_restrict', return_value='restrict')
    def test_free_exhausted_skips_classifier(self, _mock_ensure, _mock_free):
        """Free-exhausted: acquires lock, calls ensure_free_exhausted_restrict, no LLM classifier."""
        mock_classifier = MagicMock()
        fair_use_mod._classify_user_purpose = mock_classifier

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(fair_use_mod.trigger_classifier_if_needed('test-uid', _make_trigger()))
        finally:
            loop.close()

        _mock_ensure.assert_called_once_with('test-uid')
        mock_classifier.assert_not_called()
        # Lock is acquired first (cheap Redis check), then released after free-exhausted path
        _mock_redis.set.assert_called_once()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    @patch.object(fair_use_mod, 'is_free_credits_exhausted', return_value=False)
    def test_non_free_user_calls_classifier(self, _mock_free, _mock_speech):
        """Non-free user: goes through the normal LLM classifier pipeline."""
        classify_called = {'called': False}
        _fair_use_db.create_fair_use_event.reset_mock()

        async def mock_classify(uid):
            classify_called['called'] = True
            return {'misuse_score': 0.1, 'usage_type': 'personal'}

        fair_use_mod._classify_user_purpose = mock_classify

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(fair_use_mod.trigger_classifier_if_needed('test-uid', _make_trigger()))
        finally:
            loop.close()

        assert classify_called['called'] is True


# ---------------------------------------------------------------------------
# escalate_enforcement tests — no free-exhausted bypass
# ---------------------------------------------------------------------------


class TestEscalateEnforcement:
    """After architecture change, escalate_enforcement only handles abuse detection.
    Free-exhausted users never reach this function (handled by ensure_free_exhausted_restrict).
    The score gate (misuse_score >= threshold) is always required."""

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


# ---------------------------------------------------------------------------
# DG budget tests (simplified — no limit_ms parameter)
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
