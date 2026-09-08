"""Regression tests for Rich markup-like fragments in CLI status messages."""

from __future__ import annotations

import json

from omi_cli import config as cfg
from omi_cli.main import app


MARKUP_PROFILE = "bad[/bold]profile"
MARKUP_VALUE = "http://127.0.0.1/[oops]"


def test_config_profile_use_escapes_markup_profile_name(config_path, cli_runner) -> None:
    result = cli_runner.invoke(app, ["--profile", MARKUP_PROFILE, "config", "profile", "use", MARKUP_PROFILE])

    assert result.exit_code == 0, result.output
    assert "MarkupError" not in result.stderr
    assert MARKUP_PROFILE in result.stderr
    assert cfg.load().active_profile == MARKUP_PROFILE


def test_config_set_escapes_markup_profile_and_value(config_path, cli_runner) -> None:
    result = cli_runner.invoke(
        app,
        ["--profile", MARKUP_PROFILE, "config", "set", "local_api_url", MARKUP_VALUE],
    )

    assert result.exit_code == 0, result.output
    assert "MarkupError" not in result.stderr
    assert MARKUP_PROFILE in result.stderr
    assert MARKUP_VALUE in result.stderr
    assert cfg.load().get_profile(MARKUP_PROFILE).local_api_url == MARKUP_VALUE.rstrip("/")


def test_config_profile_delete_error_escapes_markup_profile_name(config_path, cli_runner) -> None:
    result = cli_runner.invoke(app, ["config", "profile", "delete", MARKUP_PROFILE, "--yes"])

    assert result.exit_code != 0
    assert "MarkupError" not in result.stderr
    assert MARKUP_PROFILE in result.stderr


def test_auth_logout_escapes_markup_profile_name(config_path, cli_runner) -> None:
    result = cli_runner.invoke(app, ["--profile", MARKUP_PROFILE, "auth", "logout"])

    assert result.exit_code == 0, result.output
    assert "MarkupError" not in result.stderr
    assert MARKUP_PROFILE in result.stderr


def test_auth_refresh_error_detail_escapes_markup_profile_name(config_path, cli_runner) -> None:
    profile = cfg.Profile(name=MARKUP_PROFILE, auth_method="api_key", api_key="omi_dev_" + "x" * 32)
    config = cfg.load()
    config.set_profile(profile)
    config.active_profile = MARKUP_PROFILE
    cfg.save(config)

    result = cli_runner.invoke(app, ["--profile", MARKUP_PROFILE, "auth", "refresh"])

    assert result.exit_code != 0
    assert "MarkupError" not in result.stderr
    assert MARKUP_PROFILE in result.stderr


def test_json_auth_refresh_error_detail_keeps_raw_profile_name(config_path, cli_runner) -> None:
    profile = cfg.Profile(name=MARKUP_PROFILE, auth_method="api_key", api_key="omi_dev_" + "x" * 32)
    config = cfg.load()
    config.set_profile(profile)
    config.active_profile = MARKUP_PROFILE
    cfg.save(config)

    result = cli_runner.invoke(app, ["--json", "--profile", MARKUP_PROFILE, "auth", "refresh"])

    assert result.exit_code != 0
    payload = json.loads(result.stderr)
    assert payload["detail"] == (
        f"Profile '{MARKUP_PROFILE}' uses API-key auth — there is no token to refresh. "
        "Rotate keys in the Omi web app if needed."
    )
    assert "\\[" not in payload["detail"]
