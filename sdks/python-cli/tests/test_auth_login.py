"""Login verification uses the production client and preserves typed failures."""

from __future__ import annotations

import json
import sys
import time

import httpx
import pytest

from omi_cli import config as cfg
from omi_cli.client import MAX_RETRY_ATTEMPTS
from omi_cli.main import main
from tests.conftest import FAKE_API_BASE, FAKE_API_KEY


@pytest.fixture(params=["api_key", "browser"])
def login_args(request, config_path, monkeypatch) -> list[str]:
    if request.param == "api_key":
        return ["--api-key", FAKE_API_KEY]

    def fake_browser_login(profile_name, *, api_base, provider):
        # The browser/token exchange is external to this boundary; verification
        # still runs through the real OmiClient and HTTPX mock transport.
        return cfg.Profile(name=profile_name, api_base=api_base, auth_method="api_key", api_key=FAKE_API_KEY)

    monkeypatch.setattr("omi_cli.auth.oauth.login_with_browser", fake_browser_login)
    return ["--browser"]


def test_login_transport_failure_is_not_reported_as_success(login_args, respx_mock, monkeypatch, capsys) -> None:
    route = respx_mock.get("/v1/dev/user/memories").mock(
        side_effect=httpx.ConnectError("request failed at https://user:secret@example.invalid/?token=private-token")
    )
    monkeypatch.setattr(time, "sleep", lambda _: None)
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "--api-base", FAKE_API_BASE, "auth", "login", *login_args])

    with pytest.raises(SystemExit) as info:
        main()

    captured = capsys.readouterr()
    assert info.value.code == 3
    assert route.call_count == MAX_RETRY_ATTEMPTS
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "error": "Connection failed",
        "detail": "Could not reach the Omi API after multiple attempts. Check your connection and try again.",
    }
    assert "secret" not in captured.err
    assert "private-token" not in captured.err


def test_login_http_503_keeps_existing_warning_policy(login_args, respx_mock, monkeypatch, capsys) -> None:
    route = respx_mock.get("/v1/dev/user/memories").respond(503, json={"detail": "unavailable"})
    monkeypatch.setattr(time, "sleep", lambda _: None)
    monkeypatch.setattr(sys, "argv", ["omi", "--no-color", "--api-base", FAKE_API_BASE, "auth", "login", *login_args])

    main()

    captured = capsys.readouterr()
    assert route.call_count == MAX_RETRY_ATTEMPTS
    assert captured.out == ""
    assert "Could not verify" in captured.err
    assert "It is stored" in captured.err
    assert "Logged in" in captured.err
