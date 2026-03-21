"""
Live integration tests for sync fair-use gates (#5854).

Requires: Redis on localhost:6379 (no password).
Tests the actual Redis operations (record_speech_ms with source param,
rolling window queries, and check_soft_caps) against a real Redis instance.
"""

import os
import time

import pytest
import redis

# Set up environment before importing fair_use
os.environ.setdefault('FAIR_USE_ENABLED', 'true')
os.environ.setdefault('FAIR_USE_KILL_SWITCH', 'false')
os.environ.setdefault('FAIR_USE_EXEMPT_UIDS', '')
os.environ.setdefault('ENCRYPTION_SECRET', 'test-secret-key-that-is-long-enough-for-encryption-32ch')

# Stub heavy deps
import sys
from types import ModuleType

for mod_name in [
    'database._client',
    'database.fair_use',
    'database.users',
    'database.user_usage',
    'database.conversations',
    'firebase_admin',
    'firebase_admin.messaging',
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = ModuleType(mod_name)

sys.modules['database._client'].db = None


# Check Redis availability
def _redis_available():
    try:
        r = redis.Redis(host='localhost', port=6379, socket_connect_timeout=2)
        r.ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _redis_available(), reason="Redis not available on localhost:6379")


@pytest.fixture(autouse=True)
def patch_redis():
    """Patch the fair_use module to use local Redis."""
    import database.redis_db as redis_db_mod

    local_redis = redis.Redis(host='localhost', port=6379, decode_responses=False)
    redis_db_mod.r = local_redis

    import utils.fair_use as fu

    fu.redis_client = local_redis
    # Ensure enabled
    original_enabled = fu.FAIR_USE_ENABLED
    fu.FAIR_USE_ENABLED = True

    yield local_redis

    fu.FAIR_USE_ENABLED = original_enabled


@pytest.fixture
def test_uid():
    """Unique test UID to avoid collisions."""
    uid = f'test-sync-{int(time.time() * 1000)}'
    yield uid
    # Cleanup
    import utils.fair_use as fu

    r = fu.redis_client
    r.delete(f'fair_use:speech:{uid}')
    r.delete(f'fair_use:bucket:{uid}')


class TestSyncFairUseLiveRedis:
    """Test fair-use operations with real Redis — simulating sync endpoint flow."""

    def test_record_speech_ms_source_sync_writes_to_redis(self, test_uid, patch_redis):
        """record_speech_ms with source='sync' writes to the same Redis keys as realtime."""
        import utils.fair_use as fu

        fu.record_speech_ms(test_uid, 30000, source='sync')

        # Verify data in Redis
        totals = fu.get_rolling_speech_ms(test_uid)
        assert totals['daily_ms'] == 30000
        assert totals['three_day_ms'] == 30000
        assert totals['weekly_ms'] == 30000

    def test_record_speech_ms_source_realtime_same_pool(self, test_uid, patch_redis):
        """Source='sync' and source='realtime' write to the same pool."""
        import utils.fair_use as fu

        fu.record_speech_ms(test_uid, 10000, source='realtime')
        fu.record_speech_ms(test_uid, 20000, source='sync')

        totals = fu.get_rolling_speech_ms(test_uid)
        # Both sources accumulate in the same pool
        assert totals['daily_ms'] == 30000

    def test_check_soft_caps_with_sync_speech(self, test_uid, patch_redis):
        """Sync speech contributes to soft cap checks."""
        import utils.fair_use as fu

        # Record enough to be under cap
        fu.record_speech_ms(test_uid, 1000, source='sync')
        caps = fu.check_soft_caps(test_uid)
        assert caps == []

    def test_sync_speech_triggers_daily_cap(self, test_uid, patch_redis):
        """Large sync upload can trigger daily soft cap."""
        import utils.fair_use as fu

        original_cap = fu.FAIR_USE_DAILY_SPEECH_MS
        fu.FAIR_USE_DAILY_SPEECH_MS = 5000  # Low cap for test

        try:
            fu.record_speech_ms(test_uid, 6000, source='sync')
            totals = fu.get_rolling_speech_ms(test_uid)
            caps = fu.check_soft_caps(test_uid, speech_totals=totals)
            assert len(caps) > 0
            assert caps[0]['trigger'].value == 'daily'
        finally:
            fu.FAIR_USE_DAILY_SPEECH_MS = original_cap

    def test_precomputed_totals_match_redis(self, test_uid, patch_redis):
        """get_rolling_speech_ms returns data that check_soft_caps can use."""
        import utils.fair_use as fu

        fu.record_speech_ms(test_uid, 5000, source='sync')
        totals = fu.get_rolling_speech_ms(test_uid)

        assert totals['daily_ms'] == 5000
        caps = fu.check_soft_caps(test_uid, speech_totals=totals)
        assert caps == []  # Under default caps

    def test_full_sync_flow_simulation(self, test_uid, patch_redis):
        """Simulate the full sync endpoint fair-use flow:
        1. Record speech from VAD segments
        2. Check soft caps
        3. Verify totals
        """
        import utils.fair_use as fu

        # Simulate VAD segments: 3 segments of ~30s each
        vad_segments = [
            {'start': 0.0, 'end': 30.0},
            {'start': 150.0, 'end': 180.0},
            {'start': 300.0, 'end': 330.0},
        ]
        total_speech_ms = int(sum(s['end'] - s['start'] for s in vad_segments)) * 1000
        assert total_speech_ms == 90000  # 90 seconds

        # Phase 1: Record speech
        fu.record_speech_ms(test_uid, total_speech_ms, source='sync')

        # Phase 2: Check caps
        totals = fu.get_rolling_speech_ms(test_uid)
        assert totals['daily_ms'] == 90000
        caps = fu.check_soft_caps(test_uid, speech_totals=totals)
        assert caps == []  # 90s << 2h daily cap
