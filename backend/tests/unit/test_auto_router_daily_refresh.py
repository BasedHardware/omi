"""Unit tests for DailyRefreshCache.

The cache has three behaviors to pin:
1. TTL: stale cache triggers loader call.
2. Lock: concurrent callers serialize; only one loader invocation on cache miss.
3. Stale fallback: loader raise on refresh returns last good value; loader raise
   on first-ever call propagates.
"""

import asyncio
import pytest
from datetime import datetime, timezone

from utils.auto_router.daily_refresh import DailyRefreshCache

# pyproject.toml sets asyncio_mode=STRICT, so every async test needs an explicit marker.
# Apply to all tests in this module at once.
pytestmark = pytest.mark.asyncio


class _Clock:
    """Manual clock for deterministic TTL tests."""

    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# ---------------------------------------------------------------------------
# AC1: Fresh cache returns cached value without calling loader
# ---------------------------------------------------------------------------


class TestFreshCache:
    """A cache that has been recently populated should not invoke the loader again."""

    async def test_fresh_cache_returns_value_without_loader_call(self):
        clock = _Clock()
        cache: DailyRefreshCache[int] = DailyRefreshCache(ttl_seconds=60, clock=clock)
        loader_calls = []

        async def loader() -> int:
            loader_calls.append(1)
            return 42

        # First call populates the cache.
        first = await cache.get_or_refresh(loader)
        assert first == 42
        assert len(loader_calls) == 1

        # Subsequent calls within TTL do NOT invoke loader.
        clock.advance(30)
        second = await cache.get_or_refresh(loader)
        third = await cache.get_or_refresh(loader)
        assert second == 42
        assert third == 42
        assert len(loader_calls) == 1

    async def test_fresh_cache_at_exactly_ttl_boundary_is_stale(self):
        # At age == ttl, cache is stale (strict `<` comparison in _is_fresh).
        clock = _Clock()
        cache: DailyRefreshCache[int] = DailyRefreshCache(ttl_seconds=60, clock=clock)

        async def loader() -> int:
            return 1

        await cache.get_or_refresh(loader)
        cache.loader_call_count = 0  # reset counter

        clock.advance(60)  # exactly at TTL boundary
        await cache.get_or_refresh(loader)
        assert cache.loader_call_count == 1


# ---------------------------------------------------------------------------
# AC2: Stale cache triggers loader call
# ---------------------------------------------------------------------------


class TestStaleCache:
    """A cache past its TTL should refresh on next call."""

    async def test_stale_cache_invokes_loader(self):
        clock = _Clock()
        cache: DailyRefreshCache[str] = DailyRefreshCache(ttl_seconds=60, clock=clock)
        call_count = 0

        async def loader() -> str:
            nonlocal call_count
            call_count += 1
            return f"value-{call_count}"

        first = await cache.get_or_refresh(loader)
        assert first == "value-1"
        assert call_count == 1

        clock.advance(61)  # past TTL

        second = await cache.get_or_refresh(loader)
        assert second == "value-2"
        assert call_count == 2


# ---------------------------------------------------------------------------
# AC3: Lock contention — 10 concurrent calls fire exactly 1 loader
# ---------------------------------------------------------------------------


class TestLockContention:
    """Concurrent callers on an empty cache should fire the loader only ONCE."""

    async def test_ten_concurrent_calls_with_empty_cache_invoke_loader_once(self):
        cache: DailyRefreshCache[int] = DailyRefreshCache(ttl_seconds=60)

        async def slow_loader() -> int:
            await asyncio.sleep(0.05)  # ensure other callers queue up first
            return 42

        results = await asyncio.gather(*[cache.get_or_refresh(slow_loader) for _ in range(10)])
        assert all(r == 42 for r in results)
        assert cache.loader_call_count == 1

    async def test_concurrent_calls_with_fresh_cache_dont_invoke_loader(self):
        cache: DailyRefreshCache[int] = DailyRefreshCache(ttl_seconds=60)
        loader_calls = 0

        async def loader() -> int:
            nonlocal loader_calls
            loader_calls += 1
            await asyncio.sleep(0.01)
            return 7

        # First call populates.
        await cache.get_or_refresh(loader)
        assert loader_calls == 1

        # 10 concurrent calls while fresh.
        results = await asyncio.gather(*[cache.get_or_refresh(loader) for _ in range(10)])
        assert all(r == 7 for r in results)
        assert loader_calls == 1  # loader NOT re-invoked


