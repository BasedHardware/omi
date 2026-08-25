from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev_harness import config, desktop_profile

REPO_ROOT = Path(__file__).resolve().parents[3]


def _resolve(user_env: dict[str, str] | None = None) -> desktop_profile.DesktopLocalProfile:
    env = {"OMI_LOCAL_STATE_ROOT": str(REPO_ROOT / ".local-harness-state")}
    if user_env:
        env.update(user_env)
    cfg = config.load_config(REPO_ROOT, env=env, create_layout=False)
    return desktop_profile.resolve_profile(cfg, user="alice", seeded_users=("alice",), env=env)


def test_validate_profile_blocks_default_omi_dev() -> None:
    profile = _resolve()
    assert profile.app_name == desktop_profile.LOCAL_APP_NAME
    assert profile.bundle_id == desktop_profile.LOCAL_BUNDLE_ID

    errors = desktop_profile.validate_profile(profile)
    assert errors
    assert any(desktop_profile.LOCAL_PROFILE_OMI_DEV_BLOCKED in error for error in errors)


def test_validate_profile_allows_omi_memory_named_bundle() -> None:
    profile = _resolve({"OMI_APP_NAME": "omi-memory"})
    assert profile.app_name == "omi-memory"
    assert profile.bundle_id == "com.omi.omi-memory"

    errors = desktop_profile.validate_profile(profile)
    assert not errors
