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

# Import the FastAPI app via importlib (avoids the pip-installed `main` package
# shadowing our local module).
_PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SPEC = importlib.util.spec_from_file_location("main", os.path.join(_PLUGIN_ROOT, "main.py"))
main = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(main)
app = main.app


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """Point simple_storage at a per-test tmp dir so tests don't pollute each other."""
    import simple_storage

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
# /webhook GET — Meta verification handshake
# ---------------------------------------------------------------------------
class TestWebhookVerify:
    def test_returns_challenge_on_matching_verify_token(self, client):
        # Pre-register a user with a known verify_token.
        import simple_storage

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
        import simple_storage

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
        # Detailed behavior is tested in test_setup_token_leak.py::TestSetupHappyPath.
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
        """Smoke test for /toggle — detailed behavior is in test_toggle.py."""
        r = client.post("/toggle", json={"phone": "15550001111", "enabled": True, "access_token": "at1"})
        # Unknown phone with wrong access_token both return 403.
        assert r.status_code == 403
