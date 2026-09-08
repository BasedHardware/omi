"""Tests for the Typer root: --version, --help, global-flag plumbing."""

from __future__ import annotations

import json
import sys
import time

import httpx
import pytest

from omi_cli import __version__
from omi_cli.client import MAX_RETRY_ATTEMPTS
from omi_cli.main import app, main


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


@pytest.mark.parametrize("source", ["flag", "env"])
@pytest.mark.parametrize("json_mode", [False, True])
@pytest.mark.parametrize(
    "api_base",
    [
        "ftp://user:secret@example.invalid/?token=private-token",
        "http://user:secret@127.0.0.1:0/?token=private-token",
        "http://user:secret@127.0.0.1:99999/?token=private-token",
    ],
)
def test_invalid_api_base_is_safe_usage_error(authed_profile, monkeypatch, capsys, source, json_mode, api_base) -> None:
    argv = ["omi", "--no-color", *(["--json"] if json_mode else [])]
    if source == "flag":
        argv.extend(["--api-base", api_base])
    else:
        monkeypatch.setenv("OMI_API_BASE", api_base)
    argv.extend(["memory", "list"])
    monkeypatch.setattr(sys, "argv", argv)

    def unexpected_call(*args, **kwargs):
        pytest.fail("Invalid API configuration must not issue HTTP requests or retry")

    monkeypatch.setattr(httpx.Client, "request", unexpected_call)
    monkeypatch.setattr(time, "sleep", unexpected_call)

    with pytest.raises(SystemExit) as info:
        main()

    captured = capsys.readouterr()
    assert info.value.code == 1
    assert captured.out == ""
    if json_mode:
        assert json.loads(captured.err) == {
            "error": "Invalid API base URL",
            "detail": "Use a valid absolute http:// or https:// URL for the Omi API.",
        }
    else:
        assert "Invalid API base URL" in captured.err
        assert "Use a valid absolute http:// or https:// URL for the Omi API." in captured.err
    assert "unexpected error" not in captured.err
    assert "Traceback" not in captured.err
    assert "secret" not in captured.err
    assert "private-token" not in captured.err


@pytest.mark.parametrize("json_mode", [False, True])
@pytest.mark.parametrize(
    "error_type, expected_message, expected_detail",
    [
        (
            httpx.ConnectError,
            "Connection failed",
            "Could not reach the Omi API after multiple attempts. Check your connection and try again.",
        ),
        (httpx.ReadTimeout, "Request timed out", "The Omi API request timed out after multiple attempts."),
        (
            httpx.RemoteProtocolError,
            "Protocol error",
            "The Omi API request encountered a protocol error after multiple attempts.",
        ),
    ],
)
def test_main_transport_failure_preserves_error_contract(
    authed_profile, respx_mock, monkeypatch, capsys, json_mode, error_type, expected_message, expected_detail
) -> None:
    route = respx_mock.get("/v1/dev/user/memories").mock(
        side_effect=error_type("request failed at https://user:secret@example.invalid/?token=private-token")
    )
    monkeypatch.setattr(time, "sleep", lambda _: None)
    monkeypatch.setattr(sys, "argv", ["omi", "--no-color", *(["--json"] if json_mode else []), "memory", "list"])

    with pytest.raises(SystemExit) as info:
        main()

    captured = capsys.readouterr()
    assert info.value.code == 3
    assert route.call_count == MAX_RETRY_ATTEMPTS
    assert captured.out == ""
    if json_mode:
        assert json.loads(captured.err) == {
            "error": expected_message,
            "detail": expected_detail,
        }
    else:
        assert expected_message in captured.err
        assert expected_detail in captured.err
    assert "unexpected error" not in captured.err
    assert "Traceback" not in captured.err
    assert "secret" not in captured.err
    assert "private-token" not in captured.err


def test_module_entry_point_honors_json_error_contract(config_path, monkeypatch, tmp_path) -> None:
    """Issue #12998: `python -m omi_cli` must route through omi_cli.main.main()
    so the documented --json error contract survives module invocation."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    package_root = str(Path(__file__).resolve().parents[1])
    # Install a network tripwire in the child without replacing its real -m
    # entrypoint. A future validation regression must not contact the live API.
    (tmp_path / "sitecustomize.py").write_text(
        "import socket\n"
        "def reject_network(*args, **kwargs):\n"
        "    raise RuntimeError('Unexpected network access in module-entry test')\n"
        "socket.getaddrinfo = reject_network\n"
        "socket.socket.connect = reject_network\n"
        "socket.socket.connect_ex = reject_network\n"
    )
    env = dict(os.environ, OMI_API_KEY="not-a-real-key")
    env["PYTHONPATH"] = os.pathsep.join([str(tmp_path), package_root])
    result = subprocess.run(
        [sys.executable, "-m", "omi_cli", "--json", "memory", "list"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(tmp_path),
        check=False,
        timeout=15,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    payload = json.loads(result.stderr)
    assert payload["error"] == "That doesn't look like an Omi developer key"
