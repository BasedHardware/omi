"""Goal update regressions (#13111, #13103)."""
import json
import sys

import pytest

from omi_cli.main import app, main


def test_goal_update_horizon_and_context(authed_profile, respx_mock, cli_runner):
    route = respx_mock.patch("/v1/dev/user/goals/g1").respond(json={"id": "g1"})
    result = cli_runner.invoke(
        app,
        ["--json", "goal", "update", "g1", "--horizon-at", "2026-12-01T00:00:00", "--desired-outcome", "ship"],
    )
    assert result.exit_code == 0, result.output
    body = json.loads(route.calls.last.request.content)
    assert body["horizon_at"].startswith("2026-12-01")
    assert body["desired_outcome"] == "ship"


def test_goal_update_clear_horizon(authed_profile, respx_mock, cli_runner):
    route = respx_mock.patch("/v1/dev/user/goals/g1").respond(json={"id": "g1"})
    result = cli_runner.invoke(app, ["--json", "goal", "update", "g1", "--clear-horizon"])
    assert result.exit_code == 0, result.output
    body = json.loads(route.calls.last.request.content)
    assert body == {"horizon_at": None}


def test_goal_update_rejects_conflicting_horizon(authed_profile, respx_mock, monkeypatch, capsys):
    monkeypatch.setattr(
        sys,
        "argv",
        ["omi", "--json", "goal", "update", "g1", "--horizon-at", "2026-12-01T00:00:00", "--clear-horizon"],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    err = json.loads(capsys.readouterr().err)
    assert "horizon" in err["detail"].lower()
    assert not respx_mock.calls
