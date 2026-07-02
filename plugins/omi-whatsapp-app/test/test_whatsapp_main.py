"""Tests for the WhatsApp plugin's HTTP surface (skeleton + GET verification).

Mirrors plugins/omi-telegram-app/test/test_main.py in structure. Covers:
- /health
- /webhook GET (Meta verification): correct challenge echoed back on match,
  403 on mismatch, 404 on non-subscribe request.
"""

from __future__ import annotations

import importlib.util
import os
from unittest.mock import AsyncMock, patch

import pytest

# Load `main` via the conftest helper, which isolates sys.modules['main'],
# sys.modules['simple_storage'], and sys.modules['whatsapp_client'] so this
# test file doesn't collide with omi-telegram-app when both suites run
# together in one pytest invocation.
from conftest import load_main_module

main = load_main_module()
app = main.app


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """Point simple_storage at a per-test tmp dir so tests don't pollute each other."""
    simple_storage = main.simple_storage

    monkeypatch.setattr(simple_storage, "STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(simple_storage, "USERS_FILE", os.path.join(str(tmp_path), "users_data.json"))
    monkeypatch.setattr(simple_storage, "PENDING_FILE", os.path.join(str(tmp_path), "pending_setups.json"))
    monkeypatch.setattr(simple_storage, "users", {})
    monkeypatch.setattr(simple_storage, "pending_setups", {})
    yield


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    return TestClient(app)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------
class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["service"] == "omi-whatsapp-clone"


# ---------------------------------------------------------------------------
# /status — bound-phone count + auto-reply state. Added for PR #8682
# (cubic P1): the Omi desktop's ConnectSheet handshake polls /status
# instead of /health so the user-side setup completion can be confirmed
# (connected_phones >= 1 requires a real /start-equivalent message).
# Mirrors plugins/omi-telegram-app/test/test_main.py::TestStatus.
# ---------------------------------------------------------------------------
import os

PLUGIN_BEARER = os.environ.get("AI_CLONE_PLUGIN_TOKEN", "test-token")
AUTH = {"Authorization": f"Bearer {PLUGIN_BEARER}"}


class TestStatus:
    def test_status_authenticated_no_users(self, client):
        r = client.get("/status", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["connected_phones"] == 0
        assert body["auto_reply_enabled"] is False
        assert body["first_phone"] is None
        assert body["service"] == "omi-whatsapp-clone"

    def test_status_reflects_bound_phone_and_auto_reply(self, client):
        from conftest import load_simple_storage

        ss = load_simple_storage()
        ss.save_user(
            phone="15550001111",
            omi_uid="uid-1",
            persona_id="persona-1",
            omi_dev_api_key="dev-key",
            access_token="access-token",
            phone_number_id="phone-id-1",
            verify_token="verify-token-1",
            auto_reply_enabled=True,
        )

        r = client.get("/status", headers=AUTH)
        assert r.status_code == 200
        body = r.json()
        assert body["connected_phones"] == 1
        assert body["first_phone"] == "15550001111"
        assert body["auto_reply_enabled"] is True


# ---------------------------------------------------------------------------
# /webhook GET — Meta verification handshake
# ---------------------------------------------------------------------------
class TestWebhookVerify:
    def test_returns_challenge_on_matching_verify_token(self, client):
        # Pre-register a user with a known verify_token.
        simple_storage = main.simple_storage

        simple_storage.save_user(
            phone="15550001111",
            omi_uid="u1",
            persona_id="p1",
            omi_dev_api_key="k1",
            access_token="at1",
            phone_number_id="pn1",
            verify_token="VT_MATCH",
            auto_reply_enabled=False,
        )

        r = client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "VT_MATCH",
                "hub.challenge": "1234567890",
            },
        )
        assert r.status_code == 200
        assert r.text == "1234567890"
        assert r.headers["content-type"].startswith("text/plain")

    def test_returns_challenge_for_pending_setup_verify_token(self, client):
        """Verification should succeed for verify_tokens of pending_setups too —
        the user does the verification step BEFORE the /start handshake."""
        simple_storage = main.simple_storage

        simple_storage.save_pending_setup(
            "setup_tok",
            {
                "verify_token": "VT_PEND",
                "phone_number_id": "pn1",
                "access_token": "at1",
            },
        )

        r = client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "VT_PEND",
                "hub.challenge": "9999",
            },
        )
        assert r.status_code == 200
        assert r.text == "9999"

    def test_403_on_unknown_verify_token(self, client):
        r = client.get(
            "/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "VT_UNKNOWN",
                "hub.challenge": "1234",
            },
        )
        assert r.status_code == 403

    def test_404_when_hub_mode_not_subscribe(self, client):
        r = client.get("/webhook", params={"hub.mode": "unsubscribe"})
        assert r.status_code == 404

    def test_404_when_no_params_at_all(self, client):
        # No hub.mode at all = not a verification request. 404 is the right answer.
        r = client.get("/webhook")
        assert r.status_code == 404

    def test_400_when_subscribe_but_token_or_challenge_missing(self, client):
        r = client.get("/webhook", params={"hub.mode": "subscribe"})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# /setup — stub for now (501)
# ---------------------------------------------------------------------------
class TestSetupStub:
    def test_setup_accepts_well_formed_request(self, client):
        """Smoke test: a well-formed /setup request doesn't return 5xx (we mock the Meta calls)."""
        from unittest.mock import AsyncMock, patch

        async def fake_subscribe(phone_number_id, access_token):
            return {"success": True}

        async def fake_get_info(phone_number_id, access_token):
            # Meta returns formatted phone like "+1 555-000-1111"; our _normalize_e164
            # strips formatting. Test that the deep link uses digits only.
            return {"display_phone_number": "+1 555-000-1111", "verified_name": "Test"}

        with patch("main.whatsapp_client.subscribe_app", new=AsyncMock(side_effect=fake_subscribe)):
            with patch("main.whatsapp_client.get_phone_number_info", new=AsyncMock(side_effect=fake_get_info)):
                r = client.post(
                    "/setup",
                    json={
                        "access_token": "at1",
                        "phone_number_id": "pn1",
                        "verify_token": "vt1",
                        "omi_uid": "u1",
                        "persona_id": "p1",
                        "omi_dev_api_key": "k1",
                        "public_base_url": "https://clone.example.com",
                    },
                )
        # Detailed behavior is tested in test_whatsapp_setup_token_leak.py::TestSetupHappyPath.
        assert r.status_code == 200
        # P1.3 fix: deep link uses digits-only E.164 (no '+', no formatting),
        # NOT phone_number_id which is an internal Graph ID
        deep_link = r.json()["deep_link"]
        assert deep_link.startswith("https://wa.me/15550001111?text=")
        assert "%2Fstart" in deep_link or "/start" in deep_link


# ---------------------------------------------------------------------------
# /toggle — stub for now (501)
# ---------------------------------------------------------------------------
class TestToggleStub:
    def test_toggle_403_on_unknown_phone(self, client):
        """Smoke test for /toggle — detailed behavior is in test_whatsapp_toggle.py."""
        r = client.post("/toggle", json={"phone": "15550001111", "enabled": True, "access_token": "at1"})
        # Unknown phone with wrong access_token both return 403.
        assert r.status_code == 403
