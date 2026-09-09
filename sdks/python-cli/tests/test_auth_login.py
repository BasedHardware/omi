"""Login verification uses the production client and preserves typed failures."""

from __future__ import annotations

import json
import sys
import time

import httpx
import pytest

from omi_cli import config as cfg
from omi_cli.auth.store import store_api_key
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
        return store_api_key(profile_name, FAKE_API_KEY, api_base=api_base)

    monkeypatch.setattr("omi_cli.auth.oauth.login_with_browser", fake_browser_login)
    return ["--browser"]


@pytest.mark.parametrize("json_mode", [False, True])
def test_login_transport_failure_is_not_reported_as_success(
    login_args, respx_mock, monkeypatch, capsys, json_mode
) -> None:
    previous_key = "omi_dev_" + ("y" * 32)
    store_api_key("default", previous_key, api_base=FAKE_API_BASE)
    route = respx_mock.get("/v1/dev/user/memories").mock(
        side_effect=httpx.ConnectError("request failed at https://user:secret@example.invalid/?token=private-token")
    )
    monkeypatch.setattr(time, "sleep", lambda _: None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "omi",
            "--no-color",
            *(["--json"] if json_mode else []),
            "--api-base",
            FAKE_API_BASE,
            "auth",
            "login",
            *login_args,
        ],
    )

    with pytest.raises(SystemExit) as info:
        main()

    captured = capsys.readouterr()
    assert info.value.code == 3
    assert route.call_count == MAX_RETRY_ATTEMPTS
    assert captured.out == ""
    expected_detail = "Could not reach the Omi API after multiple attempts. Check your connection and try again."
    if "--browser" in login_args:
        stored_detail = (
            "The new credential is stored but has not been verified. "
            "Run `omi auth whoami` to verify it when the API is reachable. "
            "Browser login created a developer API key; an earlier machine key may have been replaced."
        )
        if json_mode:
            assert json.loads(captured.err) == {
                "error": "Connection failed",
                "detail": f"{expected_detail} {stored_detail}",
                "credential_stored": True,
                "credential_verified": False,
            }
        else:
            assert "The new credential is stored but has not been verified." in captured.err
            assert "omi auth whoami" in captured.err
            assert "credential_stored" in captured.err
            assert "credential_verified" in captured.err
            assert "may have been replaced" in captured.err
        assert cfg.load().get_profile("default").api_key == FAKE_API_KEY
    else:
        if json_mode:
            assert json.loads(captured.err) == {"error": "Connection failed", "detail": expected_detail}
        else:
            assert expected_detail in captured.err
            assert "credential_stored" not in captured.err
        assert cfg.load().get_profile("default").api_key == previous_key
    assert "Logged in" not in captured.err
    assert "secret" not in captured.err
    assert "private-token" not in captured.err
    assert FAKE_API_KEY not in captured.err
    assert previous_key not in captured.err


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


def test_explicit_login_key_recovers_from_invalid_environment_key(config_path, respx_mock, monkeypatch, capsys) -> None:
    monkeypatch.setenv(cfg.ENV_API_KEY, "stale-malformed-key")
    monkeypatch.setattr(sys, "argv", ["omi", "--json", "auth", "login", "--api-key", FAKE_API_KEY])
    route = respx_mock.get(f"{cfg.DEFAULT_API_BASE}/v1/dev/user/memories").respond(200, json=[])

    main()

    captured = capsys.readouterr()
    assert route.call_count == 1
    assert route.calls[0].request.headers["Authorization"] == f"Bearer {FAKE_API_KEY}"
    assert json.loads(captured.out) == {
        "profile": "default",
        "auth_method": "api_key",
        "api_base": cfg.DEFAULT_API_BASE,
    }
    assert captured.err == ""
    assert cfg.load().get_profile("default").api_key == FAKE_API_KEY


@pytest.mark.parametrize("source", ["flag", "profile"])
@pytest.mark.parametrize("auth_method", ["api_key", "browser"])
@pytest.mark.parametrize(
    "api_base",
    [
        "ftp://user:secret@example.invalid/?token=private-token",
        "http://user:secret@127.0.0.1:0/?token=private-token",
        "http://user:secret@127.0.0.1:99999/?token=private-token",
    ],
)
def test_invalid_login_base_preserves_existing_profile(
    authed_profile, config_path, monkeypatch, capsys, source, auth_method, api_base
) -> None:
    argv = ["omi", "--json"]
    if source == "flag":
        argv.extend(["--api-base", api_base])
    else:
        config = cfg.load()
        config.get_profile("default").api_base = api_base
        cfg.save(config)
    original_config = config_path.read_bytes()
    argv.extend(["auth", "login"])
    argv.extend(["--browser"] if auth_method == "browser" else ["--api-key", "omi_dev_" + ("y" * 32)])
    monkeypatch.setattr(sys, "argv", argv)

    def unexpected_call(*args, **kwargs):
        pytest.fail("Invalid API configuration must fail before HTTP, browser login, or retry backoff")

    monkeypatch.setattr(httpx, "Client", unexpected_call)
    monkeypatch.setattr("omi_cli.auth.oauth.login_with_browser", unexpected_call)
    monkeypatch.setattr(time, "sleep", unexpected_call)

    with pytest.raises(SystemExit) as info:
        main()

    captured = capsys.readouterr()
    assert info.value.code == 1
    assert captured.out == ""
    assert json.loads(captured.err) == {
        "error": "Invalid API base URL",
        "detail": "Use a valid absolute http:// or https:// URL for the Omi API.",
    }
    assert "secret" not in captured.err
    assert "private-token" not in captured.err
    assert config_path.read_bytes() == original_config
