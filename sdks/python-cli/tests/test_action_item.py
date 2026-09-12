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


def test_action_item_create_batch_list_format(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    route = respx_mock.post("/v1/dev/user/action-items/batch").respond(
        json={
            "action_items": [
                {"id": "a1", "description": "buy milk", "completed": False},
                {"id": "a2", "description": "feed cat", "completed": True},
            ],
            "created_count": 2,
        }
    )
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(
        json.dumps([{"description": "buy milk"}, {"description": "feed cat", "completed": True}]),
        encoding="utf-8",
    )
    result = cli_runner.invoke(app, ["--json", "action-item", "create-batch", str(batch_file)])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["created_count"] == 2
    assert len(payload["action_items"]) == 2
    sent_body = json.loads(route.calls.last.request.content)
    assert len(sent_body["action_items"]) == 2


def test_action_item_create_batch_dict_format(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    respx_mock.post("/v1/dev/user/action-items/batch").respond(
        json={"action_items": [{"id": "a1", "description": "write tests", "completed": False}], "created_count": 1}
    )
    batch_file = tmp_path / "batch_dict.json"
    batch_file.write_text(
        json.dumps({"action_items": [{"description": "write tests"}]}),
        encoding="utf-8",
    )
    result = cli_runner.invoke(app, ["action-item", "create-batch", str(batch_file)])
    assert result.exit_code == 0
    assert "1 items" in result.stderr
    assert "write tests" in result.stdout


def test_action_item_create_batch_missing_file(authed_profile, cli_runner, tmp_path) -> None:
    missing = tmp_path / "does_not_exist.json"
    result = cli_runner.invoke(app, ["action-item", "create-batch", str(missing)])
    assert result.exit_code == 1
    assert "file not found" in result.stderr.lower()


def test_action_item_create_batch_directory_rejected(authed_profile, cli_runner, tmp_path) -> None:
    directory = tmp_path / "batch_dir"
    directory.mkdir()
    result = cli_runner.invoke(app, ["action-item", "create-batch", str(directory)])
    assert result.exit_code == 1
    assert "file not found" in result.stderr.lower()


def test_action_item_create_batch_empty_rejected(authed_profile, cli_runner, tmp_path) -> None:
    batch_file = tmp_path / "empty.json"
    batch_file.write_text("[]", encoding="utf-8")
    result = cli_runner.invoke(app, ["action-item", "create-batch", str(batch_file)])
    assert result.exit_code == 1
    assert "cannot be empty" in result.stderr.lower()


def test_action_item_create_batch_oversize_rejected(authed_profile, cli_runner, tmp_path) -> None:
    batch_file = tmp_path / "oversize.json"
    items = [{"description": f"task {i}"} for i in range(51)]
    batch_file.write_text(json.dumps(items), encoding="utf-8")
    result = cli_runner.invoke(app, ["action-item", "create-batch", str(batch_file)])
    assert result.exit_code == 1
    assert "maximum 50 action items" in result.stderr.lower()


def test_action_item_create_batch_invalid_item_rejected(authed_profile, cli_runner, tmp_path) -> None:
    batch_file = tmp_path / "invalid_item.json"
    batch_file.write_text(json.dumps([{"description": "  "}]), encoding="utf-8")
    result = cli_runner.invoke(app, ["action-item", "create-batch", str(batch_file)])
    assert result.exit_code == 1
    assert "must be an object with a non-empty 'description'" in result.stderr.lower()


def test_action_item_create_batch_non_string_description_rejected(authed_profile, cli_runner, tmp_path) -> None:
    batch_file = tmp_path / "non_string_item.json"
    batch_file.write_text(json.dumps([{"description": 12345}]), encoding="utf-8")
    result = cli_runner.invoke(app, ["action-item", "create-batch", str(batch_file)])
    assert result.exit_code == 1
    assert "must be an object with a non-empty 'description'" in result.stderr.lower()


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


@pytest.mark.parametrize("found", [True, False])
def test_action_item_get_searches_beyond_five_pages(authed_profile, respx_mock, cli_runner, found) -> None:
    """A full fifth page cannot establish that an action item does not exist."""
    offsets = []

    def respond(request):
        offset = int(request.url.params["offset"])
        offsets.append(offset)
        assert request.url.params["limit"] == "200"
        if offset < 1000:
            return httpx.Response(200, json=[{"id": f"a{i}"} for i in range(offset, offset + 200)])
        assert offset == 1000
        return httpx.Response(200, json=[{"id": "target"}] if found else [])

    respx_mock.get("/v1/dev/user/action-items").mock(side_effect=respond)
    result = cli_runner.invoke(app, ["--json", "action-item", "get", "target"])
    assert offsets == [0, 200, 400, 600, 800, 1000]
    assert result.exit_code == (0 if found else 5)
    if found:
        assert json.loads(result.stdout) == {"id": "target"}


def test_action_item_get_stops_after_short_page(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.get("/v1/dev/user/action-items").respond(json=[{"id": "other"}])
    result = cli_runner.invoke(app, ["--json", "action-item", "get", "missing"])
    assert result.exit_code == 5
    assert route.call_count == 1
