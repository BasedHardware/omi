import json

import pytest
import respx

from omi_cli.main import app
from tests.test_local import FAKE_LOCAL_URL, _configure_local_profile, _tool_response


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
def test_ambiguous_table_preserves_raw_result(config_path, cli_runner, table):
    _configure_local_profile(config_path)
    with respx.mock(base_url=FAKE_LOCAL_URL) as router:
        router.post("/v1/local/tool").respond(json=_tool_response(table))
        result = cli_runner.invoke(app, ["--json", "local", "sql", "SELECT 1"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"text": table}


def test_unambiguous_table_still_normalizes(config_path, cli_runner):
    _configure_local_profile(config_path)
    with respx.mock(base_url=FAKE_LOCAL_URL) as router:
        router.post("/v1/local/tool").respond(
            json=_tool_response("id | name\n--------------------\n1 | café\n\n1 row(s)")
        )
        result = cli_runner.invoke(app, ["--json", "local", "sql", "SELECT 1"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "columns": ["id", "name"],
        "rows": [{"id": "1", "name": "café"}],
        "row_count": 1,
    }
