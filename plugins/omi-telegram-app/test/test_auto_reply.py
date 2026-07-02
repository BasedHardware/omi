"""Tests for plugins/omi-telegram-app/ T-004 — auto-reply dispatch.

The /webhook handler:
- Reads update from Telegram
- For known chats with auto_reply_enabled: calls persona_client.chat, then
  telegram_client.send_message with the reply.
- Safety: skip own (bot) messages, skip groups, skip non-text, skip when
  persona returns empty (timeout/connect error or empty reply).

Also covers:
- /toggle endpoint flips auto_reply_enabled for a chat_id and returns new state.
- /toggle endpoint rejects unknown chat_id with 404.
"""

import logging
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def telegram_api():
    """Mock httpx for telegram_client + main. Records calls."""
    calls: list[dict] = []

    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    async def _post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        body = kwargs.get("json") or {}
        if "setWebhook" in (url or ""):
            return _make_response(200, {"ok": True, "result": True})
        if "getMe" in (url or ""):
            return _make_response(200, {"ok": True, "result": {"username": "test_bot", "id": 999}})
        if "sendMessage" in (url or ""):
            return _make_response(200, {"ok": True, "result": {"message_id": 1}})
        return _make_response(200, {"ok": True, "result": None})

    client.post = AsyncMock(side_effect=_post)

    with patch("telegram_client.httpx.AsyncClient", return_value=client), patch(
        "telegram_client._get_client", return_value=client
    ):
        yield {"client": client, "calls": calls}


def _make_response(status_code: int, body: dict):
    return httpx.Response(
        status_code=status_code,
        json=body,
        request=httpx.Request("POST", "https://api.telegram.org/test"),
    )


@pytest.fixture
def persona_mock():
    """Patch the persona_chat call inside main.py. Returns an AsyncMock.

    main.py imports it as `_persona_chat` to avoid clashing with the
    `chat_id` parameter name in the webhook handler.
    """
    mock_chat = AsyncMock()
    with patch("main._persona_chat", new=mock_chat):
        yield mock_chat


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_update(chat_id, text, *, chat_type="private", from_id=None, from_is_bot=False):
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "from": {"id": from_id or chat_id, "first_name": "Alice", "is_bot": from_is_bot},
            "chat": {"id": chat_id, "type": chat_type},
            "text": text,
            "date": 1700000000,
        },
    }


def _seed_user(chat_id, *, auto_reply_enabled=True, **overrides):
    """Seed a user in simple_storage with the given auto_reply state."""
    from simple_storage import save_user, users

    users.clear()
    user = {
        "chat_id": str(chat_id),
        "omi_uid": "u-1",
        "persona_id": "p-1",
        "omi_dev_api_key": "omi_dev_k",
        "bot_token": "123:abc",
        "auto_reply_enabled": auto_reply_enabled,
    }
    user.update(overrides)
    save_user(
        chat_id=str(chat_id),
        omi_uid=user["omi_uid"],
        persona_id=user["persona_id"],
        omi_dev_api_key=user["omi_dev_api_key"],
        bot_token=user["bot_token"],
        auto_reply_enabled=user["auto_reply_enabled"],
    )
    return user


def _post_webhook(update, *, secret="default"):
    """Default = use real WEBHOOK_SECRET. 'none' = no header. str = use as-is."""
    from fastapi.testclient import TestClient

    from main import WEBHOOK_SECRET, app

    client = TestClient(app)
    headers = {}
    if secret == "default":
        headers["X-Telegram-Bot-Api-Secret-Token"] = WEBHOOK_SECRET
    elif secret != "none":
        headers["X-Telegram-Bot-Api-Secret-Token"] = secret
    return client.post("/webhook", json=update, headers=headers)


def _send_message_calls(calls):
    return [c for c in calls if "sendMessage" in (c.get("url") or "")]


