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


def test_memory_export_success_multipage(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    page1 = [{"id": f"m{i}", "content": f"val{i}"} for i in range(100)]
    page2 = [{"id": "m100", "content": "val100"}]
    import httpx

    route = respx_mock.get("/v1/dev/user/memories").mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2), httpx.Response(200, json=[])]
    )
    out_file = tmp_path / "subdir" / "export.json"
    result = cli_runner.invoke(app, ["memory", "export", "-o", str(out_file)])
    assert result.exit_code == 0, result.output
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert len(data) == 101
    assert data[0]["id"] == "m0"
    assert data[-1]["id"] == "m100"
    assert len(route.calls) == 3
    assert route.calls[1].request.url.params["offset"] == "100"
    assert route.calls[2].request.url.params["offset"] == "200"


def test_memory_export_empty(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    respx_mock.get("/v1/dev/user/memories").respond(json=[])
    out_file = tmp_path / "empty_export.json"
    result = cli_runner.invoke(app, ["memory", "export", "-o", str(out_file)])
    assert result.exit_code == 0, result.output
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data == []


def test_memory_export_fail_fast_on_api_error(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    page1 = [{"id": f"m{i}", "content": f"val{i}"} for i in range(100)]
    import httpx
    from omi_cli.errors import ServerError

    # OmiClient retries GET 5xx up to 4 times (MAX_RETRY_ATTEMPTS).
    # We provide 4 responses to satisfy the retry loop, then the final error.
    respx_mock.get("/v1/dev/user/memories").mock(
        side_effect=[
            httpx.Response(200, json=page1), 
            httpx.Response(500, json={"error": "server error"}), 
            httpx.Response(500, json={"error": "server error"}), 
            httpx.Response(500, json={"error": "server error"}), 
            httpx.Response(500, json={"error": "server error"}), 
        ]
    )
    out_file = tmp_path / "failed_export.json"
    result = cli_runner.invoke(app, ["memory", "export", "-o", str(out_file)])
    assert result.exit_code == 3  # EXIT_SERVER
    # Crucial: verify that partial write did not leak to output path
    assert not out_file.exists()


def test_memory_export_api_none_at_offset(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    """Verify that a None response at offset > 0 triggers RuntimeError and prevents partial write."""
    page1 = [{"id": f"m{i}", "content": "val"} for i in range(100)]
    import httpx

    respx_mock.get("/v1/dev/user/memories").mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(204)]
    )
    out_file = tmp_path / "none_export.json"
    result = cli_runner.invoke(app, ["memory", "export", "-o", str(out_file)])
    assert result.exit_code != 0
    # RuntimeError is printed to stdout/stderr by Typer's exception handler
    # We check result.stdout/stderr or the exception itself if available
    assert "API returned None unexpectedly at offset 100" in str(result.exception) or \
           "API returned None unexpectedly at offset 100" in result.stdout or \
           "API returned None unexpectedly at offset 100" in result.stderr
    # Crucial: verify no file was left behind
    assert not out_file.exists()
