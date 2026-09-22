"""Regression tests for Rich markup-like fragments in auth status messages."""

from __future__ import annotations

from omi_cli import config as cfg
from omi_cli.main import app


MARKUP_PROFILE = "bad[/bold]profile"


def test_auth_logout_escapes_markup_profile_name(config_path, cli_runner) -> None:
    result = cli_runner.invoke(app, ["--profile", MARKUP_PROFILE, "auth", "logout"])

    assert result.exit_code == 0, result.output
    assert "MarkupError" not in result.stderr
    assert MARKUP_PROFILE in result.stderr


def test_auth_refresh_success_escapes_markup_profile_name(config_path, cli_runner, monkeypatch) -> None:
    profile = cfg.Profile(
        name=MARKUP_PROFILE,
        auth_method="oauth",
        id_token="token",
        refresh_token="refresh",
    )
    config = cfg.load()
    config.set_profile(profile)
    config.active_profile = MARKUP_PROFILE
    cfg.save(config)
    monkeypatch.setattr("omi_cli.commands.auth.oauth_auth.refresh_id_token", lambda _name: "token")

    result = cli_runner.invoke(app, ["--profile", MARKUP_PROFILE, "auth", "refresh"])

    assert result.exit_code == 0, result.output
    assert "MarkupError" not in result.stderr
    assert MARKUP_PROFILE in result.stderr
