"""Tests for ``omi local``."""

from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path

import httpx
import pytest
import respx

from omi_cli import config as cfg
from omi_cli.errors import CliError, NotFoundError
from omi_cli.local_client import LocalOmiClient
from omi_cli.main import app
from omi_cli.output import Renderer

FAKE_LOCAL_URL = "http://127.0.0.1:47778"
FAKE_LOCAL_TOKEN = "local_test_token"


def _configure_local_profile(config_path: Path) -> None:
    config = cfg.load()
    profile = config.get_profile("default")
    profile.local_api_url = FAKE_LOCAL_URL
    profile.local_token = FAKE_LOCAL_TOKEN
    config.set_profile(profile)
    cfg.save(config)


def _tool_response(value):
    return {"ok": True, "name": "tool", "content_type": "text/plain", "result": json.dumps(value)}


def test_local_configure_persists_profile_config(config_path: Path, cli_runner) -> None:
    result = cli_runner.invoke(
        app,
        ["--json", "local", "configure", "--url", FAKE_LOCAL_URL + "/", "--token", FAKE_LOCAL_TOKEN],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["local_api_url"] == FAKE_LOCAL_URL
    assert payload["local_token"] != FAKE_LOCAL_TOKEN

    profile = cfg.load().get_profile("default")
    assert profile.local_api_url == FAKE_LOCAL_URL
    assert profile.local_token == FAKE_LOCAL_TOKEN


def test_local_configure_escapes_markup_like_profile_name(config_path: Path, cli_runner) -> None:
    """Rich markup in a profile name must be escaped in the configure message.

    `omi local configure` prints the profile name inside a Rich-markup
    message; a profile named 'bad[/bold]' would otherwise crash the render
    after the config had already been saved.
    """
    tricky = "bad[/bold]"
    result = cli_runner.invoke(
        app,
        [
            "--profile",
            tricky,
            "local",
            "configure",
            "--url",
            FAKE_LOCAL_URL,
            "--token",
            FAKE_LOCAL_TOKEN,
        ],
    )
    assert result.exit_code == 0, repr(result.exception)
    assert "bad[/bold]" in result.output
    assert cfg.load().get_profile(tricky).local_api_url == FAKE_LOCAL_URL


def test_local_status_without_config_is_json(config_path: Path, cli_runner) -> None:
    result = cli_runner.invoke(app, ["--json", "local", "status"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["configured"] is False
    assert payload["local_api_url"] is None
    assert payload["local_token"] == "(none)"


def test_local_status_calls_status_tool(config_path: Path, cli_runner) -> None:
    _configure_local_profile(config_path)
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        route = router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response({"ok": True})))
        result = cli_runner.invoke(app, ["--json", "local", "status"])

    assert result.exit_code == 0, result.output
    request = route.calls[0].request
    assert request.headers["Authorization"] == f"Bearer {FAKE_LOCAL_TOKEN}"
    body = json.loads(request.content)
    assert body == {"name": "get_local_status", "arguments": {}}
    assert json.loads(result.stdout)["desktop"] == {"ok": True}


def test_local_tools_lists_local_affordances(config_path: Path, cli_runner) -> None:
    _configure_local_profile(config_path)
    tools = [{"name": "search_screen_history"}, {"name": "get_screenshot"}]
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        route = router.get("/v1/local/tools").mock(return_value=httpx.Response(200, json={"ok": True, "tools": tools}))
        result = cli_runner.invoke(app, ["--json", "local", "tools"])

    assert result.exit_code == 0, result.output
    assert route.calls[0].request.headers["Authorization"] == f"Bearer {FAKE_LOCAL_TOKEN}"
    assert json.loads(result.stdout) == {"ok": True, "tools": tools}


def test_local_call_accepts_args_json(config_path: Path, cli_runner) -> None:
    _configure_local_profile(config_path)
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        route = router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response({"ok": True})))
        result = cli_runner.invoke(
            app,
            ["--json", "local", "call", "search_screen_history", "--args-json", '{"query":"deck","days":3}'],
        )

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == {
        "name": "search_screen_history",
        "arguments": {"query": "deck", "days": 3},
    }
    assert json.loads(result.stdout) == {"ok": True}


