"""Regression tests for /setup bearer auth on the WhatsApp plugin.

Mirrors plugins/omi-telegram-app/test/test_setup_auth.py but for the
WhatsApp plugin. Identified by maintainer security review on PR #8528.

The dependency `require_bearer` is defined in plugins/_shared/auth.py
and tested in plugins/_shared/test/test_auth.py. This file is the
integration coverage: the auth gate is actually wired into the plugin's
/setup and /toggle routes.

Loads the plugin's `main.py` via the conftest helper to avoid the bare-
name module collision with the Telegram plugin's tests.
"""

from __future__ import annotations

import os
import sys

import pytest


# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.abspath(os.path.join(_PLUGIN_DIR, ".."))
_SHARED = os.path.abspath(os.path.join(_PLUGIN_ROOT, "..", "_shared"))
for p in (_PLUGIN_ROOT, _SHARED):
    if p not in sys.path:
        sys.path.insert(0, p)

from conftest import load_main_module  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Strip token + dev mode env. Tests opt in explicitly.

    Also set a placeholder WHATSAPP_APP_SECRET so the plugin's
    import-time guard (which requires WHATSAPP_APP_SECRET or
    OMI_DEV_MODE=1) doesn't crash the module load. We're testing
    the BEARER auth gate here, not the webhook signature — the
    placeholder value is irrelevant to that test.
    """
    monkeypatch.delenv("AI_CLONE_PLUGIN_TOKEN", raising=False)
    monkeypatch.delenv("OMI_DEV_MODE", raising=False)
    monkeypatch.setenv("WHATSAPP_APP_SECRET", "test-placeholder-secret")
    yield


@pytest.fixture
def client():
    """FastAPI TestClient against the WhatsApp plugin's main module."""
    from fastapi.testclient import TestClient

    main = load_main_module()
    return TestClient(main.app)


def _post_setup(client, *, token=None):
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return client.post(
        "/setup",
        json={
            "access_token": "fake-access",
            "phone_number_id": "111",
            "verify_token": "vt",
            "omi_uid": "u",
            "persona_id": "p",
            "omi_dev_api_key": "k",
            "phone": "15550001111",
        },
        headers=headers,
    )


class TestWhatsappSetupAuth:
    def test_setup_without_token_returns_503(self, client):
        """Production misconfig: token not set, no dev mode -> 503.

        Without this gate, anyone with the plugin URL could call Meta's
        subscribed_apps and set up webhooks for the user's WhatsApp
        Business app — a free SSRF / quota-burn vector.
        """
        r = _post_setup(client)
        assert r.status_code == 503, (
            "Without AI_CLONE_PLUGIN_TOKEN configured, /setup must fail "
            "closed with 503 — not silently proceed and call Meta."
        )
        assert "not configured" in r.json()["detail"].lower()

    def test_setup_without_header_returns_401(self, client, monkeypatch):
        monkeypatch.setenv("AI_CLONE_PLUGIN_TOKEN", "the-secret")
        r = _post_setup(client)
        assert r.status_code == 401

    def test_setup_with_wrong_token_returns_401(self, client, monkeypatch):
        monkeypatch.setenv("AI_CLONE_PLUGIN_TOKEN", "the-secret")
        r = _post_setup(client, token="wrong-token")
        assert r.status_code == 401

    def test_setup_with_correct_token_passes_auth_gate(self, client, monkeypatch):
        """A valid bearer passes the gate; the downstream Meta call
        fails with 4xx for the fake creds (existing behavior).
        """
        monkeypatch.setenv("AI_CLONE_PLUGIN_TOKEN", "the-secret")
        r = _post_setup(client, token="the-secret")
        # Not 401/503 — proves we got past the auth gate.
        assert r.status_code not in (401, 503), (
            f"Correct bearer should pass auth gate. Got {r.status_code}: " f"{r.text}"
        )

    def test_setup_with_dev_mode_no_token_allows(self, client, monkeypatch):
        """Dev mode + no token = allow. Matches the WhatsApp-webhook pattern.

        Tightened per cubic (P3): the previous assertion only checked
        `!= 503`. That's a weak guard — a refactor that required the
        bearer first (returning 401) would still pass it. Now we also
        forbid 401, so the test catches both the misconfig path (503)
        and the wrong-shape path (401) and proves the auth gate let
        the request through.
        """
        monkeypatch.setenv("OMI_DEV_MODE", "1")
        r = _post_setup(client)
        assert r.status_code not in (401, 503), (
            f"Dev mode + no token must pass the auth gate. Got "
            f"{r.status_code}: {r.text}"
        )
