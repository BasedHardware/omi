"""Writes must not be replayed when the server may already have applied them."""
import json
import sys
import time

import httpx
import pytest

from omi_cli.client import OmiClient
from omi_cli.errors import ServerError
from omi_cli.main import main


@pytest.mark.parametrize("method", ["post", "patch"])
@pytest.mark.parametrize("failure", ["timeout", "server_error"])
def test_ambiguous_write_is_not_replayed(authed_profile, respx_mock, monkeypatch, method, failure):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    applied = []

    def server(request):
        applied.append(request.content)
        if failure == "timeout":
            raise httpx.ReadTimeout("synthetic lost response", request=request)
        return httpx.Response(500, json={"detail": "response failed after commit"})

    respx_mock.route(method=method.upper(), path="/v1/dev/user/goals").mock(side_effect=server)
    with OmiClient(authed_profile) as client:
        with pytest.raises(ServerError, match="outcome unknown"):
            getattr(client, method)("/v1/dev/user/goals", json_body={"title": "synthetic"})
    assert len(applied) == 1


@pytest.mark.parametrize("failure", [httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout])
def test_write_retries_before_submission(authed_profile, respx_mock, monkeypatch, failure):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    route = respx_mock.post("/v1/dev/user/goals").mock(
        side_effect=[failure("not submitted"), httpx.Response(201, json={"id": "g1"})]
    )
    with OmiClient(authed_profile) as client:
        assert client.post("/v1/dev/user/goals", json_body={"title": "synthetic"}) == {"id": "g1"}
    assert route.call_count == 2


def test_read_still_retries_after_timeout(authed_profile, respx_mock, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    route = respx_mock.get("/v1/dev/user/goals").mock(
        side_effect=[httpx.ReadTimeout("lost response"), httpx.Response(200, json=[])]
    )
    with OmiClient(authed_profile) as client:
        assert client.get("/v1/dev/user/goals") == []
    assert route.call_count == 2


def test_goal_create_reports_unknown_write_without_replay(authed_profile, respx_mock, monkeypatch, capsys):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    route = respx_mock.post("/v1/dev/user/goals").mock(side_effect=httpx.ReadTimeout("lost response"))
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "goal", "create", "synthetic", "--target", "1"])
    with pytest.raises(SystemExit) as info:
        main()
    assert info.value.code == 3
    captured = capsys.readouterr()
    payload = json.loads(captured.err or captured.out)
    assert "outcome unknown" in str(payload)
    assert "check the resource" in str(payload)
    assert route.call_count == 1
