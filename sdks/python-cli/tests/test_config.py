"""Tests for ``omi_cli.config``."""

from __future__ import annotations

import json
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


def test_load_malformed_toml_returns_empty_config_with_error(config_path: Path) -> None:
    """A broken config must not crash diagnostics — return an empty Config
    that records why parsing failed."""
    config_path.write_text("active_profile = [\n", encoding="utf-8")  # invalid TOML
    config = cfg.load()
    assert config.path == config_path
    assert config.active_profile == cfg.DEFAULT_PROFILE_NAME
    assert config.profiles == {}
    assert config.was_load_error
    assert config.load_error is not None
    assert "not valid TOML" in config.load_error


def test_load_invalid_utf8_records_unicode_error(config_path: Path) -> None:
    """A config with invalid UTF-8 must not crash diagnostics either; it is
    recorded on load_error so write commands refuse to clobber it."""
    config_path.write_bytes(b"active_profile = \xff\xfe\n")
    config = cfg.load()
    assert config.profiles == {}
    assert config.was_load_error
    assert config.load_error is not None
    assert "not valid UTF-8" in config.load_error


def test_save_refuses_to_overwrite_malformed_config(config_path: Path) -> None:
    """save() must refuse to overwrite a file that failed to parse on load:
    a write command would otherwise silently destroy profiles/credentials the
    user could still repair by hand."""
    config_path.write_text("active_profile = [\n", encoding="utf-8")  # invalid TOML
    config = cfg.load()
    assert config.was_load_error
    original = config_path.read_bytes()

    with pytest.raises(PermissionError, match="refusing to overwrite"):
        cfg.save(config)

    # The corrupt file is left untouched.
    assert config_path.read_bytes() == original


def test_version_succeeds_with_malformed_config(config_path: Path, cli_runner) -> None:
    """`omi version` must keep working when the config TOML is malformed."""
    config_path.write_text("active_profile = [\n", encoding="utf-8")  # invalid TOML
    result = cli_runner.invoke(app, ["version"])
    assert result.exit_code == 0, result.output
    assert "omi-cli" in result.output


def test_config_path_succeeds_with_malformed_config(config_path: Path, cli_runner) -> None:
    """`omi config path` must keep working when the config TOML is malformed."""
    config_path.write_text("active_profile = [\n", encoding="utf-8")  # invalid TOML
    result = cli_runner.invoke(app, ["config", "path"])
    assert result.exit_code == 0, result.output
    assert str(config_path) in result.output


