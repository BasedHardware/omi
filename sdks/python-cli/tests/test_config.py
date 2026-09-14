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


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits only")
def test_save_tightens_perms_on_newly_created_parent_dir(config_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nested = config_path.parent / "nested" / "config.toml"
    monkeypatch.setenv(cfg.ENV_CONFIG_PATH, str(nested))
    assert not nested.parent.exists()

    config = cfg.load()
    profile = config.get_profile()
    profile.auth_method = "api_key"
    profile.api_key = "omi_dev_secret"
    config.set_profile(profile)
    cfg.save(config)

    assert stat.S_IMODE(nested.parent.stat().st_mode) == 0o700


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits only")
def test_save_preserves_perms_on_existing_custom_parent_dir(config_path: Path) -> None:
    """A pre-existing, user-selected $OMI_CONFIG directory may be shared with
    other files/processes; save() must not silently tighten its mode."""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.parent.chmod(0o750)

    config = cfg.load()
    profile = config.get_profile()
    profile.auth_method = "api_key"
    profile.api_key = "omi_dev_secret"
    config.set_profile(profile)
    cfg.save(config)

    assert stat.S_IMODE(config_path.parent.stat().st_mode) == 0o750
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


def test_save_cleans_up_temp_file_when_replace_fails(config_path: Path, monkeypatch) -> None:
    """A failed os.replace() (e.g. the destination is locked on Windows) must
    not leave the fully serialized, credential-bearing temp file on disk."""
    config = cfg.load()
    profile = config.get_profile()
    profile.auth_method = "api_key"
    profile.api_key = "omi_dev_secret"
    config.set_profile(profile)

    written_tmp_path: list[Path] = []
    original_replace = cfg.os.replace

    def failing_replace(src, dst):
        written_tmp_path.append(Path(src))
        raise PermissionError("destination is locked")

    monkeypatch.setattr(cfg.os, "replace", failing_replace)

    with pytest.raises(PermissionError, match="destination is locked"):
        cfg.save(config)

    assert written_tmp_path
    assert not written_tmp_path[0].exists()
    assert not config_path.exists()

    monkeypatch.setattr(cfg.os, "replace", original_replace)
    cfg.save(config)
    assert cfg.load().get_profile().api_key == "omi_dev_secret"


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


# -- Regression tests for non-table profile containers (PR #13349) --


def test_profiles_string_value(config_path: Path) -> None:
    """profiles = 'mistake' should report load error, not crash."""
    config_path.write_text('profiles = "mistake"\n', encoding="utf-8")
    config = cfg.load()
    assert config.was_load_error
    assert "profiles" in config.load_error.lower()


def test_profiles_nested_string(config_path: Path) -> None:
    """[profiles] default = 'mistake' should report load error."""
    config_path.write_text('[profiles]\ndefault = "mistake"\n', encoding="utf-8")
    config = cfg.load()
    assert config.was_load_error
    assert "default" in config.load_error


def test_valid_profiles_still_work(config_path: Path) -> None:
    """Valid profiles should load normally."""
    config_path.write_text('[profiles.default]\napi_base = "https://api.example.com"\n', encoding="utf-8")
    config = cfg.load()
    assert not config.was_load_error
    assert "default" in config.profiles


def test_no_profiles_section(config_path: Path) -> None:
    """Missing profiles section should load normally."""
    config_path.write_text('active_profile = "other"\n', encoding="utf-8")
    config = cfg.load()
    assert not config.was_load_error
    assert config.active_profile == "other"


# -- Regression tests for non-string active_profile selector (Issue #13442) --


@pytest.mark.parametrize(
    "invalid_toml,expected_type",
    [
        ('active_profile = ["work"]\n', "list"),
        ("active_profile = 42\n", "int"),
        ("active_profile = true\n", "bool"),
        ("[active_profile]\nname = 'work'\n", "dict"),
    ],
)
def test_active_profile_non_string_records_load_error(config_path: Path, invalid_toml: str, expected_type: str) -> None:
    """active_profile must be a string; non-string values should set load_error instead of crashing."""
    config_path.write_text(invalid_toml, encoding="utf-8")
    config = cfg.load()
    assert config.was_load_error
    assert config.active_profile == cfg.DEFAULT_PROFILE_NAME
    assert config.profiles == {}
    assert config.load_error is not None
    assert f"'active_profile' must be a string, got {expected_type}" in config.load_error


def test_active_profile_non_string_refuses_save_overwrite(config_path: Path) -> None:
    """A config with invalid active_profile type must not be overwritten by save()."""
    config_path.write_text(
        'active_profile = ["work"]\n[profiles.work]\napi_base = "https://api.omi.me"\n', encoding="utf-8"
    )
    config = cfg.load()
    assert config.was_load_error

    with pytest.raises(PermissionError, match="refusing to overwrite"):
        cfg.save(config)

    # The file on disk is preserved intact
    assert 'active_profile = ["work"]' in config_path.read_text(encoding="utf-8")


def test_active_profile_non_string_diagnostics_succeed(config_path: Path, cli_runner) -> None:
    """Read-only diagnostics commands must still succeed when active_profile is invalid."""
    config_path.write_text('active_profile = ["work"]\n', encoding="utf-8")
    result = cli_runner.invoke(app, ["version"])
    assert result.exit_code == 0, result.output

    result_path = cli_runner.invoke(app, ["config", "path"])
    assert result_path.exit_code == 0, result_path.output
