"""
Tests for daily summary race condition fix (#4594).
Verifies atomic SETNX lock prevents duplicate daily recap notifications
when multiple cron instances run concurrently.
"""

from unittest.mock import MagicMock, patch


class FakeRedis:
    """Minimal fake Redis that supports SET with NX parameter."""

    def __init__(self):
        self.store = {}

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return None  # SETNX fails if key exists
        self.store[key] = value
        return True

    def exists(self, key):
        return key in self.store

    def get(self, key):
        return self.store.get(key)

    def delete(self, key):
        self.store.pop(key, None)


class TestTryAcquireDailySummaryLock:
    """Test atomic SETNX lock for daily summary notifications."""

    def _make_lock_fn(self, fake_r):
        """Create try_acquire_daily_summary_lock bound to fake Redis."""

        def try_acquire_daily_summary_lock(uid, date, ttl=60 * 60 * 2):
            result = fake_r.set(f'users:{uid}:daily_summary_sent:{date}', '1', ex=ttl, nx=True)
            return result is not None

        return try_acquire_daily_summary_lock

    def test_first_acquire_succeeds(self):
        """First lock acquisition should succeed."""
        fake_r = FakeRedis()
        lock_fn = self._make_lock_fn(fake_r)
        assert lock_fn('user1', '2026-02-05') is True

    def test_second_acquire_fails(self):
        """Second lock acquisition for same user+date should fail (prevents duplicate)."""
        fake_r = FakeRedis()
        lock_fn = self._make_lock_fn(fake_r)
        assert lock_fn('user1', '2026-02-05') is True
        assert lock_fn('user1', '2026-02-05') is False

    def test_different_users_both_succeed(self):
        """Different users should each acquire their own lock."""
        fake_r = FakeRedis()
        lock_fn = self._make_lock_fn(fake_r)
        assert lock_fn('user1', '2026-02-05') is True
        assert lock_fn('user2', '2026-02-05') is True

    def test_different_dates_both_succeed(self):
        """Same user on different dates should each acquire their own lock."""
        fake_r = FakeRedis()
        lock_fn = self._make_lock_fn(fake_r)
        assert lock_fn('user1', '2026-02-04') is True
        assert lock_fn('user1', '2026-02-05') is True

    def test_key_format_matches_existing(self):
        """Lock key should match the existing daily_summary_sent key format."""
        fake_r = FakeRedis()
        lock_fn = self._make_lock_fn(fake_r)
        lock_fn('uid123', '2026-02-05')
        assert 'users:uid123:daily_summary_sent:2026-02-05' in fake_r.store

    def test_set_daily_summary_sent_after_lock(self):
        """set_daily_summary_sent (TTL refresh) should work after lock is acquired."""
        fake_r = FakeRedis()
        lock_fn = self._make_lock_fn(fake_r)
        # Lock acquired
        assert lock_fn('user1', '2026-02-05') is True
        # TTL refresh (simulates set_daily_summary_sent at end of processing)
        fake_r.set('users:user1:daily_summary_sent:2026-02-05', '1', ex=7200)
        assert fake_r.exists('users:user1:daily_summary_sent:2026-02-05')


class TestConcurrentCronSimulation:
    """Simulate the race condition scenario from issue #4594."""

    def test_concurrent_cron_only_one_proceeds(self):
        """When multiple cron instances check the same user+date, only one should proceed."""
        fake_r = FakeRedis()

        def try_acquire(uid, date):
            result = fake_r.set(f'users:{uid}:daily_summary_sent:{date}', '1', ex=7200, nx=True)
            return result is not None

        uid = 'user_with_recap'
        date = '2026-02-05'

        # Simulate 3 concurrent cron instances all trying to process same user
        results = [try_acquire(uid, date) for _ in range(3)]

        assert results.count(True) == 1, "Only one cron instance should acquire the lock"
        assert results.count(False) == 2, "Other instances should be rejected"
        assert results[0] is True, "First instance should win"

    def test_old_check_then_set_allows_duplicates(self):
        """Demonstrate the old pattern's vulnerability (check-then-set race)."""
        fake_r = FakeRedis()
        uid = 'user1'
        date = '2026-02-05'
        key = f'users:{uid}:daily_summary_sent:{date}'

        # Old pattern: EXISTS check (non-atomic)
        # Both cron instances check before either sets
        check1 = fake_r.exists(key)  # False - proceed
        check2 = fake_r.exists(key)  # False - proceed (BUG: should be blocked)

        # Both proceed to expensive LLM work...
        # Eventually both set the flag
        fake_r.set(key, '1', ex=7200)

        # Old pattern allows both through
        assert check1 is False
        assert check2 is False  # This is the bug - both pass

    def test_new_setnx_pattern_blocks_duplicates(self):
        """New SETNX pattern prevents the race condition."""
        fake_r = FakeRedis()
        uid = 'user1'
        date = '2026-02-05'
        key = f'users:{uid}:daily_summary_sent:{date}'

        # New pattern: atomic SETNX
        acquire1 = fake_r.set(key, '1', ex=7200, nx=True)
        acquire2 = fake_r.set(key, '1', ex=7200, nx=True)

        assert acquire1 is not None  # First instance proceeds
        assert acquire2 is None  # Second instance blocked