# ---------------------------------------------------------------------------
# AC4: Loader raises → returns last good value (stale fallback)
# ---------------------------------------------------------------------------


class TestStaleFallback:
    """Loader raise on refresh should fall back to the previously cached value."""

    async def test_loader_raises_on_refresh_returns_stale_value(self):
        cache: DailyRefreshCache[str] = DailyRefreshCache(ttl_seconds=60)
        call_count = 0

        async def flaky_loader() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "good-value"
            raise RuntimeError("upstream API is down")

        # First call succeeds.
        first = await cache.get_or_refresh(flaky_loader)
        assert first == "good-value"

        # Force the cache to be considered stale (without invalidating the value).
        # We do this by manipulating the cache directly via a small trick:
        # since _last_loaded_at is private, we instead call invalidate() and rely
        # on the fact that invalidate preserves the value for stale-fallback.
        cache.invalidate()

        # Second call: loader raises, but stale value should be returned.
        second = await cache.get_or_refresh(flaky_loader)
        assert second == "good-value"


# ---------------------------------------------------------------------------
# AC5: Loader raises on first-ever call → propagates
# ---------------------------------------------------------------------------


class TestFirstCallPropagates:
    """If the loader raises and there's NO cached value, the exception propagates."""

    async def test_loader_raises_on_empty_cache_propagates(self):
        cache: DailyRefreshCache[int] = DailyRefreshCache(ttl_seconds=60)

        async def failing_loader() -> int:
            raise ValueError("upstream API is down")

        with pytest.raises(ValueError, match="upstream API is down"):
            await cache.get_or_refresh(failing_loader)


# ---------------------------------------------------------------------------
# AC6: age_seconds
# ---------------------------------------------------------------------------


class TestAgeTracking:
    """age_seconds returns seconds since last load, or None if never loaded."""

    async def test_age_seconds_none_when_never_loaded(self):
        cache: DailyRefreshCache[int] = DailyRefreshCache(ttl_seconds=60, clock=_Clock())
        assert cache.age_seconds is None

    async def test_age_seconds_tracks_elapsed_time(self):
        clock = _Clock()
        cache: DailyRefreshCache[int] = DailyRefreshCache(ttl_seconds=60, clock=clock)

        async def loader() -> int:
            return 1

        await cache.get_or_refresh(loader)
        assert cache.age_seconds == 0.0

        clock.advance(30)
        assert cache.age_seconds == 30.0

        clock.advance(30)
        assert cache.age_seconds == 60.0

    async def test_age_seconds_never_negative(self):
        clock = _Clock()
        cache: DailyRefreshCache[int] = DailyRefreshCache(ttl_seconds=60, clock=clock)

        async def loader() -> int:
            return 1

        await cache.get_or_refresh(loader)
        # Even if clock somehow goes backward, age should clamp to 0.
        clock.now -= 1000
        assert cache.age_seconds == 0.0


# ---------------------------------------------------------------------------
# AC7: Custom TTL
# ---------------------------------------------------------------------------


class TestCustomTTL:
    """The TTL is configurable."""

    async def test_ttl_of_one_second(self):
        clock = _Clock()
        cache: DailyRefreshCache[int] = DailyRefreshCache(ttl_seconds=1, clock=clock)

        async def loader() -> int:
            return 1

        await cache.get_or_refresh(loader)
        cache.loader_call_count = 0

        clock.advance(0.5)
        await cache.get_or_refresh(loader)
        assert cache.loader_call_count == 0  # still fresh

        clock.advance(0.6)  # total 1.1s elapsed
        await cache.get_or_refresh(loader)
        assert cache.loader_call_count == 1  # stale, refreshed

    async def test_zero_or_negative_ttl_rejected(self):
        # Constructor validation is sync, but we mark async to inherit the
        # module-level pytestmark; the async keyword is harmless here.
        with pytest.raises(ValueError, match="ttl_seconds must be > 0"):
            DailyRefreshCache(ttl_seconds=0)
        with pytest.raises(ValueError, match="ttl_seconds must be > 0"):
            DailyRefreshCache(ttl_seconds=-1)


