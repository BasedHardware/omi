"""SQL column labels must not override the structure of a successful table."""

import json

import pytest
import respx

from omi_cli.main import app
from tests.test_local import FAKE_LOCAL_URL, _configure_local_profile, _tool_response


@pytest.mark.parametrize("heading", ["SQL Error: count", "OK: count", "Error: count"])
def test_sql_status_like_heading_keeps_rows(config_path, cli_runner, heading):
    _configure_local_profile(config_path)
    table = f"{heading} | total\n----------------------------------------\n1 | 2\n\n1 row(s)"
    with respx.mock(base_url=FAKE_LOCAL_URL) as router:
        route = router.post("/v1/local/tool").respond(json=_tool_response(table))
        result = cli_runner.invoke(app, ["--json", "local", "sql", f"SELECT 1 AS '{heading}', 2 AS total"])
    assert result.exit_code == 0, result.output
    assert route.call_count == 1
    assert json.loads(result.stdout) == {
        "columns": [heading, "total"],
        "rows": [{heading: "1", "total": "2"}],
        "row_count": 1,
    }


@pytest.mark.parametrize(
    "text,expected",
    [
        ("OK: updated 2 rows", {"ok": True, "message": "OK: updated 2 rows"}),
        ("Error: query refused", {"error": "Error: query refused"}),
        ("SQL Error: query failed\nTry another query.", {"error": "SQL Error: query failed\nTry another query."}),
    ],
)
def test_sql_non_table_status_is_preserved(config_path, cli_runner, text, expected):
    _configure_local_profile(config_path)
    with respx.mock(base_url=FAKE_LOCAL_URL) as router:
        router.post("/v1/local/tool").respond(json=_tool_response(text))
        result = cli_runner.invoke(app, ["--json", "local", "sql", "SELECT 1"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == expected
