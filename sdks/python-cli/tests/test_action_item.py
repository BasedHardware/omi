"""Tests for ``omi action-item`` commands."""

from __future__ import annotations

import json

from omi_cli.main import app


def test_action_item_list(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/action-items").respond(
        json=[{"id": "a1", "description": "ship it", "completed": False}]
    )
    result = cli_runner.invoke(app, ["--json", "action-item", "list"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload[0]["id"] == "a1"


def test_action_item_create(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/action-items").respond(
        json={"id": "a1", "description": "buy milk", "completed": False}
    )
    result = cli_runner.invoke(app, ["--json", "action-item", "create", "buy milk"])
    assert result.exit_code == 0
    body = json.loads(route.calls.last.request.content)
    assert body["description"] == "buy milk"


def test_action_item_complete_uses_patch(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.patch("/v1/dev/user/action-items/a1").respond(
        json={"id": "a1", "description": "ship", "completed": True}
    )
    result = cli_runner.invoke(app, ["--json", "action-item", "complete", "a1"])
    assert result.exit_code == 0
    body = json.loads(route.calls.last.request.content)
    assert body == {"completed": True}


def test_action_item_filter_completed(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.get("/v1/dev/user/action-items").respond(json=[])
    cli_runner.invoke(app, ["action-item", "list", "--completed"])
    request = route.calls.last.request
    assert request.url.params["completed"] == "true"


def test_action_item_delete(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.delete("/v1/dev/user/action-items/a1").respond(json={"success": True})
    result = cli_runner.invoke(app, ["action-item", "delete", "a1", "-y"])
    assert result.exit_code == 0


def test_action_item_get_missing_returns_not_found_exit_code(authed_profile, respx_mock, cli_runner) -> None:
    """Same agent contract as memory get — client-side miss is exit 5, not 1."""
    respx_mock.get("/v1/dev/user/action-items").respond(json=[])
    result = cli_runner.invoke(app, ["action-item", "get", "missing"])
    assert result.exit_code == 5  # EXIT_NOT_FOUND
    assert "not found" in result.stderr.lower()
