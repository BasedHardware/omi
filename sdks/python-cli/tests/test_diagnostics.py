"""Diagnostics must remain available when configuration needs repair."""

import json

import pytest

from omi_cli import __version__
from omi_cli.main import app


@pytest.mark.parametrize("arguments", [["version"], ["config", "path"], ["--json", "config", "path"]])
def test_diagnostics_with_malformed_config(config_path, cli_runner, arguments):
    original = b"active_profile = [\n"
    config_path.write_bytes(original)
    result = cli_runner.invoke(app, arguments)
    assert result.exit_code == 0, result.exception
    if arguments == ["version"]:
        assert result.stdout.strip() == f"omi-cli {__version__}"
    elif arguments[0] == "--json":
        assert json.loads(result.stdout) == {"path": str(config_path)}
    else:
        assert result.stdout.strip() == str(config_path)
    assert config_path.read_bytes() == original


def test_config_commands_still_reject_malformed_config(config_path, cli_runner):
    original = b"active_profile = [\n"
    config_path.write_bytes(original)
    result = cli_runner.invoke(app, ["config", "set", "api_base", "https://example.test"])
    assert result.exit_code != 0
    assert config_path.read_bytes() == original


@pytest.mark.parametrize(
    "flag,environment,expected", [(None, None, "saved"), (None, "env", "env"), ("flag", "env", "flag")]
)
def test_lazy_profile_keeps_precedence(config_path, cli_runner, monkeypatch, flag, environment, expected):
    config_path.write_text('active_profile = "saved"\n', encoding="utf-8")
    if environment:
        monkeypatch.setenv("OMI_PROFILE", environment)
    args = ["--profile", flag] if flag else []
    result = cli_runner.invoke(app, args + ["config", "set", "api_base", "https://example.test"])
    assert result.exit_code == 0, result.exception
    from omi_cli import config

    saved = config.load()
    assert saved.profiles[expected].api_base == "https://example.test"
    assert set(saved.profiles) == {expected}
