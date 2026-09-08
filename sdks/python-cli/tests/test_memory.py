"""Tests for ``omi memory`` commands via CliRunner."""

from __future__ import annotations

import json

import pytest

from omi_cli.main import app


def test_memory_list_json(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/memories").respond(
        json=[{"id": "m1", "content": "hello world", "category": "core", "visibility": "private", "tags": []}]
    )
    result = cli_runner.invoke(app, ["--json", "memory", "list"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload[0]["id"] == "m1"


def test_memory_list_pretty_renders_table(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/memories").respond(
        json=[
            {
                "id": "m1",
                "content": "hello",
                "category": "core",
                "visibility": "private",
                "tags": ["a"],
                "created_at": "2026-04-01T00:00:00Z",
            }
        ]
    )
    result = cli_runner.invoke(app, ["--no-color", "memory", "list"])
    assert result.exit_code == 0
    assert "m1" in result.stdout
    assert "hello" in result.stdout


def test_memory_create_posts_body(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/memories").respond(
        json={"id": "m99", "content": "from cli", "category": "core", "visibility": "private", "tags": []}
    )
    result = cli_runner.invoke(app, ["--json", "memory", "create", "from cli"])
    assert result.exit_code == 0
    request = route.calls.last.request
    body = json.loads(request.content)
    assert body["content"] == "from cli"
    assert body["visibility"] == "private"


def test_memory_create_with_category_and_tags(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/memories").respond(
        json={"id": "m1", "content": "x", "category": "work", "visibility": "public", "tags": ["a", "b"]}
    )
    result = cli_runner.invoke(
        app,
        ["--json", "memory", "create", "x", "--category", "work", "--visibility", "public", "--tag", "a", "--tag", "b"],
    )
    assert result.exit_code == 0
    body = json.loads(route.calls.last.request.content)
    assert body["category"] == "work"
    assert body["visibility"] == "public"
    assert body["tags"] == ["a", "b"]


def test_memory_delete_skips_prompt_with_yes(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.delete("/v1/dev/user/memories/m1").respond(204)
    result = cli_runner.invoke(app, ["memory", "delete", "m1", "--yes"])
    assert result.exit_code == 0


def test_memory_create_batch_posts_body(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(
        json.dumps(
            [
                {"content": "first", "category": "work", "visibility": "public", "tags": ["a"]},
                {"content": "second"},
            ]
        ),
        encoding="utf-8",
    )
    route = respx_mock.post("/v1/dev/user/memories/batch").respond(
        json={
            "memories": [{"id": "m1"}, {"id": "m2"}],
            "created_count": 2,
        }
    )
    result = cli_runner.invoke(app, ["--json", "memory", "create-batch", str(batch_file)])
    assert result.exit_code == 0, result.output
    body = json.loads(route.calls.last.request.content)
    assert body == {
        "memories": [
            {"content": "first", "category": "work", "visibility": "public", "tags": ["a"]},
            {"content": "second", "visibility": "private", "tags": []},
        ]
    }
    payload = json.loads(result.stdout)
    assert payload["created_count"] == 2


def test_memory_create_batch_accepts_memories_object(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(json.dumps({"memories": [{"content": "hello"}]}), encoding="utf-8")
    route = respx_mock.post("/v1/dev/user/memories/batch").respond(
        json={"memories": [{"id": "m1"}], "created_count": 1}
    )
    result = cli_runner.invoke(app, ["--json", "memory", "create-batch", str(batch_file)])
    assert result.exit_code == 0, result.output
    body = json.loads(route.calls.last.request.content)
    assert body == {"memories": [{"content": "hello", "visibility": "private", "tags": []}]}


def test_memory_create_batch_malformed_json_sends_no_request(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    batch_file = tmp_path / "bad.json"
    batch_file.write_text("{ not json", encoding="utf-8")
    respx_mock.post("/v1/dev/user/memories/batch").respond(json={"memories": [], "created_count": 0})
    result = cli_runner.invoke(app, ["memory", "create-batch", str(batch_file)])
    assert result.exit_code == 1
    assert "not valid json" in result.stderr.lower()
    assert not respx_mock.calls


def test_memory_create_batch_over_25_is_usage_error(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    batch_file = tmp_path / "many.json"
    batch_file.write_text(json.dumps([{"content": f"m{i}"} for i in range(26)]), encoding="utf-8")
    respx_mock.post("/v1/dev/user/memories/batch").respond(json={"memories": [], "created_count": 0})
    result = cli_runner.invoke(app, ["memory", "create-batch", str(batch_file)])
    assert result.exit_code == 1
    assert "25" in result.stderr
    assert not respx_mock.calls


def test_memory_create_batch_missing_file_is_usage_error(authed_profile, cli_runner, tmp_path) -> None:
    result = cli_runner.invoke(app, ["memory", "create-batch", str(tmp_path / "nope.json")])
    assert result.exit_code == 1
    assert "not found" in result.stderr.lower()


def test_memory_create_batch_auth_failure(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    batch_file = tmp_path / "batch.json"
    batch_file.write_text(json.dumps([{"content": "x"}]), encoding="utf-8")
    respx_mock.post("/v1/dev/user/memories/batch").respond(401, json={"detail": "nope"})
    result = cli_runner.invoke(app, ["memory", "create-batch", str(batch_file)])
    assert result.exit_code == 2
    assert "auth" in result.stderr.lower()


def test_memory_update_requires_at_least_one_field(authed_profile, cli_runner) -> None:
    result = cli_runner.invoke(app, ["memory", "update", "m1"])
    # exit 1 = usage error
    assert result.exit_code == 1
    assert "no fields to update" in result.stderr.lower()


def test_memory_update_patches_body(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.patch("/v1/dev/user/memories/m1").respond(
        json={
            "id": "m1",
            "content": "new",
            "category": "core",
            "visibility": "private",
            "tags": [],
            "created_at": "2026-04-01T00:00:00Z",
            "updated_at": "2026-04-26T00:00:00Z",
            "manually_added": True,
            "reviewed": False,
            "edited": True,
        }
    )
    result = cli_runner.invoke(app, ["--json", "memory", "update", "m1", "--content", "new"])
    assert result.exit_code == 0
    body = json.loads(route.calls.last.request.content)
    assert body == {"content": "new"}


def test_memory_unauthenticated_is_clear(config_path, cli_runner) -> None:
    result = cli_runner.invoke(app, ["memory", "list"])
    assert result.exit_code == 2  # EXIT_AUTH
    assert "auth login" in result.stderr.lower() or "not authenticated" in result.stderr.lower()


def test_memory_get_missing_returns_not_found_exit_code(authed_profile, respx_mock, cli_runner) -> None:
    """Client-side scan for a missing memory must surface as exit 5 (NotFoundError),
    matching the documented agent contract — not exit 1 (UsageError)."""
    respx_mock.get("/v1/dev/user/memories").respond(json=[])
    result = cli_runner.invoke(app, ["memory", "get", "does-not-exist"])
    assert result.exit_code == 5  # EXIT_NOT_FOUND
    assert "not found" in result.stderr.lower()


def test_memory_get_found_in_later_page(authed_profile, respx_mock, cli_runner) -> None:
    """Confirm the paging loop still finds an item past the first page."""
    page1 = [
        {"id": f"m{i}", "content": "x", "category": "core", "visibility": "private", "tags": []} for i in range(100)
    ]
    page2 = [{"id": "target", "content": "found me", "category": "core", "visibility": "private", "tags": []}]
    import httpx

    respx_mock.get("/v1/dev/user/memories").mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
    )
    result = cli_runner.invoke(app, ["--json", "memory", "get", "target"])
    assert result.exit_code == 0


@pytest.mark.parametrize("command", [["memory", "list"], ["memory", "get", "m1"]])
def test_memory_pretty_preserves_markup_like_content(authed_profile, respx_mock, cli_runner, command) -> None:
    respx_mock.get("/v1/dev/user/memories").respond(
        json=[{"id": "m1", "content": "[draft] literal [/bold] :warning:", "tags": []}]
    )
    result = cli_runner.invoke(app, ["--no-color", *command])
    assert result.exit_code == 0, result.output
    assert "[draft] literal [/bold] :warning:" in result.stdout
