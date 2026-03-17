"""
Level 1 live test: fair-use system against real Redis with reduced thresholds.

Run with:
  FAIR_USE_ENABLED=true FAIR_USE_DAILY_SPEECH_MS=10000 FAIR_USE_3DAY_SPEECH_MS=20000 \
  FAIR_USE_WEEKLY_SPEECH_MS=30000 FAIR_USE_CHECK_INTERVAL_SECONDS=5 \
  ENCRYPTION_SECRET="omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv" \
  pytest tests/integration/test_fair_use_live.py -v -s
"""

import os
import sys
import time
import types
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Pre-import stubs for heavy deps that aren't available locally
# ---------------------------------------------------------------------------
_db_client = types.ModuleType('database._client')
_db_client.db = MagicMock()
sys.modules.setdefault('database._client', _db_client)

# Firestore stubs
sys.modules.setdefault('google.cloud.firestore', MagicMock())
sys.modules.setdefault('google.cloud.firestore_v1', MagicMock())

# Stub database.fair_use with in-memory state
_fair_use_state = {}


class InMemoryFairUseDB:
    """In-memory Firestore replacement for fair_use state."""

    def __init__(self):
        self.states = {}
        self.events = []

    def get_fair_use_state(self, uid):
        return self.states.get(uid, {})

    def update_fair_use_state(self, uid, updates):
        if uid not in self.states:
            self.states[uid] = {}
        self.states[uid].update(updates)

    def create_fair_use_event(self, uid, event_data):
        event_id = f'evt-{len(self.events)}'
        self.events.append({'uid': uid, 'event_id': event_id, **event_data})
        return event_id

    def get_fair_use_events(self, uid, limit=50):
        return [e for e in self.events if e['uid'] == uid][:limit]

    def get_violation_counts(self, uid):
        events = [e for e in self.events if e['uid'] == uid]
        now = datetime.utcnow()
        count_7d = sum(1 for e in events if e.get('enforcement_action', 'none') != 'none')
        return {'violation_count_7d': count_7d, 'violation_count_30d': count_7d}

    def resolve_fair_use_event(self, uid, event_id, admin_uid='', notes=''):
        for e in self.events:
            if e['uid'] == uid and e['event_id'] == event_id:
                e['resolved'] = True
                e['admin_uid'] = admin_uid

    def reset_fair_use_state(self, uid, admin_uid=''):
        self.states.pop(uid, None)

    def get_flagged_users(self, stage_filter=None, limit=50):
        return []


_mem_db = InMemoryFairUseDB()
_fair_use_mod = types.ModuleType('database.fair_use')
_fair_use_mod.get_fair_use_state = _mem_db.get_fair_use_state
_fair_use_mod.update_fair_use_state = _mem_db.update_fair_use_state
_fair_use_mod.create_fair_use_event = _mem_db.create_fair_use_event
_fair_use_mod.get_fair_use_events = _mem_db.get_fair_use_events
_fair_use_mod.get_violation_counts = _mem_db.get_violation_counts
_fair_use_mod.resolve_fair_use_event = _mem_db.resolve_fair_use_event
_fair_use_mod.reset_fair_use_state = _mem_db.reset_fair_use_state
_fair_use_mod.get_flagged_users = _mem_db.get_flagged_users
sys.modules['database.fair_use'] = _fair_use_mod

sys.modules.setdefault('database.users', MagicMock())
sys.modules.setdefault('utils.notifications', MagicMock())

# Set env vars BEFORE importing fair_use
os.environ['FAIR_USE_ENABLED'] = 'true'
os.environ['FAIR_USE_DAILY_SPEECH_MS'] = '10000'  # 10 seconds
os.environ['FAIR_USE_3DAY_SPEECH_MS'] = '20000'  # 20 seconds
os.environ['FAIR_USE_WEEKLY_SPEECH_MS'] = '30000'  # 30 seconds
os.environ['FAIR_USE_CHECK_INTERVAL_SECONDS'] = '5'

# Now import fair_use — it reads real Redis
import utils.fair_use as fair_use

TEST_UID = f'live_test_user_{int(time.time())}'


