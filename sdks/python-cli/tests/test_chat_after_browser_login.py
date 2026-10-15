"""Browser sign-in must leave a profile `omi chat` can use.

`omi auth login --browser` mints a developer API key from the Firebase session and used to
store only the key, while `omi chat` demanded an ``oauth`` profile and told the user to run
the very login that produced the rejected profile. Browser sign-in now keeps the Firebase
session beside the key: `/v1/dev/*` routes keep using the key, `/v2/messages` uses the
session's ID token, and an expired ID token is refreshed in place without touching the key.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request

import httpx
import pytest
import respx
from typer.testing import CliRunner

from omi_cli import config as cfg
from omi_cli.auth import oauth
from omi_cli.auth.store import store_api_key
from omi_cli.main import app

API = "https://api.test.omi.local"
DEV_KEY = "omi_dev_" + "k" * 32


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    target = tmp_path / "config.toml"
    monkeypatch.setenv(cfg.ENV_CONFIG_PATH, str(target))
    for var in (cfg.ENV_API_KEY, cfg.ENV_API_BASE, cfg.ENV_PROFILE):
        monkeypatch.delenv(var, raising=False)
    config = cfg.load()
    profile = config.get_profile("default")
    profile.api_base = API
    cfg.save(config)
    return target


def _fake_browser(url: str, new: int = 0) -> bool:
    """Act like the backend's auth callback page: bounce to the loopback redirect_uri."""
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    redirect, state = query["redirect_uri"][0], query["state"][0]

    def go() -> None:
        urllib.request.urlopen(f"{redirect}?code=authcode&state={urllib.parse.quote(state)}").read()

    threading.Thread(target=go, daemon=True).start()
    return True


def _mock_login(router: respx.MockRouter) -> None:
    router.post(f"{API}/v1/auth/token").mock(return_value=httpx.Response(200, json={"custom_token": "ct"}))
    router.post(url__startswith="https://identitytoolkit.googleapis.com/").mock(
        return_value=httpx.Response(
            200, json={"idToken": "firebase-id", "refreshToken": "firebase-rt", "expiresIn": "3600"}
        )
    )
    router.get(f"{API}/v1/dev/keys").mock(return_value=httpx.Response(200, json=[]))
    router.post(f"{API}/v1/dev/keys").mock(return_value=httpx.Response(201, json={"key": DEV_KEY}))
    router.get(f"{API}/v1/dev/key").mock(return_value=httpx.Response(200, json={"scopes": ["memories:read"]}))


def test_browser_login_keeps_the_session_and_chat_uses_it(isolated_config, monkeypatch) -> None:
    monkeypatch.setattr(oauth.webbrowser, "open", _fake_browser)
    runner = CliRunner()
    with respx.mock(assert_all_called=False) as router:
        _mock_login(router)
        chat_route = router.get(f"{API}/v2/messages").mock(return_value=httpx.Response(200, json=[]))
        memories_route = router.get(f"{API}/v1/dev/user/memories").mock(return_value=httpx.Response(200, json=[]))

        login = runner.invoke(app, ["--json", "auth", "login", "--browser"])
        assert login.exit_code == 0, login.output + login.stderr
        assert json.loads(login.stdout)["auth_method"] == "api_key"

        stored = cfg.load().get_profile("default")
        assert (stored.auth_method, stored.api_key) == ("api_key", DEV_KEY)
        assert (stored.id_token, stored.refresh_token) == ("firebase-id", "firebase-rt")
        assert stored.id_token_expires_at is not None and stored.id_token_expires_at > time.time()

        chat = runner.invoke(app, ["--json", "chat", "--history"])
        assert chat.exit_code == 0, chat.output + chat.stderr
        assert chat_route.calls.last.request.headers["Authorization"] == "Bearer firebase-id"

        memories = runner.invoke(app, ["--json", "memory", "list"])
        assert memories.exit_code == 0, memories.output + memories.stderr
        assert memories_route.calls.last.request.headers["Authorization"] == f"Bearer {DEV_KEY}"


def test_chat_refreshes_an_expired_session_without_touching_the_key(isolated_config) -> None:
    store_api_key("default", DEV_KEY, api_base=API, firebase_session=("stale-id", "firebase-rt", time.time() - 5))
    runner = CliRunner()
    with respx.mock(assert_all_called=False) as router:
        refresh_route = router.post(url__startswith="https://securetoken.googleapis.com/").mock(
            return_value=httpx.Response(200, json={"id_token": "fresh-id", "refresh_token": "firebase-rt-2"})
        )
        chat_route = router.get(f"{API}/v2/messages").mock(return_value=httpx.Response(200, json=[]))

        chat = runner.invoke(app, ["--json", "chat", "--history"])

    assert chat.exit_code == 0, chat.output + chat.stderr
    assert refresh_route.called
    assert chat_route.calls.last.request.headers["Authorization"] == "Bearer fresh-id"
    stored = cfg.load().get_profile("default")
    assert (stored.auth_method, stored.api_key) == ("api_key", DEV_KEY)
    assert (stored.id_token, stored.refresh_token) == ("fresh-id", "firebase-rt-2")


def test_pasted_key_drops_the_session_and_chat_asks_for_browser_sign_in(isolated_config) -> None:
    store_api_key("default", DEV_KEY, api_base=API, firebase_session=("firebase-id", "firebase-rt", time.time() + 3600))
    runner = CliRunner()
    with respx.mock(assert_all_called=False) as router:
        router.get(f"{API}/v1/dev/key").mock(return_value=httpx.Response(200, json={"scopes": ["memories:read"]}))
        chat_route = router.get(f"{API}/v2/messages").mock(return_value=httpx.Response(200, json=[]))

        login = runner.invoke(app, ["--json", "auth", "login", "--api-key", "omi_dev_" + "p" * 32])
        assert login.exit_code == 0, login.output + login.stderr
        stored = cfg.load().get_profile("default")
        assert stored.refresh_token is None and stored.id_token is None

        chat = runner.invoke(app, ["--json", "chat", "--history"])

    assert chat.exit_code == 1
    assert "browser sign-in" in chat.stderr
    assert not chat_route.called


def test_has_firebase_session_and_needs_refresh_cover_both_profile_shapes() -> None:
    pasted = cfg.Profile(name="p", auth_method="api_key", api_key=DEV_KEY)
    browser = cfg.Profile(name="b", auth_method="api_key", api_key=DEV_KEY, id_token="i", refresh_token="r")
    legacy = cfg.Profile(
        name="o", auth_method="oauth", id_token="i", refresh_token="r", id_token_expires_at=time.time() + 60
    )
    assert not oauth.has_firebase_session(pasted) and not oauth.needs_refresh(pasted)
    assert oauth.has_firebase_session(browser) and oauth.needs_refresh(browser)  # unknown age: refresh
    assert oauth.has_firebase_session(legacy) and not oauth.needs_refresh(legacy)
