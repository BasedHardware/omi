import base64
import json

import pytest
import respx

from omi_cli.main import app
from tests.test_local import FAKE_LOCAL_URL, _configure_local_profile


@pytest.mark.parametrize("key", ["image_base64", "base64", "data_base64", "data"])
@pytest.mark.parametrize("write_file", [False, True])
def test_screenshot_alias_output(config_path, cli_runner, tmp_path, key, write_file) -> None:
    _configure_local_profile(config_path)
    encoded = base64.b64encode(b"synthetic pixels").decode()
    response = {key: encoded, "screenshot_id": "9"}
    output = tmp_path / "shot.jpg"
    args = ["--json", "local", "screenshot", "9"]
    if write_file:
        args += ["--output", str(output)]
    with respx.mock(base_url=FAKE_LOCAL_URL) as router:
        router.post("/v1/local/tool").respond(json={"ok": True, "name": "get_screenshot", **response})
        result = cli_runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    if write_file:
        assert output.read_bytes() == b"synthetic pixels"
        assert encoded not in result.stdout
        assert payload["result"][key + "_redacted"] is True
        assert payload["result"][key + "_chars"] == len(encoded)
        assert key not in payload["result"]
    else:
        assert payload[key] == encoded


@pytest.mark.parametrize("metadata", [None, "", 7, {"width": 100}, [1, 2]])
def test_screenshot_output_preserves_non_payload_data(config_path, cli_runner, tmp_path, metadata) -> None:
    _configure_local_profile(config_path)
    encoded = base64.b64encode(b"synthetic pixels").decode()
    output = tmp_path / "shot.jpg"
    with respx.mock(base_url=FAKE_LOCAL_URL) as router:
        router.post("/v1/local/tool").respond(json={"ok": True, "name": "get_screenshot", "image_base64": encoded, "data": metadata})
        result = cli_runner.invoke(app, ["--json", "local", "screenshot", "9", "--output", str(output)])
    assert result.exit_code == 0, result.output
    assert output.read_bytes() == b"synthetic pixels"
    payload = json.loads(result.stdout)["result"]
    assert payload["data"] == metadata
    assert "data_redacted" not in payload
    assert "image_base64" not in payload