@pytest.mark.parametrize("json_mode", [False, True])
def test_local_call_preserves_fields_from_later_result_rows(config_path: Path, cli_runner, json_mode: bool) -> None:
    _configure_local_profile(config_path)
    rows = [{"id": "first"}, {"id": "second", "detail": "later-value"}]
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response(rows)))
        result = cli_runner.invoke(app, (["--json"] if json_mode else []) + ["local", "call", "test_tool"])

    assert result.exit_code == 0, result.output
    if json_mode:
        assert json.loads(result.stdout) == rows
    else:
        assert "detail" in result.stdout
        assert "later-value" in result.stdout


def test_local_call_exits_nonzero_when_api_reports_error(config_path: Path, cli_runner) -> None:
    _configure_local_profile(config_path)
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(
            return_value=httpx.Response(400, json={"ok": False, "error": "Error: task not found"})
        )
        result = cli_runner.invoke(
            app, ["--json", "local", "call", "complete_task", "--args-json", '{"task_id":"missing"}']
        )

    assert result.exit_code != 0


def test_local_client_preserves_api_error_detail(config_path: Path) -> None:
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(
            return_value=httpx.Response(400, json={"ok": False, "error": "Error: task not found"})
        )
        client = LocalOmiClient(api_url=FAKE_LOCAL_URL, token=FAKE_LOCAL_TOKEN)
        try:
            try:
                client.call_tool("complete_task", {"task_id": "missing"})
            except CliError as exc:
                assert "task not found" in str(exc)
            else:  # pragma: no cover
                raise AssertionError("expected CliError")
        finally:
            client.close()


def test_search_screen_routes_to_screen_history_tool(config_path: Path, cli_runner) -> None:
    _configure_local_profile(config_path)
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        route = router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response([{"id": 7}])))
        result = cli_runner.invoke(
            app,
            ["--json", "local", "search-screen", "pricing page", "--days", "14", "--app", "Safari"],
        )

    assert result.exit_code == 0, result.output
    body = json.loads(route.calls[0].request.content)
    assert body == {
        "name": "search_screen_history",
        "arguments": {"query": "pricing page", "days": 14, "limit": 15, "app_filter": "Safari"},
    }
    assert json.loads(result.stdout) == [{"id": 7}]


def test_search_screen_supports_limit_and_structures_text_results(config_path: Path, cli_runner) -> None:
    _configure_local_profile(config_path)
    response = """
Found 1 screenshot(s) matching "Discord":

1. [Jun 7, 2026 at 12:34 PM] Discord - #general (screenshot_id: 42, similarity: 0.87)
   Content: Status update preview
""".strip()
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        route = router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response(response)))
        result = cli_runner.invoke(app, ["--json", "local", "search-screen", "Discord", "--days", "30", "--limit", "3"])

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == {
        "name": "search_screen_history",
        "arguments": {"query": "Discord", "days": 30, "limit": 3},
    }
    payload = json.loads(result.stdout)
    assert payload["result_count"] == 1
    assert payload["results"][0]["screenshot_id"] == 42
    assert payload["results"][0]["ocr_preview"] == "Status update preview"


def test_search_screen_no_results_is_structured_in_json(config_path: Path, cli_runner) -> None:
    _configure_local_profile(config_path)
    response = (
        'No matching screen-history results for "Discord" in the last 1 day(s). Local history exists '
        "(10 screenshot(s), 10 indexed), so try a broader query."
    )
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        route = router.post("/v1/local/tool").mock(
            side_effect=[
                httpx.Response(200, json=_tool_response(response)),
                httpx.Response(
                    200,
                    json=_tool_response(
                        "screenshot_id | timestamp | app_name | is_indexed\n"
                        "--------------------------------------------------------------------------------\n"
                        "42 | 2026-06-07T12:34:00Z | Discord | 1\n\n"
                        "1 row(s)"
                    ),
                ),
            ]
        )
        result = cli_runner.invoke(app, ["--json", "local", "search-screen", "Discord", "--days", "1"])

    assert result.exit_code == 0, result.output
    bodies = [json.loads(call.request.content) for call in route.calls]
    assert bodies[0] == {
        "name": "search_screen_history",
        "arguments": {"query": "Discord", "days": 1, "limit": 15},
    }
    assert bodies[1]["name"] == "execute_sql"
    assert "appName LIKE '%Discord%'" in bodies[1]["arguments"]["query"]
    payload = json.loads(result.stdout)
    assert payload["results"] == []
    assert payload["query"] == "Discord"
    assert payload["days"] == 1
    assert payload["suggestions"]
    assert payload["exact_fallback"]["result"]["rows"][0]["screenshot_id"] == "42"
    assert payload["suggested_screenshot_ids"] == ["42"]


