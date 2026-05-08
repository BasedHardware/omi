"""Tests for ``omi_cli.config``."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from omi_cli import config as cfg


def test_default_config_path_honors_env(monkeypatch, tmp_path: Path) -> None:
    custom = tmp_path / "custom.toml"
    monkeypatch.setenv(cfg.ENV_CONFIG_PATH, str(custom))
    assert cfg.default_config_path() == custom


def test_load_missing_file_returns_empty_config(config_path: Path) -> None:
    config = cfg.load()
    assert config.path == config_path
    assert config.active_profile == cfg.DEFAULT_PROFILE_NAME
    assert config.profiles == {}


def test_save_and_round_trip_preserves_unknown_keys(config_path: Path) -> None:
    config = cfg.load()
    profile = config.get_profile("work")
    profile.auth_method = "api_key"
    profile.api_key = "omi_dev_abc"
    profile.api_base = "https://api.staging.omi.me"
    profile.extra = {"future_setting": True}
    config.set_profile(profile)
    config.active_profile = "work"
    cfg.save(config)

    reloaded = cfg.load()
    assert reloaded.active_profile == "work"
    assert "work" in reloaded.profiles
    p2 = reloaded.profiles["work"]
    assert p2.api_key == "omi_dev_abc"
    assert p2.api_base == "https://api.staging.omi.me"
    assert p2.extra.get("future_setting") is True


def test_save_creates_file_with_secure_perms(config_path: Path) -> None:
    config = cfg.load()
    profile = config.get_profile()
    profile.auth_method = "api_key"
    profile.api_key = "omi_dev_secret"
    config.set_profile(profile)
    cfg.save(config)

    mode = stat.S_IMODE(os.stat(config_path).st_mode)
    # Owner read/write only — credentials are inside.
    assert mode == 0o600


def test_save_does_not_leave_world_readable_window(monkeypatch, config_path: Path) -> None:
    """TOCTOU regression test (Greptile P1).

    Force a permissive umask, save the config, and assert that *neither* the
    final file nor any leftover temp file is world-readable. Earlier versions
    of ``save()`` created the temp with default umask perms (~0o644) before
    chmodding to 0o600 — that left a window where another local user could
    read bearer credentials.
    """
    # Force a permissive umask. If save() relied on umask alone, the file would
    # be created at 0o666 by default and the test would fail.
    old_umask = os.umask(0o000)
    try:
        config = cfg.load()
        profile = config.get_profile()
        profile.auth_method = "api_key"
        profile.api_key = "omi_dev_secret"
        config.set_profile(profile)
        cfg.save(config)
    finally:
        os.umask(old_umask)

    # Final file is owner-only.
    mode = stat.S_IMODE(os.stat(config_path).st_mode)
    assert mode == 0o600

    # No leftover temp file with relaxed perms.
    tmp = config_path.with_suffix(config_path.suffix + ".tmp")
    assert not tmp.exists()


def test_save_overwrites_stale_temp_file(config_path: Path) -> None:
    """If a previous save() crashed mid-write, a stale .tmp may remain.
    save() should detect this and recover instead of erroring on O_EXCL."""
    tmp = config_path.with_suffix(config_path.suffix + ".tmp")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text("stale leftover")
    assert tmp.exists()

    config = cfg.load()
    profile = config.get_profile()
    profile.auth_method = "api_key"
    profile.api_key = "omi_dev_recovered"
    config.set_profile(profile)
    cfg.save(config)

    assert not tmp.exists()
    reloaded = cfg.load().get_profile()
    assert reloaded.api_key == "omi_dev_recovered"


def test_masked_credential_for_api_key(config_path: Path) -> None:
    profile = cfg.Profile(name="default", auth_method="api_key", api_key="omi_dev_abcdefghij1234")
    masked = profile.masked_credential()
    assert "omi_dev_abcdefghij1234" not in masked
    assert "…" in masked
    assert masked.startswith("omi_de")


def test_masked_credential_short_token_still_redacts() -> None:
    profile = cfg.Profile(name="default", auth_method="api_key", api_key="abc12")
    assert "…" in profile.masked_credential()


def test_masked_credential_empty_when_no_auth() -> None:
    profile = cfg.Profile(name="default")
    assert profile.masked_credential() == "(none)"


def test_resolve_profile_name_precedence(config_path: Path, monkeypatch) -> None:
    config = cfg.load()
    config.active_profile = "work"
    cfg.save(config)
    reloaded = cfg.load()
    assert cfg.resolve_profile_name(None, reloaded) == "work"  # config default

    monkeypatch.setenv(cfg.ENV_PROFILE, "personal")
    assert cfg.resolve_profile_name(None, reloaded) == "personal"  # env beats config

    assert cfg.resolve_profile_name("flag-profile", reloaded) == "flag-profile"  # flag beats env


def test_delete_profile_resets_active_when_deleting_active(config_path: Path) -> None:
    config = cfg.load()
    config.get_profile("work")
    config.active_profile = "work"
    config.delete_profile("work")
    assert config.active_profile == cfg.DEFAULT_PROFILE_NAME
    assert "work" not in config.profiles


def test_is_authenticated_states() -> None:
    p = cfg.Profile(name="x")
    assert not p.is_authenticated()
    p.auth_method = "api_key"
    p.api_key = "omi_dev_xxx"
    assert p.is_authenticated()
    p.auth_method = "oauth"
    p.api_key = None
    p.id_token = "id..."
    assert p.is_authenticated()
    p.id_token = None
    p.refresh_token = "refr..."
    assert p.is_authenticated()
