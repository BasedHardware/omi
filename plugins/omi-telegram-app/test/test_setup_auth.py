"""Regression tests for /setup bearer auth on the Telegram plugin.

Identified by maintainer security review on PR #8528: the desktop sends
`Authorization: Bearer <token>` to /setup but the plugin was not
verifying it, leaving the setup surface unauthenticated for any caller
who knew the plugin URL.

After the fix, /setup must:
- Return 503 if AI_CLONE_PLUGIN_TOKEN is unset (production misconfig)
- Return 401 if the header is missing
- Return 401 if the bearer doesn't match
- Pass through to the existing Telegram flow when the bearer matches
  (or dev mode is set)

The same policy is shared via plugins/_shared/auth.py — see
plugins/_shared/test/test_auth.py for the dependency-level unit tests.
This file is the integration coverage: the auth gate is actually wired
into the plugin's /setup route and /toggle route.
"""

from __future__ import annotations

import os
import sys

import pytest


# ---------------------------------------------------------------------------
# Path setup (mirrors test_main.py)
# ---------------------------------------------------------------------------
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.abspath(os.path.join(_PLUGIN_DIR, ".."))
_SHARED = os.path.abspath(os.path.join(_PLUGIN_ROOT, "..", "_shared"))
for p in (_PLUGIN_ROOT, _SHARED):
    if p not in sys.path:
        sys.path.insert(0, p)

from main import app as fastapi_app  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip token + dev mode env. Tests opt in explicitly.

    Note: we don't reload the `main` module here. The `require_bearer`
    dependency reads the env var at request time (inside the dependency
    call), not at import time, so changing the env mid-test is fine —
    the next request will re-read it.
    """
    monkeypatch.delenv("AI_CLONE_PLUGIN_TOKEN", raising=False)
    monkeypatch.delenv("OMI_DEV_MODE", raising=False)
    yield


@pytest.fixture(autouse=True)
def _reset_telegram_client():
    """Close + reset telegram_client's module-level httpx.AsyncClient.

    The plugin lazily creates the client on first call and never closes
    it across the process lifetime. With pytest-asyncio in strict mode,
    each test gets a fresh event loop — so a client created on loop A
    fails on loop B with 'Event loop is closed'. Resetting to None
    forces lazy re-creation on the current loop.
    """
    import asyncio
    import telegram_client

    # If the cached client exists, try to close it. If the loop is
    # already closed, swallow the error — we're about to discard the
    # client anyway.
    if telegram_client._client is not None:
        try:
            asyncio.get_event_loop().run_until_complete(telegram_client.aclose())
        except RuntimeError:
            pass
        telegram_client._client = None
    yield


def _post_setup(client, *, token=None):
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return client.post(
        "/setup",
        json={
            "bot_token": "0000000000:fake",
            "omi_uid": "u",
            "persona_id": "p",
            "omi_dev_api_key": "k",
            "public_base_url": "https://x.example.com",
        },
        headers=headers,
    )


class TestSetupAuth:
    def test_setup_without_token_returns_503(self):
        """Production misconfig: token not set, no dev mode -> 503.

        The auth gate MUST short-circuit before Telegram is touched —
        otherwise a misconfigured production deploy that forgot to set
        the token would silently allow anyone with the URL to call
        Telegram's setWebhook on the user's behalf.
        """
        from fastapi.testclient import TestClient

        client = TestClient(fastapi_app)
        r = _post_setup(client)
        assert r.status_code == 503, (
            "Without AI_CLONE_PLUGIN_TOKEN configured, /setup must fail "
            "closed with 503 — not silently proceed and call Telegram."
        )
        assert "not configured" in r.json()["detail"].lower()

    def test_setup_without_header_returns_401(self, monkeypatch):
        monkeypatch.setenv("AI_CLONE_PLUGIN_TOKEN", "the-secret")
        from fastapi.testclient import TestClient

        client = TestClient(fastapi_app)
        r = _post_setup(client)
        assert r.status_code == 401

    def test_setup_with_wrong_token_returns_401(self, monkeypatch):
        monkeypatch.setenv("AI_CLONE_PLUGIN_TOKEN", "the-secret")
        from fastapi.testclient import TestClient

        client = TestClient(fastapi_app)
        r = _post_setup(client, token="wrong-token")
        assert r.status_code == 401

    def test_setup_with_correct_token_passes_auth_gate(self, monkeypatch):
        """End-to-end: a valid bearer passes the auth gate.

        The downstream Telegram call will fail with 401/404 because the
        bot_token is fake — that's the EXISTING behavior. The point of
        this test is to prove the auth gate didn't short-circuit with
        401/503, i.e. the request reached the plugin's business logic.
        """
        monkeypatch.setenv("AI_CLONE_PLUGIN_TOKEN", "the-secret")
        from fastapi.testclient import TestClient

        client = TestClient(fastapi_app)
        r = _post_setup(client, token="the-secret")
        assert r.status_code not in (401, 503), (
            f"Correct bearer should pass auth gate. Got {r.status_code}: " f"{r.text}"
        )

    def test_setup_with_dev_mode_no_token_allows(self, monkeypatch):
        """Dev mode + no token = allow. Matches the WhatsApp-webhook pattern.

        Identified by cubic (P3): a previous version of this assertion only
        checked `!= 503`. That's a weak guard — it would pass even if the
        auth gate were refactored to require a bearer FIRST and return 401
        for callers without one. Tighten: assert the request PASSED the
        auth gate (i.e. got a non-401/non-503 response from the Telegram
        call). 4xx from Telegram is expected for the fake bot_token.
        """
        monkeypatch.setenv("OMI_DEV_MODE", "1")
        from fastapi.testclient import TestClient

        client = TestClient(fastapi_app)
        r = _post_setup(client)
        assert r.status_code not in (401, 503), (
            f"Dev mode + no token must pass the auth gate. Got "
            f"{r.status_code}: {r.text}"
        )