def _cleanup_redis(uid):
    """Remove all fair_use Redis keys for a test user."""
    try:
        fair_use.redis_client.delete(
            fair_use._redis_key(uid),
            f'fair_use:bucket:{uid}',
            f'fair_use:stage:{uid}',
            f'fair_use:vad_delta:{uid}',
            f'fair_use:classifier_lock:{uid}',
        )
    except Exception:
        pass


@pytest.fixture(autouse=True)
def clean_redis():
    """Clean up Redis before and after each test."""
    _cleanup_redis(TEST_UID)
    _mem_db.states.clear()
    _mem_db.events.clear()
    yield
    _cleanup_redis(TEST_UID)


class TestRedisRecordAndRead:
    """Test speech recording and reading against real Redis."""

    def test_record_and_read_speech(self):
        """Record speech and verify it appears in rolling totals."""
        fair_use.record_speech_ms(TEST_UID, 5000)
        result = fair_use.get_rolling_speech_ms(TEST_UID)

        assert result['daily_ms'] == 5000
        assert result['three_day_ms'] == 5000
        assert result['weekly_ms'] == 5000

    def test_accumulates_across_records(self):
        """Multiple records in same bucket accumulate."""
        fair_use.record_speech_ms(TEST_UID, 3000)
        fair_use.record_speech_ms(TEST_UID, 4000)
        result = fair_use.get_rolling_speech_ms(TEST_UID)

        assert result['daily_ms'] == 7000

    def test_zero_speech_not_recorded(self):
        """Zero or negative speech should not be recorded."""
        fair_use.record_speech_ms(TEST_UID, 0)
        fair_use.record_speech_ms(TEST_UID, -100)
        result = fair_use.get_rolling_speech_ms(TEST_UID)

        assert result['daily_ms'] == 0


class TestSoftCapTriggerLive:
    """Test soft cap detection with real Redis and reduced thresholds."""

    def test_under_cap_no_trigger(self):
        """9 seconds (under 10s daily cap) should not trigger."""
        fair_use.record_speech_ms(TEST_UID, 9000)
        triggered = fair_use.check_soft_caps(TEST_UID)

        assert triggered == []

    def test_over_daily_cap_triggers(self):
        """11 seconds (over 10s daily cap) should trigger daily cap."""
        fair_use.record_speech_ms(TEST_UID, 11000)
        triggered = fair_use.check_soft_caps(TEST_UID)

        assert len(triggered) >= 1
        triggers = [t['trigger'].value for t in triggered]
        assert 'daily' in triggers

    def test_over_all_caps_triggers_all(self):
        """31 seconds (over all caps) should trigger all three."""
        fair_use.record_speech_ms(TEST_UID, 31000)
        triggered = fair_use.check_soft_caps(TEST_UID)

        assert len(triggered) == 3
        triggers = {t['trigger'].value for t in triggered}
        assert triggers == {'daily', '3day', 'weekly'}

    def test_exact_cap_does_not_trigger(self):
        """Exactly 10 seconds should NOT trigger (> not >=)."""
        fair_use.record_speech_ms(TEST_UID, 10000)
        triggered = fair_use.check_soft_caps(TEST_UID)

        assert triggered == []


