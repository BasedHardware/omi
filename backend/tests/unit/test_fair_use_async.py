"""Tests for async fair-use flows: classifier trigger, notification, and admin router."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import routers.fair_use_admin as fair_use_admin_mod
import utils.fair_use as fair_use_mod
from models.fair_use import SoftCapTrigger

# Fake database.fair_use module. Referenced directly by some test bodies, and
# patched onto the real fair_use module per-test by the autouse fixture below.
# Configured with the same canned return values the old sys.modules stub used.
_fair_use_db = MagicMock(name='fair_use_db')
_fair_use_db.get_fair_use_state = MagicMock(return_value={})
_fair_use_db.update_fair_use_state = MagicMock()
_fair_use_db.create_fair_use_event = MagicMock(return_value='evt-1')
_fair_use_db.get_violation_counts = MagicMock(return_value={'violation_count_7d': 0, 'violation_count_30d': 0})
_fair_use_db.get_flagged_users = MagicMock(return_value=[])
_fair_use_db.get_fair_use_events = MagicMock(return_value=[{'case_ref': 'FU-TEST01'}])
_fair_use_db.resolve_fair_use_event = MagicMock()
_fair_use_db.reset_fair_use_state = MagicMock()


@pytest.fixture(autouse=True)
def _patch_fair_use_deps():
    """Patch the real fair_use module's IO dependencies with mocks per test.

    utils.fair_use imports cleanly, so instead of corrupting sys.modules at
    module scope we patch the module attributes (the sanctioned Tier-2 seam)
    for the duration of each test.
    """
    with patch.object(fair_use_mod, 'redis_client', MagicMock(name='redis_client')), patch.object(
        fair_use_mod, 'fair_use_db', _fair_use_db
    ), patch.object(fair_use_mod, 'users_db', MagicMock(name='users_db')), patch.object(
        fair_use_mod, 'has_transcription_credits', MagicMock(return_value=True)
    ), patch.object(
        fair_use_mod, 'is_paid_plan', MagicMock(return_value=False)
    ):
        yield


def _redis():
    """Get the Redis mock that the fair_use module actually references."""
    return fair_use_mod.redis_client


def _reset():
    """Fully reset the Redis mock used by fair_use, clearing all side_effects."""
    r = _redis()
    r.reset_mock()
    for attr in ('set', 'get', 'eval', 'delete', 'pipeline', 'zrangebyscore', 'hmget', 'setex', 'zadd', 'hincrby'):
        getattr(r, attr).side_effect = None
        getattr(r, attr).return_value = MagicMock()


class TestTriggerClassifierIfNeeded:
    """Test the async classifier trigger with lock dedup."""

    def setup_method(self):
        _reset()

    @pytest.mark.asyncio
    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, '_get_classify_user_purpose')
    @patch.object(fair_use_mod, 'escalate_enforcement')
    @patch.object(fair_use_mod, '_send_fair_use_notification', new_callable=AsyncMock)
    async def test_runs_classifier_and_escalates(self, mock_notify, mock_escalate, mock_get_classify):
        mock_classify = AsyncMock(return_value={'misuse_score': 0.9, 'usage_type': 'audiobook'})
        mock_get_classify.return_value = mock_classify
        _redis().set.return_value = True  # Lock acquired
        mock_escalate.return_value = {'action': 'warning', 'previous_stage': 'none', 'new_stage': 'warning'}

        triggered = [{'trigger': SoftCapTrigger.DAILY, 'speech_ms': 8000000, 'threshold_ms': 7200000}]
        await fair_use_mod.trigger_classifier_if_needed('user1', triggered)

        mock_classify.assert_called_once_with('user1')
        mock_escalate.assert_called_once()
        mock_notify.assert_called_once_with('user1', 'warning', case_ref='FU-TEST01')
        # Lock should NOT be released on success (5-min TTL cooldown prevents repeated LLM calls)
        _redis().eval.assert_not_called()

    @pytest.mark.asyncio
    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    async def test_skips_when_lock_not_acquired(self):
        _redis().set.return_value = False  # Lock not acquired

        triggered = [{'trigger': SoftCapTrigger.DAILY, 'speech_ms': 8000000, 'threshold_ms': 7200000}]
        await fair_use_mod.trigger_classifier_if_needed('user1', triggered)

        _redis().eval.assert_not_called()

    @pytest.mark.asyncio
    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, '_get_classify_user_purpose')
    @patch.object(fair_use_mod, 'escalate_enforcement')
    @patch.object(fair_use_mod, '_send_fair_use_notification', new_callable=AsyncMock)
    async def test_no_notification_when_no_action(self, mock_notify, mock_escalate, mock_get_classify):
        mock_classify = AsyncMock(return_value={'misuse_score': 0.1, 'usage_type': 'none'})
        mock_get_classify.return_value = mock_classify
        _redis().set.return_value = True
        mock_escalate.return_value = {'action': 'none', 'previous_stage': 'none', 'new_stage': 'none'}

        triggered = [{'trigger': SoftCapTrigger.DAILY, 'speech_ms': 8000000, 'threshold_ms': 7200000}]
        await fair_use_mod.trigger_classifier_if_needed('user1', triggered)

        mock_notify.assert_not_called()

    @pytest.mark.asyncio
    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, '_get_classify_user_purpose')
    async def test_releases_lock_on_classifier_error(self, mock_get_classify):
        mock_classify = AsyncMock(side_effect=Exception('LLM timeout'))
        mock_get_classify.return_value = mock_classify
        _redis().set.return_value = True

        triggered = [{'trigger': SoftCapTrigger.DAILY, 'speech_ms': 8000000, 'threshold_ms': 7200000}]
        await fair_use_mod.trigger_classifier_if_needed('user1', triggered)

        # Lock should still be released via compare-and-delete
        _redis().eval.assert_called_once()

    @pytest.mark.asyncio
    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    async def test_handles_redis_lock_error(self):
        _redis().set.side_effect = Exception('Redis down')

        triggered = [{'trigger': SoftCapTrigger.DAILY, 'speech_ms': 8000000, 'threshold_ms': 7200000}]
        # Should not raise
        await fair_use_mod.trigger_classifier_if_needed('user1', triggered)


class TestSendFairUseNotification:
    """Test notification dispatch for each enforcement stage."""

    @pytest.mark.asyncio
    @patch.object(fair_use_mod, '_get_send_notification')
    async def test_sends_warning_notification(self, mock_get_send):
        mock_send = MagicMock()
        mock_get_send.return_value = mock_send
        await fair_use_mod._send_fair_use_notification('user1', 'warning')

        mock_send.assert_called_once()
        args = mock_send.call_args
        assert args[0][0] == 'user1'
        assert 'Fair Use Notice' in args[0][1]

    @pytest.mark.asyncio
    @patch.object(fair_use_mod, '_get_send_notification')
    async def test_sends_throttle_notification(self, mock_get_send):
        mock_send = MagicMock()
        mock_get_send.return_value = mock_send
        await fair_use_mod._send_fair_use_notification('user1', 'throttle')

        mock_send.assert_called_once()
        assert 'Transcription Quality Reduced' in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    @patch.object(fair_use_mod, '_get_send_notification')
    async def test_sends_restrict_notification(self, mock_get_send):
        mock_send = MagicMock()
        mock_get_send.return_value = mock_send
        await fair_use_mod._send_fair_use_notification('user1', 'restrict')

        mock_send.assert_called_once()
        assert 'Transcription Limit Reached' in mock_send.call_args[0][1]

    @pytest.mark.asyncio
    @patch.object(fair_use_mod, '_get_send_notification')
    async def test_no_notification_for_unknown_action(self, mock_get_send):
        mock_send = MagicMock()
        mock_get_send.return_value = mock_send
        await fair_use_mod._send_fair_use_notification('user1', 'unknown_action')

        mock_send.assert_not_called()


class TestBoundaryCaps:
    """Test exact boundary conditions for soft caps."""

    def setup_method(self):
        _reset()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(fair_use_mod, 'FAIR_USE_DAILY_SPEECH_MS', 7200000)
    @patch.object(fair_use_mod, 'FAIR_USE_3DAY_SPEECH_MS', 28800000)
    @patch.object(fair_use_mod, 'FAIR_USE_WEEKLY_SPEECH_MS', 36000000)
    @patch.object(fair_use_mod, 'get_rolling_speech_ms')
    def test_exact_cap_value_does_not_trigger(self, mock_speech):
        """Caps use > (strictly greater), so exact value should NOT trigger."""
        mock_speech.return_value = {'daily_ms': 7200000, 'three_day_ms': 28800000, 'weekly_ms': 36000000}
        result = fair_use_mod.check_soft_caps('user1')
        assert result == []

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(fair_use_mod, 'FAIR_USE_DAILY_SPEECH_MS', 7200000)
    @patch.object(fair_use_mod, 'FAIR_USE_3DAY_SPEECH_MS', 28800000)
    @patch.object(fair_use_mod, 'FAIR_USE_WEEKLY_SPEECH_MS', 36000000)
    @patch.object(fair_use_mod, 'get_rolling_speech_ms')
    def test_one_ms_over_cap_triggers(self, mock_speech):
        """One ms over should trigger."""
        mock_speech.return_value = {'daily_ms': 7200001, 'three_day_ms': 28800001, 'weekly_ms': 36000001}
        result = fair_use_mod.check_soft_caps('user1')
        assert len(result) == 3

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(fair_use_mod, 'FAIR_USE_DAILY_SPEECH_MS', 7200000)
    @patch.object(fair_use_mod, 'FAIR_USE_3DAY_SPEECH_MS', 28800000)
    @patch.object(fair_use_mod, 'FAIR_USE_WEEKLY_SPEECH_MS', 36000000)
    @patch.object(fair_use_mod, 'get_rolling_speech_ms')
    def test_only_daily_triggered(self, mock_speech):
        """Only daily cap exceeded, others under."""
        mock_speech.return_value = {'daily_ms': 8000000, 'three_day_ms': 10000000, 'weekly_ms': 15000000}
        result = fair_use_mod.check_soft_caps('user1')
        assert len(result) == 1
        assert result[0]['trigger'] == SoftCapTrigger.DAILY


class TestHardRestrictBoundary:
    """Test hard restriction at exact cap boundaries."""

    def setup_method(self):
        _reset()
        _fair_use_db.get_fair_use_state.reset_mock()
        _fair_use_db.update_fair_use_state.reset_mock()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(fair_use_mod, 'get_enforcement_stage', return_value='restrict')
    @patch.object(fair_use_mod, 'get_rolling_speech_ms')
    def test_exact_cap_not_hard_restricted(self, mock_speech, _):
        """At exactly the cap, should NOT be hard restricted (uses > not >=)."""
        _fair_use_db.get_fair_use_state.return_value = {
            'restrict_until': datetime.utcnow() + timedelta(days=7),
        }
        mock_speech.return_value = {'daily_ms': 7200000, 'three_day_ms': 28800000, 'weekly_ms': 36000000}

        assert fair_use_mod.is_hard_restricted('user1') is False


class TestFairUseStatusRestrictionExpiry:
    def setup_method(self):
        _reset()
        _fair_use_db.get_fair_use_state.reset_mock()
        _fair_use_db.update_fair_use_state.reset_mock()

    @staticmethod
    def _dg_budget():
        return {
            'daily_limit_ms': 0,
            'used_ms': 0,
            'remaining_ms': 0,
            'exhausted': False,
            'resets_at': None,
        }

    def test_status_normalizes_naturally_expired_restriction_with_one_state_read(self):
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'restrict_until': datetime.utcnow() - timedelta(seconds=1),
            'last_case_ref': 'FU-EXPIRED',
        }

        with patch.object(fair_use_admin_mod, 'fair_use_db', _fair_use_db), patch.object(
            fair_use_admin_mod,
            'get_rolling_speech_ms',
            return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0},
        ), patch.object(fair_use_admin_mod, 'get_dg_budget_status', return_value=self._dg_budget()):
            result = fair_use_admin_mod.get_my_fair_use_status('user1')

        assert result['stage'] == 'throttle'
        assert 'temporarily reduced' in result['message']
        _fair_use_db.get_fair_use_state.assert_called_once_with('user1')
        _fair_use_db.update_fair_use_state.assert_called_once_with(
            'user1', {'stage': 'throttle', 'restrict_until': None}
        )

    def test_status_preserves_active_restriction_with_one_state_read(self):
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'restrict_until': datetime.utcnow() + timedelta(days=1),
            'last_case_ref': 'FU-ACTIVE',
        }

        with patch.object(fair_use_admin_mod, 'fair_use_db', _fair_use_db), patch.object(
            fair_use_admin_mod,
            'get_rolling_speech_ms',
            return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0},
        ), patch.object(fair_use_admin_mod, 'get_dg_budget_status', return_value=self._dg_budget()):
            result = fair_use_admin_mod.get_my_fair_use_status('user1')

        assert result['stage'] == 'restrict'
        assert 'temporarily limited' in result['message']
        _fair_use_db.get_fair_use_state.assert_called_once_with('user1')
        _fair_use_db.update_fair_use_state.assert_not_called()


class TestOverflowAndInvalidData:
    """Test handling of unexpected Redis data."""

    def setup_method(self):
        _reset()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_none_hmget_values_skipped(self):
        """None values from HMGET (expired/missing buckets) should be ignored."""
        import time

        now = int(time.time())
        bucket = str((now - 3600) // 60)

        _redis().zrangebyscore.side_effect = [[bucket.encode()], [], []]
        _redis().hmget.return_value = [None]

        result = fair_use_mod.get_rolling_speech_ms('user1')
        assert result['daily_ms'] == 0
        assert result['weekly_ms'] == 0

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_redis_error_returns_zeros(self):
        """Redis errors should return zero totals, not raise."""
        _redis().zrangebyscore.side_effect = Exception('Connection refused')

        result = fair_use_mod.get_rolling_speech_ms('user1')
        assert result == {'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_very_large_speech_ms_accumulated(self):
        """Very large speech values should accumulate without overflow."""
        import time

        now = int(time.time())
        bucket = str((now - 60) // 60)

        _redis().zrangebyscore.side_effect = [[bucket.encode()], [], []]
        _redis().hmget.return_value = [b'999999999999']  # ~277 hours

        result = fair_use_mod.get_rolling_speech_ms('user1')
        assert result['daily_ms'] == 999999999999
        assert result['weekly_ms'] == 999999999999
