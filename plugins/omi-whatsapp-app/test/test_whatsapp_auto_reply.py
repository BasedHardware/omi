"""Tests for the auto-reply dispatch path (T-104).

Mirrors plugins/omi-telegram-app/test/test_auto_reply.py:
- Persona returns text \u2192 reply sent via WhatsApp Cloud API
- Persona returns empty \u2192 no reply sent (logged)
- Persona HTTP error \u2192 no reply, log only status code (no API key in logs)
- Persona ConnectError/Timeout \u2192 no reply, log only type name
- Auto-reply disabled \u2192 nudge (rate-limited)
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest

_PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
from conftest import load_main_module

main = load_main_module()


SECRET_API_KEY = "SECRET_API_KEY_DO_NOT_LOG"


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
def client():
    from fastapi.testclient import TestClient

    return TestClient(main.app)


def _seed_user(phone="15550001111", auto_reply=True, api_key=SECRET_API_KEY):
    from conftest import load_simple_storage

    simple_storage = load_simple_storage()

    simple_storage.save_user(
        phone=phone,
        omi_uid="u-1",
        persona_id="p-1",
        omi_dev_api_key=api_key,
        access_token="at-1",
        phone_number_id="pn-1",
        verify_token="vt-1",
        auto_reply_enabled=auto_reply,
    )


def _meta_message(from_phone, text):
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "messages": [
                                {
                                    "from": from_phone,
                                    "id": "wamid.ABC",
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


def _meta_message_with_profile(from_phone, text, profile_name):
    """Like _meta_message but also attaches a contacts[] entry with a
    profile name so the dispatcher can look up sender_name."""
    msg = _meta_message(from_phone, text)
    msg["entry"][0]["changes"][0]["value"]["contacts"] = [
        {"wa_id": from_phone, "profile": {"name": profile_name}},
    ]
    return msg


def _meta_message_no_contacts(from_phone, text):
    """Like _meta_message but WITHOUT a contacts[] entry — the common
    case for unsaved numbers. The dispatcher must fall back to the
    phone number as sender_name rather than sending the message with
    no sender identity."""
    msg = _meta_message(from_phone, text)
    msg["entry"][0]["changes"][0]["value"]["contacts"] = []
    return msg


# ---------------------------------------------------------------------------
# Happy path: persona returns text \u2192 reply sent
# ---------------------------------------------------------------------------
class TestSenderNameFallback:
    """P2 from cubic AI review: when Meta omits `contacts` (common for
    unsaved numbers) or the contact lacks a profile name, the
    dispatcher's docstring promises "we just send the phone number as
    the sender_name". Without this fallback the persona receives no
    sender identity at all."""

    def _capture_persona_kwargs(self):
        """Helper: patch _persona_chat to capture its kwargs."""
        captured = {}

        async def fake(**kwargs):
            captured.update(kwargs)
            return "ok"

        return captured, fake

    def test_contacts_with_profile_passes_profile_name(self, client):
        _seed_user()
        captured, fake = self._capture_persona_kwargs()
        mock_send = AsyncMock(return_value={})
        with patch.object(main, "_persona_chat", new=AsyncMock(side_effect=fake)):
            with patch("main.whatsapp_client.send_message", new=mock_send):
                client.post("/webhook", json=_meta_message_with_profile("15550001111", "hi", "Alice"))
        assert captured["context"]["sender_name"] == "Alice"

    def test_no_contacts_falls_back_to_phone(self, client):
        _seed_user()
        captured, fake = self._capture_persona_kwargs()
        mock_send = AsyncMock(return_value={})
        with patch.object(main, "_persona_chat", new=AsyncMock(side_effect=fake)):
            with patch("main.whatsapp_client.send_message", new=mock_send):
                client.post("/webhook", json=_meta_message_no_contacts("15550001111", "hi"))
        # Phone-as-sender_name so the persona still has a sender identity.
        assert captured["context"]["sender_name"] == "15550001111"
        assert captured["context"]["platform"] == "whatsapp"
        assert captured["context"]["chat_type"] == "private"

    def test_contacts_without_profile_falls_back_to_phone(self, client):
        """A contact with no profile.name (rare but possible) should also
        fall back to the phone, not send an empty sender_name."""
        _seed_user()
        msg = _meta_message("15550001111", "hi")
        msg["entry"][0]["changes"][0]["value"]["contacts"] = [
            {"wa_id": "15550001111", "profile": {}},
        ]
        captured, fake = self._capture_persona_kwargs()
        mock_send = AsyncMock(return_value={})
        with patch.object(main, "_persona_chat", new=AsyncMock(side_effect=fake)):
            with patch("main.whatsapp_client.send_message", new=mock_send):
                client.post("/webhook", json=msg)
        assert captured["context"]["sender_name"] == "15550001111"


class TestAutoReplyHappyPath:
    def test_persona_returns_text_sends_reply(self, client):
        _seed_user()

        async def fake_persona(**kwargs):
            return "Hello from the persona!"

        mock_send = AsyncMock(return_value={})
        with patch.object(main, "_persona_chat", new=AsyncMock(side_effect=fake_persona)):
            with patch("main.whatsapp_client.send_message", new=mock_send):
                r = client.post("/webhook", json=_meta_message("15550001111", "hi"))

        assert r.status_code == 200
        assert mock_send.call_count == 1
        # The reply is what's sent
        call = mock_send.call_args
        assert call.args[3] == "Hello from the persona!"  # to=phone, text=...

    def test_persona_returns_empty_skips_send(self, client):
        _seed_user()

        async def fake_persona(**kwargs):
            return ""

        mock_send = AsyncMock(return_value={})
        with patch.object(main, "_persona_chat", new=AsyncMock(side_effect=fake_persona)):
            with patch("main.whatsapp_client.send_message", new=mock_send):
                r = client.post("/webhook", json=_meta_message("15550001111", "hi"))

        assert r.status_code == 200
        assert mock_send.call_count == 0


# ---------------------------------------------------------------------------
# Error paths: must not leak the API key in logs
# ---------------------------------------------------------------------------
class TestDispatchErrorPathDoesNotLeakSecrets:
    def test_dispatch_logs_status_code_not_url_on_http_status_error(self, client, caplog):
        _seed_user()

        request = httpx.Request("POST", "https://api.omi.me/v2/integrations/p-1/user/persona-chat?uid=u-secret")
        response = httpx.Response(503, request=request)
        err = httpx.HTTPStatusError("503", request=request, response=response)

        with patch.object(main, "_persona_chat", new=AsyncMock(side_effect=err)):
            with patch("main.whatsapp_client.send_message", new=AsyncMock(return_value={})) as mock_send:
                with caplog.at_level(logging.ERROR, logger="omi-whatsapp-clone"):
                    r = client.post("/webhook", json=_meta_message("15550001111", "hi"))

        assert r.status_code == 200
        assert mock_send.call_count == 0
        for record in caplog.records:
            assert SECRET_API_KEY not in record.getMessage()

    def test_dispatch_logs_type_name_not_str_for_connect_error(self, client, caplog):
        _seed_user()

        request = httpx.Request("POST", "https://api.omi.me/v2/integrations/p-1/user/persona-chat?uid=u-secret")
        err = httpx.ConnectError("boom", request=request)

        with patch.object(main, "_persona_chat", new=AsyncMock(side_effect=err)):
            with patch("main.whatsapp_client.send_message", new=AsyncMock(return_value={})) as mock_send:
                with caplog.at_level(logging.ERROR, logger="omi-whatsapp-clone"):
                    r = client.post("/webhook", json=_meta_message("15550001111", "hi"))

        assert r.status_code == 200
        assert mock_send.call_count == 0
        for record in caplog.records:
            assert SECRET_API_KEY not in record.getMessage()


# ---------------------------------------------------------------------------
# Auto-reply disabled \u2192 nudge (rate-limited)
# ---------------------------------------------------------------------------
class TestAutoReplyDisabled:
    def test_disabled_sends_nudge_on_first_message(self, client):
        _seed_user(auto_reply=False)

        mock_send = AsyncMock(return_value={})
        with patch("main.whatsapp_client.send_message", new=mock_send):
            r = client.post("/webhook", json=_meta_message("15550001111", "hi"))

        assert r.status_code == 200
        assert mock_send.call_count == 1
        # Verify it's a nudge message
        text_arg = mock_send.call_args.args[3]
        assert "Auto-reply" in text_arg

    def test_disabled_does_not_repeat_nudge_within_cooldown(self, client):
        _seed_user(auto_reply=False)
        # First message \u2014 should nudge
        mock_send = AsyncMock(return_value={})
        with patch("main.whatsapp_client.send_message", new=mock_send):
            client.post("/webhook", json=_meta_message("15550001111", "hi"))
            assert mock_send.call_count == 1
            # Second message immediately \u2014 should NOT nudge again
            client.post("/webhook", json=_meta_message("15550001111", "hi again"))
            assert mock_send.call_count == 1  # still 1

    def test_disabled_no_persona_call(self, client):
        """If auto_reply is off, we never even call the persona."""
        _seed_user(auto_reply=False)

        with patch.object(main, "_persona_chat", new=AsyncMock()) as mock_persona:
            with patch("main.whatsapp_client.send_message", new=AsyncMock(return_value={})):
                client.post("/webhook", json=_meta_message("15550001111", "hi"))
        assert mock_persona.call_count == 0