# ---------------------------------------------------------------------------
# AC8: invalidate() forces next refresh
# ---------------------------------------------------------------------------


class TestInvalidate:
    """invalidate() forces the next call to refresh (without clearing value)."""

    async def test_invalidate_forces_refresh_but_keeps_value_for_fallback(self):
        clock = _Clock()
        cache: DailyRefreshCache[str] = DailyRefreshCache(ttl_seconds=60, clock=clock)
        call_count = 0

        async def loader() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "first"
            raise RuntimeError("boom")

        # Populate.
        first = await cache.get_or_refresh(loader)
        assert first == "first"

        # Invalidate.
        cache.invalidate()

        # Advance clock past TTL so the next call refreshes.
        clock.advance(61)

        # Next call: loader raises, stale fallback returns "first".
        result = await cache.get_or_refresh(loader)
        assert result == "first"
        # The cached value is still set (for stale fallback).
        assert cache.has_value
        # NEW behavior (cubic fix): _last_loaded_at is NOT advanced on failure.
        # The failure cooldown tracks when to retry — separate from the
        # "last successful load" timestamp.
        # After a failure: age_seconds is None (no successful load since invalidate).
        assert cache.age_seconds is None
        # _last_failed_at is set (will trigger retry after failure_cooldown elapses).
        assert cache._last_failed_at == 1061.0


# ---------------------------------------------------------------------------
# AC: last_loaded_wall_time (used by endpoint for updated_at)
# ---------------------------------------------------------------------------


class TestLastLoadedWallTime:
    """Endpoint uses cache.last_loaded_wall_time() to set updated_at."""

    async def test_last_loaded_wall_time_none_before_load(self):
        cache: DailyRefreshCache[str] = DailyRefreshCache(ttl_seconds=60)
        assert cache.last_loaded_wall_time() is None
        assert cache.last_loaded_at is None

    async def test_last_loaded_wall_time_set_after_load(self):
        cache: DailyRefreshCache[str] = DailyRefreshCache(ttl_seconds=60)

        async def loader() -> str:
            return "value"

        await cache.get_or_refresh(loader)
        # Should be a recent datetime (within last few seconds).
        wall_time = cache.last_loaded_wall_time()
        assert wall_time is not None
        elapsed = (datetime.now(timezone.utc) - wall_time).total_seconds()
        assert 0 <= elapsed < 5, f"last_loaded_wall_time should be very recent, got {elapsed}s ago"


# ---------------------------------------------------------------------------
# Failure cooldown (cubic review)
# ---------------------------------------------------------------------------


