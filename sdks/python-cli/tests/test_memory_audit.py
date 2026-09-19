
import json
import httpx
from omi_cli.main import app
from typer.testing import CliRunner

def test_export_none_at_offset_0(authed_profile, respx_mock, cli_runner, tmp_path):
    # Mock API returning None instead of [] for empty user
    respx_mock.get("/v1/dev/user/memories").mock(side_effect=[httpx.Response(204)])
    out_file = tmp_path / "none_0.json"
    result = cli_runner.invoke(app, ["memory", "export", "-o", str(out_file)])
    assert result.exit_code == 0
    assert out_file.exists()
    assert json.loads(out_file.read_text()) == []

def test_export_short_pages(authed_profile, respx_mock, cli_runner, tmp_path):
    page1 = [{"id": f"m{i}"} for i in range(100)]
    page2 = [{"id": f"m{i}"} for i in range(100, 150)]
    page3 = [{"id": f"m{i}"} for i in range(150, 160)]
    
    respx_mock.get("/v1/dev/user/memories").mock(
        side_effect=[
            httpx.Response(200, json=page1),
            httpx.Response(200, json=page2),
            httpx.Response(200, json=page3),
            httpx.Response(200, json=[]),
        ]
    )
    out_file = tmp_path / "short_pages.json"
    result = cli_runner.invoke(app, ["memory", "export", "-o", str(out_file)])
    assert result.exit_code == 0
    data = json.loads(out_file.read_text())
    assert len(data) == 160
    assert data[0]["id"] == "m0"
    assert data[-1]["id"] == "m159"