def test_search_screen_exact_fallback_constrains_app_filter(config_path: Path, cli_runner) -> None:
    _configure_local_profile(config_path)
    response = 'No matching screen-history results for "Discord" in the last 1 day(s) with app filter "Discord".'
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        route = router.post("/v1/local/tool").mock(
            side_effect=[
                httpx.Response(200, json=_tool_response(response)),
                httpx.Response(200, json=_tool_response("No results")),
            ]
        )
        result = cli_runner.invoke(app, ["--json", "local", "search-screen", "Discord", "--app", "Discord"])

    assert result.exit_code == 0, result.output
    fallback_query = json.loads(route.calls[1].request.content)["arguments"]["query"]
    assert "WHERE (appName LIKE '%Discord%' ESCAPE '!') AND" in fallback_query


@pytest.mark.parametrize("literal,decoy", [("50%", "500"), ("a_b", "axb"), ("a!b", "ab"), ("it's", "its")])
@pytest.mark.parametrize("field", ["appName", "windowTitle", "ocrText", "app_filter"])
def test_search_screen_fallback_matches_literal_text(
    config_path: Path, cli_runner, literal: str, decoy: str, field: str
) -> None:
    _configure_local_profile(config_path)
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute(
            "CREATE TABLE screenshots (id INTEGER, timestamp TEXT, appName TEXT, windowTitle TEXT, ocrText TEXT, isIndexed INTEGER)"
        )
        for row_id, value in enumerate((literal, decoy), start=1):
            values = {"appName": "Browser", "windowTitle": "notes", "ocrText": "notes"}
            values["appName" if field == "app_filter" else field] = value
            db.execute(
                "INSERT INTO screenshots VALUES (?, ?, ?, ?, ?, ?)",
                (row_id, "2026-09-07T00:00:00Z", values["appName"], values["windowTitle"], values["ocrText"], 1),
            )

        def respond(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            if body["name"] == "search_screen_history":
                return httpx.Response(200, json=_tool_response("No matching screen-history results"))
            assert body["name"] == "execute_sql"
            rows = [dict(row) for row in db.execute(body["arguments"]["query"])]
            return httpx.Response(200, json=_tool_response({"rows": rows}))

        args = ["--json", "local", "search-screen", "notes" if field == "app_filter" else literal]
        if field == "app_filter":
            args.extend(["--app", literal])
        with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
            router.post("/v1/local/tool").mock(side_effect=respond)
            result = cli_runner.invoke(app, args)
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["suggested_screenshot_ids"] == [1]


def test_sql_routes_to_execute_sql_with_env_overrides(config_path: Path, cli_runner, monkeypatch) -> None:
    _configure_local_profile(config_path)
    monkeypatch.setenv(cfg.ENV_LOCAL_API_URL, "http://127.0.0.1:48888")
    monkeypatch.setenv(cfg.ENV_LOCAL_TOKEN, "env_local_token")

    with respx.mock(base_url="http://127.0.0.1:48888", assert_all_called=True) as router:
        route = router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response({"rows": []})))
        result = cli_runner.invoke(app, ["--json", "local", "sql", "SELECT 1"])

    assert result.exit_code == 0, result.output
    assert route.calls[0].request.headers["Authorization"] == "Bearer env_local_token"
    body = json.loads(route.calls[0].request.content)
    assert body == {"name": "execute_sql", "arguments": {"query": "SELECT 1"}}