class TestDailyRefreshFailureCooldown:
    """Cubic review caught that failed refreshes would advance _last_loaded_at
    to now(), causing the cache to be "fresh" for the full TTL (24h) even
    though the data was stale. Now we use a separate _last_failed_at timestamp
    + failure_cooldown to force a retry sooner than the full TTL after a
    transient backend outage."""

    @pytest.mark.asyncio
    async def test_retry_after_failure_cooldown_not_full_ttl(self):
        """After a failure, the next refresh fires after failure_cooldown
        (5 min default), not after the full TTL (24h).

        The cooldown is the NEW gate: previously, after a failure the
        cache was marked fresh for the full TTL (24h of stale data). Now
        after failure_cooldown elapses, the loader is called again.

        We verify this by counting loader calls. Without the cooldown,
        the old code would mark the cache fresh after the failure and
        never call the loader again until the full TTL elapsed.
        """
        from utils.auto_router.daily_refresh import DailyRefreshCache

        fake_clock = [1000.0]
        cache = DailyRefreshCache(
            ttl_seconds=24 * 60 * 60,  # 24h
            clock=lambda: fake_clock[0],
            failure_cooldown_seconds=5 * 60,  # 5 min
        )

        call_count = 0

        async def loader():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "first-success"
            if call_count == 2:
                raise RuntimeError("transient")
            return f"recovered-{call_count}"

        # First call: succeeds at t=1000.
        result = await cache.get_or_refresh(loader)
        assert result == "first-success"
        assert cache._last_loaded_at == 1000.0
        assert cache._last_failed_at is None
        assert call_count == 1

        # 1 minute later — still within TTL, cache is fresh.
        fake_clock[0] += 60
        result = await cache.get_or_refresh(loader)
        assert result == "first-success"  # no loader call
        assert call_count == 1

        # 1 hour later — within TTL. Force a refresh via invalidate.
        fake_clock[0] += 60 * 60
        cache.invalidate()
        result = await cache.get_or_refresh(loader)
        # The loader was called (call 2), raised. Stale value returned.
        assert result == "first-success"
        assert call_count == 2
        # _last_failed_at is set.
        assert cache._last_failed_at == fake_clock[0]

        # 1 minute after the failure — still in failure cooldown.
        # Without the cooldown, this would also return stale (the previous
        # bug). The cooldown ensures we don't retry too fast.
        fake_clock[0] += 60
        result = await cache.get_or_refresh(loader)
        assert result == "first-success"  # stale value
        assert call_count == 2  # loader NOT re-called (cooldown active)

        # 6 minutes after the failure — past failure cooldown.
        # NEW: the loader should be called again (cooldown has elapsed).
        # OLD BUG: the cache would still be marked fresh from the failure
        # (we set _last_loaded_at = now() in the old code), so the loader
        # would NOT be called and stale data would persist for the full TTL.
        fake_clock[0] += 5 * 60 + 1
        result = await cache.get_or_refresh(loader)
        assert call_count == 3, f"Loader should be called after cooldown elapses, but was called {call_count} times"
        assert result == "recovered-3"

    @pytest.mark.asyncio
    async def test_failure_cooldown_capped_at_ttl(self):
        """If failure_cooldown > ttl, cap it at ttl (would be silly to wait longer)."""
        from utils.auto_router.daily_refresh import DailyRefreshCache

        fake_clock = [1000.0]
        cache = DailyRefreshCache(
            ttl_seconds=60,  # 1 min TTL
            clock=lambda: fake_clock[0],
            failure_cooldown_seconds=10 * 60,  # 10 min requested
        )
        # Cooldown is capped at ttl_seconds (60).
        assert cache._failure_cooldown == 60

    @pytest.mark.asyncio
    async def test_successful_refresh_clears_failure_state(self):
        """A successful refresh clears _last_failed_at (so the cache
        returns to "fresh" status and the failure cooldown is no longer
        blocking subsequent reads)."""
        from utils.auto_router.daily_refresh import DailyRefreshCache

        fake_clock = [1000.0]
        cache = DailyRefreshCache(
            ttl_seconds=24 * 60 * 60,
            clock=lambda: fake_clock[0],
        )

        async def good_loader():
            return "fresh-value"

        async def bad_loader():
            raise RuntimeError("transient")

        # First refresh succeeds (populates cache).
        await cache.get_or_refresh(good_loader)
        assert cache._last_failed_at is None

        # Advance past TTL, then fail.
        fake_clock[0] += 24 * 60 * 60 + 1
        result = await cache.get_or_refresh(bad_loader)
        assert result == "fresh-value"
        assert cache._last_failed_at == fake_clock[0]

        # Advance past failure cooldown.
        fake_clock[0] += 5 * 60 + 1
        # Next call succeeds — failure state cleared.
        result2 = await cache.get_or_refresh(good_loader)
        assert result2 == "fresh-value"
        assert cache._last_failed_at is None, "Failure state should be cleared on success"
        assert cache._is_fresh()

    @pytest.mark.asyncio
    async def test_invalidate_clears_failure_state(self):
        """invalidate() clears _last_failed_at so the next call fires immediately
        (caller is signaling "try again now", don't wait for cooldown)."""
        from utils.auto_router.daily_refresh import DailyRefreshCache

        fake_clock = [1000.0]
        cache = DailyRefreshCache(
            ttl_seconds=24 * 60 * 60,
            clock=lambda: fake_clock[0],
        )

        # Populate with a good value first.
        async def good_loader():
            return "value"

        await cache.get_or_refresh(good_loader)
        assert cache._last_failed_at is None

        # Advance past TTL, then fail.
        fake_clock[0] += 24 * 60 * 60 + 1

        async def bad_loader():
            raise RuntimeError("transient")

        await cache.get_or_refresh(bad_loader)
        assert cache._last_failed_at == fake_clock[0]

        # Invalidate.
        cache.invalidate()
        assert cache._last_failed_at is None
        assert cache._last_loaded_at is None
