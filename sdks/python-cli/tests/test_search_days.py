import json
import httpx
import sqlite3
from datetime import datetime, timedelta

import pytest
import respx

from omi_cli.main import app
from tests.test_local import FAKE_LOCAL_URL, _configure_local_profile, _tool_response


@pytest.mark.parametrize("days", [1, 7])
@pytest.mark.parametrize("app_filter", [None, "Browser"])
def test_exact_search_respects_days(config_path, cli_runner, days, app_filter):
    _configure_local_profile(config_path)
    now = datetime(2026, 9, 8, 12)
    db = sqlite3.connect(":memory:")
    db.create_function(
        "datetime", 2, lambda clock, modifier: (now + timedelta(days=int(modifier.split()[0]))).isoformat(" ")
    )
    db.execute("CREATE TABLE screenshots(id, timestamp, appName, windowTitle, ocrText, isIndexed)")
    cutoff = now - timedelta(days=days)
    rows = [("old", cutoff - timedelta(seconds=1)), ("boundary", cutoff), ("recent", now)]
    for id, stamp in rows:
        db.execute(
            "INSERT INTO screenshots VALUES(?,?,?,?,?,?)", (id, stamp.isoformat(" "), "Browser", "needle", "needle", 1)
        )

    def response(request):
        body = json.loads(request.content)
        if body["name"] == "search_screen_history":
            return httpx.Response(200, json=_tool_response('No matching screen-history results for "needle".'))
        result = db.execute(body["arguments"]["query"])
        columns = [d[0] for d in result.description]
        data = result.fetchall()
        table = (
            " | ".join(columns)
            + "\n--------------------\n"
            + "\n".join(" | ".join(map(str, row)) for row in data)
            + f"\n\n{len(data)} row(s)"
        )
        return httpx.Response(200, json=_tool_response(table))

    args = ["--json", "local", "search-screen", "needle", "--days", str(days)]
    if app_filter:
        args += ["--app", app_filter]
    try:
        with respx.mock(base_url=FAKE_LOCAL_URL) as router:
            router.post("/v1/local/tool").mock(side_effect=response)
            result = cli_runner.invoke(app, args)
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["suggested_screenshot_ids"] == ["recent", "boundary"]
    finally:
        db.close()
