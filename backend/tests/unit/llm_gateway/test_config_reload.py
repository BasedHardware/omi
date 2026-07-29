"""Tests for the R5b mtime-watched config reloader.

The reloader wraps DailyRefreshCache (TTL + lock + stale-fallback) with
mtime polling. Tests cover:
- First-call load
- Cached on unchanged mtime
- Reload on mtime change
- Stale fallback on ConfigValidationError
- First-call error propagation
- Concurrent get() serialization
- Integration with load_gateway_config (uses the real default config in some tests)
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import pytest

from llm_gateway.gateway.config_loader import (
    ConfigValidationError,
    load_gateway_config,
)
from llm_gateway.gateway.config_reload import (
    GatewayConfigReloader,
    _CONFIG_FILES,
    _max_mtime,
)

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[3] / "llm_gateway" / "config"


def _copy_default_config_to(tmp_path: Path) -> Path:
    """Snapshot the default config into tmp_path so tests can mutate freely."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    for fname in _CONFIG_FILES:
        src = DEFAULT_CONFIG_DIR / fname
        dst = config_dir / fname
        dst.write_text(src.read_text())
    return config_dir


def _bump_mtime(path: Path) -> None:
    """Ensure mtime advances past the previous value (some FS have 1s resolution)."""
    time.sleep(0.05)
    path.touch()


# ---------------------------------------------------------------------------
# _max_mtime helper
# ---------------------------------------------------------------------------


class TestMaxMtime:
    def test_max_mtime_returns_zero_when_no_files_exist(self, tmp_path):
        assert _max_mtime(tmp_path) == 0.0

    def test_max_mtime_returns_max_of_existing_files(self, tmp_path):
        f1 = tmp_path / "lanes.yaml"
        f2 = tmp_path / "route_artifacts.yaml"
        f1.write_text("a")
        time.sleep(0.05)
        f2.write_text("b")
        # Both files exist; _max_mtime returns the larger mtime (f2).
        assert _max_mtime(tmp_path) == f2.stat().st_mtime

    def test_max_mtime_ignores_unrelated_files(self, tmp_path):
        f1 = tmp_path / "lanes.yaml"
        f1.write_text("a")
        # Unrelated file with a future mtime should NOT affect the result
        unrelated = tmp_path / "unrelated.yaml"
        unrelated.write_text("x")
        future = time.time() + 3600
        os.utime(unrelated, (future, future))
        assert _max_mtime(tmp_path) == f1.stat().st_mtime


# ---------------------------------------------------------------------------
# First-call load
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reloader_loads_on_first_call(tmp_path):
    config_dir = _copy_default_config_to(tmp_path)
    reloader = GatewayConfigReloader(config_dir)
    cfg = await reloader.get()
    assert 'omi:auto:chat-structured' in cfg.lanes and len(cfg.lanes) >= 1
    assert len(cfg.route_artifacts) >= 2
    # Last-loaded config is exposed for diagnostics
    assert reloader.last_loaded_config is cfg


# ---------------------------------------------------------------------------
# Cache behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reloader_returns_cached_when_mtime_unchanged(tmp_path):
    config_dir = _copy_default_config_to(tmp_path)
    reloader = GatewayConfigReloader(config_dir)
    cfg1 = await reloader.get()
    cfg2 = await reloader.get()
    # Same object — no reload, no second load call
    assert cfg1 is cfg2


@pytest.mark.asyncio
async def test_reloader_reloads_on_mtime_change(tmp_path):
    config_dir = _copy_default_config_to(tmp_path)
    reloader = GatewayConfigReloader(config_dir)
    cfg1 = await reloader.get()
    # Bump mtime on one of the config files
    _bump_mtime(config_dir / "lanes.yaml")
    cfg2 = await reloader.get()
    # New instance — reloaded because mtime changed
    assert cfg1 is not cfg2


@pytest.mark.asyncio
async def test_reloader_reloads_when_any_of_three_files_change(tmp_path):
    """mtime is the max across all 3 files; bumping any one triggers reload."""
    config_dir = _copy_default_config_to(tmp_path)
    reloader = GatewayConfigReloader(config_dir)
    cfg_initial = await reloader.get()
    for fname in ("lanes.yaml", "route_artifacts.yaml", "feature_bundles.yaml"):
        _bump_mtime(config_dir / fname)
        cfg_after = await reloader.get()
        assert cfg_after is not cfg_initial, f"reload did not happen after {fname} mtime change"
        cfg_initial = cfg_after