class TestEscalationLive:
    """Test the full escalation state machine with real Redis + in-memory Firestore."""

    def test_escalate_to_warning(self):
        """First violation with high abuse score escalates to warning."""
        fair_use.record_speech_ms(TEST_UID, 11000)
        triggered = fair_use.check_soft_caps(TEST_UID)

        classifier_result = {'abuse_score': 0.9, 'abuse_type': 'audiobook'}
        result = fair_use.escalate_enforcement(TEST_UID, triggered, classifier_result)

        assert result['action'] == 'warning'
        assert result['new_stage'] == 'warning'
        assert _mem_db.states[TEST_UID]['stage'] == 'warning'

    def test_no_escalation_low_score(self):
        """Low abuse score should not escalate."""
        fair_use.record_speech_ms(TEST_UID, 11000)
        triggered = fair_use.check_soft_caps(TEST_UID)

        classifier_result = {'abuse_score': 0.3, 'abuse_type': 'none'}
        result = fair_use.escalate_enforcement(TEST_UID, triggered, classifier_result)

        assert result['action'] == 'none'
        assert result['new_stage'] == 'none'

    def test_escalate_warning_to_throttle(self):
        """Warning + 2 violations + high score -> throttle."""
        # Set up: user is already at warning with 2 prior violations
        _mem_db.states[TEST_UID] = {'stage': 'warning'}
        _mem_db.events.extend(
            [
                {'uid': TEST_UID, 'enforcement_action': 'warning'},
                {'uid': TEST_UID, 'enforcement_action': 'warning'},
            ]
        )

        fair_use.record_speech_ms(TEST_UID, 11000)
        triggered = fair_use.check_soft_caps(TEST_UID)

        classifier_result = {'abuse_score': 0.85, 'abuse_type': 'audiobook'}
        result = fair_use.escalate_enforcement(TEST_UID, triggered, classifier_result)

        assert result['action'] == 'throttle'
        assert result['new_stage'] == 'throttle'
        assert _mem_db.states[TEST_UID]['stage'] == 'throttle'
        assert _mem_db.states[TEST_UID]['vad_threshold_delta'] == fair_use.FAIR_USE_STAGE2_VAD_DELTA

    def test_escalate_throttle_to_restrict(self):
        """Throttle + 3 violations + high score -> restrict."""
        _mem_db.states[TEST_UID] = {'stage': 'throttle'}
        _mem_db.events.extend(
            [
                {'uid': TEST_UID, 'enforcement_action': 'warning'},
                {'uid': TEST_UID, 'enforcement_action': 'throttle'},
                {'uid': TEST_UID, 'enforcement_action': 'throttle'},
            ]
        )

        fair_use.record_speech_ms(TEST_UID, 31000)
        triggered = fair_use.check_soft_caps(TEST_UID)

        classifier_result = {'abuse_score': 0.92, 'abuse_type': 'audiobook'}
        result = fair_use.escalate_enforcement(TEST_UID, triggered, classifier_result)

        assert result['action'] == 'restrict'
        assert result['new_stage'] == 'restrict'
        assert 'restrict_until' in _mem_db.states[TEST_UID]


class TestHardRestrictionLive:
    """Test hard restriction checks with real Redis."""

    def test_restricted_user_over_cap(self):
        """Restricted user over cap should be hard restricted."""
        _mem_db.states[TEST_UID] = {
            'stage': 'restrict',
            'restrict_until': datetime.utcnow() + timedelta(days=7),
        }
        # Force cache miss
        fair_use.invalidate_enforcement_cache(TEST_UID)

        fair_use.record_speech_ms(TEST_UID, 11000)
        assert fair_use.is_hard_restricted(TEST_UID) is True

    def test_restricted_user_under_cap(self):
        """Restricted user under cap should NOT be hard restricted."""
        _mem_db.states[TEST_UID] = {
            'stage': 'restrict',
            'restrict_until': datetime.utcnow() + timedelta(days=7),
        }
        fair_use.invalidate_enforcement_cache(TEST_UID)

        fair_use.record_speech_ms(TEST_UID, 5000)
        assert fair_use.is_hard_restricted(TEST_UID) is False

    def test_expired_restriction_resets(self):
        """Expired restriction should reset to throttle."""
        _mem_db.states[TEST_UID] = {
            'stage': 'restrict',
            'restrict_until': datetime.utcnow() - timedelta(days=1),
        }
        fair_use.invalidate_enforcement_cache(TEST_UID)

        fair_use.record_speech_ms(TEST_UID, 11000)
        assert fair_use.is_hard_restricted(TEST_UID) is False
        assert _mem_db.states[TEST_UID]['stage'] == 'throttle'