def test_sql_json_structures_table_text(config_path: Path, cli_runner) -> None:
    _configure_local_profile(config_path)
    sql_text = "screenshots | appName\n----------------------------------------\n12 | Discord\n\n1 row(s)"
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response(sql_text)))
        result = cli_runner.invoke(app, ["--json", "local", "sql", "SELECT 1"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == {
        "columns": ["screenshots", "appName"],
        "rows": [{"screenshots": "12", "appName": "Discord"}],
        "row_count": 1,
    }


def test_sql_json_structures_single_column_table_text(config_path: Path, cli_runner) -> None:
    _configure_local_profile(config_path)
    sql_text = "screenshots\n--------------------\n12\n\n1 row(s)"
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response(sql_text)))
        result = cli_runner.invoke(app, ["--json", "local", "sql", "SELECT COUNT(*) AS screenshots FROM screenshots"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == {
        "columns": ["screenshots"],
        "rows": [{"screenshots": "12"}],
        "row_count": 1,
    }


def test_sql_json_falls_back_to_raw_text_when_cells_contain_pipes_or_newlines(config_path: Path, cli_runner) -> None:
    _configure_local_profile(config_path)
    # Cell with pipe delimiter in single column output
    sql_text_pipe = "value\n-----\na|b\n\n1 row(s)"
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response(sql_text_pipe)))
        result = cli_runner.invoke(app, ["--json", "local", "sql", "SELECT 'a|b' AS value"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"text": sql_text_pipe}

    # Multiline cell resulting in row count mismatch
    sql_text_newline = "value\n-----\na\nb\n\n1 row(s)"
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response(sql_text_newline)))
        result_nl = cli_runner.invoke(app, ["--json", "local", "sql", "SELECT 'a' || char(10) || 'b' AS value"])

    assert result_nl.exit_code == 0, result_nl.output
    assert json.loads(result_nl.stdout) == {"text": sql_text_newline}

    # Multiline cell containing an empty continuation line
    sql_text_empty_cont = "value\n-----\na\n\nb\n\n2 row(s)"
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response(sql_text_empty_cont)))
        result_empty_cont = cli_runner.invoke(
            app, ["--json", "local", "sql", "SELECT 'a' || char(10) || char(10) || 'b' AS value"]
        )

    assert result_empty_cont.exit_code == 0, result_empty_cont.output
    assert json.loads(result_empty_cont.stdout) == {"text": sql_text_empty_cont}


@pytest.mark.parametrize(
    "table",
    [
        "preview\n--------------------\nleft | right\n\n1 row(s)",
        "preview\n--------------------\nline one\nline two\n\n1 row(s)",
        "preview\n--------------------\n\n\n1 row(s)",
        "x | x\n--------------------\na | b\n\n1 row(s)",
        "x\n--------------------\na\nResult truncated after 1 row(s) to protect chat context. Refine the projection or aggregate the result.\n\n2 row(s)",
    ],
)
def test_sql_json_preserves_ambiguous_or_truncated_tables(config_path: Path, cli_runner, table: str) -> None:
    _configure_local_profile(config_path)
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response(table)))
        result = cli_runner.invoke(app, ["--json", "local", "sql", "SELECT 1"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"text": table}


def test_sql_json_keeps_unambiguous_tables_structured(config_path: Path, cli_runner) -> None:
    _configure_local_profile(config_path)
    table = "id | name\n--------------------\n1 | café\n\n1 row(s)"
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response(table)))
        result = cli_runner.invoke(app, ["--json", "local", "sql", "SELECT 1"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {
        "columns": ["id", "name"],
        "rows": [{"id": "1", "name": "café"}],
        "row_count": 1,
    }


def test_sql_json_keeps_cell_that_only_starts_like_truncation_notice(config_path: Path, cli_runner) -> None:
    _configure_local_profile(config_path)
    table = "preview\n--------------------\nResult truncated after lunch\n\n1 row(s)"
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response(table)))
        result = cli_runner.invoke(app, ["--json", "local", "sql", "SELECT 1"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {
        "columns": ["preview"],
        "rows": [{"preview": "Result truncated after lunch"}],
        "row_count": 1,
    }


def test_task_commands_route_to_local_tools(config_path: Path, cli_runner) -> None:
    _configure_local_profile(config_path)
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        route = router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response({"ok": True})))
        search = cli_runner.invoke(app, ["--json", "local", "task", "search", "taxes", "--include-completed"])
        complete = cli_runner.invoke(app, ["--json", "local", "task", "complete", "task_1"])
        delete = cli_runner.invoke(app, ["--json", "local", "task", "delete", "task_1", "--yes"])

    assert search.exit_code == 0, search.output
    assert complete.exit_code == 0, complete.output
    assert delete.exit_code == 0, delete.output
    bodies = [json.loads(call.request.content) for call in route.calls]
    assert bodies == [
        {"name": "search_tasks", "arguments": {"query": "taxes", "include_completed": True}},
        {"name": "complete_task", "arguments": {"task_id": "task_1"}},
        {"name": "delete_task", "arguments": {"task_id": "task_1"}},
    ]


