"""Tests for the Typer root: --version, --help, global-flag plumbing."""

from __future__ import annotations

import json

from omi_cli import __version__
from omi_cli.main import app


def test_version_flag(cli_runner) -> None:
    result = cli_runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_version_subcommand(cli_runner) -> None:
    result = cli_runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_help_lists_all_top_level_commands(cli_runner) -> None:
    result = cli_runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("auth", "config", "memory", "conversation", "action-item", "goal", "version"):
        assert cmd in result.stdout


def test_auth_status_unauthenticated_in_json(config_path, cli_runner) -> None:
    result = cli_runner.invoke(app, ["--json", "auth", "status"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["authenticated"] is False
    assert payload["auth_method"] is None


def test_omi_api_key_env_var_is_validated(config_path, cli_runner, monkeypatch) -> None:
    """Greptile P2: an obviously-bad OMI_API_KEY env value must surface as a
    UsageError (exit 1) before the CLI tries to call the API and bounces off
    a 401."""
    monkeypatch.setenv("OMI_API_KEY", "not-a-real-key")
    result = cli_runner.invoke(app, ["memory", "list"])
    assert result.exit_code == 1  # EXIT_USAGE — same shape as the paste flow's bad-format error
    assert "developer key" in result.stderr.lower() or "omi_dev_" in result.stderr.lower()


def test_omi_api_key_env_var_with_valid_format_is_accepted(config_path, cli_runner, monkeypatch, respx_mock) -> None:
    """A well-formed env-var key should reach the API exactly like the on-disk path."""
    from tests.conftest import FAKE_API_BASE

    monkeypatch.setenv("OMI_API_KEY", "omi_dev_" + ("a" * 32))
    monkeypatch.setenv("OMI_API_BASE", FAKE_API_BASE)
    respx_mock.get("/v1/dev/user/memories").respond(json=[])
    result = cli_runner.invoke(app, ["--json", "memory", "list"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "[]"