class TestCacheInvalidation:
    """Test enforcement cache works with real Redis."""

    def test_stage_cache_reads_from_redis(self):
        """Stage should be cached in Redis after first read."""
        _mem_db.states[TEST_UID] = {'stage': 'warning'}

        stage = fair_use.get_enforcement_stage(TEST_UID)
        assert stage == 'warning'

        # Verify it's cached
        cached = fair_use.redis_client.get(f'fair_use:stage:{TEST_UID}')
        assert cached is not None
        assert (cached.decode() if isinstance(cached, bytes) else cached) == 'warning'

    def test_invalidate_clears_cache(self):
        """Invalidation should clear the Redis cache."""
        _mem_db.states[TEST_UID] = {'stage': 'warning'}
        fair_use.get_enforcement_stage(TEST_UID)  # populate cache

        fair_use.invalidate_enforcement_cache(TEST_UID)

        cached = fair_use.redis_client.get(f'fair_use:stage:{TEST_UID}')
        assert cached is None

    def test_vad_delta_cache(self):
        """VAD delta should be cached and returnable."""
        _mem_db.states[TEST_UID] = {'vad_threshold_delta': 0.08}

        delta = fair_use.get_user_vad_threshold_delta(TEST_UID)
        assert delta == 0.08

        # Second call should hit cache
        delta2 = fair_use.get_user_vad_threshold_delta(TEST_UID)
        assert delta2 == 0.08


class TestRedisLockLive:
    """Test the compare-and-delete lock against real Redis."""

    def test_lock_acquire_and_release(self):
        """Lock should be acquirable and releasable."""
        lock_key = fair_use._classifier_lock_key(TEST_UID)

        import uuid

        token = str(uuid.uuid4())
        acquired = fair_use.redis_client.set(lock_key, token, nx=True, ex=10)
        assert acquired is True

        # Same key should fail
        acquired2 = fair_use.redis_client.set(lock_key, 'other', nx=True, ex=10)
        assert acquired2 is not True  # Could be False or None

        # Release with correct token
        fair_use._release_lock(lock_key, token)

        # Now it should be acquirable again
        acquired3 = fair_use.redis_client.set(lock_key, 'new', nx=True, ex=10)
        assert acquired3 is True

        # Cleanup
        fair_use.redis_client.delete(lock_key)

    def test_release_with_wrong_token_does_not_delete(self):
        """Releasing with wrong token should NOT delete the lock."""
        lock_key = fair_use._classifier_lock_key(TEST_UID)

        import uuid

        real_token = str(uuid.uuid4())
        fair_use.redis_client.set(lock_key, real_token, nx=True, ex=10)

        # Try to release with wrong token
        fair_use._release_lock(lock_key, 'wrong_token')

        # Lock should still exist
        val = fair_use.redis_client.get(lock_key)
        assert val is not None
        assert (val.decode() if isinstance(val, bytes) else val) == real_token

        # Cleanup
        fair_use.redis_client.delete(lock_key)


class TestExemptUser:
    """Test exempt UID behavior with real Redis."""

    @patch.object(fair_use, 'FAIR_USE_EXEMPT_UIDS', {TEST_UID})
    def test_exempt_user_never_triggers(self):
        """Exempt user should never trigger caps even when over limit."""
        fair_use.record_speech_ms(TEST_UID, 50000)  # Way over all caps
        triggered = fair_use.check_soft_caps(TEST_UID)

        assert triggered == []

    @patch.object(fair_use, 'FAIR_USE_EXEMPT_UIDS', {TEST_UID})
    def test_exempt_user_not_hard_restricted(self):
        """Exempt user should never be hard restricted."""
        _mem_db.states[TEST_UID] = {
            'stage': 'restrict',
            'restrict_until': datetime.utcnow() + timedelta(days=7),
        }
        fair_use.invalidate_enforcement_cache(TEST_UID)

        fair_use.record_speech_ms(TEST_UID, 50000)
        assert fair_use.is_hard_restricted(TEST_UID) is False


class TestKillSwitch:
    """Test kill switch behavior."""

    @patch.object(fair_use, 'FAIR_USE_KILL_SWITCH', True)
    def test_kill_switch_disables_caps(self):
        """Kill switch should prevent any cap checks."""
        fair_use.record_speech_ms(TEST_UID, 50000)
        triggered = fair_use.check_soft_caps(TEST_UID)

        assert triggered == []

    @patch.object(fair_use, 'FAIR_USE_KILL_SWITCH', True)
    def test_kill_switch_disables_hard_restrict(self):
        """Kill switch should prevent hard restriction."""
        _mem_db.states[TEST_UID] = {
            'stage': 'restrict',
            'restrict_until': datetime.utcnow() + timedelta(days=7),
        }
        fair_use.invalidate_enforcement_cache(TEST_UID)

        fair_use.record_speech_ms(TEST_UID, 50000)
        assert fair_use.is_hard_restricted(TEST_UID) is False


