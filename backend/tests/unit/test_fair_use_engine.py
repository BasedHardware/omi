"""Tests for the fair-use anti-abuse engine (utils/fair_use.py)."""

import sys
import types
from datetime import datetime, timedelta
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
_fair_use_db.get_fair_use_state = MagicMock(return_value={})
_fair_use_db.update_fair_use_state = MagicMock()
_fair_use_db.create_fair_use_event = MagicMock(return_value='evt-123')
_fair_use_db.get_violation_counts = MagicMock(return_value={'violation_count_7d': 0, 'violation_count_30d': 0})
sys.modules.setdefault('database.fair_use', _fair_use_db)

# Stub database.users
sys.modules.setdefault('database.users', MagicMock())

# Stub notifications
sys.modules.setdefault('utils.notifications', MagicMock())

# Now import the module under test
import utils.fair_use as fair_use_mod
from models.fair_use import SoftCapTrigger


class TestRecordSpeechMs:
    """Test Redis recording of speech milliseconds."""

    def setup_method(self):
        _mock_redis.reset_mock()
        _mock_redis.pipeline.return_value = MagicMock()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_records_positive_speech(self):
        pipe = MagicMock()
        _mock_redis.pipeline.return_value = pipe
        fair_use_mod.record_speech_ms('user1', 5000)
        assert pipe.hincrby.called
        assert pipe.zadd.called
        assert pipe.execute.called

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_ignores_zero_speech(self):
        pipe = MagicMock()
        _mock_redis.pipeline.return_value = pipe
        fair_use_mod.record_speech_ms('user1', 0)
        assert not pipe.execute.called

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_ignores_negative_speech(self):
        pipe = MagicMock()
        _mock_redis.pipeline.return_value = pipe
        fair_use_mod.record_speech_ms('user1', -100)
        assert not pipe.execute.called

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', False)
    def test_noop_when_disabled(self):
        pipe = MagicMock()
        _mock_redis.pipeline.return_value = pipe
        fair_use_mod.record_speech_ms('user1', 5000)
        assert not pipe.execute.called

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_handles_redis_error(self):
        _mock_redis.pipeline.side_effect = Exception('Redis down')
        # Should not raise
        fair_use_mod.record_speech_ms('user1', 5000)


