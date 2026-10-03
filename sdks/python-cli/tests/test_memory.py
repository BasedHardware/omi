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


def test_memory_export_json_stdout(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/memories").respond(
        json=[{"id": "m1", "content": "Export me", "category": "work", "visibility": "private", "tags": ["python"]}]
    )
    result = cli_runner.invoke(app, ["memory", "export", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["id"] == "m1"


def test_memory_export_csv_to_file(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    respx_mock.get("/v1/dev/user/memories").respond(
        json=[{"id": "m1", "content": "CSV export", "category": "work", "visibility": "private", "tags": ["tag1"]}]
    )
    out_file = tmp_path / "export.csv"
    result = cli_runner.invoke(app, ["memory", "export", "--format", "csv", "--output", str(out_file)])
    assert result.exit_code == 0
    assert out_file.exists()
    content = out_file.read_text(encoding="utf-8")
    # Verify UTF-8 BOM prefix
    assert content.startswith("\ufeff")
    assert "id,category,visibility,content,tags" in content
    assert "m1,work,private,CSV export,tag1" in content


def test_memory_export_csv_formula_injection_guard(authed_profile, respx_mock, cli_runner, tmp_path) -> None:
    respx_mock.get("/v1/dev/user/memories").respond(
        json=[
            {
                "id": "m1",
                "content": "=1+1",
                "category": "+work",
                "visibility": "-private",
                "tags": ["@tag"],
            }
        ]
    )
    out_file = tmp_path / "export_formula.csv"
    result = cli_runner.invoke(app, ["memory", "export", "--format", "csv", "--output", str(out_file)])
    assert result.exit_code == 0
    content = out_file.read_text(encoding="utf-8")
    assert "'=1+1" in content
    assert "'+work" in content
    assert "'-private" in content
    assert "'@tag" in content


def test_memory_export_pagination_scans_past_short_page(authed_profile, respx_mock, cli_runner) -> None:
    """A short non-final page must not stop export early; scan until an empty page."""
    import httpx

    page1 = [{"id": f"m{i}", "content": "x", "category": "work"} for i in range(50)]
    page2 = [{"id": "target", "content": "later page", "category": "work"}]
    page3 = []

    route = respx_mock.get("/v1/dev/user/memories").mock(
        side_effect=[httpx.Response(200, json=page1), httpx.Response(200, json=page2), httpx.Response(200, json=page3)]
    )

    result = cli_runner.invoke(app, ["memory", "export", "--format", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 51
    assert payload[-1]["id"] == "target"
    assert len(route.calls) == 3


def test_memory_export_passes_categories_param(authed_profile, respx_mock, cli_runner) -> None:
    route = respx_mock.get("/v1/dev/user/memories").respond(
        json=[{"id": "m1", "content": "filtered", "category": "work"}]
    )
    result = cli_runner.invoke(app, ["memory", "export", "--categories", "work,skills"])
    assert result.exit_code == 0
    assert route.calls.last.request.url.params["categories"] == "work,skills"


def test_memory_export_markdown_stdout(authed_profile, respx_mock, cli_runner) -> None:
    respx_mock.get("/v1/dev/user/memories").respond(
        json=[{"id": "m1", "content": "Markdown export", "category": "skills", "visibility": "public", "tags": []}]
    )
    result = cli_runner.invoke(app, ["memory", "export", "-f", "markdown"])
    assert result.exit_code == 0
    assert "type: omi-memories" in result.stdout
    assert "### Memory `m1`" in result.stdout
    assert "Markdown export" in result.stdout
