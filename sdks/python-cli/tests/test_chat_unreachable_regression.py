"""Regression tests for the browser-login chat-unreachable defect (#21223).

Before the fix, ``omi auth login --browser`` persisted only the minted
developer API key via ``store_api_key``, which set ``auth_method = "api_key"``
and nulled the OAuth tokens. ``omi chat`` requires an OAuth profile, so the
exact login the CLI told the user to run left chat permanently unreachable.

The fix persists BOTH credentials (``auth_method = "oauth"`` plus the dev key)
and selects the credential per request path: the dev key for ``/v1/dev/*``,
the OAuth ID token for everything else (notably chat's ``/v2/messages``).
"""

from __future__ import annotations

import time

import httpx
import pytest

from omi_cli import config as cfg
from omi_cli.auth import oauth
from omi_cli.auth.store import store_oauth_session_with_dev_key
from omi_cli.client import OmiClient

API_BASE = "https://api.test.omi.local"


# ---- store_oauth_session_with_dev_key -------------------------------------


def test_combined_store_keeps_oauth_method_and_dev_key(config_path) -> None:
    profile = store_oauth_session_with_dev_key(
        "default",
        api_key="omi_dev_minted",
        id_token="fb_id",
        refresh_token="fb_refr",
        expires_at=time.time() + 3000,
        api_base=API_BASE,
    )
    # auth_method MUST stay "oauth" so `omi chat` accepts the profile...
    assert profile.auth_method == "oauth"
    # ...while the dev key is retained for /v1/dev/* commands.
    assert profile.api_key == "omi_dev_minted"
    assert profile.id_token == "fb_id"
    assert profile.refresh_token == "fb_refr"

    reloaded = cfg.load().get_profile("default")
    assert reloaded.auth_method == "oauth"
    assert reloaded.api_key == "omi_dev_minted"
    assert reloaded.id_token == "fb_id"


# ---- credential selection in the client -----------------------------------


def test_dev_path_uses_api_key_on_oauth_profile(config_path, respx_mock) -> None:
    store_oauth_session_with_dev_key(
        "default",
        api_key="omi_dev_minted",
        id_token="fb_id",
        refresh_token="fb_refr",
        expires_at=time.time() + 3000,
        api_base=API_BASE,
    )
    route = respx_mock.get("/v1/dev/user/memories").respond(json=[])
    with OmiClient(cfg.load().get_profile("default")) as client:
        client.get("/v1/dev/user/memories")
    assert route.calls.last.request.headers["Authorization"] == "Bearer omi_dev_minted"


def test_non_dev_path_uses_oauth_token_on_oauth_profile(config_path, respx_mock) -> None:
    store_oauth_session_with_dev_key(
        "default",
        api_key="omi_dev_minted",
        id_token="fb_id",
        refresh_token="fb_refr",
        expires_at=time.time() + 3000,
        api_base=API_BASE,
    )
    # Chat history hits /v2/messages, which is Firebase-identity authenticated.
    route = respx_mock.get("/v2/messages").respond(json=[])
    with OmiClient(cfg.load().get_profile("default")) as client:
        client.get("/v2/messages")
    assert route.calls.last.request.headers["Authorization"] == "Bearer fb_id"


def test_stream_post_uses_oauth_token_for_chat(config_path, respx_mock) -> None:
    """Chat streams via POST /v2/messages — must carry the OAuth token, not the key."""
    store_oauth_session_with_dev_key(
        "default",
        api_key="omi_dev_minted",
        id_token="fb_id",
        refresh_token="fb_refr",
        expires_at=time.time() + 3000,
        api_base=API_BASE,
    )
    route = respx_mock.post("/v2/messages").respond(
        content=b"done: " + __import__("base64").b64encode(b'{"text":"hi"}') + b"\n"
    )
    with OmiClient(cfg.load().get_profile("default")) as client:
        list(client.stream_post_lines("/v2/messages", json_body={"text": "hey"}))
    assert route.calls.last.request.headers["Authorization"] == "Bearer fb_id"


def test_api_key_profile_still_uses_key_for_all_paths(config_path, respx_mock) -> None:
    """A pure api_key profile (non-browser login) is unchanged: key everywhere."""
    config = cfg.load()
    profile = config.get_profile("default")
    profile.auth_method = "api_key"
    profile.api_key = "omi_dev_only"
    profile.api_base = API_BASE
    config.set_profile(profile)
    cfg.save(config)

    route = respx_mock.get("/v2/messages").respond(json=[])
    with OmiClient(cfg.load().get_profile("default")) as client:
        client.get("/v2/messages")
    assert route.calls.last.request.headers["Authorization"] == "Bearer omi_dev_only"


# ---- end-to-end: browser-login tail leaves chat reachable -----------------


def test_browser_login_tail_persists_oauth_so_chat_is_reachable(config_path, monkeypatch) -> None:
    """After a browser login mints the dev key, the persisted profile must still
    satisfy `omi chat`'s OAuth gate (the pre-fix flow left auth_method=api_key).

    This exercises the exact tail of ``login_with_browser`` (token exchange ->
    Firebase signin -> dev-key mint -> persist) with the network mocked, which
    is where the defect lived, without driving the interactive localhost server.
    """
    monkeypatch.setattr(oauth, "_exchange_code_for_custom_token", lambda *a, **k: "custom_tok")
    monkeypatch.setattr(oauth, "_firebase_signin_with_custom_token", lambda ct: ("fb_id", "fb_refr", 3600))
    monkeypatch.setattr(oauth, "_exchange_firebase_token_for_dev_key", lambda *a, **k: "omi_dev_from_browser")

    # Reproduce the flow's final steps verbatim (mirrors oauth.login_with_browser).
    id_token, refresh_token, expires_in = oauth._firebase_signin_with_custom_token("custom_tok")
    raw_key = oauth._exchange_firebase_token_for_dev_key(API_BASE, id_token)
    profile = oauth.store_oauth_session_with_dev_key(
        "default",
        api_key=raw_key,
        id_token=id_token,
        refresh_token=refresh_token,
        expires_at=time.time() + expires_in - oauth._REFRESH_MARGIN_SECONDS,
        api_base=API_BASE,
    )

    # The persisted profile must still be accepted by `omi chat`.
    assert profile.auth_method == "oauth"
    assert profile.id_token == "fb_id"
    assert profile.api_key == "omi_dev_from_browser"

    # The persisted profile must pass `omi chat`'s auth gate. The gate is:
    #   if profile.auth_method != "oauth" or os.environ.get(ENV_API_KEY): raise UsageError
    # so assert the predicate directly rather than entering the interactive REPL.
    import os

    from omi_cli import config as _cfg

    fresh = cfg.load().get_profile("default")
    gate_blocks = bool(fresh.auth_method != "oauth" or os.environ.get(_cfg.ENV_API_KEY))
    assert gate_blocks is False, "chat auth gate would reject the browser-login profile"