class TestGetRollingSpeechMs:
    """Test rolling window speech totals from Redis."""

    def setup_method(self):
        _mock_redis.reset_mock()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    def test_returns_zeros_when_no_data(self):
        _mock_redis.zrangebyscore.return_value = []
        result = fair_use_mod.get_rolling_speech_ms('user1')
        assert result == {'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', False)
    def test_returns_zeros_when_disabled(self):
        result = fair_use_mod.get_rolling_speech_ms('user1')
        assert result == {'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_BUCKET_SECONDS', 60)
    def test_aggregates_buckets_correctly(self):
        import time

        now = int(time.time())
        # Bucket from 1 hour ago (within daily window)
        recent_bucket = str((now - 3600) // 60)
        # Bucket from 2 days ago (within 3-day window, outside daily)
        two_day_bucket = str((now - 2 * 86400) // 60)
        # Bucket from 5 days ago (within weekly, outside 3-day)
        five_day_bucket = str((now - 5 * 86400) // 60)

        _mock_redis.zrangebyscore.return_value = [
            recent_bucket.encode(),
            two_day_bucket.encode(),
            five_day_bucket.encode(),
        ]
        _mock_redis.hmget.return_value = [b'1000', b'2000', b'3000']

        result = fair_use_mod.get_rolling_speech_ms('user1')

        assert result['daily_ms'] == 1000
        assert result['three_day_ms'] == 3000  # 1000 + 2000
        assert result['weekly_ms'] == 6000  # 1000 + 2000 + 3000


class TestCheckSoftCaps:
    """Test soft cap violation detection."""

    def setup_method(self):
        _mock_redis.reset_mock()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(fair_use_mod, 'get_rolling_speech_ms')
    def test_no_violation_under_caps(self, mock_speech):
        mock_speech.return_value = {'daily_ms': 1000, 'three_day_ms': 2000, 'weekly_ms': 3000}
        result = fair_use_mod.check_soft_caps('user1')
        assert result == []

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(fair_use_mod, 'FAIR_USE_DAILY_SPEECH_MS', 7200000)
    @patch.object(fair_use_mod, 'get_rolling_speech_ms')
    def test_daily_cap_triggered(self, mock_speech):
        mock_speech.return_value = {'daily_ms': 8000000, 'three_day_ms': 8000000, 'weekly_ms': 8000000}
        result = fair_use_mod.check_soft_caps('user1')
        triggers = [t['trigger'] for t in result]
        assert SoftCapTrigger.DAILY in triggers

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', {'exempt-user'})
    @patch.object(fair_use_mod, 'get_rolling_speech_ms')
    def test_exempt_user_never_triggered(self, mock_speech):
        mock_speech.return_value = {'daily_ms': 999999999, 'three_day_ms': 999999999, 'weekly_ms': 999999999}
        result = fair_use_mod.check_soft_caps('exempt-user')
        assert result == []

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', True)
    def test_kill_switch_disables_caps(self):
        result = fair_use_mod.check_soft_caps('user1')
        assert result == []

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', False)
    def test_disabled_returns_empty(self):
        result = fair_use_mod.check_soft_caps('user1')
        assert result == []


class TestEscalateEnforcement:
    """Test the graduated enforcement state machine."""

    def setup_method(self):
        _mock_redis.reset_mock()
        _fair_use_db.get_fair_use_state.reset_mock()
        _fair_use_db.update_fair_use_state.reset_mock()
        _fair_use_db.create_fair_use_event.reset_mock()
        _fair_use_db.get_violation_counts.reset_mock()
        _fair_use_db.create_fair_use_event.return_value = 'evt-123'

    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_none_to_warning_on_high_abuse_score(self, _):
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'none'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 0, 'violation_count_30d': 0}

        triggered = [{'trigger': SoftCapTrigger.DAILY, 'speech_ms': 8000000, 'threshold_ms': 7200000}]
        classifier = {'abuse_score': 0.85, 'abuse_type': 'audiobook'}

        result = fair_use_mod.escalate_enforcement('user1', triggered, classifier)

        assert result['action'] == 'warning'
        assert result['new_stage'] == 'warning'
        assert _fair_use_db.update_fair_use_state.called

    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_none_stays_none_on_low_abuse_score(self, _):
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'none'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 0, 'violation_count_30d': 0}

        triggered = [{'trigger': SoftCapTrigger.DAILY, 'speech_ms': 8000000, 'threshold_ms': 7200000}]
        classifier = {'abuse_score': 0.3, 'abuse_type': 'none'}

        result = fair_use_mod.escalate_enforcement('user1', triggered, classifier)

        assert result['action'] == 'none'
        assert result['new_stage'] == 'none'
        assert not _fair_use_db.update_fair_use_state.called

    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_warning_to_throttle_on_repeated_violations(self, _):
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'warning'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 3, 'violation_count_30d': 5}

        triggered = [{'trigger': SoftCapTrigger.DAILY, 'speech_ms': 8000000, 'threshold_ms': 7200000}]
        classifier = {'abuse_score': 0.9, 'abuse_type': 'podcast'}

        result = fair_use_mod.escalate_enforcement('user1', triggered, classifier)

        assert result['action'] == 'throttle'
        assert result['new_stage'] == 'throttle'

    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_throttle_to_restrict_on_persistent_abuse(self, _):
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'throttle'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 4, 'violation_count_30d': 8}

        triggered = [{'trigger': SoftCapTrigger.WEEKLY, 'speech_ms': 40000000, 'threshold_ms': 36000000}]
        classifier = {'abuse_score': 0.95, 'abuse_type': 'commercial'}

        result = fair_use_mod.escalate_enforcement('user1', triggered, classifier)

        assert result['action'] == 'restrict'
        assert result['new_stage'] == 'restrict'

    @patch.object(
        fair_use_mod, 'get_rolling_speech_ms', return_value={'daily_ms': 0, 'three_day_ms': 0, 'weekly_ms': 0}
    )
    def test_warning_stays_warning_with_insufficient_violations(self, _):
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'warning'}
        _fair_use_db.get_violation_counts.return_value = {'violation_count_7d': 1, 'violation_count_30d': 1}

        triggered = [{'trigger': SoftCapTrigger.DAILY, 'speech_ms': 8000000, 'threshold_ms': 7200000}]
        classifier = {'abuse_score': 0.9, 'abuse_type': 'audiobook'}

        result = fair_use_mod.escalate_enforcement('user1', triggered, classifier)

        assert result['action'] == 'none'
        assert result['new_stage'] == 'warning'