def test_recap_routes_to_daily_recap(config_path: Path, cli_runner) -> None:
    _configure_local_profile(config_path)
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        route = router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response("recap text")))
        result = cli_runner.invoke(app, ["--json", "local", "recap", "--days-ago", "1"])

    assert result.exit_code == 0, result.output
    assert json.loads(route.calls[0].request.content) == {
        "name": "get_daily_recap",
        "arguments": {"days_ago": 1},
    }
    assert json.loads(result.stdout) == "recap text"


def test_screenshot_writes_base64_output_and_keeps_json_stdout(config_path: Path, cli_runner, tmp_path: Path) -> None:
    _configure_local_profile(config_path)
    image_bytes = b"fake-image"
    response = {"image_base64": base64.b64encode(image_bytes).decode("ascii"), "screenshot_id": "9"}
    output = tmp_path / "shot.jpg"

    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        route = router.post("/v1/local/tool").mock(
            return_value=httpx.Response(200, json={"ok": True, "name": "get_screenshot", **response})
        )
        result = cli_runner.invoke(app, ["--json", "local", "screenshot", "9", "--output", str(output)])

    assert result.exit_code == 0, result.output
    assert output.read_bytes() == image_bytes
    assert json.loads(route.calls[0].request.content) == {
        "name": "get_screenshot",
        "arguments": {"screenshot_id": "9"},
    }
    payload = json.loads(result.stdout)
    assert payload["path"] == str(output)
    assert payload["bytes"] == len(image_bytes)
    assert payload["screenshot_id"] == "9"
    assert "image_base64" not in payload["result"]
    assert payload["result"]["image_base64_redacted"] is True


def test_screenshot_exports_long_text_response(config_path: Path, cli_runner, tmp_path: Path) -> None:
    """Text fallback must not fail merely because the text is too long for a filename."""
    _configure_local_profile(config_path)
    text = "Screenshot description " * 100
    output = tmp_path / "shot.txt"
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response(text)))
        result = cli_runner.invoke(app, ["--json", "local", "screenshot", "9", "--output", str(output)])

    assert result.exit_code == 0, repr(result.exception)
    assert output.read_text() == text
    assert json.loads(result.stdout)["bytes"] == len(text.encode())


def test_screenshot_copies_existing_file_response(config_path: Path, cli_runner, tmp_path: Path) -> None:
    _configure_local_profile(config_path)
    source = tmp_path / "source.jpg"
    source.write_bytes(b"synthetic-image")
    output = tmp_path / "copy.jpg"
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response(str(source))))
        result = cli_runner.invoke(app, ["--json", "local", "screenshot", "9", "--output", str(output)])

    assert result.exit_code == 0, repr(result.exception)
    assert output.read_bytes() == source.read_bytes()


