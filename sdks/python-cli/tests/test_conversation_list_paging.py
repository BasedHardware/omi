import pytest
import respx
from httpx import Response
from typer.testing import CliRunner
from omi_cli.main import app

runner = CliRunner()

@respx.mock
def test_conversation_list_honours_limit_above_100():
    # Server clamps to 100 items per request
    page1 = [{"id": f"conv_{i}"} for i in range(100)]
    page2 = [{"id": f"conv_{i}"} for i in range(100, 150)]

    respx.get("https://api.omi.me/v1/dev/user/conversations").side_effect = [
        Response(200, json=page1),
        Response(200, json=page2),
    ]

    result = runner.invoke(app, ["conversation", "list", "--limit", "150", "--json"])
    assert result.exit_code == 0
    import json
    data = json.loads(result.stdout)
    assert len(data) == 150
