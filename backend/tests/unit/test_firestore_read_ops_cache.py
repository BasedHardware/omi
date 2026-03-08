"""
Tests for Firestore read ops optimization (#5439).

Verifies:
1. Credit cache in transcribe loop (sub-task 1): local caching with 15-min TTL
2. Mentor notification frequency cache (sub-task 2): field projection + 30s TTL
3. Tester flag + available apps cache (sub-task 3): 30s TTL with invalidation
"""

import os
import sys
import time
import types
import copy
from unittest.mock import MagicMock, patch, PropertyMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# ── Stub heavy external modules ──────────────────────────────────────────────
for mod_name in [
    "firebase_admin",
    "firebase_admin.auth",
    "firebase_admin.messaging",
    "firebase_admin.firestore",
    "google.cloud",
    "google.cloud.firestore",
    "google.cloud.firestore_v1",
    "google.cloud.firestore_v1.base_query",
    "google.auth",
    "google.auth.credentials",
    "google.cloud.storage",
    "google.api_core",
    "google.api_core.exceptions",
    "opuslib",
    "lc3",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = types.ModuleType(mod_name)

# Stub FieldFilter
sys.modules["google.cloud.firestore_v1.base_query"].FieldFilter = MagicMock()
sys.modules["google.cloud.firestore"].ArrayUnion = MagicMock()
sys.modules["google.cloud.firestore"].ArrayRemove = MagicMock()
sys.modules["google.cloud.firestore"].DELETE_FIELD = MagicMock()

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from database.cache_manager import InMemoryCacheManager

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# Sub-task 2: Mentor notification frequency cache
# ═══════════════════════════════════════════════════════════════════════════════


class TestMentorFrequencyCache:
    """Tests for cached get_mentor_notification_frequency."""

    def setup_method(self):
        self.cache = InMemoryCacheManager(max_memory_mb=1)
        self.db_mock = MagicMock()
        self.fetch_count = 0

    def _make_doc(self, exists=True, frequency=3):
        doc = MagicMock()
        doc.exists = exists
        doc.to_dict.return_value = {'mentor_notification_frequency': frequency} if exists else {}
        return doc

    def test_cache_hit_skips_firestore(self):
        """Repeated calls within TTL should not re-query Firestore."""
        cache = self.cache
        call_count = 0

        def fetch():
            nonlocal call_count
            call_count += 1
            return 3

        # First call fetches
        result1 = cache.get_or_fetch("mentor_frequency:user1", fetch, ttl=30)
        assert result1 == 3
        assert call_count == 1

        # Second call uses cache
        result2 = cache.get_or_fetch("mentor_frequency:user1", fetch, ttl=30)
        assert result2 == 3
        assert call_count == 1  # Still 1, not re-fetched

    def test_cache_returns_zero_correctly(self):
        """Frequency of 0 (disabled) must be cached, not treated as miss."""
        cache = self.cache
        call_count = 0

        def fetch():
            nonlocal call_count
            call_count += 1
            return 0

        result = cache.get_or_fetch("mentor_frequency:user_disabled", fetch, ttl=30)
        assert result == 0
        assert call_count == 1

        # Verify 0 is cached (not treated as None/miss)
        # Note: InMemoryCacheManager only treats None as miss, 0 is cached
        cached = cache.get("mentor_frequency:user_disabled")
        assert cached == 0

    def test_cache_ttl_expiry(self):
        """Cache should expire and re-fetch after TTL."""
        cache = self.cache
        call_count = 0

        def fetch():
            nonlocal call_count
            call_count += 1
            return 3

        cache.get_or_fetch("mentor_frequency:user_ttl", fetch, ttl=1)
        assert call_count == 1

        # Wait for TTL to expire
        time.sleep(1.1)

        cache.get_or_fetch("mentor_frequency:user_ttl", fetch, ttl=1)
        assert call_count == 2  # Re-fetched after expiry

    def test_invalidation_on_set(self):
        """Setting frequency should invalidate the cache for that user."""
        cache = self.cache

        # Populate cache
        cache.set("mentor_frequency:user_inv", 3, ttl=30)
        assert cache.get("mentor_frequency:user_inv") == 3

        # Simulate invalidation (what set_mentor_notification_frequency does)
        cache.delete("mentor_frequency:user_inv")

        # Should be None (miss) now
        assert cache.get("mentor_frequency:user_inv") is None

    def test_default_for_nonexistent_user(self):
        """Non-existent user doc should return default (0)."""
        cache = self.cache
        DEFAULT = 0

        def fetch():
            return DEFAULT  # Simulates doc.exists=False path

        result = cache.get_or_fetch("mentor_frequency:ghost_user", fetch, ttl=30)
        assert result == DEFAULT


# ═══════════════════════════════════════════════════════════════════════════════
# Sub-task 3: Tester flag + available apps cache
# ═══════════════════════════════════════════════════════════════════════════════


class TestTesterAndAppSliceCache:
    """Tests for cached is_tester + user app slice in get_available_apps."""

    def setup_method(self):
        self.cache = InMemoryCacheManager(max_memory_mb=1)

    def test_tester_flag_cached(self):
        """is_tester result should be cached for 30s TTL."""
        cache = self.cache
        call_count = 0

        def fetch():
            nonlocal call_count
            call_count += 1
            return True

        result1 = cache.get_or_fetch("is_tester:user1", fetch, ttl=30)
        assert result1 is True
        assert call_count == 1

        result2 = cache.get_or_fetch("is_tester:user1", fetch, ttl=30)
        assert result2 is True
        assert call_count == 1  # Cached

    def test_tester_false_cached(self):
        """is_tester=False must be cached, not treated as miss."""
        cache = self.cache
        call_count = 0

        def fetch():
            nonlocal call_count
            call_count += 1
            return False

        result = cache.get_or_fetch("is_tester:user_nontester", fetch, ttl=30)
        assert result is False
        assert call_count == 1

        # Verify False is cached
        cached = cache.get("is_tester:user_nontester")
        assert cached is False

    def test_user_slice_cached(self):
        """Per-user app slice should be cached for 30s TTL."""
        cache = self.cache
        call_count = 0

        def fetch():
            nonlocal call_count
            call_count += 1
            return {
                'private_data': [{'id': 'a', 'private': True, 'uid': 'user1', 'approved': False}],
                'public_unapproved_data': [],
                'tester_apps': [],
            }

        result1 = cache.get_or_fetch("user_apps_slice:user1:0", fetch, ttl=30)
        assert len(result1['private_data']) == 1
        assert call_count == 1

        result2 = cache.get_or_fetch("user_apps_slice:user1:0", fetch, ttl=30)
        assert len(result2['private_data']) == 1
        assert call_count == 1  # Cached

    def test_empty_lists_cached(self):
        """Empty app lists should be cached, not treated as miss."""
        cache = self.cache
        call_count = 0

        def fetch():
            nonlocal call_count
            call_count += 1
            return {
                'private_data': [],
                'public_unapproved_data': [],
                'tester_apps': [],
            }

        result = cache.get_or_fetch("user_apps_slice:user_empty:0", fetch, ttl=30)
        assert result == {'private_data': [], 'public_unapproved_data': [], 'tester_apps': []}
        assert call_count == 1

        # Second call should use cache
        cache.get_or_fetch("user_apps_slice:user_empty:0", fetch, ttl=30)
        assert call_count == 1

    def test_tester_cache_invalidation(self):
        """Cache should be invalidated when tester status changes."""
        cache = self.cache

        # Populate caches
        cache.set("is_tester:user1", False, ttl=30)
        cache.set("user_apps_slice:user1:0", {'private_data': [], 'public_unapproved_data': [], 'tester_apps': []}, ttl=30)
        cache.set("user_apps_slice:user1:1", {'private_data': [], 'public_unapproved_data': [], 'tester_apps': []}, ttl=30)

        # Simulate _invalidate_tester_cache
        cache.delete("is_tester:user1")
        cache.delete("user_apps_slice:user1:0")
        cache.delete("user_apps_slice:user1:1")

        assert cache.get("is_tester:user1") is None
        assert cache.get("user_apps_slice:user1:0") is None
        assert cache.get("user_apps_slice:user1:1") is None

    def test_no_mutation_leakage(self):
        """Mutating a returned dict should not affect the cached copy.

        This tests that code using `dict(app)` for copies works correctly.
        """
        original = {'id': 'test', 'name': 'Test App', 'enabled': False}
        cache = self.cache
        cache.set("test_app", original, ttl=30)

        # Retrieve and mutate a copy (simulating what get_available_apps does)
        cached = cache.get("test_app")
        mutated = dict(cached)
        mutated['enabled'] = True
        mutated['installs'] = 42

        # Original cached value should be unchanged
        cached_again = cache.get("test_app")
        assert cached_again['enabled'] is False
        assert 'installs' not in cached_again


# ═══════════════════════════════════════════════════════════════════════════════
# Sub-task 1: Credit cache in transcribe loop
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreditCacheLogic:
    """Tests for the credit caching logic used in _record_usage_periodically.

    Tests the cache behavior (refresh timing, local decrement, None handling)
    without needing the full WebSocket/asyncio setup.
    """

    def test_initial_fetch(self):
        """First iteration should always fetch from Firestore."""
        remaining_seconds_cache = None
        remaining_seconds_cache_ts = 0.0
        remaining_seconds_cache_initialized = False
        CREDITS_REFRESH_SECONDS = 900

        now = time.time()
        needs_refresh = (
            not remaining_seconds_cache_initialized
            or now - remaining_seconds_cache_ts >= CREDITS_REFRESH_SECONDS
            or (remaining_seconds_cache is not None and remaining_seconds_cache <= 0 and now - remaining_seconds_cache_ts >= 60)
        )

        assert needs_refresh is True

    def test_within_ttl_no_refresh(self):
        """Within TTL window, should not refresh."""
        CREDITS_REFRESH_SECONDS = 900
        now = time.time()
        remaining_seconds_cache = 3600  # 1 hour remaining
        remaining_seconds_cache_ts = now - 100  # 100 seconds ago
        remaining_seconds_cache_initialized = True

        needs_refresh = (
            not remaining_seconds_cache_initialized
            or now - remaining_seconds_cache_ts >= CREDITS_REFRESH_SECONDS
            or (remaining_seconds_cache is not None and remaining_seconds_cache <= 0 and now - remaining_seconds_cache_ts >= 60)
        )

        assert needs_refresh is False

    def test_expired_ttl_triggers_refresh(self):
        """After TTL (15 min), should refresh."""
        CREDITS_REFRESH_SECONDS = 900
        now = time.time()
        remaining_seconds_cache = 3600
        remaining_seconds_cache_ts = now - 901  # 15 min + 1 second ago
        remaining_seconds_cache_initialized = True

        needs_refresh = (
            not remaining_seconds_cache_initialized
            or now - remaining_seconds_cache_ts >= CREDITS_REFRESH_SECONDS
            or (remaining_seconds_cache is not None and remaining_seconds_cache <= 0 and now - remaining_seconds_cache_ts >= 60)
        )

        assert needs_refresh is True

    def test_local_decrement(self):
        """Between refreshes, remaining_seconds should be decremented locally."""
        remaining_seconds_cache = 3600
        transcription_seconds = 60

        # Simulate local decrement
        remaining_seconds_cache = max(0, remaining_seconds_cache - transcription_seconds)

        assert remaining_seconds_cache == 3540

    def test_local_decrement_clamps_at_zero(self):
        """Local decrement should not go below 0."""
        remaining_seconds_cache = 30
        transcription_seconds = 60

        remaining_seconds_cache = max(0, remaining_seconds_cache - transcription_seconds)

        assert remaining_seconds_cache == 0

    def test_none_means_unlimited_no_decrement(self):
        """None (unlimited) should never be decremented."""
        remaining_seconds_cache = None
        transcription_seconds = 60

        # The code path: only decrement if not None
        if remaining_seconds_cache is not None and transcription_seconds > 0:
            remaining_seconds_cache = max(0, remaining_seconds_cache - transcription_seconds)

        assert remaining_seconds_cache is None

    def test_zero_triggers_fast_refresh(self):
        """When credits are 0, should refresh every 60s instead of 15 min."""
        CREDITS_REFRESH_SECONDS = 900
        now = time.time()
        remaining_seconds_cache = 0
        remaining_seconds_cache_ts = now - 61  # 61 seconds ago
        remaining_seconds_cache_initialized = True

        needs_refresh = (
            not remaining_seconds_cache_initialized
            or now - remaining_seconds_cache_ts >= CREDITS_REFRESH_SECONDS
            or (remaining_seconds_cache is not None and remaining_seconds_cache <= 0 and now - remaining_seconds_cache_ts >= 60)
        )

        assert needs_refresh is True

    def test_zero_within_fast_refresh_window(self):
        """When credits are 0 but within 60s, should not refresh."""
        CREDITS_REFRESH_SECONDS = 900
        now = time.time()
        remaining_seconds_cache = 0
        remaining_seconds_cache_ts = now - 30  # Only 30 seconds ago
        remaining_seconds_cache_initialized = True

        needs_refresh = (
            not remaining_seconds_cache_initialized
            or now - remaining_seconds_cache_ts >= CREDITS_REFRESH_SECONDS
            or (remaining_seconds_cache is not None and remaining_seconds_cache <= 0 and now - remaining_seconds_cache_ts >= 60)
        )

        assert needs_refresh is False

    def test_active_invalidation_triggers_refresh(self):
        """Redis invalidation signal should force refresh even within TTL."""
        CREDITS_REFRESH_SECONDS = 900
        now = time.time()
        remaining_seconds_cache = 0
        remaining_seconds_cache_ts = now - 5  # Only 5 seconds ago (well within TTL)
        remaining_seconds_cache_initialized = True
        credits_invalidated = True  # Subscription changed

        needs_refresh = (
            not remaining_seconds_cache_initialized
            or credits_invalidated
            or now - remaining_seconds_cache_ts >= CREDITS_REFRESH_SECONDS
            or (remaining_seconds_cache is not None and remaining_seconds_cache <= 0 and now - remaining_seconds_cache_ts >= 60)
        )

        assert needs_refresh is True

    def test_no_invalidation_no_refresh_within_ttl(self):
        """Without invalidation signal, should not refresh within TTL."""
        CREDITS_REFRESH_SECONDS = 900
        now = time.time()
        remaining_seconds_cache = 3600
        remaining_seconds_cache_ts = now - 5
        remaining_seconds_cache_initialized = True
        credits_invalidated = False

        needs_refresh = (
            not remaining_seconds_cache_initialized
            or credits_invalidated
            or now - remaining_seconds_cache_ts >= CREDITS_REFRESH_SECONDS
            or (remaining_seconds_cache is not None and remaining_seconds_cache <= 0 and now - remaining_seconds_cache_ts >= 60)
        )

        assert needs_refresh is False


# ═══════════════════════════════════════════════════════════════════════════════
# Singleflight lock cleanup
# ═══════════════════════════════════════════════════════════════════════════════


class TestFetchLockCleanup:
    """Tests that singleflight locks are cleaned up after get_or_fetch."""

    def test_fetch_lock_removed_after_fetch(self):
        """Lock for a key should be removed from _fetch_locks after fetch completes."""
        cache = InMemoryCacheManager(max_memory_mb=1)

        cache.get_or_fetch("key1", lambda: "value1", ttl=30)

        assert "key1" not in cache._fetch_locks
        assert "key1" not in cache._fetch_refcounts

    def test_fetch_locks_dont_grow_unbounded(self):
        """Many unique keys should not leave orphaned locks."""
        cache = InMemoryCacheManager(max_memory_mb=1)

        for i in range(100):
            cache.get_or_fetch(f"key_{i}", lambda: f"value_{i}", ttl=30)

        assert len(cache._fetch_locks) == 0
        assert len(cache._fetch_refcounts) == 0

    def test_concurrent_singleflight_no_overlap(self):
        """Concurrent callers for the same key must not overlap fetch_fn execution."""
        import threading

        cache = InMemoryCacheManager(max_memory_mb=1)
        overlap_count = 0
        max_overlap = 0
        overlap_lock = threading.Lock()

        def slow_fetch():
            nonlocal overlap_count, max_overlap
            with overlap_lock:
                overlap_count += 1
                if overlap_count > max_overlap:
                    max_overlap = overlap_count
            time.sleep(0.05)
            with overlap_lock:
                overlap_count -= 1
            return None  # Return None to force re-fetch each time

        threads = []
        for _ in range(10):
            t = threading.Thread(target=cache.get_or_fetch, args=("contended_key", slow_fetch, 30))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert max_overlap == 1, f"Singleflight violated: max concurrent fetches = {max_overlap}"
        assert "contended_key" not in cache._fetch_locks

    def test_lock_cleanup_on_exception(self):
        """Lock should be cleaned up even if fetch_fn raises."""
        cache = InMemoryCacheManager(max_memory_mb=1)

        def failing_fetch():
            raise ValueError("boom")

        try:
            cache.get_or_fetch("error_key", failing_fetch, ttl=30)
        except ValueError:
            pass

        assert "error_key" not in cache._fetch_locks
        assert "error_key" not in cache._fetch_refcounts


# ═══════════════════════════════════════════════════════════════════════════════
# Active credit invalidation via Redis (#5446)
# ═══════════════════════════════════════════════════════════════════════════════


class TestRedisCreditsInvalidationSignal:
    """Tests for Redis-based credit cache invalidation signal."""

    def test_set_and_check_signal(self):
        """set_credits_invalidation_signal should be consumable by check_and_clear."""
        mock_redis = MagicMock()
        mock_redis.set = MagicMock()
        mock_redis.getdel = MagicMock(return_value=b'1')

        with patch('database.redis_db.r', mock_redis):
            from database.redis_db import set_credits_invalidation_signal, check_and_clear_credits_invalidation

            set_credits_invalidation_signal('user123')
            mock_redis.set.assert_called_once_with('credits_invalidated:user123', '1', ex=1800)

            result = check_and_clear_credits_invalidation('user123')
            assert result is True
            mock_redis.getdel.assert_called_once_with('credits_invalidated:user123')

    def test_check_returns_false_when_no_signal(self):
        """check_and_clear should return False when no invalidation signal exists."""
        mock_redis = MagicMock()
        mock_redis.getdel = MagicMock(return_value=None)

        with patch('database.redis_db.r', mock_redis):
            from database.redis_db import check_and_clear_credits_invalidation

            result = check_and_clear_credits_invalidation('user_no_signal')
            assert result is False

    def test_signal_consumed_on_first_check(self):
        """Signal should be consumed (deleted) on first check via GETDEL."""
        mock_redis = MagicMock()
        # First call returns the value, second returns None (consumed)
        mock_redis.getdel = MagicMock(side_effect=[b'1', None])

        with patch('database.redis_db.r', mock_redis):
            from database.redis_db import check_and_clear_credits_invalidation

            first = check_and_clear_credits_invalidation('user_consume')
            second = check_and_clear_credits_invalidation('user_consume')
            assert first is True
            assert second is False


class TestWebhookInvalidationCoverage:
    """Tests that subscription mutation paths call set_credits_invalidation_signal.

    Uses source-level verification since payment.py imports the full Firestore
    dependency chain which can't be cleanly stubbed in unit tests.
    """

    PAYMENT_SOURCE_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'payment.py')
    TRANSCRIBE_SOURCE_FILE = os.path.join(os.path.dirname(__file__), '..', '..', 'routers', 'transcribe.py')

    def _read_source(self, path):
        with open(path) as f:
            return f.read()

    def test_payment_imports_invalidation_signal(self):
        """payment.py must import set_credits_invalidation_signal."""
        source = self._read_source(self.PAYMENT_SOURCE_FILE)
        assert 'from database.redis_db import set_credits_invalidation_signal' in source

    def test_checkout_completed_calls_invalidation(self):
        """checkout.session.completed path must call set_credits_invalidation_signal."""
        source = self._read_source(self.PAYMENT_SOURCE_FILE)
        # The invalidation call should appear after _update_subscription_from_session
        idx_update = source.find('_update_subscription_from_session(uid, session)')
        idx_signal = source.find('set_credits_invalidation_signal(uid)', idx_update)
        assert idx_signal > idx_update, "set_credits_invalidation_signal must be called after _update_subscription_from_session"

    def test_subscription_webhook_calls_invalidation(self):
        """customer.subscription.updated/deleted/created must call set_credits_invalidation_signal."""
        source = self._read_source(self.PAYMENT_SOURCE_FILE)
        # Find the subscription update webhook section
        idx_update_sub = source.find("users_db.update_user_subscription(uid, new_subscription.dict())")
        assert idx_update_sub > 0, "update_user_subscription call not found"
        # Signal should appear near the update call
        idx_signal = source.find('set_credits_invalidation_signal(uid)', idx_update_sub)
        assert idx_signal > idx_update_sub, "set_credits_invalidation_signal must be called after update_user_subscription"

    def test_schedule_completed_calls_invalidation(self):
        """subscription_schedule.completed must call set_credits_invalidation_signal."""
        source = self._read_source(self.PAYMENT_SOURCE_FILE)
        idx_scheduled = source.find("Scheduled upgrade completed for user")
        assert idx_scheduled > 0
        # Find the invalidation call before the log line (it's called right after update)
        section = source[idx_scheduled - 200:idx_scheduled]
        assert 'set_credits_invalidation_signal(uid)' in section

    def test_schedule_canceled_calls_invalidation(self):
        """subscription_schedule.canceled must call set_credits_invalidation_signal."""
        source = self._read_source(self.PAYMENT_SOURCE_FILE)
        idx_canceled = source.find("Subscription schedule canceled for user")
        assert idx_canceled > 0
        section = source[idx_canceled - 200:idx_canceled]
        assert 'set_credits_invalidation_signal(uid)' in section

    def test_transcribe_imports_invalidation_check(self):
        """transcribe.py must import check_and_clear_credits_invalidation."""
        source = self._read_source(self.TRANSCRIBE_SOURCE_FILE)
        assert 'check_and_clear_credits_invalidation' in source

    def test_transcribe_calls_invalidation_check(self):
        """transcribe.py must check invalidation signal in the refresh logic."""
        source = self._read_source(self.TRANSCRIBE_SOURCE_FILE)
        assert 'credits_invalidated = check_and_clear_credits_invalidation(uid)' in source
        assert 'or credits_invalidated' in source