def test_screenshot_same_source_and_output_is_noop(config_path: Path, cli_runner, tmp_path: Path) -> None:
    """Writing a screenshot onto its own source path must not raise SameFileError."""
    _configure_local_profile(config_path)
    source = tmp_path / "shot.jpg"
    source.write_bytes(b"synthetic-image")
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response(str(source))))
        result = cli_runner.invoke(app, ["--json", "local", "screenshot", "9", "--output", str(source)])

    assert result.exit_code == 0, repr(result.exception)
    assert source.read_bytes() == b"synthetic-image"
    assert json.loads(result.stdout)["bytes"] == len(b"synthetic-image")


def test_screenshot_same_source_and_output_is_noop_mapping_path(config_path: Path, cli_runner, tmp_path: Path) -> None:
    """Same-file no-op must also hold for the mapping-with-path response shape."""
    _configure_local_profile(config_path)
    source = tmp_path / "shot.jpg"
    source.write_bytes(b"synthetic-image")
    # The Desktop tool may return a structured mapping (path/file_path/...)
    # rather than a bare path string; the API envelope's result field is then
    # an object, not a JSON-encoded string.
    response = {"ok": True, "name": "tool", "content_type": "text/plain", "result": {"path": str(source)}}
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=response))
        result = cli_runner.invoke(app, ["--json", "local", "screenshot", "9", "--output", str(source)])

    assert result.exit_code == 0, repr(result.exception)
    assert source.read_bytes() == b"synthetic-image"
    assert json.loads(result.stdout)["bytes"] == len(b"synthetic-image")


def test_screenshot_hard_link_output_is_noop(config_path: Path, cli_runner, tmp_path: Path) -> None:
    """Writing a screenshot to a hard link of its source must not raise SameFileError."""
    _configure_local_profile(config_path)
    import os

    source = tmp_path / "shot.jpg"
    source.write_bytes(b"synthetic-image")
    link = tmp_path / "shot-link.jpg"
    os.link(source, link)
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=_tool_response(str(source))))
        result = cli_runner.invoke(app, ["--json", "local", "screenshot", "9", "--output", str(link)])

    assert result.exit_code == 0, repr(result.exception)
    assert link.read_bytes() == b"synthetic-image"
    assert json.loads(result.stdout)["bytes"] == len(b"synthetic-image")


def test_screenshot_preserves_structured_local_api_error_in_json(config_path: Path, cli_runner, tmp_path: Path) -> None:
    _configure_local_profile(config_path)
    output = tmp_path / "pending.jpg"
    error_payload = {
        "ok": False,
        "error": "screenshot_pending",
        "reason": "The frame is in the active recording segment that has not been flushed to disk yet.",
        "hint": "Retry in ~60s, or choose an older screenshot_id whose video chunk is already finalized.",
        "screenshot_id": 123,
    }

    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(422, json=error_payload))
        result = cli_runner.invoke(
            app,
            ["--json", "local", "screenshot", "123", "--output", str(output)],
            standalone_mode=False,
        )

    assert result.exit_code != 0
    assert not output.exists()
    assert isinstance(result.exception, CliError)
    payload = result.exception.extra
    assert payload["status_code"] == 422
    assert payload["ok"] is False
    assert payload["error"] == "screenshot_pending"
    assert payload["reason"] == error_payload["reason"]
    assert payload["hint"] == error_payload["hint"]
    assert payload["screenshot_id"] == 123


def test_non_json_error_escapes_structured_extra_markup(capsys: pytest.CaptureFixture[str]) -> None:
    Renderer(json_mode=False).error(
        "Local Omi Desktop API error (422)",
        extra={"hint": "Use [safe] text", "[danger]": "<value>"},
    )

    captured = capsys.readouterr()
    assert "hint: Use [safe] text" in captured.err
    assert "[danger]: <value>" in captured.err


def test_unwrap_tool_response_raises_on_embedded_failure(config_path: Path) -> None:
    """A structured Desktop failure inside the result JSON must raise, not pass through."""
    from omi_cli.errors import CliError
    from omi_cli.local_client import _unwrap_tool_response

    failure = {
        "ok": False,
        "database_available": False,
        "screen_history_available": False,
        "message": "Failed to read local Omi status: test",
    }
    envelope = {
        "ok": True,
        "name": "get_local_status",
        "content_type": "text/plain",
        "result": json.dumps(failure),
    }
    with pytest.raises(CliError) as excinfo:
        _unwrap_tool_response(envelope)
    assert "Failed to read local Omi status" in str(excinfo.value)
    assert excinfo.value.exit_code == 1


