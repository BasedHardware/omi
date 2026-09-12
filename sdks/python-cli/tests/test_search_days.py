import json

import httpx
import pytest
import respx

from omi_cli.main import app
from tests.test_local import FAKE_LOCAL_URL, _configure_local_profile, _tool_response


@pytest.mark.parametrize("days", [1, 7, 30])
@pytest.mark.parametrize("app_filter", [None, "Browser"])
def test_exact_search_sql_honors_days_window(config_path, cli_runner, days, app_filter) -> None:
    _configure_local_profile(config_path)
    empty = 'No matching screen-history results for "needle".'
    table = (
        "screenshot_id | timestamp | app_name | is_indexed\n"
        "--------------------------------------------------------------------------------\n"
        "42 | 2026-09-12T00:00:00Z | Browser | 1\n\n"
        "1 row(s)"
    )
    args = ["--json", "local", "search-screen", "needle", "--days", str(days)]
    if app_filter:
        args += ["--app", app_filter]
    with respx.mock(base_url=FAKE_LOCAL_URL) as router:
        route = router.post("/v1/local/tool").mock(
            side_effect=[
                httpx.Response(200, json=_tool_response(empty)),
                httpx.Response(200, json=_tool_response(table)),
            ]
        )
        result = cli_runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    sql = json.loads(route.calls[1].request.content)["arguments"]["query"]
    assert f"timestamp >= datetime('now', '-{days} days')" in sql
    if app_filter:
        assert "AND (" in sql or ") AND" in sql
    else:
        assert sql.count("(") >= 1
    assert json.loads(result.stdout)["suggested_screenshot_ids"] == ["42"]
