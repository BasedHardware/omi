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
from typing import Awaitable, Callable, Generic, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


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

    # How long to wait before retrying a failed refresh (cubic review).
    # Shorter than the full TTL so a transient backend outage self-heals
    # quickly instead of serving stale data for the full TTL. Capped at
    # `ttl_seconds` so we never wait longer than the freshness threshold.
    DEFAULT_FAILURE_COOLDOWN_SECONDS = 5 * 60  # 5 minutes

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        failure_cooldown_seconds: float = DEFAULT_FAILURE_COOLDOWN_SECONDS,
    ):
        if ttl_seconds <= 0:
            raise ValueError(f"ttl_seconds must be > 0, got {ttl_seconds}")
        if failure_cooldown_seconds < 0:
            raise ValueError(f"failure_cooldown_seconds must be >= 0, got {failure_cooldown_seconds}")
        # Cap cooldown at TTL so we never wait longer than the freshness
        # threshold (would be silly).
        self._ttl = ttl_seconds
        self._failure_cooldown = min(failure_cooldown_seconds, ttl_seconds)
        self._clock = clock
        self._value: Optional[T] = None
        self._last_loaded_at: Optional[float] = None
        # Set after a failed refresh. While this is set, _is_fresh() returns
        # False until `_failure_cooldown` seconds have elapsed (cubic review:
        # shorter retry interval than the full TTL).
        self._last_failed_at: Optional[float] = None
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

        Combine with the clock function to convert to wall-clock time:
            wall_time = last_loaded_at + (monotonic_now() - last_loaded_at)
        For most use cases, prefer `last_loaded_wall_time()` which does this for you.
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
        return self._value is not None

    def _is_fresh(self) -> bool:
        """True if cache is non-empty AND within TTL window AND (no recent failure
        OR we're still within the failure cooldown).

        The failure cooldown window acts as a brief "quiet period" after a
        failed refresh: during it, _is_fresh() returns True (so callers
        get the stale value without re-firing the loader — prevents a tight
        retry loop against a failing backend). After the cooldown elapses,
        _is_fresh() returns False so the next call triggers a fresh attempt.

        Cubic review: previously a failed refresh would set `_last_loaded_at
        = now()`, marking the cache as fresh for the full TTL. This meant a
        1-minute backend outage at the refresh boundary would result in
        ~48 hours of stale model picks. Now we track `_last_failed_at`
        separately and require the cooldown to elapse before treating the
        cache as stale again. The cooldown is capped at the TTL so we
        never wait longer than the freshness threshold.
        """
        # Must have a value to be "fresh".
        if self._value is None:
            return False
        # Within the failure cooldown window, treat the cache as fresh
        # (skip loader, return stale value) — this is the brief quiet period.
        # NOTE: checked BEFORE _last_loaded_at because invalidate() may have
        # cleared _last_loaded_at, but the cooldown should still apply.
        if self._last_failed_at is not None and (self._clock() - self._last_failed_at) < self._failure_cooldown:
            return True  # still "fresh" — don't hammer the failing backend
        # Past the cooldown: check TTL. If we have a successful load timestamp
        # and it's within TTL, we're fresh.
        if self._last_loaded_at is None:
            return False
        if (self._clock() - self._last_loaded_at) >= self._ttl:
            return False
        return True

    @property
    def ttl_seconds(self) -> float:
        """Public accessor for the cache TTL (in seconds).

        Used by metrics.py + tests that need to know the freshness threshold
        without reaching into a private attribute (cubic review: cross-file
        access to `_ttl` is fragile coupling).
        """
        return self._ttl

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
            assert self._value is not None  # guaranteed by _is_fresh()
            return self._value

        async with self._lock:
            # Double-check inside the lock: another caller may have just refreshed.
            if self._is_fresh():
                assert self._value is not None
                return self._value

            # Cache is stale or empty — invoke the loader.
            self.loader_call_count += 1
            try:
                self._value = await loader()
                self._last_loaded_at = self._clock()
                # Clear failure state on successful refresh.
                self._last_failed_at = None
                return self._value
            except Exception as e:
                # Record the failure timestamp for the cooldown logic in
                # _is_fresh() (cubic review: shorter retry interval than the
                # full TTL — see _is_fresh docstring).
                self._last_failed_at = self._clock()
                if self._value is not None:
                    age_str = f"{self.age_seconds:.1f}s" if self.age_seconds is not None else "unknown"
                    logger.warning(
                        f"DailyRefreshCache: loader raised ({type(e).__name__}: {e}), "
                        f"returning stale value (age {age_str}); will retry in "
                        f"{self._failure_cooldown}s"
                    )
                    # Don't update _last_loaded_at — let _is_fresh() return False
                    # until the failure cooldown elapses, so the next call
                    # triggers a retry sooner than the full TTL.
                    return self._value
                # No prior value — propagate.
                raise

    def invalidate(self) -> None:
        """Force the next call to refresh (does not clear the cached value —
        next call may still fall back to it on loader failure).
        """
        self._last_loaded_at = None
        # Also clear failure cooldown so the next refresh fires immediately
        # (caller is signaling "try again now").
        self._last_failed_at = None