# ---------------------------------------------------------------------------
# Stale fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reloader_stale_fallback_on_config_validation_error(tmp_path):
    """After a successful load, corrupting the config returns the cached value."""
    config_dir = _copy_default_config_to(tmp_path)
    reloader = GatewayConfigReloader(config_dir)
    cfg_good = await reloader.get()
    # Corrupt lanes.yaml so the next load fails
    _bump_mtime(config_dir / "lanes.yaml")
    # Unbalanced flow sequence — YAML parser raises.
    (config_dir / "lanes.yaml").write_text("- item1\n- item2\n- [unclosed")
    # Mtime changed; next get() fails to load. DailyRefreshCache's stale
    # fallback returns the previously cached value (cfg_good).
    cfg_stale = await reloader.get()
    assert cfg_stale is cfg_good


@pytest.mark.asyncio
async def test_reloader_propagates_first_call_error(tmp_path):
    """On first call, if the loader raises and there's no cached value, propagate."""
    config_dir = _copy_default_config_to(tmp_path)
    # Corrupt BEFORE any successful load
    (config_dir / "lanes.yaml").write_text("- item1\n- [unclosed")
    reloader = GatewayConfigReloader(config_dir)
    with pytest.raises(ConfigValidationError):
        await reloader.get()


@pytest.mark.asyncio
async def test_reloader_recovers_after_first_call_error_then_success(tmp_path):
    """After a first-call failure, fixing the file + bumping mtime succeeds."""
    config_dir = _copy_default_config_to(tmp_path)
    (config_dir / "lanes.yaml").write_text("- item1\n- [unclosed")
    reloader = GatewayConfigReloader(config_dir)
    with pytest.raises(ConfigValidationError):
        await reloader.get()
    # Restore the file
    _bump_mtime(config_dir / "lanes.yaml")
    (config_dir / "lanes.yaml").write_text((DEFAULT_CONFIG_DIR / "lanes.yaml").read_text())
    cfg = await reloader.get()
    assert 'omi:auto:chat-structured' in cfg.lanes and len(cfg.lanes) >= 1


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reloader_serializes_concurrent_get_calls(tmp_path):
    """5 concurrent get() calls — only one loader invocation."""
    config_dir = _copy_default_config_to(tmp_path)
    reloader = GatewayConfigReloader(config_dir)
    results = await asyncio.gather(*[reloader.get() for _ in range(5)])
    assert all(r is results[0] for r in results)
    # The DailyRefreshCache's loader_call_count should be 1
    assert reloader._cache.loader_call_count == 1


# ---------------------------------------------------------------------------
# invalidate()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reloader_invalidate_forces_reload(tmp_path):
    config_dir = _copy_default_config_to(tmp_path)
    reloader = GatewayConfigReloader(config_dir)
    cfg1 = await reloader.get()
    reloader.invalidate()
    cfg2 = await reloader.get()
    assert cfg1 is not cfg2


@pytest.mark.asyncio
async def test_reloader_invalidate_clears_last_loaded(tmp_path):
    config_dir = _copy_default_config_to(tmp_path)
    reloader = GatewayConfigReloader(config_dir)
    await reloader.get()
    assert reloader.last_loaded_config is not None
    reloader.invalidate()
    assert reloader.last_loaded_config is None


# ---------------------------------------------------------------------------
# Integration with the real default config (smoke test against the actual files)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reloader_works_against_real_default_config():
    """End-to-end: load the real default config via the reloader."""
    reloader = GatewayConfigReloader(DEFAULT_CONFIG_DIR)
    cfg = await reloader.get()
    assert 'omi:auto:chat-structured' in cfg.lanes and len(cfg.lanes) >= 1
    assert len(cfg.route_artifacts) >= 2
    # No prod_mode rejection: the new placeholder field is the marker, not dev_only
    assert all(cfg.route_artifacts[rid].evidence.is_prod_eligible() for rid in cfg.route_artifacts)