class TestIsHardRestricted:
    """Test hard restriction check."""

    def setup_method(self):
        _mock_redis.reset_mock()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(fair_use_mod, 'get_rolling_speech_ms')
    def test_restricted_user_over_cap_is_hard_restricted(self, mock_speech):
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'restrict_until': datetime.utcnow() + timedelta(days=7),
        }
        mock_speech.return_value = {'daily_ms': 8000000, 'three_day_ms': 0, 'weekly_ms': 0}

        assert fair_use_mod.is_hard_restricted('user1') is True

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(fair_use_mod, 'get_rolling_speech_ms')
    def test_restricted_user_under_cap_is_not_hard_restricted(self, mock_speech):
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'restrict_until': datetime.utcnow() + timedelta(days=7),
        }
        mock_speech.return_value = {'daily_ms': 1000, 'three_day_ms': 1000, 'weekly_ms': 1000}

        assert fair_use_mod.is_hard_restricted('user1') is False

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    def test_non_restricted_user_is_not_hard_restricted(self):
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'warning'}
        assert fair_use_mod.is_hard_restricted('user1') is False

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', False)
    def test_disabled_is_not_hard_restricted(self):
        assert fair_use_mod.is_hard_restricted('user1') is False

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', {'exempt-user'})
    def test_exempt_user_is_not_hard_restricted(self):
        assert fair_use_mod.is_hard_restricted('exempt-user') is False

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    def test_expired_restriction_resets_to_throttle(self):
        _fair_use_db.get_fair_use_state.return_value = {
            'stage': 'restrict',
            'restrict_until': datetime.utcnow() - timedelta(days=1),  # Expired
        }
        result = fair_use_mod.is_hard_restricted('user1')
        assert result is False
        _fair_use_db.update_fair_use_state.assert_called_once()


class TestEnforcementCache:
    """Test Redis-cached enforcement stage lookups."""

    def setup_method(self):
        _mock_redis.reset_mock()

    def test_returns_cached_stage(self):
        _mock_redis.get.return_value = b'warning'
        stage = fair_use_mod.get_enforcement_stage('user1')
        assert stage == 'warning'

    def test_falls_back_to_firestore_on_cache_miss(self):
        _mock_redis.get.return_value = None
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'throttle'}
        stage = fair_use_mod.get_enforcement_stage('user1')
        assert stage == 'throttle'
        _mock_redis.setex.assert_called_once()

    def test_invalidate_cache_deletes_keys(self):
        fair_use_mod.invalidate_enforcement_cache('user1')
        _mock_redis.delete.assert_called_once()


class TestReleaseLock:
    """Test atomic compare-and-delete lock release."""

    def setup_method(self):
        _mock_redis.reset_mock()

    def test_release_calls_eval_with_lua_script(self):
        fair_use_mod._release_lock('lock:key', 'token-123')
        _mock_redis.eval.assert_called_once()
        args = _mock_redis.eval.call_args
        # Should pass key and token as arguments
        assert args[0][1] == 1  # numkeys
        assert args[0][2] == 'lock:key'
        assert args[0][3] == 'token-123'


class TestDatetimeNormalization:
    """Test that timezone-aware Firestore datetimes don't break enforcement."""

    def setup_method(self):
        _mock_redis.reset_mock()
        _fair_use_db.get_fair_use_state.reset_mock()
        _fair_use_db.update_fair_use_state.reset_mock()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    def test_aware_datetime_does_not_raise(self):
        from datetime import timezone

        # Simulate Firestore returning an aware datetime
        aware_past = datetime.now(timezone.utc) - timedelta(days=1)
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'restrict', 'restrict_until': aware_past}

        # Should not raise TypeError from naive/aware comparison
        result = fair_use_mod.is_hard_restricted('user1')
        assert result is False  # Expired restriction
        _fair_use_db.update_fair_use_state.assert_called_once()

    @patch.object(fair_use_mod, 'FAIR_USE_ENABLED', True)
    @patch.object(fair_use_mod, 'FAIR_USE_KILL_SWITCH', False)
    @patch.object(fair_use_mod, 'FAIR_USE_EXEMPT_UIDS', set())
    @patch.object(fair_use_mod, 'get_rolling_speech_ms')
    def test_aware_future_datetime_still_restricts(self, mock_speech):
        from datetime import timezone

        aware_future = datetime.now(timezone.utc) + timedelta(days=7)
        _fair_use_db.get_fair_use_state.return_value = {'stage': 'restrict', 'restrict_until': aware_future}
        mock_speech.return_value = {'daily_ms': 8000000, 'three_day_ms': 0, 'weekly_ms': 0}

        result = fair_use_mod.is_hard_restricted('user1')
        assert result is True
