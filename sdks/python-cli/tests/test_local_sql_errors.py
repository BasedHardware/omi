"""The Desktop SQL failure response must remain a failure at the CLI boundary."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from omi_cli import config as cfg
from omi_cli.main import main

LOCAL_URL = "http://127.0.0.1:47778"
# ChatToolExecutor.executeSQL returns this string on a database error.
SQL_ERROR = "SQL Error: The local database could not complete that query."
SQL_COMMANDS = [
    ["local", "sql", "SELECT * FROM missing_table"],
    ["local", "call", "execute_sql", "--args-json", '{"query":"SELECT * FROM missing_table"}'],
]


@pytest.fixture
def local_profile(config_path):
    config = cfg.load()
    profile = config.get_profile("default")
    profile.local_api_url = LOCAL_URL
    profile.local_token = "synthetic_local_token"
    cfg.save(config)


@pytest.mark.parametrize("command", SQL_COMMANDS)
@pytest.mark.parametrize("json_mode", [False, True])
def test_local_sql_error_exits_nonzero(local_profile, monkeypatch, capsys, command, json_mode):
    monkeypatch.setattr("sys.argv", ["omi", *(["--json"] if json_mode else []), *command])
    # LocalAgentAPIServer currently wraps SQL errors in an HTTP 200 / ok:true
    # envelope because its HTTP error check recognizes only the "Error:" prefix.
    envelope = {"ok": True, "name": "execute_sql", "content_type": "text/plain", "result": SQL_ERROR}
    with respx.mock(base_url=LOCAL_URL, assert_all_called=True) as router:
        route = router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=envelope))
        with pytest.raises(SystemExit) as exc:
            main()

    assert exc.value.code == 1
    assert route.call_count == 1
    assert json.loads(route.calls[0].request.content)["name"] == "execute_sql"
    captured = capsys.readouterr()
    assert captured.out == ""
    if json_mode:
        assert json.loads(captured.err)["error"] == SQL_ERROR
    else:
        assert SQL_ERROR in captured.err


@pytest.mark.parametrize("command", SQL_COMMANDS)
@pytest.mark.parametrize("json_mode", [False, True])
def test_local_sql_empty_result_still_succeeds(local_profile, monkeypatch, capsys, command, json_mode):
    monkeypatch.setattr("sys.argv", ["omi", *(["--json"] if json_mode else []), *command])
    envelope = {"ok": True, "name": "execute_sql", "content_type": "text/plain", "result": "No results"}
    with respx.mock(base_url=LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=envelope))
        main()

    captured = capsys.readouterr()
    assert captured.err == ""
    if json_mode:
        result = json.loads(captured.out)
        assert result == ({"rows": [], "columns": [], "row_count": 0} if command[1] == "sql" else "No results")
    else:
        assert "No results" in captured.out


def test_other_tool_can_return_sql_error_text_as_data(local_profile, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["omi", "--json", "local", "call", "get_daily_recap"])
    envelope = {"ok": True, "name": "get_daily_recap", "content_type": "text/plain", "result": SQL_ERROR}
    with respx.mock(base_url=LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=envelope))
        main()

    captured = capsys.readouterr()
    assert json.loads(captured.out) == SQL_ERROR
    assert captured.err == ""


@pytest.mark.parametrize(
    "command,json_mode",
    [
        (["local", "sql", "SELECT 1 AS 'SQL Error: count'"], False),
        (["local", "call", "execute_sql", "--args-json", '{"query":"SELECT 1 AS \'SQL Error: count\'"}'], True),
    ],
)
def test_sql_error_column_heading_is_successful_data(local_profile, monkeypatch, capsys, command, json_mode):
    monkeypatch.setattr("sys.argv", ["omi", *(["--json"] if json_mode else []), *command])
    # SQLQueryResultProjection.format starts successful output with column names.
    table = "SQL Error: count\n--------------------\n1\n\n1 row(s)"
    envelope = {"ok": True, "name": "execute_sql", "content_type": "text/plain", "result": table}
    with respx.mock(base_url=LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(return_value=httpx.Response(200, json=envelope))
        main()

    captured = capsys.readouterr()
    assert (json.loads(captured.out) if json_mode else captured.out.rstrip()) == table
    assert captured.err == ""
