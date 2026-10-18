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


def test_memory_get_continues_after_short_filtered_page(authed_profile, respx_mock, cli_runner) -> None:
    """A malformed record filtered by the API must not hide later memories."""
    page1 = [
        {"id": f"m{i}", "content": "x", "category": "core", "visibility": "private", "tags": []} for i in range(99)
    ]
    page2 = [{"id": "target", "content": "found me", "category": "core", "visibility": "private", "tags": []}]
    import httpx

    route = respx_mock.get("/v1/dev/user/memories").mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2)]
    )
    result = cli_runner.invoke(app, ["--json", "memory", "get", "target"])
    assert result.exit_code == 0, result.output
    assert len(route.calls) == 2
    assert route.calls[1].request.url.params["offset"] == "100"


@pytest.mark.parametrize("command", [["memory", "list"], ["memory", "get", "m1"]])
def test_memory_pretty_preserves_markup_like_content(authed_profile, respx_mock, cli_runner, command) -> None:
    respx_mock.get("/v1/dev/user/memories").respond(
        json=[{"id": "m1", "content": "[draft] literal [/bold] :warning:", "tags": []}]
    )
    result = cli_runner.invoke(app, ["--no-color", *command])
    assert result.exit_code == 0, result.output
    assert "[draft] literal [/bold] :warning:" in result.stdout


@pytest.mark.parametrize("content", ["", "   ", "\t\n"])
def test_memory_create_rejects_blank_content_before_network(authed_profile, respx_mock, cli_runner, content) -> None:
    result = cli_runner.invoke(app, ["--json", "memory", "create", content])
    assert result.exit_code == 1
    assert "content cannot be empty" in result.stderr.lower()
    assert len(respx_mock.calls) == 0


@pytest.mark.parametrize("content", ["", "  "])
def test_memory_update_rejects_blank_content_before_network(authed_profile, respx_mock, cli_runner, content) -> None:
    result = cli_runner.invoke(app, ["--json", "memory", "update", "m1", "--content", content])
    assert result.exit_code == 1
    assert "content cannot be empty" in result.stderr.lower()
    assert len(respx_mock.calls) == 0


@pytest.mark.parametrize(
    "invoke_args",
    [
        ["memory", "create"],
        ["memory", "update", "m1", "--content"],
    ],
)
def test_memory_rejects_raw_content_over_500_chars(authed_profile, respx_mock, cli_runner, invoke_args) -> None:
    """The raw string is what the backend caps at 500, so trailing whitespace cannot smuggle it past the CLI."""
    oversized = ("a" * 500) + "   "
    result = cli_runner.invoke(app, ["--json", *invoke_args, oversized])
    assert result.exit_code == 1
    assert "at most 500 characters" in result.stderr.lower()
    assert "503" in result.stderr
    assert len(respx_mock.calls) == 0


def test_memory_create_accepts_500_char_boundary(authed_profile, respx_mock, cli_runner) -> None:
    boundary = "a" * 500
    route = respx_mock.post("/v1/dev/user/memories").respond(json={"id": "m1", "content": boundary, "tags": []})
    result = cli_runner.invoke(app, ["--json", "memory", "create", boundary])
    assert result.exit_code == 0, result.output
    body = json.loads(route.calls.last.request.content)
    assert body["content"] == boundary


def test_memory_create_strips_content_and_tags_before_post(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.post("/v1/dev/user/memories").respond(json={"id": "m1", "content": "trimmed", "tags": ["work"]})
    result = cli_runner.invoke(app, ["--json", "memory", "create", "  trimmed  ", "--tag", "  work  "])
    assert result.exit_code == 0, result.output
    body = json.loads(route.calls.last.request.content)
    assert body["content"] == "trimmed"
    assert body["tags"] == ["work"]


def test_memory_update_strips_content_and_tags_before_patch(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.patch("/v1/dev/user/memories/m1").respond(json={"id": "m1", "content": "new", "tags": ["x"]})
    result = cli_runner.invoke(app, ["--json", "memory", "update", "m1", "--content", "  new  ", "--tag", "  x  "])
    assert result.exit_code == 0, result.output
    body = json.loads(route.calls.last.request.content)
    assert body == {"content": "new", "tags": ["x"]}


@pytest.mark.parametrize(
    "invoke_args",
    [
        ["memory", "create", "ok", "--tag"],
        ["memory", "update", "m1", "--tag"],
    ],
)
def test_memory_rejects_blank_tags_before_network(authed_profile, respx_mock, cli_runner, invoke_args) -> None:
    result = cli_runner.invoke(app, ["--json", *invoke_args, "   "])
    assert result.exit_code == 1
    assert "tags cannot be empty" in result.stderr.lower()
    assert len(respx_mock.calls) == 0
