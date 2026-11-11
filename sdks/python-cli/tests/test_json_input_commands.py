"""User-supplied JSON must be encodable before a command starts an API call."""

from __future__ import annotations

import json
import sys

import pytest

from omi_cli.local_client import LocalOmiClient
from omi_cli.main import app, main


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e400", "-1e400"])
@pytest.mark.parametrize("command", ["local", "conversation"])
@pytest.mark.parametrize("authenticated", [False, True])
def test_json_input_rejects_non_finite_numbers(
    number, command, authenticated, config_path, tmp_path, monkeypatch, respx_mock, capsys
) -> None:
    # Check both configured and fresh installs. Bad JSON should never be
    # mistaken for a credentials problem or reach the HTTP serializer.
    if authenticated:
        monkeypatch.setenv("OMI_API_KEY", "omi_dev_" + "x" * 32)
        monkeypatch.setenv("OMI_LOCAL_API_URL", "http://127.0.0.1:47778")
        monkeypatch.setenv("OMI_LOCAL_TOKEN", "synthetic-local-token")
    if command == "local":
        args = ["local", "call", "search_screen_history", "--args-json", '{"nested":[' + number + ']}']
        expected_error = "--args-json must be valid JSON"
    else:
        source = tmp_path / "segments.json"
        source.write_text('[{"text":"hello","start":0,"end":' + number + '}]', encoding="utf-8")
        args = ["conversation", "from-segments", str(source)]
        expected_error = f"Invalid JSON in {source}"

    monkeypatch.setattr(sys, "argv", ["omi", "--json", *args])
    with pytest.raises(SystemExit) as exit_info:
        main()
    captured = capsys.readouterr()
    assert exit_info.value.code == 1
    assert captured.out == ""
    error = json.loads(captured.err)
    assert error["error"] == expected_error
    assert "finite" in error["detail"]
    assert not respx_mock.calls


@pytest.mark.parametrize("command", ["local", "conversation"])
def test_json_input_preserves_finite_numbers_and_literal_strings(
    command, authed_profile, respx_mock, cli_runner, tmp_path, monkeypatch
) -> None:
    from omi_cli.main import AppContext

    value = {"text": "NaN Infinity -Infinity", "start": -1.5e2, "end": 1e300}
    if command == "local":
        # Use the actual command and HTTP serializer with a test-only client.
        monkeypatch.setattr(
            AppContext,
            "make_local_client",
            lambda self: LocalOmiClient(api_url=authed_profile.api_base, token="synthetic-local-token"),
        )
        route = respx_mock.post("/v1/local/tool").respond(json={"ok": True})
        args = ["local", "call", "test_tool", "--args-json", json.dumps(value)]
    else:
        source = tmp_path / "segments.json"
        source.write_text(json.dumps([value]), encoding="utf-8")
        route = respx_mock.post("/v1/dev/user/conversations/from-segments").respond(
            json={"id": "test-conversation", "status": "queued"}
        )
        args = ["conversation", "from-segments", str(source)]

    result = cli_runner.invoke(app, ["--json", *args])

    assert result.exit_code == 0, result.output
    body = json.loads(route.calls.last.request.content)
    assert (body["arguments"] if command == "local" else body["transcript_segments"][0]) == value