# ---------------------------------------------------------------------------
# Auto-reply dispatch
# ---------------------------------------------------------------------------
class TestAutoReplyDispatch:
    def test_dispatches_to_persona_and_sends_reply(self, telegram_api, persona_mock):
        _seed_user(555, auto_reply_enabled=True)
        persona_mock.return_value = "Hello from Omi"

        resp = _post_webhook(_make_update(555, "hi"))
        assert resp.status_code == 200

        # persona_client.chat was called with the right args
        persona_mock.assert_awaited_once()
        call_kwargs = persona_mock.await_args.kwargs
        assert call_kwargs["app_id"] == "p-1"
        assert call_kwargs["api_key"] == "omi_dev_k"
        assert call_kwargs["text"] == "hi"

        # sendMessage was called with the reply
        sends = _send_message_calls(telegram_api["calls"])
        assert len(sends) == 1
        assert int(sends[0]["json"]["chat_id"]) == 555
        assert sends[0]["json"]["text"] == "Hello from Omi"

    def test_no_send_when_persona_returns_empty(self, telegram_api, persona_mock):
        """Persona returned '' (timeout or refusal) -> don't send anything."""
        _seed_user(555, auto_reply_enabled=True)
        persona_mock.return_value = ""

        resp = _post_webhook(_make_update(555, "hi"))
        assert resp.status_code == 200

        sends = _send_message_calls(telegram_api["calls"])
        assert sends == []

    def test_no_dispatch_when_persona_raises_http_error(self, telegram_api, persona_mock):
        """Persona 401/403/5xx -> logged, no crash, no send."""
        _seed_user(555, auto_reply_enabled=True)
        # Build a fake HTTP error with a request so httpx doesn't complain
        request = httpx.Request("POST", "https://api.omi.me/test")
        response = httpx.Response(status_code=401, request=request)
        persona_mock.side_effect = httpx.HTTPStatusError("401 Unauthorized", request=request, response=response)

        resp = _post_webhook(_make_update(555, "hi"))
        assert resp.status_code == 200

        sends = _send_message_calls(telegram_api["calls"])
        assert sends == []


# ---------------------------------------------------------------------------
# Safety filters
# ---------------------------------------------------------------------------
class TestSafetyFilters:
    def test_skips_group_chat(self, telegram_api, persona_mock):
        """Groups never auto-reply (out of scope for v1)."""
        _seed_user(555, auto_reply_enabled=True)
        resp = _post_webhook(_make_update(555, "hi", chat_type="group"))
        assert resp.status_code == 200

        persona_mock.assert_not_awaited()
        sends = _send_message_calls(telegram_api["calls"])
        assert sends == []

    def test_skips_supergroup_chat(self, telegram_api, persona_mock):
        _seed_user(555, auto_reply_enabled=True)
        resp = _post_webhook(_make_update(555, "hi", chat_type="supergroup"))
        assert resp.status_code == 200

        persona_mock.assert_not_awaited()

    def test_skips_channel_chat(self, telegram_api, persona_mock):
        _seed_user(555, auto_reply_enabled=True)
        resp = _post_webhook(_make_update(555, "hi", chat_type="channel"))
        assert resp.status_code == 200

        persona_mock.assert_not_awaited()

    def test_skips_message_from_a_bot(self, telegram_api, persona_mock):
        """Skip if sender is a bot (own-message safety)."""
        _seed_user(555, auto_reply_enabled=True)
        # from a different bot, not from the chat owner
        resp = _post_webhook(_make_update(555, "hi", from_id=12345, from_is_bot=True))
        assert resp.status_code == 200

        persona_mock.assert_not_awaited()

    def test_skips_message_with_no_text(self, telegram_api, persona_mock):
        """Voice notes, photos, stickers — no text — skip for v1."""
        _seed_user(555, auto_reply_enabled=True)
        update = {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "from": {"id": 555, "first_name": "Alice", "is_bot": False},
                "chat": {"id": 555, "type": "private"},
                # no `text` field — voice message
                "voice": {"file_id": "abc", "duration": 3},
                "date": 1700000000,
            },
        }
        resp = _post_webhook(update)
        assert resp.status_code == 200

        persona_mock.assert_not_awaited()

    def test_skips_when_auto_reply_disabled_still_nudges(self, telegram_api, persona_mock):
        """auto_reply=False -> don't dispatch, but DO send the nudge (existing T-003 behavior)."""
        _seed_user(555, auto_reply_enabled=False)
        resp = _post_webhook(_make_update(555, "hi"))
        assert resp.status_code == 200

        persona_mock.assert_not_awaited()
        # The nudge reply should still be sent
        sends = _send_message_calls(telegram_api["calls"])
        assert len(sends) == 1
        assert "disabled" in sends[0]["json"]["text"].lower()


