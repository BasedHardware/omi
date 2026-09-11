"""Config mutations must emit JSON in --json mode (#13044)."""
import json


def test_config_set_emits_json(authed_profile, cli_runner):
    from omi_cli.main import app

    result = cli_runner.invoke(app, ["--json", "config", "set", "api_base", "https://example.test"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["key"] == "api_base"


def test_config_profile_use_emits_json(authed_profile, cli_runner):
    from omi_cli.main import app

    result = cli_runner.invoke(app, ["--json", "config", "profile", "use", "work"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["active_profile"] == "work"
