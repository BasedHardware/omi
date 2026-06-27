"""Tests for ``omi goal`` commands."""

from __future__ import annotations

import json

from omi_cli.main import app


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