def test_config_path_json_succeeds_with_malformed_config(config_path: Path, cli_runner) -> None:
    """The `--json config path` branch must keep working when the config TOML
    is malformed (regression guard for the JSON renderer path)."""
    config_path.write_text("active_profile = [\n", encoding="utf-8")  # invalid TOML
    result = cli_runner.invoke(app, ["--json", "config", "path"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["path"] == str(config_path)


def test_config_set_preserves_unknown_root_settings(config_path: Path, cli_runner) -> None:
    config_path.write_text(
        'active_profile = "default"\n'
        'future_flag = true\n'
        '[future_display]\n'
        'language = "ar"\n'
        '[profiles.default]\n'
        'api_base = "https://api.omi.me"\n',
        encoding="utf-8",
    )
    result = cli_runner.invoke(app, ["config", "set", "api_base", "https://example.test"])
    assert result.exit_code == 0, result.output
    with config_path.open("rb") as handle:
        saved = cfg.tomllib.load(handle)
    assert saved["profiles"]["default"]["api_base"] == "https://example.test"
    assert saved["future_flag"] is True
    assert saved["future_display"] == {"language": "ar"}


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
    """A temp file left by a crashed save() does not block a new save():
    save() picks a fresh unique temp name and never deletes a pre-existing
    file it does not own."""
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


def test_save_retries_when_unique_temp_name_collides(config_path: Path, monkeypatch) -> None:
    """The retry branch: when open_owner_only() hits FileExistsError on the
    generated unique name, save() must re-roll the name instead of crashing,
    and must not unlink the colliding file."""
    config = cfg.load()
    profile = config.get_profile()
    profile.auth_method = "api_key"
    profile.api_key = "omi_dev_retry"
    config.set_profile(profile)

    generated_names: list[Path] = []
    collision_seen = False
    original_open = cfg.open_owner_only

    def colliding_open(path: Path) -> int:
        nonlocal collision_seen
        generated_names.append(path)
        if not collision_seen:
            # Simulate another writer having claimed this exact pid+hex path
            # between generation and open. The planted file must survive.
            path.write_text("other writer's temp")
            collision_seen = True
            raise FileExistsError(path)
        return original_open(path)

    monkeypatch.setattr(cfg, "open_owner_only", colliding_open)
    cfg.save(config)

    assert collision_seen
    assert len(generated_names) == 2  # first name collided, second succeeded
    colliding = generated_names[0]
    assert colliding != generated_names[1]
    # Never unlink a file it doesn't own.
    assert colliding.exists()
    assert colliding.read_text() == "other writer's temp"

    reloaded = cfg.load().get_profile()
    assert reloaded.api_key == "omi_dev_retry"


@pytest.mark.parametrize("failure_type", [PermissionError, KeyboardInterrupt, SystemExit])
def test_save_cleans_own_temp_when_replace_fails(config_path: Path, monkeypatch, failure_type) -> None:
    config = cfg.load()
    profile = config.get_profile()
    profile.auth_method = "api_key"
    profile.api_key = "omi_dev_original"
    cfg.save(config)
    original = config_path.read_bytes()
    other_temp = config_path.with_suffix(".toml.other-writer.tmp")
    other_temp.write_bytes(b"another writer")
    profile.api_key = "omi_dev_replacement"
    failure = failure_type("replacement interrupted or failed")
    attempted = []

    def fail_replace(source, destination):
        attempted.append(Path(source))
        assert Path(destination) == config_path
        assert b"omi_dev_replacement" in Path(source).read_bytes()
        raise failure

    monkeypatch.setattr(cfg.os, "replace", fail_replace)
    with pytest.raises(failure_type) as exc:
        cfg.save(config)

    assert exc.value is failure
    assert config_path.read_bytes() == original
    assert attempted and not attempted[0].exists()
    assert other_temp.read_bytes() == b"another writer"


@pytest.mark.parametrize("failure_type", [PermissionError, KeyboardInterrupt, SystemExit])
def test_save_cleanup_failure_preserves_replace_error(config_path: Path, monkeypatch, failure_type) -> None:
    config = cfg.load()
    config.get_profile().api_key = "omi_dev_synthetic"
    failure = failure_type("replacement interrupted or failed")
    cleanup_attempts = []

    def fail_replace(source, destination):
        raise failure

    def fail_unlink(path):
        cleanup_attempts.append(Path(path))
        raise OSError("cleanup also failed")

    with monkeypatch.context() as patcher:
        patcher.setattr(cfg.os, "replace", fail_replace)
        patcher.setattr(cfg.os, "unlink", fail_unlink)
        with pytest.raises(failure_type) as exc:
            cfg.save(config)

    assert exc.value is failure
    assert len(cleanup_attempts) == 1
    cleanup_attempts[0].unlink()


def test_save_concurrent_writers_retry_on_unique_name_collision(config_path: Path) -> None:
    """Real interleaving: a nested save() inside the first writer's dump
    claims a temp path; the outer writer's own path cannot collide with it
    (unique per invocation), so both complete and neither unlinks the other."""
    first = cfg.Config(path=config_path, active_profile="first")
    second = cfg.Config(path=config_path, active_profile="second")
    original_dump = cfg.tomli_w.dump

    def interleaved_dump(payload, handle):
        if payload["active_profile"] == "first":
            before = set(config_path.parent.glob(config_path.name + ".*.tmp"))
            cfg.save(second)
            after = set(config_path.parent.glob(config_path.name + ".*.tmp"))
            # The inner save's temp was already renamed; nothing leaked.
            assert after - before == set()
        original_dump(payload, handle)

    with patch.object(cfg.tomli_w, "dump", interleaved_dump):
        cfg.save(first)

    reloaded = cfg.load()
    assert config_path.exists()
    assert not list(config_path.parent.glob(config_path.name + ".*.tmp"))
    assert reloaded.active_profile in {"first", "second"}


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
