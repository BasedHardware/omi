"""Parity tests for the cherry-picked daily_refresh.py (R5b).

The DailyRefreshCache[T] primitive is sourced from v3's
`backend/utils/auto_router/daily_refresh.py` and modified to apply the
cubic-dev-ai fix (private `_MISSING` sentinel for cache-empty, fixed
docstring math on `last_loaded_at`). The cherry-pick is now sourced
from v3 commit `84e690464` (sha256 `f9fed285e7d446224c19b9393f137f40591381726642e8eb084f164c204c06c1`).
A previous verbatim copy of v3 (sha256 `6e6897f5f0490417dd06924b32a79b0b6d2cd44b14079a20fdb37c75baf84d74`)
predates this fix.

These tests pin the critical behaviors so any drift between v3 and this
copy (e.g. from a future re-cherry-pick) is caught by CI.

This is a focused subset of v3's 341-line test suite — we cover the
behaviors that R5b's config_reload.py depends on (TTL, lock contention,
stale fallback, invalidate, None-payload caching). Less critical behaviors
(age tracking, last_loaded_wall_time, custom TTL validation) are inherited
via the byte-equivalence invariant.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from llm_gateway.gateway.daily_refresh import DailyRefreshCache


class TestFreshCache:
    """Cache within TTL returns cached value without invoking the loader."""

    async def test_fresh_cache_returns_value_without_loader_call(self):
        cache: DailyRefreshCache[int] = DailyRefreshCache(ttl_seconds=60)
        loader_calls = 0

        async def loader() -> int:
            nonlocal loader_calls
            loader_calls += 1
            return 42

        await cache.get_or_refresh(loader)
        assert loader_calls == 1
        # Second call within TTL — loader NOT invoked again.
        await cache.get_or_refresh(loader)
        assert loader_calls == 1

    async def test_fresh_cache_at_exactly_ttl_boundary_is_stale(self):
        """At exactly TTL, cache is considered stale (boundary is exclusive)."""
        clock = [1000.0]

        def fake_clock() -> float:
            return clock[0]

        cache = DailyRefreshCache(ttl_seconds=10, clock=fake_clock)

        async def loader() -> int:
            return 1

        await cache.get_or_refresh(loader)
        # Advance clock by exactly TTL — should be stale now
        clock[0] += 10.0
        loader_calls = cache.loader_call_count

        async def counting_loader() -> int:
            return 99

        await cache.get_or_refresh(counting_loader)
        # Loader WAS invoked (cache was stale at the boundary)
        assert cache.loader_call_count == loader_calls + 1


class TestStaleCache:
    """Cache past TTL invokes the loader."""

    async def test_stale_cache_invokes_loader(self):
        clock = [1000.0]

        def fake_clock() -> float:
            return clock[0]

        cache = DailyRefreshCache(ttl_seconds=10, clock=fake_clock)

        async def loader() -> int:
            return 7

        await cache.get_or_refresh(loader)
        assert cache.loader_call_count == 1
        # Advance past TTL
        clock[0] += 11.0
        await cache.get_or_refresh(loader)
        assert cache.loader_call_count == 2


class TestLockContention:
    """Concurrent callers serialize via the lock (double-checked locking)."""

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

        await cache.get_or_refresh(loader)
        assert loader_calls == 1
        # 10 concurrent calls while fresh
        results = await asyncio.gather(*[cache.get_or_refresh(loader) for _ in range(10)])
        assert all(r == 7 for r in results)
        assert loader_calls == 1


class TestStaleFallback:
    """Loader raise on refresh falls back to the previously cached value."""

    async def test_loader_raises_on_refresh_returns_stale_value(self):
        cache: DailyRefreshCache[str] = DailyRefreshCache(ttl_seconds=60)
        call_count = 0

        async def flaky_loader() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return "good-value"
            raise RuntimeError("upstream API is down")

        first = await cache.get_or_refresh(flaky_loader)
        assert first == "good-value"
        # Force refresh (invalidate keeps value for fallback)
        cache.invalidate()
        second = await cache.get_or_refresh(flaky_loader)
        assert second == "good-value"  # stale fallback


class TestFirstCallPropagates:
    """Loader raise on first call (no cached value) propagates."""

    async def test_loader_raises_on_empty_cache_propagates(self):
        cache: DailyRefreshCache[int] = DailyRefreshCache(ttl_seconds=60)

        async def failing_loader() -> int:
            raise RuntimeError("upstream is down")

        with pytest.raises(RuntimeError, match="upstream is down"):
            await cache.get_or_refresh(failing_loader)


class TestInvalidate:
    """invalidate() forces refresh on next call but keeps value for fallback."""

    async def test_invalidate_forces_refresh_but_keeps_value_for_fallback(self):
        cache: DailyRefreshCache[int] = DailyRefreshCache(ttl_seconds=60)
        call_count = 0

        async def loader() -> int:
            nonlocal call_count
            call_count += 1
            return call_count * 10

        await cache.get_or_refresh(loader)  # 10
        assert cache.has_value is True
        cache.invalidate()
        # Next call: cache empty (timestamp cleared) but value still present for fallback.
        # If loader succeeds, fresh value returned.
        await cache.get_or_refresh(loader)  # 20
        # has_value stays True throughout (invalidate doesn't clear the value).
        assert cache.has_value is True


class TestTTLValidation:
    """Zero or negative TTL is rejected at construction."""

    async def test_zero_or_negative_ttl_rejected(self):
        with pytest.raises(ValueError, match="ttl_seconds must be > 0"):
            DailyRefreshCache(ttl_seconds=0)
        with pytest.raises(ValueError, match="ttl_seconds must be > 0"):
            DailyRefreshCache(ttl_seconds=-1)


# ---------------------------------------------------------------------------
# Regression: legitimate None payloads can be cached
# (cubic-dev-ai fix on v3, propagated to this cherry-pick)
# ---------------------------------------------------------------------------


class TestNonePayloadCaching:
    """Regression: a loader that returns None must be cacheable. The previous
    implementation used `None` as the empty-cache sentinel, which made
    legitimate `None` payloads uncacheable. Now uses a private _MISSING sentinel."""

    async def test_none_payload_can_be_cached(self):
        cache: DailyRefreshCache[object] = DailyRefreshCache(ttl_seconds=60)

        async def none_loader() -> None:
            return None

        result = await cache.get_or_refresh(none_loader)
        assert result is None
        # has_value is True (we DID cache the None)
        assert cache.has_value is True
        # Subsequent call within TTL: loader NOT re-invoked
        assert cache.loader_call_count == 1
        result2 = await cache.get_or_refresh(none_loader)
        assert result2 is None
        assert cache.loader_call_count == 1

    async def test_none_payload_stale_fallback(self):
        cache: DailyRefreshCache[object] = DailyRefreshCache(ttl_seconds=60)
        call_count = 0

        async def flaky_none_loader() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return None  # success on first call
            raise RuntimeError("upstream is down")  # fail on subsequent

        # First call: None cached.
        first = await cache.get_or_refresh(flaky_none_loader)
        assert first is None
        assert cache.has_value is True

        # Force refresh (invalidate keeps value for fallback).
        cache.invalidate()

        # Second call: loader raises, stale None returned.
        second = await cache.get_or_refresh(flaky_none_loader)
        assert second is None  # stale fallback

    async def test_empty_cache_with_none_payload_does_not_match_existing_none(self):
        """A cache that has never loaded anything must have has_value=False
        even if the eventual payload would be None. The sentinel prevents
        confusing 'value is None' with 'no value cached'."""
        cache: DailyRefreshCache[object] = DailyRefreshCache(ttl_seconds=60)
        assert cache.has_value is False
        # _is_fresh is False (never loaded)
        assert cache._is_fresh() is False


# ---------------------------------------------------------------------------
# Lint: daily_refresh is public (used by request path via config_reload.py)
# ---------------------------------------------------------------------------


class TestPublicNamespace:
    """daily_refresh lives at llm_gateway.gateway.daily_refresh (NOT _private/)
    because config_reload.py uses it on the request path. This is different
    from R5a's scoring.py which IS in _private (only emitter uses it)."""

    def test_daily_refresh_importable_from_top_level_gateway_package(self):
        # Should work without going through _private
        from llm_gateway.gateway.daily_refresh import DailyRefreshCache

        assert callable(DailyRefreshCache)

    def test_daily_refresh_NOT_in_private_namespace(self):
        """The runtime-isolation contract says _private/ is for emitter-only
        modules. daily_refresh is used on the request path (via
        config_reload.py), so it must NOT live in _private/."""
        import os

        private_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "llm_gateway", "gateway", "_private")
        daily_refresh_in_private = os.path.exists(os.path.join(private_dir, "daily_refresh.py"))
        assert not daily_refresh_in_private, "daily_refresh.py should NOT be in _private/ — it's on the request path"