# ---------------------------------------------------------------------------
# /toggle endpoint
# ---------------------------------------------------------------------------
class TestToggle:
    def test_toggle_enables_when_disabled(self, telegram_api, persona_mock):
        from fastapi.testclient import TestClient

        from main import app
        from simple_storage import users

        users.clear()
        _seed_user(777, auto_reply_enabled=False)

        client = TestClient(app)
        resp = client.post("/toggle", json={"chat_id": "777", "enabled": True})
        assert resp.status_code == 200
        assert resp.json() == {"chat_id": "777", "auto_reply_enabled": True}

        # Verify in storage
        assert users["777"]["auto_reply_enabled"] is True

    def test_toggle_disables_when_enabled(self, telegram_api, persona_mock):
        from fastapi.testclient import TestClient

        from main import app
        from simple_storage import users

        users.clear()
        _seed_user(777, auto_reply_enabled=True)

        client = TestClient(app)
        resp = client.post("/toggle", json={"chat_id": "777", "enabled": False})
        assert resp.status_code == 200
        assert resp.json() == {"chat_id": "777", "auto_reply_enabled": False}

        assert users["777"]["auto_reply_enabled"] is False

    def test_toggle_unknown_chat_returns_403(self, telegram_api, persona_mock):
        """After the PR #8528 security redesign: /toggle no longer
        accepts a bot_token parameter. Auth is via the plugin bearer
        (Authorization: Bearer header); the chat_id alone identifies
        the chat. Unknown chat_id -> 403 (no token-check path to test
        any more)."""
        from fastapi.testclient import TestClient

        from main import app
        from simple_storage import users

        users.clear()

        client = TestClient(app)
        resp = client.post("/toggle", json={"chat_id": "no-such-chat", "enabled": True})
        assert resp.status_code == 403

    def test_toggle_does_not_require_bot_token(self, telegram_api, persona_mock):
        """P1 (Git-on-my-level review): the manifest must not require
        the caller to send the bot_token. Verify /toggle accepts a
        request with only chat_id + enabled (no credential in body).
        This is the core invariant that lets chat users toggle without
        exposing long-lived secrets through chat."""
        from fastapi.testclient import TestClient

        from main import app
        from simple_storage import users

        users.clear()
        _seed_user(777, auto_reply_enabled=False)

        client = TestClient(app)
        resp = client.post(
            "/toggle",
            json={"chat_id": "777", "enabled": True},
        )
        assert resp.status_code == 200, (
            f"chat_id-only toggle must work after the security redesign. "
            f"Got {resp.status_code}: {resp.text}"
        )
        assert resp.json() == {"chat_id": "777", "auto_reply_enabled": True}

    def test_toggle_rejects_extra_bot_token_in_body(self, telegram_api, persona_mock):
        """If a caller (e.g. a misconfigured chat assistant) sends
        bot_token in the body, the request must NOT silently use it
        for auth. The new ToggleRequest model has no bot_token field;
        Pydantic will accept the extra field (default behavior) but the
        auth path no longer reads it — the toggle should still succeed
        via chat_id alone. This proves a leftover bot_token in the body
        can't weaken the security model."""
        from fastapi.testclient import TestClient

        from main import app
        from simple_storage import users

        users.clear()
        _seed_user(777, auto_reply_enabled=False, bot_token="real-token")

        client = TestClient(app)
        # Caller sends a WRONG bot_token in the body. If the auth
        # path still read bot_token, this would 403. Under the new
        # bearer+chat_id auth model, it must succeed because the
        # bot_token in the body is ignored.
        resp = client.post(
            "/toggle",
            json={"chat_id": "777", "enabled": True, "bot_token": "WRONG-TOKEN"},
        )
        assert resp.status_code == 200, (
            f"bot_token in body must be ignored (not used for auth). "
            f"Got {resp.status_code}: {resp.text}"
        )

    def test_toggle_missing_required_field_returns_422(self, telegram_api, persona_mock):
        """Pydantic should reject the request if `enabled` is missing
        (the only non-chat_id required field after the redesign)."""
        from fastapi.testclient import TestClient

        from main import app
        from simple_storage import users

        users.clear()
        _seed_user(777, auto_reply_enabled=True)

        client = TestClient(app)
        resp = client.post(
            "/toggle",
            json={"chat_id": "777"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Defense-in-depth: persona dispatch error path must not leak the omi_dev_api_key
# or uid in logs. (Cubic flagged the setup path; this guards the dispatch path.)
# ---------------------------------------------------------------------------
class TestDispatchErrorPathDoesNotLeakSecrets:
    @pytest.mark.asyncio
    async def test_dispatch_logs_status_code_not_url_on_http_status_error(self, caplog):
        from main import _dispatch_auto_reply
        import httpx

        request = httpx.Request("POST", "https://api.omi.me/v2/integrations/p-1/user/persona-chat?uid=u-secret")
        response = httpx.Response(503, request=request)
        err = httpx.HTTPStatusError("503", request=request, response=response)

        with patch("main._persona_chat", new=AsyncMock(side_effect=err)):
            with caplog.at_level(logging.ERROR, logger="omi-telegram-clone"):
                await _dispatch_auto_reply(
                    user={
                        "persona_id": "p-1",
                        "omi_dev_api_key": "SECRET_API_KEY_DO_NOT_LOG",
                        "bot_token": "bt",
                        "omi_uid": "u-secret",
                    },
                    chat_id="42",
                    text="hello",
                )

        # The API key must not appear in any log record.
        leaked = [r for r in caplog.records if "SECRET_API_KEY_DO_NOT_LOG" in r.getMessage()]
        assert not leaked, f"api_key leaked into logs: {[r.getMessage() for r in leaked]}"
        # The uid IS allowed (it's the caller's own uid, not a secret) but the
        # status code should be there.
        assert any(
            "HTTP 503" in r.getMessage() for r in caplog.records
        ), "expected log message to include 'HTTP 503' (status code)"

    @pytest.mark.asyncio
    async def test_dispatch_logs_type_name_not_str_for_connect_error(self, caplog):
        from main import _dispatch_auto_reply
        import httpx

        request = httpx.Request("POST", "https://api.omi.me/v2/integrations/p-1/user/persona-chat?uid=u-secret")
        err = httpx.ConnectError("boom", request=request)

        with patch("main._persona_chat", new=AsyncMock(side_effect=err)):
            with caplog.at_level(logging.ERROR, logger="omi-telegram-clone"):
                await _dispatch_auto_reply(
                    user={
                        "persona_id": "p-1",
                        "omi_dev_api_key": "SECRET_API_KEY_DO_NOT_LOG",
                        "bot_token": "bt",
                        "omi_uid": "u-secret",
                    },
                    chat_id="42",
                    text="hello",
                )

        leaked = [r for r in caplog.records if "SECRET_API_KEY_DO_NOT_LOG" in r.getMessage()]
        assert not leaked
        # Should log the type name, not str(e)
        assert any("ConnectError" in r.getMessage() for r in caplog.records)
