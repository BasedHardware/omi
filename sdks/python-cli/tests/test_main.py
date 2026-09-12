"""Tests for the Typer root: --version, --help, global-flag plumbing."""

from __future__ import annotations

import io
import json

import pytest

from omi_cli import __version__
from omi_cli.main import app


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, EOFError])
def test_login_prompt_interruption_exits_cleanly(config_path, monkeypatch, capsys, interruption) -> None:
    """Regression: Ctrl-C / Ctrl-D at an interactive prompt must print
    "Aborted." and exit 130 — not fall through to the generic handler with
    an empty ``str(click.Abort())`` message ("unexpected error: ``")."""
    from omi_cli.main import main

    class InterruptedInput(io.StringIO):
        def isatty(self):
            return True

        def readline(self, *args, **kwargs):
            raise interruption

    monkeypatch.setattr("sys.stdin", InterruptedInput())
    monkeypatch.setattr("sys.argv", ["omi", "auth", "login"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 130
    stderr = capsys.readouterr().err
    assert "Aborted." in stderr
    assert "unexpected error" not in stderr


def test_version_flag(cli_runner) -> None:
    result = cli_runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_version_subcommand(cli_runner) -> None:
    result = cli_runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_version_subcommand_json(config_path, cli_runner) -> None:
    result = cli_runner.invoke(app, ["--json", "version"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"version": __version__}
    assert result.stderr == ""
    assert not config_path.exists()


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


def test_module_entry_point_honors_json_error_contract(config_path, monkeypatch, tmp_path) -> None:
    """Issue #12998: `python -m omi_cli` must route through omi_cli.main.main()
    so the documented --json error contract survives module invocation."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    package_root = str(Path(__file__).resolve().parents[1])
    env = dict(os.environ, OMI_API_KEY="not-a-real-key")
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [package_root, env.get("PYTHONPATH", "")])
    )
    result = subprocess.run(
        [sys.executable, "-m", "omi_cli", "--json", "memory", "list"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        check=False,
    )
    assert result.returncode == 1
    payload = json.loads(result.stderr)
    assert "error" in payload


@pytest.mark.parametrize("operation", ["list", "create", "whoami"])
def test_env_key_overrides_saved_key_without_persisting(
    operation, authed_profile, config_path, cli_runner, monkeypatch, respx_mock
) -> None:
    env_key = "omi_dev_" + "e" * 32
    original_config = config_path.read_bytes()
    monkeypatch.setenv("OMI_API_KEY", env_key)
    if operation in ("list", "whoami"):
        route = respx_mock.get("/v1/dev/user/memories").respond(json=[])
        args = ["auth", "whoami"] if operation == "whoami" else ["memory", "list"]
    else:
        route = respx_mock.post("/v1/dev/user/memories").respond(json={"id": "synthetic"})
        args = ["memory", "create", "synthetic test memory"]

    result = cli_runner.invoke(app, ["--json", *args])

    assert result.exit_code == 0, result.output
    assert route.calls.last.request.headers["Authorization"] == f"Bearer {env_key}"
    assert config_path.read_bytes() == original_config
    if operation == "whoami":
        payload = json.loads(result.stdout)
        assert payload["credential"] == f"{env_key[:6]}…{env_key[-4:]}"
        assert payload["credential"] != authed_profile.masked_credential()


def test_invalid_env_key_does_not_fall_back_to_saved_account(
    authed_profile, cli_runner, monkeypatch, respx_mock
) -> None:
    monkeypatch.setenv("OMI_API_KEY", "invalid-key")
    route = respx_mock.get("/v1/dev/user/memories").respond(json=[])

    result = cli_runner.invoke(app, ["--json", "memory", "list"])

    assert result.exit_code == 1
    assert not route.called
    assert "developer key" in result.stderr.lower()


@pytest.mark.parametrize("command", ["status", "tools"])
def test_local_commands_ignore_invalid_cloud_key(
    command, authed_profile, config_path, cli_runner, monkeypatch
) -> None:
    import respx

    from omi_cli import config as cfg

    config = cfg.load()
    profile = config.get_profile()
    profile.local_api_url = "http://127.0.0.1:47778"
    profile.local_token = "synthetic-local-token"
    cfg.save(config)
    original_config = config_path.read_bytes()
    monkeypatch.setenv("OMI_API_KEY", "invalid-cloud-key")
    with respx.mock(base_url=profile.local_api_url) as router:
        if command == "status":
            route = router.post("/v1/local/tool").respond(
                json={"ok": True, "result": json.dumps({"ok": True})}
            )
        else:
            route = router.get("/v1/local/tools").respond(json={"ok": True, "tools": []})
        result = cli_runner.invoke(app, ["--json", "local", command])

    assert result.exit_code == 0, result.output
    assert route.calls.last.request.headers["Authorization"] == "Bearer synthetic-local-token"
    assert config_path.read_bytes() == original_config


def test_auth_status_reports_saved_profile_despite_invalid_env_key(
    authed_profile, cli_runner, monkeypatch
) -> None:
    monkeypatch.setenv("OMI_API_KEY", "invalid-cloud-key")
    result = cli_runner.invoke(app, ["--json", "auth", "status"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["credential"] == authed_profile.masked_credential()
