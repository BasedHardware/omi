"""Unit tests for DailyRefreshCache.

The cache has three behaviors to pin:
1. TTL: stale cache triggers loader call.
2. Lock: concurrent callers serialize; only one loader invocation on cache miss.
3. Stale fallback: loader raise on refresh returns last good value; loader raise
   on first-ever call propagates.
"""

import asyncio
import pytest

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

        # Next call: loader raises, stale fallback returns "first".
        result = await cache.get_or_refresh(loader)
        assert result == "first"
        # The cached value is still set; age_seconds is None (no successful load).
        assert cache.has_value
        assert cache.age_seconds is None
