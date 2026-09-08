"""Tests for ``omi action-item`` commands."""

from __future__ import annotations

import json

import httpx
import pytest

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


@pytest.mark.parametrize("target_index", [999, 1000, 1200])
def test_action_item_get_finds_items_beyond_five_pages(authed_profile, respx_mock, cli_runner, target_index) -> None:
    items = [{"id": f"a{i}", "description": "task", "completed": False} for i in range(target_index + 1)]

    def list_page(request):
        offset = int(request.url.params["offset"])
        limit = int(request.url.params["limit"])
        return httpx.Response(200, json=items[offset : offset + limit])

    route = respx_mock.get("/v1/dev/user/action-items").mock(side_effect=list_page)
    result = cli_runner.invoke(app, ["--json", "action-item", "get", f"a{target_index}"])
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == items[target_index]
    assert [int(call.request.url.params["offset"]) for call in route.calls] == list(range(0, target_index + 1, 200))


def test_action_item_get_exhausts_full_pages_before_reporting_missing(authed_profile, respx_mock, cli_runner) -> None:
    items = [{"id": f"a{i}", "description": "task", "completed": False} for i in range(1200)]

    def list_page(request):
        offset = int(request.url.params["offset"])
        limit = int(request.url.params["limit"])
        return httpx.Response(200, json=items[offset : offset + limit])

    route = respx_mock.get("/v1/dev/user/action-items").mock(side_effect=list_page)
    result = cli_runner.invoke(app, ["--json", "action-item", "get", "missing"])
    assert result.exit_code == 5
    assert [int(call.request.url.params["offset"]) for call in route.calls] == list(range(0, 1201, 200))