def test_unwrap_tool_response_passes_healthy_result(config_path: Path) -> None:
    """A healthy embedded result must still unwrap to its parsed value."""
    from omi_cli.local_client import _unwrap_tool_response

    envelope = {
        "ok": True,
        "name": "get_local_status",
        "content_type": "text/plain",
        "result": json.dumps({"ok": True, "database_available": True, "screen_history_available": True}),
    }
    result = _unwrap_tool_response(envelope)
    assert isinstance(result, dict)
    assert result["ok"] is True
    assert result["database_available"] is True


def test_unwrap_tool_response_extracts_message_from_structured_error(config_path: Path) -> None:
    """A structured error object must surface its message, not the whole mapping."""
    from omi_cli.errors import CliError
    from omi_cli.local_client import _unwrap_tool_response

    failure = {
        "ok": False,
        "error": {"message": "Desktop backend unavailable", "code": "ERR_DESKTOP_DOWN"},
    }
    envelope = {
        "ok": True,
        "name": "get_local_status",
        "content_type": "text/plain",
        "result": json.dumps(failure),
    }
    with pytest.raises(CliError) as excinfo:
        _unwrap_tool_response(envelope)
    # The human message is the extracted error.message, not the whole mapping.
    assert "Desktop backend unavailable" in excinfo.value.message
    assert not excinfo.value.message.startswith("{")


def test_local_api_error_preserves_not_found_subclass(config_path: Path) -> None:
    _configure_local_profile(config_path)
    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(
            return_value=httpx.Response(
                404,
                json={"ok": False, "error": "screenshot_not_found", "screenshot_id": "missing"},
            )
        )
        with LocalOmiClient(api_url=FAKE_LOCAL_URL, token=FAKE_LOCAL_TOKEN) as client:
            with pytest.raises(NotFoundError) as exc_info:
                client.call_tool("get_screenshot", {"screenshot_id": "missing"})

    assert exc_info.value.extra["status_code"] == 404
    assert exc_info.value.extra["error"] == "screenshot_not_found"
    assert exc_info.value.extra["screenshot_id"] == "missing"


def test_main_json_screenshot_error_preserves_structured_stderr(
    config_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    _configure_local_profile(config_path)
    output = tmp_path / "pending.jpg"
    error_payload = {
        "ok": False,
        "error": "screenshot_pending",
        "reason": "The frame is in the active recording segment that has not been flushed to disk yet.",
        "hint": "Retry in ~60s, or choose an older screenshot_id whose video chunk is already finalized.",
        "screenshot_id": 123,
    }

    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(422, json=error_payload))
        monkeypatch.setattr(
            "sys.argv",
            ["omi", "--json", "local", "screenshot", "123", "--output", str(output)],
        )
        from omi_cli.main import main

        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code != 0
    assert not output.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    payload = json.loads(captured.err)
    assert payload["status_code"] == 422
    assert payload["ok"] is False
    assert payload["error"] == "screenshot_pending"
    assert payload["reason"] == error_payload["reason"]
    assert payload["hint"] == error_payload["hint"]
    assert payload["screenshot_id"] == 123


def test_screenshot_non_json_local_api_error_has_status_code(config_path: Path, cli_runner, tmp_path: Path) -> None:
    _configure_local_profile(config_path)
    output = tmp_path / "failed.jpg"

    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(500, text="plain failure"))
        result = cli_runner.invoke(
            app,
            ["--json", "local", "screenshot", "123", "--output", str(output)],
            standalone_mode=False,
        )

    assert result.exit_code != 0
    assert not output.exists()
    assert isinstance(result.exception, CliError)
    payload = result.exception.extra
    assert result.exception.message == "Local Omi Desktop API error (500)"
    assert result.exception.detail == "plain failure"
    assert payload["status_code"] == 500
