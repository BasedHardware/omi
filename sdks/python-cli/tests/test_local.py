"""Tests for ``omi local``."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import respx

from omi_cli import config as cfg
from omi_cli.errors import CliError
from omi_cli.local_client import LocalOmiClient
from omi_cli.main import app

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
        "arguments": {"query": "pricing page", "days": 14, "app_filter": "Safari"},
    }
    assert json.loads(result.stdout) == [{"id": 7}]


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
    assert payload["output"] == str(output)
    assert "image_base64" not in payload["result"]
    assert payload["result"]["image_base64_redacted"] is True
