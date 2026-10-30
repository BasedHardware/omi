"""Corrupt or truncated compressed responses must not hide unknown write outcomes or fail GET retries."""

from __future__ import annotations

import json
import sys
import time

import httpx
import pytest

from omi_cli.client import OmiClient
from omi_cli.errors import ServerError
from omi_cli.main import main


def _corrupt_gzip_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"Content-Encoding": "gzip"},
        stream=httpx.ByteStream(b"not a gzip body"),
    )


@pytest.mark.parametrize("method", ["post", "patch", "delete"])
def test_write_decoding_error_is_not_replayed(authed_profile, respx_mock, monkeypatch, method):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    applied = []

    def server(request):
        applied.append(request.method)
        return _corrupt_gzip_response(request)

    path = "/v1/dev/user/goals" if method != "delete" else "/v1/dev/user/goals/g1"
    respx_mock.route(method=method.upper(), path=path).mock(side_effect=server)

    with OmiClient(authed_profile) as client:
        with pytest.raises(ServerError, match="outcome unknown") as info:
            if method == "post":
                client.post(path, json_body={"title": "synthetic"})
            elif method == "patch":
                client.patch(path, json_body={"title": "synthetic"})
            else:
                client.delete(path)

    assert info.value.exit_code == 3
    assert f"{method.upper()} outcome unknown" in info.value.message
    assert "check the resource" in info.value.detail
    assert len(applied) == 1


def test_get_decoding_error_recovers_on_retry(authed_profile, respx_mock, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    route = respx_mock.get("/v1/dev/user/goals").mock(
        side_effect=[_corrupt_gzip_response, httpx.Response(200, json=[{"id": "g1"}])]
    )
    with OmiClient(authed_profile) as client:
        assert client.get("/v1/dev/user/goals") == [{"id": "g1"}]
    assert route.call_count == 2


def test_get_decoding_error_exhausts_retries(authed_profile, respx_mock, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    route = respx_mock.get("/v1/dev/user/goals").mock(side_effect=_corrupt_gzip_response)
    with OmiClient(authed_profile) as client:
        with pytest.raises(ServerError) as info:
            client.get("/v1/dev/user/goals")
    assert info.value.exit_code == 3
    assert route.call_count == 4


def test_goal_create_reports_unknown_write_on_decoding_error_json(authed_profile, respx_mock, monkeypatch, capsys):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    route = respx_mock.post("/v1/dev/user/goals").mock(side_effect=_corrupt_gzip_response)
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "goal", "create", "synthetic", "--target", "1"])
    with pytest.raises(SystemExit) as info:
        main()
    assert info.value.code == 3
    captured = capsys.readouterr()
    payload = json.loads(captured.err or captured.out)
    assert "outcome unknown" in str(payload)
    assert "check the resource" in str(payload)
    assert route.call_count == 1


def test_goal_create_reports_unknown_write_on_decoding_error_text(authed_profile, respx_mock, monkeypatch, capsys):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    route = respx_mock.post("/v1/dev/user/goals").mock(side_effect=_corrupt_gzip_response)
    monkeypatch.setattr(sys, "argv", ["omi", "goal", "create", "synthetic", "--target", "1"])
    with pytest.raises(SystemExit) as info:
        main()
    assert info.value.code == 3
    captured = capsys.readouterr()
    output = captured.err or captured.out
    assert "outcome unknown" in output
    assert "check the resource" in output
    assert route.call_count == 1
