from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from omi_cli.commands.local import _write_screenshot_result
from omi_cli.errors import UsageError
from omi_cli.main import app

from .test_local import FAKE_LOCAL_URL, _configure_local_profile, _tool_response


def test_write_screenshot_result_plain_string_utf8(tmp_path: Path):
    text = "Screenshot OCR: café 東京"
    output = tmp_path / "shot.txt"

    with patch("locale.getpreferredencoding", return_value="cp1252"):
        written = _write_screenshot_result(text, output)

    assert written == output
    assert output.read_text(encoding="utf-8") == text


def test_write_screenshot_result_mapping_content_utf8(tmp_path: Path):
    text = "Screenshot OCR: café 東京"
    data = {"content": text, "screenshot_id": "42"}
    output = tmp_path / "shot.txt"

    with patch("locale.getpreferredencoding", return_value="cp1252"):
        written = _write_screenshot_result(data, output)

    assert written == output
    assert output.read_text(encoding="utf-8") == text


def test_write_screenshot_result_fallback_json_utf8(tmp_path: Path):
    data = {"screenshot_id": "42", "label": "café 東京"}
    output = tmp_path / "shot.json"

    with patch("locale.getpreferredencoding", return_value="cp1252"):
        written = _write_screenshot_result(data, output)

    assert written == output
    assert json.loads(output.read_text(encoding="utf-8")) == data


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 2


@pytest.mark.parametrize(
    "encode",
    [
        lambda raw: base64.b64encode(raw).decode("ascii"),
        lambda raw: base64.encodebytes(raw).decode("ascii"),
        lambda raw: base64.b64encode(raw).decode("ascii") + "\n",
        lambda raw: "data:image/png;base64," + base64.encodebytes(raw).decode("ascii"),
    ],
    ids=["plain", "line-wrapped", "trailing-newline", "data-uri-wrapped"],
)
def test_screenshot_base64_survives_line_wrapping(tmp_path: Path, encode):
    """Line-wrapped base64 is ordinary output, not corruption.

    base64.encodebytes and most MIME encoders wrap at 76 columns, but
    b64decode(validate=True) rejects every character outside the alphabet,
    newlines included, so these payloads were refused as invalid.
    """
    output = tmp_path / "shot.png"

    written = _write_screenshot_result({"image_base64": encode(PNG_BYTES)}, output)

    assert written == output
    assert output.read_bytes() == PNG_BYTES


def test_screenshot_base64_still_rejects_real_corruption(tmp_path: Path):
    """Stripping whitespace must not loosen the check on anything else."""
    output = tmp_path / "shot.png"

    with pytest.raises(UsageError, match="valid base64"):
        _write_screenshot_result({"image_base64": "not base64 at all!!"}, output)


def test_screenshot_command_writes_line_wrapped_png(config_path: Path, cli_runner, tmp_path: Path):
    _configure_local_profile(config_path)
    output = tmp_path / "shot.png"
    response = {"image_base64": base64.encodebytes(PNG_BYTES).decode("ascii"), "screenshot_id": "9"}

    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(
            return_value=httpx.Response(200, json={"ok": True, "name": "get_screenshot", **response})
        )
        result = cli_runner.invoke(app, ["--json", "local", "screenshot", "9", "--output", str(output)])

    assert result.exit_code == 0, result.output
    assert output.read_bytes() == PNG_BYTES


def test_screenshot_command_writes_multilingual_content(config_path: Path, cli_runner, tmp_path: Path):
    _configure_local_profile(config_path)
    text = "Screenshot OCR: café 東京"
    response = {"content": text, "screenshot_id": "9"}
    output = tmp_path / "shot.txt"

    with respx.mock(base_url=FAKE_LOCAL_URL, assert_all_called=True) as router:
        router.post("/v1/local/tool").mock(
            return_value=httpx.Response(200, json={"ok": True, "name": "get_screenshot", **response})
        )
        with patch("locale.getpreferredencoding", return_value="cp1252"):
            result = cli_runner.invoke(app, ["--json", "local", "screenshot", "9", "--output", str(output)])

    assert result.exit_code == 0, result.output
    assert output.read_text(encoding="utf-8") == text
    payload = json.loads(result.stdout)
    assert payload["path"] == str(output)
    assert payload["screenshot_id"] == "9"
