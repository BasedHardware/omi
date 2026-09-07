"""Tests for ``omi_cli.config``."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import BinaryIO
from unittest.mock import patch

import pytest

from omi_cli import _secure_file
from omi_cli import config as cfg
from omi_cli.main import app


def _assert_owner_only_descriptor(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt  # type: ignore[import-not-found]

        windows_handle = msvcrt.get_osfhandle(handle.fileno())
        assert _secure_file._windows_dacl_sddl(windows_handle) == "D:P(A;;FA;;;OW)"
        return

    mode = stat.S_IMODE(os.fstat(handle.fileno()).st_mode)
    assert mode == 0o600


def _assert_owner_only(path: Path) -> None:
    with path.open("rb") as handle:
        _assert_owner_only_descriptor(handle)


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
    profile.local_api_url = "http://127.0.0.1:47778"
    profile.local_token = "local_secret"
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
    assert p2.local_api_url == "http://127.0.0.1:47778"
    assert p2.local_token == "local_secret"
    assert p2.extra.get("future_setting") is True


def test_save_creates_file_with_secure_perms(config_path: Path) -> None:
    config = cfg.load()
    profile = config.get_profile()
    profile.auth_method = "api_key"
    profile.api_key = "omi_dev_secret"
    config.set_profile(profile)
    cfg.save(config)

    _assert_owner_only(config_path)


def test_save_does_not_leave_world_readable_window(monkeypatch, config_path: Path) -> None:
    """TOCTOU regression test (Greptile P1).

    Force a permissive umask, inspect the temp file when serialization starts,
    and assert that neither it nor the final file is accessible to other users.
    Earlier versions created the temp with inherited/default permissions before
    tightening them, which exposed bearer credentials during serialization.
    """
    tmp = config_path.with_suffix(config_path.suffix + ".tmp")
    original_dump = cfg.tomli_w.dump
    checked_during_write = False

    def dump_after_permission_check(payload, handle) -> None:
        nonlocal checked_during_write
        _assert_owner_only_descriptor(handle)
        checked_during_write = True
        original_dump(payload, handle)

    monkeypatch.setattr(cfg.tomli_w, "dump", dump_after_permission_check)

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

    assert checked_during_write
    _assert_owner_only(config_path)
    assert not tmp.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows DACL enforcement only")
def test_save_fails_closed_when_windows_dacl_verification_fails(monkeypatch, config_path: Path) -> None:
    monkeypatch.setattr(_secure_file, "_windows_dacl_sddl", lambda _handle: "D:")
    config = cfg.load()
    profile = config.get_profile()
    profile.auth_method = "api_key"
    profile.api_key = "omi_dev_secret"
    config.set_profile(profile)

    with pytest.raises(PermissionError, match="did not enforce owner-only"):
        cfg.save(config)

    assert not config_path.exists()
    assert not config_path.with_suffix(config_path.suffix + ".tmp").exists()


def test_save_overwrites_stale_temp_file(config_path: Path) -> None:
    """A stale temp file left by a crashed save() must not block a new save(),
    and the new save must never delete a pre-existing file it does not own."""
    tmp = config_path.with_suffix(config_path.suffix + ".tmp")
    config_path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text("stale leftover")
    stale_content = tmp.read_text()
    assert tmp.exists()

    config = cfg.load()
    profile = config.get_profile()
    profile.auth_method = "api_key"
    profile.api_key = "omi_dev_recovered"
    config.set_profile(profile)
    cfg.save(config)

    # The stale file is left untouched (it may belong to another writer).
    assert tmp.exists()
    assert tmp.read_text() == stale_content
    reloaded = cfg.load().get_profile()
    assert reloaded.api_key == "omi_dev_recovered"


def test_save_concurrent_writers_do_not_unlink_each_others_temp(config_path: Path) -> None:
    """A second concurrent save() must not treat the first writer's temp file
    as stale and unlink it (issue: first writer then fails at os.replace)."""
    first = cfg.Config(path=config_path, active_profile="first")
    second = cfg.Config(path=config_path, active_profile="second")
    original_dump = cfg.tomli_w.dump

    def interleaved_dump(payload, handle):
        # While the first writer is serializing, a second writer runs a full
        # save() — this collides on the shared fixed temp path.
        if payload["active_profile"] == "first":
            cfg.save(second)
        original_dump(payload, handle)

    with patch.object(cfg.tomli_w, "dump", interleaved_dump):
        cfg.save(first)  # FileNotFoundError on the unfixed implementation

    reloaded = cfg.load()
    assert config_path.exists()
    assert not config_path.with_suffix(config_path.suffix + ".tmp").exists()
    # Both writes completed; the last one wins, but no writer crashed.
    assert reloaded.active_profile in {"first", "second"}


def test_save_stale_temp_file_is_still_recovered(config_path: Path) -> None:
    """Recovery from a genuinely stale temp file (no live writer) still works."""
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

    # The stale file is left untouched (it may belong to another writer).
    assert tmp.exists()
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


def test_masked_local_token() -> None:
    profile = cfg.Profile(name="default", local_token="local_secret_token")
    masked = profile.masked_local_token()
    assert "local_secret_token" not in masked
    assert "…" in masked


def test_config_set_local_token_masks_success_output(config_path: Path, cli_runner) -> None:
    result = cli_runner.invoke(
        app,
        ["config", "set", "local_token", "local_secret_token"],
    )

    assert result.exit_code == 0, result.output
    assert "local_secret_token" not in result.stderr
    assert "…" in result.stderr
    assert cfg.load().get_profile("default").local_token == "local_secret_token"


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
