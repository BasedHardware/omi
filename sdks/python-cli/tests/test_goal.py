"""Tests for ``omi goal`` commands."""

from __future__ import annotations

import json
import sys

import pytest

from omi_cli.main import app, main


def test_goal_list(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/goals").respond(
        json=[
            {
                "id": "g1",
                "title": "ship cli",
                "goal_type": "scale",
                "target_value": 10,
                "current_value": 3,
                "min_value": 0,
                "max_value": 10,
                "is_active": True,
            }
        ]
    )
    result = cli_runner.invoke(app, ["--json", "goal", "list"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload[0]["id"] == "g1"


def test_goal_create_posts(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/goals").respond(
        json={
            "id": "g1",
            "title": "drink water",
            "goal_type": "numeric",
            "target_value": 2.0,
            "current_value": 0,
            "min_value": 0,
            "max_value": 10,
            "unit": "liters",
            "is_active": True,
        }
    )
    result = cli_runner.invoke(
        app,
        [
            "--json",
            "goal",
            "create",
            "drink water",
            "--target",
            "2",
            "--type",
            "numeric",
            "--unit",
            "liters",
        ],
    )
    assert result.exit_code == 0
    body = json.loads(route.calls.last.request.content)
    assert body["target_value"] == 2.0
    assert body["goal_type"] == "numeric"
    assert body["unit"] == "liters"


def test_goal_create_qualitative_omits_metrics(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/goals").respond(
        json={
            "id": "g2",
            "title": "Build stronger relationships",
            "goal_type": None,
            "target_value": None,
            "current_value": None,
            "min_value": None,
            "max_value": None,
            "unit": None,
            "is_active": True,
        }
    )
    result = cli_runner.invoke(app, ["--json", "goal", "create", "Build stronger relationships"])
    assert result.exit_code == 0, result.stdout
    body = json.loads(route.calls.last.request.content)
    assert body == {"title": "Build stronger relationships"}


def test_goal_create_metric_defaults_preserved(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/goals").respond(
        json={
            "id": "g3",
            "title": "drink water",
            "goal_type": "scale",
            "target_value": 2.0,
            "current_value": 0,
            "min_value": 0,
            "max_value": 10,
            "is_active": True,
        }
    )
    result = cli_runner.invoke(app, ["--json", "goal", "create", "drink water", "--target", "2"])
    assert result.exit_code == 0, result.stdout
    body = json.loads(route.calls.last.request.content)
    # Historical defaults still apply when any metric option is given.
    assert body["goal_type"] == "scale"
    assert body["target_value"] == 2.0
    assert body["current_value"] == 0
    assert body["min_value"] == 0
    assert body["max_value"] == 10


def test_goal_create_unit_without_metrics_rejected(authed_profile, cli_runner) -> None:
    result = cli_runner.invoke(app, ["--json", "goal", "create", "meditate", "--unit", "sessions"])
    assert result.exit_code == 1  # EXIT_USAGE
    assert "--unit requires a metric goal" in result.stderr


def test_goal_create_partial_metrics_rejected(authed_profile, cli_runner) -> None:
    result = cli_runner.invoke(app, ["--json", "goal", "create", "drink water", "--current", "5"])
    assert result.exit_code == 1  # EXIT_USAGE
    assert "--target is required" in result.stderr


def test_goal_create_unit_attached_to_metric_goal(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/goals").respond(
        json={
            "id": "g4",
            "title": "drink water",
            "goal_type": "scale",
            "target_value": 2.0,
            "current_value": 0,
            "min_value": 0,
            "max_value": 10,
            "unit": "liters",
            "is_active": True,
        }
    )
    result = cli_runner.invoke(app, ["--json", "goal", "create", "drink water", "--target", "2", "--unit", "liters"])
    assert result.exit_code == 0, result.stdout
    body = json.loads(route.calls.last.request.content)
    assert body["unit"] == "liters"


def test_goal_progress_uses_query_param(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.patch("/v1/dev/user/goals/g1/progress").respond(
        json={
            "id": "g1",
            "title": "x",
            "goal_type": "scale",
            "target_value": 10,
            "current_value": 7,
            "min_value": 0,
            "max_value": 10,
            "is_active": True,
        }
    )
    result = cli_runner.invoke(app, ["--json", "goal", "progress", "g1", "7"])
    assert result.exit_code == 0
    request = route.calls.last.request
    # httpx serializes Python floats with the trailing ``.0`` — accept either form.
    assert request.url.params["current_value"] in ("7", "7.0")


def test_goal_history(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/goals/g1/history").respond(json=[{"recorded_at": "2026-04-25T00:00:00Z", "value": 3}])
    result = cli_runner.invoke(app, ["--json", "goal", "history", "g1", "--days", "7"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload[0]["value"] == 3


def test_goal_delete(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.delete("/v1/dev/user/goals/g1").respond(json={"success": True})
    result = cli_runner.invoke(app, ["goal", "delete", "g1", "-y"])
    assert result.exit_code == 0


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        (["--unit", "liters"], {"unit": "liters"}),
        (["--unit", ""], {"unit": ""}),
        (["--clear-unit"], {"unit": None}),
        (["--title", "drink water"], {"title": "drink water"}),
        (["--clear-unit", "--current", "2"], {"unit": None, "current_value": 2.0}),
    ],
)
def test_goal_update_unit_patch(authed_profile, respx_mock, cli_runner, options, expected) -> None:
    route = respx_mock.patch("/v1/dev/user/goals/g1").respond(json={"id": "g1", **expected})
    result = cli_runner.invoke(app, ["--json", "goal", "update", "g1", *options])
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls.last.request.content) == expected
    assert json.loads(result.stdout) == {"id": "g1", **expected}


@pytest.mark.parametrize("unit", ["liters", ""])
def test_goal_update_rejects_set_and_clear_unit(authed_profile, respx_mock, monkeypatch, capsys, unit) -> None:
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "goal", "update", "g1", "--unit", unit, "--clear-unit"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    error = json.loads(output.err)
    assert "--unit" in error["detail"]
    assert "--clear-unit" in error["detail"]
    assert not respx_mock.calls

@pytest.mark.parametrize(
    ("options", "expected"),
    [
        (["--horizon-at", "2026-12-31T23:59:59Z"], {"horizon_at": "2026-12-31T23:59:59+00:00"}),
        (["--horizon-at", "2026-12-31T23:59:59+02:00"], {"horizon_at": "2026-12-31T23:59:59+02:00"}),
        (["--clear-horizon"], {"horizon_at": None}),
        (["--clear-horizon", "--current", "5"], {"horizon_at": None, "current_value": 5.0}),
    ],
)
def test_goal_update_horizon_patch(authed_profile, respx_mock, cli_runner, options, expected) -> None:
    route = respx_mock.patch("/v1/dev/user/goals/g1").respond(json={"id": "g1", **expected})
    result = cli_runner.invoke(app, ["--json", "goal", "update", "g1", *options])
    assert result.exit_code == 0, result.output
    assert json.loads(route.calls.last.request.content) == expected
    assert json.loads(result.stdout) == {"id": "g1", **expected}


def test_goal_update_rejects_set_and_clear_horizon(authed_profile, respx_mock, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["omi", "--json", "goal", "update", "g1", "--horizon-at", "2026-12-31T23:59:59Z", "--clear-horizon"],
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    error = json.loads(output.err)
    assert "--horizon-at" in error["detail"]
    assert "--clear-horizon" in error["detail"]
    assert not respx_mock.calls


@pytest.mark.parametrize("value", ["2026-12-31T23:59:59", "2026-12-31"])
def test_goal_update_rejects_naive_horizon(authed_profile, respx_mock, monkeypatch, capsys, value) -> None:
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "goal", "update", "g1", "--horizon-at", value])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    error = json.loads(output.err)
    assert "timezone" in error["detail"].lower()
    assert not respx_mock.calls


def test_goal_update_rejects_invalid_horizon(authed_profile, respx_mock, monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "goal", "update", "g1", "--horizon-at", "not-a-datetime"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    assert output.out == ""
    error = json.loads(output.err)
    assert "invalid iso datetime" in error["detail"].lower()
    assert not respx_mock.calls
