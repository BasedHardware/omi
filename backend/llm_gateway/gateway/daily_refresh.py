"""Daily-refresh cache: TTL + asyncio.Lock + stale-fallback.

Wraps an async loader function with three behaviors:
1. **TTL**: loader runs at most once per TTL window (default 24h, matching upstream
   `/v1/auto/model-pick`).
2. **`asyncio.Lock()`**: concurrent callers serialize. Only one loader call fires
   on a cache miss; other callers wait and then read the fresh value (double-checked
   locking pattern).
3. **Stale fallback**: if the loader raises during refresh, return the last good
   cached value instead of propagating. On the first-ever call with no cached
   value and the loader raises, the exception propagates (nothing to fall back to).

Mirrors upstream's pattern in `backend/routers/auto_model.py` (`_cache_lock` +
24h `TTL_SECONDS`).

The clock function is injectable for testability (default `time.monotonic`).
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Generic, Optional, TypeVar, cast

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Private sentinel used to distinguish "no value cached" from "value is None".
# Using `None` as the empty-cache signal made it impossible to cache legitimate
# None payloads (loader was re-invoked on every call, stale fallback never
# triggered). Fix from cubic-dev-ai review.
_MISSING = object()


class DailyRefreshCache(Generic[T]):
    """A TTL-bounded cache for an async loader.

    Concurrency model:
        - First call (or post-expiry call) acquires the lock.
        - Subsequent concurrent callers wait for the lock, then DOUBLE-CHECK
          the cache. If the first caller just refreshed, they get the fresh
          value without re-running the loader.
        - This is the standard double-checked-locking pattern; safe because
          `asyncio.Lock` provides exclusive access within a single event loop.

    Failure model:
        - Loader raises → return last good cached value if present, else
          propagate the exception.
        - Stale fallback is logged at WARNING level (not error) because it's a
          degraded-but-functional state.
    """

    DEFAULT_TTL_SECONDS = 24 * 60 * 60  # 24h, matching upstream auto_model.py

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be > 0, got {ttl_seconds}")
        self._ttl = ttl_seconds
        self._clock = clock
        # `_value` uses a sentinel (not `None`) so legitimate `None` payloads
        # can be cached. See `_MISSING` above.
        self._value: T | object = _MISSING
        self._last_loaded_at: Optional[float] = None
        self._lock = asyncio.Lock()
        # Counter for tests to verify how many times loader was actually invoked.
        self.loader_call_count = 0

    @property
    def age_seconds(self) -> Optional[float]:
        """Seconds since last successful load, or None if never loaded."""
        if self._last_loaded_at is None:
            return None
        return max(0.0, self._clock() - self._last_loaded_at)

    @property
    def last_loaded_at(self) -> Optional[float]:
        """Monotonic timestamp of the last successful load, or None if never loaded.

        The monotonic clock has no wall-clock meaning, so this value cannot be
        directly converted to wall-clock time. Use `last_loaded_wall_time()`
        for an approximation (best-effort, ±a few seconds), or have the loader
        itself record `time.time()` and store it if exact wall-clock is needed.
        """
        return self._last_loaded_at

    def last_loaded_wall_time(self) -> Optional[datetime]:
        """Wall-clock time of the last successful load (UTC), or None if never loaded.

        Returns a `datetime` (UTC) by converting from the monotonic clock.
        Note: monotonic clock has no wall-clock meaning, so we use the wall clock
        at construction + elapsed time as an approximation. For exact wall-clock
        timestamps, the loader itself should record `time.time()` and store it.
        """
        if self._last_loaded_at is None:
            return None
        # Approximation: the wall clock at "monotonic = self._last_loaded_at"
        # is roughly wall_at_init + (self._last_loaded_at - monotonic_at_init).
        # We didn't capture init times, so this is best-effort.
        # For most use cases (display), ±a few seconds is fine.
        elapsed = self._clock() - self._last_loaded_at
        return datetime.now(timezone.utc) - timedelta(seconds=elapsed)

    @property
    def has_value(self) -> bool:
        """True if a value is currently cached (even if stale)."""
        return self._value is not _MISSING

    def _is_fresh(self) -> bool:
        """True if cache is non-empty AND within TTL window."""
        if self._value is _MISSING or self._last_loaded_at is None:
            return False
        return (self._clock() - self._last_loaded_at) < self._ttl

    async def get_or_refresh(self, loader: Callable[[], Awaitable[T]]) -> T:
        """Return the cached value, refreshing if stale.

        Concurrent callers serialize via the lock; only the first caller on a
        cache miss invokes the loader. If the loader raises:
        - With a previously cached value: return the stale value (degraded).
        - Without a cached value: propagate the exception.

        The loader's invocation count is tracked in `loader_call_count` for
        test introspection (verifying lock contention behavior).
        """
        # Fast path: cache is fresh, no lock needed.
        if self._is_fresh():
            assert self._value is not _MISSING  # guaranteed by _is_fresh()
            return cast(T, self._value)

        async with self._lock:
            # Double-check inside the lock: another caller may have just refreshed.
            if self._is_fresh():
                assert self._value is not _MISSING
                return cast(T, self._value)

            # Cache is stale or empty — invoke the loader.
            self.loader_call_count += 1
            try:
                value = await loader()
                self._value = value
                self._last_loaded_at = self._clock()
                return value
            except Exception as e:
                if self._value is not _MISSING:
                    age_str = f"{self.age_seconds:.1f}s" if self.age_seconds is not None else "unknown"
                    logger.warning(
                        f"DailyRefreshCache: loader raised ({type(e).__name__}: {e}), "
                        f"returning stale value (age {age_str})"
                    )
                    # Advance the timestamp so refreshIfStale respects the TTL
                    # even after a failing refresh. Without this, every subsequent
                    # call would re-fire the loader (the cache is stale AND
                    # the timestamp is still old), creating a tight retry loop
                    # against the failing backend.
                    self._last_loaded_at = self._clock()
                    return cast(T, self._value)
                # No prior value — propagate.
                raise

    def invalidate(self) -> None:
        """Force the next call to refresh (does not clear the cached value —
        next call may still fall back to it on loader failure).
        """
        self._last_loaded_at = None
