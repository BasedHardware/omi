"""Tests for the WhatsApp /webhook POST delivery path.

Covers:
- HMAC signature verification (when WHATSAPP_APP_SECRET is set)
- /start <token> handshake (binds phone to user)
- Status updates (delivery receipts) silently acknowledged
- Non-text messages ignored
- Malformed JSON silently ignored
- Unknown phone (no user record) silently ignored
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from unittest.mock import AsyncMock, patch

import pytest

from conftest import load_main_module

main = load_main_module()


SECRET = "test-app-secret-xyz"


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    from conftest import load_simple_storage

    simple_storage = load_simple_storage()

    monkeypatch.setattr(simple_storage, "STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr(simple_storage, "USERS_FILE", os.path.join(str(tmp_path), "users_data.json"))
    monkeypatch.setattr(simple_storage, "PENDING_FILE", os.path.join(str(tmp_path), "pending_setups.json"))
    monkeypatch.setattr(simple_storage, "users", {})
    monkeypatch.setattr(simple_storage, "pending_setups", {})
    yield


@pytest.fixture
def client_with_secret(monkeypatch):
    """Set WHATSAPP_APP_SECRET so signature verification is enforced."""
    from conftest import _cached_modules

    # Snapshot the cache so we can restore it after the test. We can't
    # clear the cache globally — that would invalidate the simple_storage /
    # whatsapp_client modules cached for the rest of the test session,
    # causing subsequent tests to use a different module instance than main.py
    # and miss state they saved.
    saved_cache = dict(_cached_modules)
    _cached_modules.clear()
    monkeypatch.setenv("WHATSAPP_APP_SECRET", SECRET)
    try:
        main2 = load_main_module()
        from fastapi.testclient import TestClient

        return TestClient(main2.app), main2
    finally:
        # Restore the cache to its pre-fixture state so other tests
        # continue to use the same module instance.
        _cached_modules.clear()
        _cached_modules.update(saved_cache)


@pytest.fixture
def client_no_secret():
    from fastapi.testclient import TestClient

    return TestClient(main.app)


def _sign(body: bytes) -> str:
    digest = hmac.new(SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _meta_message(from_phone: str, text: str, msg_id: str = "wamid.ABC") -> dict:
    """Build a minimal Meta webhook payload containing one inbound text message."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "BIZ_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "pn1", "display_phone_number": "15550001111"},
                            "messages": [
                                {
                                    "from": from_phone,
                                    "id": msg_id,
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


def _meta_statuses() -> dict:
    """Build a Meta webhook payload containing only delivery statuses."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "BIZ_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "pn1"},
                            "statuses": [
                                {
                                    "id": "wamid.STAT",
                                    "status": "delivered",
                                    "timestamp": "1700000000",
                                    "recipient_id": "15550001111",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# HMAC signature verification (T-103)
# ---------------------------------------------------------------------------
class TestWebhookSignature:
    def test_correct_signature_passes(self, client_with_secret):
        client, _ = client_with_secret
        payload = _meta_message("15550001111", "hello")
        body = json.dumps(payload).encode("utf-8")
        r = client.post(
            "/webhook",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": _sign(body)},
        )
        assert r.status_code == 200

    def test_wrong_signature_returns_401(self, client_with_secret):
        client, _ = client_with_secret
        payload = _meta_message("15550001111", "hello")
        body = json.dumps(payload).encode("utf-8")
        r = client.post(
            "/webhook",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=0" * 16},
        )
        assert r.status_code == 401

    def test_missing_signature_returns_401(self, client_with_secret):
        client, _ = client_with_secret
        payload = _meta_message("15550001111", "hello")
        body = json.dumps(payload).encode("utf-8")
        r = client.post("/webhook", content=body, headers={"Content-Type": "application/json"})
        assert r.status_code == 401

    def test_malformed_signature_returns_401(self, client_with_secret):
        client, _ = client_with_secret
        payload = _meta_message("15550001111", "hello")
        body = json.dumps(payload).encode("utf-8")
        r = client.post(
            "/webhook",
            content=body,
            headers={"Content-Type": "application/json", "X-Hub-Signature-256": "not-a-signature"},
        )
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# /start <token> handshake
# ---------------------------------------------------------------------------
class TestStartHandshake:
    def test_start_with_valid_token_binds_user(self, client_no_secret):
        from conftest import load_simple_storage

        simple_storage = load_simple_storage()

        simple_storage.save_pending_setup(
            "tok-1",
            {
                "omi_uid": "u-1",
                "persona_id": "p-1",
                "omi_dev_api_key": "k-1",
                "access_token": "at-1",
                "phone_number_id": "pn-1",
                "verify_token": "vt-1",
            },
        )

        with patch("main.whatsapp_client.send_message", new=AsyncMock(return_value={})):
            r = client_no_secret.post(
                "/webhook",
                json=_meta_message("15550001111", "/start tok-1"),
            )

        assert r.status_code == 200
        user = simple_storage.get_user_by_phone("15550001111")
        assert user is not None
        assert user["omi_uid"] == "u-1"
        assert user["phone_number_id"] == "pn-1"
        assert user["verify_token"] == "vt-1"
        assert user["auto_reply_enabled"] is False

    def test_start_with_no_token_does_not_bind(self, client_no_secret):
        from conftest import load_simple_storage

        simple_storage = load_simple_storage()

        with patch("main.whatsapp_client.send_message", new=AsyncMock(return_value={})):
            r = client_no_secret.post("/webhook", json=_meta_message("15550001111", "/start"))

        assert r.status_code == 200
        assert simple_storage.get_user_by_phone("15550001111") is None

    def test_start_with_unknown_token_replies_to_known_user_only(self, client_no_secret):
        """If the phone is unknown to us, we have no token to reply with \u2014 silent 200.

        If the phone is known (from a prior /setup) but token is stale, reply
        via the stored user's credentials.
        """
        from conftest import load_simple_storage

        simple_storage = load_simple_storage()

        # Known user (no pending setup)
        simple_storage.save_user(
            phone="15550001111",
            omi_uid="u-existing",
            persona_id="p-1",
            omi_dev_api_key="k-1",
            access_token="at-existing",
            phone_number_id="pn-existing",
            verify_token="vt-existing",
            auto_reply_enabled=False,
        )

        mock_send = AsyncMock(return_value={})
        with patch("main.whatsapp_client.send_message", new=mock_send):
            r = client_no_secret.post(
                "/webhook",
                json=_meta_message("15550001111", "/start wrong-token"),
            )

        assert r.status_code == 200
        # Reply sent via the stored user's creds
        assert mock_send.call_count == 1

    def test_start_with_unknown_token_unknown_phone_silent(self, client_no_secret):
        """If neither the phone nor the token is known, we can't reply \u2014 silent 200."""
        mock_send = AsyncMock(return_value={})
        with patch("main.whatsapp_client.send_message", new=mock_send):
            r = client_no_secret.post(
                "/webhook",
                json=_meta_message("15559999999", "/start wrong-token"),
            )

        assert r.status_code == 200
        # No reply sent (we have no token to authenticate with)
        assert mock_send.call_count == 0


# ---------------------------------------------------------------------------
# Status updates and other non-message payloads
# ---------------------------------------------------------------------------
class TestNonMessagePayloads:
    def test_statuses_payload_returns_200_silently(self, client_no_secret):
        mock_send = AsyncMock(return_value={})
        with patch("main.whatsapp_client.send_message", new=mock_send):
            r = client_no_secret.post("/webhook", json=_meta_statuses())
        assert r.status_code == 200
        assert mock_send.call_count == 0

    def test_malformed_json_returns_200(self, client_no_secret):
        mock_send = AsyncMock(return_value={})
        with patch("main.whatsapp_client.send_message", new=mock_send):
            r = client_no_secret.post("/webhook", content=b"{not json", headers={"Content-Type": "application/json"})
        assert r.status_code == 200
        assert mock_send.call_count == 0

    def test_non_text_message_ignored(self, client_no_secret):
        """Image / voice / etc. \u2014 not handled in v0.1."""
        from conftest import load_simple_storage

        simple_storage = load_simple_storage()

        simple_storage.save_user(
            phone="15550001111",
            omi_uid="u-1",
            persona_id="p-1",
            omi_dev_api_key="k-1",
            access_token="at-1",
            phone_number_id="pn-1",
            verify_token="vt-1",
            auto_reply_enabled=True,
        )

        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "messages": [
                                    {
                                        "from": "15550001111",
                                        "id": "wamid.IMG",
                                        "timestamp": "1700000000",
                                        "type": "image",
                                        "image": {"id": "media-1", "mime_type": "image/jpeg"},
                                    }
                                ],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }
        mock_send = AsyncMock(return_value={})
        with patch("main.whatsapp_client.send_message", new=mock_send):
            r = client_no_secret.post("/webhook", json=payload)
        assert r.status_code == 200
        assert mock_send.call_count == 0


# ---------------------------------------------------------------------------
# Unknown phone
# ---------------------------------------------------------------------------
class TestUnknownPhone:
    def test_unknown_phone_returns_200_silently(self, client_no_secret):
        mock_send = AsyncMock(return_value={})
        with patch("main.whatsapp_client.send_message", new=mock_send):
            r = client_no_secret.post(
                "/webhook",
                json=_meta_message("15559999999", "hi there"),
            )
        assert r.status_code == 200
        assert mock_send.call_count == 0


# ---------------------------------------------------------------------------
# Batched and mixed payloads (P1.2 fix)
#
# Meta batches webhook events under load. A single POST can contain multiple
# entries, each with multiple changes, each with multiple messages and/or
# statuses. We MUST process all messages, even when the same payload also
# contains statuses — dropping the whole payload on any status would silently
# lose real user messages.
# ---------------------------------------------------------------------------
class TestBatchedAndMixedPayloads:
    def test_mixed_payload_with_statuses_and_messages_processes_all_messages(self, client_no_secret):
        """A payload with both statuses AND messages must yield ALL messages, not zero."""
        from conftest import load_simple_storage

        simple_storage = load_simple_storage()

        simple_storage.save_user(
            phone="15550001111",
            omi_uid="u-1",
            persona_id="p-1",
            omi_dev_api_key="k-1",
            access_token="at-1",
            phone_number_id="pn-1",
            verify_token="vt-1",
            auto_reply_enabled=True,
        )

        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {"phone_number_id": "pn1"},
                                "statuses": [
                                    {
                                        "id": "wamid.SENT",
                                        "status": "sent",
                                        "timestamp": "1700000000",
                                        "recipient_id": "15559999999",
                                    }
                                ],
                                "messages": [
                                    {
                                        "from": "15550001111",
                                        "id": "wamid.M1",
                                        "timestamp": "1700000001",
                                        "type": "text",
                                        "text": {"body": "msg one"},
                                    },
                                    {
                                        "from": "15550001111",
                                        "id": "wamid.M2",
                                        "timestamp": "1700000002",
                                        "type": "text",
                                        "text": {"body": "msg two"},
                                    },
                                ],
                            },
                            "field": "messages",
                        }
                    ],
                }
            ],
        }
        with patch.object(main, "_persona_chat", new=AsyncMock(return_value="reply")):
            with patch("main.whatsapp_client.send_message", new=AsyncMock(return_value={})) as mock_send:
                r = client_no_secret.post("/webhook", json=payload)
        assert r.status_code == 200
        # Both messages dispatched → two persona calls → two replies sent.
        assert mock_send.call_count == 2

    def test_multiple_entries_in_one_payload_all_processed(self, client_no_secret):
        """Multiple entries under the same object — all messages must be processed."""
        from conftest import load_simple_storage

        simple_storage = load_simple_storage()

        simple_storage.save_user(
            phone="15550001111",
            omi_uid="u-1",
            persona_id="p-1",
            omi_dev_api_key="k-1",
            access_token="at-1",
            phone_number_id="pn-1",
            verify_token="vt-1",
            auto_reply_enabled=True,
        )

        payload = {
            "object": "whatsapp_business_account",
            "entry": [
                {
                    "id": "BIZ_A",
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "15550001111",
                                        "id": "wamid.A1",
                                        "type": "text",
                                        "text": {"body": "from A"},
                                    }
                                ],
                            },
                        }
                    ],
                },
                {
                    "id": "BIZ_B",
                    "changes": [
                        {
                            "value": {
                                "messages": [
                                    {
                                        "from": "15550001111",
                                        "id": "wamid.B1",
                                        "type": "text",
                                        "text": {"body": "from B"},
                                    }
                                ],
                            },
                        }
                    ],
                },
            ],
        }
        with patch.object(main, "_persona_chat", new=AsyncMock(return_value="reply")):
            with patch("main.whatsapp_client.send_message", new=AsyncMock(return_value={})) as mock_send:
                r = client_no_secret.post("/webhook", json=payload)
        assert r.status_code == 200
        assert mock_send.call_count == 2

    def test_payload_with_only_statuses_returns_200_silently(self, client_no_secret):
        """Pure status payload (no messages) — 200 OK, no dispatch."""
        with patch("main.whatsapp_client.send_message", new=AsyncMock(return_value={})) as mock_send:
            r = client_no_secret.post("/webhook", json=_meta_statuses())
        assert r.status_code == 200
        assert mock_send.call_count == 0