class TestFullFlowEndToEnd:
    """End-to-end: record speech → trigger caps → escalate → hard restrict."""

    def test_full_escalation_lifecycle(self):
        """Walk through the entire lifecycle: none → warning → throttle → restrict → expire."""
        classifier_high = {'abuse_score': 0.9, 'abuse_type': 'audiobook'}

        # Step 1: Record speech over daily cap
        fair_use.record_speech_ms(TEST_UID, 11000)
        triggered = fair_use.check_soft_caps(TEST_UID)
        assert len(triggered) >= 1

        # Step 2: First escalation → warning
        r1 = fair_use.escalate_enforcement(TEST_UID, triggered, classifier_high)
        assert r1['new_stage'] == 'warning'
        assert fair_use.get_enforcement_stage(TEST_UID) == 'warning'

        # Step 3: Second escalation — still at warning (only 1 violation event so far)
        fair_use.invalidate_enforcement_cache(TEST_UID)
        r2 = fair_use.escalate_enforcement(TEST_UID, triggered, classifier_high)
        # r1 created event with action='warning' (count=1), r2 stays warning because count < 2
        # But r2 itself logs an event. After r2 completes, there are now 2 violation events.
        assert r2['new_stage'] == 'warning'

        # Step 4: Third call — now count=2 (from r1 + r2 events with action != 'none')
        # Actually r2 action was 'none' since it didn't escalate, so count is still 1.
        # We need to manually seed one more violation to reach count=2.
        _mem_db.events.append({'uid': TEST_UID, 'enforcement_action': 'warning'})  # simulate prior
        r3 = fair_use.escalate_enforcement(TEST_UID, triggered, classifier_high)
        assert r3['new_stage'] == 'throttle'
        fair_use.invalidate_enforcement_cache(TEST_UID)
        assert fair_use.get_user_vad_threshold_delta(TEST_UID) == fair_use.FAIR_USE_STAGE2_VAD_DELTA

        # Step 5: More violations → restrict (need 3+ violation events)
        fair_use.invalidate_enforcement_cache(TEST_UID)
        r4 = fair_use.escalate_enforcement(TEST_UID, triggered, classifier_high)
        assert r4['new_stage'] == 'restrict'

        # Step 6: Hard restriction should be active
        fair_use.invalidate_enforcement_cache(TEST_UID)
        assert fair_use.is_hard_restricted(TEST_UID) is True

        # Step 7: Simulate restriction expiry
        _mem_db.states[TEST_UID]['restrict_until'] = datetime.utcnow() - timedelta(hours=1)
        fair_use.invalidate_enforcement_cache(TEST_UID)
        assert fair_use.is_hard_restricted(TEST_UID) is False
        assert _mem_db.states[TEST_UID]['stage'] == 'throttle'

    def test_events_recorded_throughout(self):
        """Verify events are recorded for each escalation step."""
        classifier_high = {'abuse_score': 0.9, 'abuse_type': 'audiobook'}

        fair_use.record_speech_ms(TEST_UID, 31000)
        triggered = fair_use.check_soft_caps(TEST_UID)

        # Round 1: none → warning
        fair_use.escalate_enforcement(TEST_UID, triggered, classifier_high)
        # Seed violations so escalation thresholds are met
        _mem_db.events.append({'uid': TEST_UID, 'enforcement_action': 'warning'})
        # Round 2: warning → throttle (count=2)
        fair_use.invalidate_enforcement_cache(TEST_UID)
        fair_use.escalate_enforcement(TEST_UID, triggered, classifier_high)
        # Round 3: throttle → restrict (count=3+)
        fair_use.invalidate_enforcement_cache(TEST_UID)
        fair_use.escalate_enforcement(TEST_UID, triggered, classifier_high)

        events = _mem_db.get_fair_use_events(TEST_UID)
        # We get 3 real events + 1 seeded = at least 3 from escalate_enforcement
        real_events = [e for e in events if 'event_id' in e]
        stages = [e['new_stage'] for e in real_events]
        assert 'warning' in stages
        assert 'throttle' in stages
        assert 'restrict' in stages
