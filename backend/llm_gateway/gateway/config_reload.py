"""Hot-reload gateway config on YAML mtime change (R5b).

Wraps `DailyRefreshCache` (TTL + `asyncio.Lock` + stale-fallback) with
mtime polling so the gateway picks up YAML changes on the next request
after merge — no pod restart required. The reloader runs ONCE per
request (mtime check is fast, `os.stat()`); only invokes the loader on
cache miss or mtime change.

Per PLAN.md §R5b: "the cache invalidation path is what makes 'nightly
rotation' mean 'the next request after merge sees the new artifact'
instead of 'restart the pod.'"
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from llm_gateway.gateway.config_loader import (
    GatewayConfig,
    load_gateway_config,
)
from llm_gateway.gateway.daily_refresh import DailyRefreshCache
from llm_gateway.gateway.resolver import SUPPORTED_AUTO_LANE_IDS

logger = logging.getLogger(__name__)


# YAML files the reloader watches. Must match what `load_gateway_config`
# loads from. Adding a file here without adding it to the loader is a no-op;
# removing one without updating the loader would silently miss changes.
_CONFIG_FILES = (
    "lanes.yaml",
    "route_artifacts.yaml",
    "feature_bundles.yaml",
    "lanes_catalog.yaml",
)


def _max_mtime(config_dir: Path) -> float:
    """Return the max mtime across the config files (or 0.0 if none exist)."""
    mtimes = []
    for fname in _CONFIG_FILES:
        path = config_dir / fname
        if path.exists():
            mtimes.append(path.stat().st_mtime)
    return max(mtimes) if mtimes else 0.0


class GatewayConfigReloader:
    """mtime-watched config reloader.

    Behavior:
    - First call: load from disk, cache the result + mtime.
    - Subsequent calls: stat the config files; if max-mtime unchanged,
      return the cached config object (same instance — no reload).
    - On mtime change: invalidate the cache, reload from disk.
    - On reload error: return last good cached config (stale fallback)
      if present; otherwise propagate the exception.
    - Concurrent calls serialize via `DailyRefreshCache`'s `asyncio.Lock`
      (double-checked locking — only one loader invocation per cache miss).
    """

    def __init__(
        self,
        config_dir: Path,
        *,
        ttl_seconds: float = 60.0,
        prod_mode_fn=None,
    ):
        self.config_dir = config_dir
        self._prod_mode_fn = prod_mode_fn
        # The mtime we last observed; on mismatch, force a refresh.
        self._mtime: Optional[float] = None
        # Last successfully loaded config, kept for stale fallback even
        # after the cache is invalidated.
        self._cached: Optional[GatewayConfig] = None
        self._cache: DailyRefreshCache[GatewayConfig] = DailyRefreshCache(ttl_seconds=ttl_seconds)

    async def get(self) -> GatewayConfig:
        """Return the current config, reloading if any config file's mtime changed."""
        current_mtime = _max_mtime(self.config_dir)
        if self._cached is None or self._mtime != current_mtime:
            # Mtime changed (or first call). Force the cache to refresh on
            # the next get_or_refresh — preserves stale value in DailyRefreshCache
            # for the fallback path. The loader populates self._cached on
            # success; on failure DailyRefreshCache returns the stale value.
            self._cache.invalidate()
            self._mtime = current_mtime
        return await self._cache.get_or_refresh(self._load)

    async def _load(self) -> GatewayConfig:
        """Loader passed to DailyRefreshCache; runs under the cache lock.

        Config loading is sync (yaml.safe_load + Pydantic validation) and
        can take ~10-50ms on cold start. To avoid blocking the event loop
        while the request handler is awaiting `get()`, the sync load runs
        in a threadpool via `asyncio.to_thread`.

        Raises ConfigValidationError on bad config; DailyRefreshCache does
        the stale-fallback dance (returns last good value if available,
        propagates if first-call).
        """
        prod_mode = self._prod_mode_fn() if self._prod_mode_fn is not None else None
        cfg = await asyncio.to_thread(
            load_gateway_config,
            self.config_dir,
            prod_mode=prod_mode,
            required_lane_ids=SUPPORTED_AUTO_LANE_IDS,
        )
        self._cached = cfg
        return cfg

    def invalidate(self) -> None:
        """Force the next get() to reload. Test helper + admin path."""
        self._mtime = None
        self._cached = None
        self._cache.invalidate()

    @property
    def last_loaded_config(self) -> Optional[GatewayConfig]:
        """The most recently successfully loaded config (for diagnostics)."""
        return self._cached
