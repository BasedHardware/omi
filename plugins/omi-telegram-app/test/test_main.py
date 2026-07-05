"""Tests for plugins/omi-telegram-app/main.py (T-003).

Covers the plugin skeleton + setup flow:
- /health returns 200
- /setup registers the bot's webhook with Telegram and returns a deep link
- /webhook rejects requests missing the X-Telegram-Bot-Api-Secret-Token header
- /webhook with /start <setup_token> stores the chat_id -> user mapping and
  sends a "Connected!" confirmation message
- /webhook with a regular message from an unknown chat returns 200 silently
- /webhook with a regular message from a known chat where auto_reply is disabled
  replies with "Auto-reply not enabled"
- simple_storage round-trip: pending_setups + users
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup: plugin's main.py imports from sibling modules and from
# plugins/_shared/persona_client. We add both before any import.
# ---------------------------------------------------------------------------
_PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.abspath(os.path.join(_PLUGIN_DIR, ".."))
_SHARED = os.path.abspath(os.path.join(_PLUGIN_ROOT, "..", "_shared"))
for p in (_PLUGIN_ROOT, _SHARED):
    if p not in sys.path:
        sys.path.insert(0, p)


# ---------------------------------------------------------------------------
# Mock httpx.AsyncClient globally before main.py imports.
# We don't yet know the full set of Telegram API calls main.py makes; the
# fixture below installs a default handler that returns sensible responses
# for setWebhook, getMe, sendMessage, and otherwise records the call.
# ---------------------------------------------------------------------------
@pytest.fixture
def telegram_api():
    """Patch httpx.AsyncClient used by main.py + telegram_client.py.

    Returns an AsyncMock whose `.post()` records the request and returns a
    canned response based on the URL. Tests inspect `calls` to assert what
    the plugin sent to Telegram.
    """
    calls: list[dict] = []

    def _handler(self_or_client, url=None, **kwargs):
        # httpx signature: client.post(url, **kwargs). Some test setups may
        # patch differently; accept both shapes.
        calls.append({"url": url, **kwargs})
        # Default response shape: simple JSON envelope
        body = kwargs.get("json") or {}
        if "setWebhook" in (url or ""):
            return _make_response(200, {"ok": True, "result": True})
        if "getMe" in (url or ""):
            return _make_response(200, {"ok": True, "result": {"username": "test_clone_bot", "id": 999}})
        if "sendMessage" in (url or ""):
            return _make_response(200, {"ok": True, "result": {"message_id": 1}})
        return _make_response(200, {"ok": True, "result": None})

    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)

    async def _post(url, **kwargs):
        return _handler(client, url, **kwargs)

    client.post = AsyncMock(side_effect=_post)

    with patch("telegram_client.httpx.AsyncClient", return_value=client), patch(
        "telegram_client._get_client", return_value=client
    ):
        yield {"client": client, "calls": calls}


def _make_response(status_code: int, body: dict):
    import httpx

    return httpx.Response(
        status_code=status_code,
        json=body,
        request=httpx.Request("POST", "https://api.telegram.org/test"),
    )


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------
class TestHealth:
    def test_health_returns_200(self):
        from fastapi.testclient import TestClient

        from main import app

        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestLifespanClosesClient:
    """P2 from cubic AI review (PR #8682): the FastAPI lifespan must
    call telegram_client.aclose() on shutdown so the module-level
    httpx.AsyncClient pool isn't held open until process exit. The
    fixture is per-test so we can patch aclose() and watch for the
    call when the TestClient context exits."""

    def test_aclose_called_on_shutdown(self):
        from unittest.mock import AsyncMock, patch

        from fastapi.testclient import TestClient

        from main import app

        with patch("main.telegram_client.aclose", new=AsyncMock()) as mock_aclose:
            with TestClient(app) as client:
                # Any request triggers startup, which schedules the
                # shutdown hook. Trigger one to be safe.
                client.get("/health")
            # TestClient context exit runs the lifespan shutdown,
            # which must call aclose() exactly once.
            assert mock_aclose.await_count == 1


# ---------------------------------------------------------------------------
# /setup
# ---------------------------------------------------------------------------
class TestSetup:
    def _post_setup(self, telegram_api):
        from fastapi.testclient import TestClient

        from main import app

        client = TestClient(app)
        return client.post(
            "/setup",
            json={
                "bot_token": "123:abc",
                "omi_uid": "user-1",
                "persona_id": "persona-abc",
                "omi_dev_api_key": "omi_dev_test",
                "public_base_url": "https://clone.example.com",
            },
        )

    def test_setup_returns_deep_link(self, telegram_api):
        resp = self._post_setup(telegram_api)
        assert resp.status_code == 200
        body = resp.json()
        assert "deep_link" in body
        assert body["deep_link"].startswith("https://t.me/")
        assert "?start=" in body["deep_link"]
        assert body["bot_username"] == "test_clone_bot"

    def test_setup_calls_set_webhook(self, telegram_api):
        self._post_setup(telegram_api)
        urls_called = [c["url"] for c in telegram_api["calls"]]
        # setWebhook must be among the calls
        assert any("setWebhook" in u for u in urls_called), f"setWebhook not in {urls_called}"
        set_webhook_call = next(c for c in telegram_api["calls"] if "setWebhook" in (c["url"] or ""))
        # The webhook URL is in the JSON body, not the URL field (which is the Telegram API URL)
        body = set_webhook_call.get("json") or {}
        assert "https://clone.example.com" in body.get("url", "")
        assert "secret_token" in body  # and a secret_token is set

    def test_setup_calls_get_me(self, telegram_api):
        self._post_setup(telegram_api)
        urls_called = [c["url"] for c in telegram_api["calls"]]
        assert any("getMe" in u for u in urls_called), f"getMe not in {urls_called}"

    def test_setup_stores_pending_setup_token(self, telegram_api):
        from simple_storage import pending_setups

        pending_setups.clear()
        resp = self._post_setup(telegram_api)
        token = resp.json()["deep_link"].split("?start=")[1]
        assert token in pending_setups
        assert pending_setups[token]["omi_uid"] == "user-1"
        assert pending_setups[token]["bot_token"] == "123:abc"
        assert pending_setups[token]["persona_id"] == "persona-abc"

    def test_setup_returns_502_when_set_webhook_fails(self, telegram_api):
        # Override the handler to fail setWebhook
        from fastapi.testclient import TestClient

        from main import app

        async def _fail_set_webhook(url, **kwargs):
            if "setWebhook" in (url or ""):
                return _make_response(400, {"ok": False, "description": "bad webhook url"})
            if "getMe" in (url or ""):
                return _make_response(200, {"ok": True, "result": {"username": "x"}})
            return _make_response(200, {"ok": True})

        telegram_api["client"].post = AsyncMock(side_effect=_fail_set_webhook)

        client = TestClient(app)
        resp = client.post(
            "/setup",
            json={
                "bot_token": "bad",
                "omi_uid": "user-1",
                "persona_id": "p",
                "omi_dev_api_key": "k",
                "public_base_url": "ftp://nope",
            },
        )
        assert resp.status_code in (502, 500)


# ---------------------------------------------------------------------------
# /webhook
# ---------------------------------------------------------------------------
class TestWebhook:
    def _post_webhook(self, update, secret="default"):
        """secret: "default" -> use WEBHOOK_SECRET, "none" -> no header, str -> use as-is."""
        from fastapi.testclient import TestClient

        from main import app, WEBHOOK_SECRET

        client = TestClient(app)
        headers = {}
        if secret == "default":
            headers["X-Telegram-Bot-Api-Secret-Token"] = WEBHOOK_SECRET
        elif secret == "none":
            pass  # explicitly no header
        else:
            headers["X-Telegram-Bot-Api-Secret-Token"] = secret
        return client.post("/webhook", json=update, headers=headers)

    def _make_update(self, chat_id: int, text: str, from_id: int | None = None):
        return {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "from": {"id": from_id or chat_id, "first_name": "Alice"},
                "chat": {"id": chat_id, "type": "private"},
                "text": text,
                "date": 1700000000,
            },
        }

    def test_webhook_rejects_without_secret_header(self, telegram_api):
        resp = self._post_webhook(self._make_update(123, "hi"), secret="none")
        assert resp.status_code == 401

    def test_webhook_rejects_with_wrong_secret(self, telegram_api):
        resp = self._post_webhook(self._make_update(123, "hi"), secret="wrong-secret")
        assert resp.status_code == 401

    def test_webhook_unknown_chat_returns_200_silently(self, telegram_api):
        resp = self._post_webhook(self._make_update(999, "hi"))
        assert resp.status_code == 200

    def test_webhook_start_command_stores_chat_mapping_and_replies(self, telegram_api):
        # First, run /setup to populate pending_setups
        from fastapi.testclient import TestClient

        from main import app
        from simple_storage import pending_setups, users

        pending_setups.clear()
        users.clear()

        setup_client = TestClient(app)
        setup_resp = setup_client.post(
            "/setup",
            json={
                "bot_token": "123:abc",
                "omi_uid": "user-1",
                "persona_id": "persona-abc",
                "omi_dev_api_key": "omi_dev_test",
                "public_base_url": "https://clone.example.com",
            },
        )
        token = setup_resp.json()["deep_link"].split("?start=")[1]

        # Now simulate the user clicking the deep link and sending /start <token>
        chat_id = 555
        update = self._make_update(chat_id, f"/start {token}")
        resp = self._post_webhook(update)
        assert resp.status_code == 200

        # chat_id should now be in users
        assert str(chat_id) in users
        assert users[str(chat_id)]["omi_uid"] == "user-1"
        assert users[str(chat_id)]["persona_id"] == "persona-abc"
        assert users[str(chat_id)]["omi_dev_api_key"] == "omi_dev_test"
        assert users[str(chat_id)]["auto_reply_enabled"] is False

        # A confirmation message should have been sent via sendMessage
        urls_called = [c["url"] for c in telegram_api["calls"]]
        assert any("sendMessage" in u for u in urls_called)

    def test_webhook_regular_message_with_auto_reply_disabled_replies(self, telegram_api):
        from fastapi.testclient import TestClient

        from main import app
        from simple_storage import users

        users.clear()
        users["777"] = {
            "omi_uid": "user-1",
            "persona_id": "persona-abc",
            "omi_dev_api_key": "omi_dev_test",
            "bot_token": "123:abc",
            "auto_reply_enabled": False,
        }

        update = self._make_update(777, "hello")
        resp = self._post_webhook(update)
        assert resp.status_code == 200

        # The handler should have sent a "not enabled" reply AND the body
        # must mention the user-facing guidance text — otherwise a
        # regression that sends an empty/stale message would slip past
        # the URL-only check. P2 (cubic): the URL assertion alone is
        # insufficient — any sendMessage call would pass.
        send_calls = [c for c in telegram_api["calls"] if "sendMessage" in c["url"]]
        assert send_calls, "expected a sendMessage call for the nudge"
        # The telegram_api fixture records the httpx call kwargs: url, json, etc.
        bodies = []
        for c in send_calls:
            if c.get("json"):
                body_text = c["json"].get("text", "") if isinstance(c["json"], dict) else ""
                bodies.append(body_text)
        assert any(bodies), f"sendMessage call had no body text: {send_calls!r}"
        # At least one body must include the actionable guidance text
        # (case-insensitive). The exact wording can change but the user
        # MUST be told to enable auto-reply in the desktop.
        assert any(
            "auto-reply" in (b or "").lower() or "auto reply" in (b or "").lower() for b in bodies
        ), f"nudge body should mention 'auto-reply', got: {bodies!r}"

    def test_webhook_regular_message_from_unknown_chat_does_not_reply(self, telegram_api):
        # /webhook from a chat that has never been set up -> 200, no sendMessage
        update = self._make_update(99999, "hello")
        resp = self._post_webhook(update)
        assert resp.status_code == 200
        urls_called = [c["url"] for c in telegram_api["calls"]]
        assert not any("sendMessage" in u for u in urls_called)


# ---------------------------------------------------------------------------
# simple_storage round-trip
# ---------------------------------------------------------------------------
class TestSimpleStorage:
    def test_users_round_trip(self):
        from simple_storage import save_user, get_user_by_chat_id, users

        users.clear()
        save_user(
            chat_id="42",
            omi_uid="u-1",
            persona_id="p-1",
            omi_dev_api_key="k-1",
            bot_token="bot-1",
        )
        loaded = get_user_by_chat_id("42")
        assert loaded is not None
        assert loaded["omi_uid"] == "u-1"
        assert loaded["bot_token"] == "bot-1"
        assert loaded["auto_reply_enabled"] is False

    def test_pending_setups_round_trip(self):
        from simple_storage import save_pending_setup, pop_pending_setup, pending_setups

        pending_setups.clear()
        save_pending_setup("tok-1", {"omi_uid": "u-1", "bot_token": "bt"})
        popped = pop_pending_setup("tok-1")
        assert popped["omi_uid"] == "u-1"
        # Second pop returns None (one-shot)
        assert pop_pending_setup("tok-1") is None

    def test_pop_pending_setup_no_op_skips_disk_write(self):
        """P2 from cubic AI review (PR #8682): pop_pending_setup must
        NOT touch the disk when both the token lookup AND the stale
        purge are no-ops. The webhook hits this path on every
        forged / unknown setup token, so the previous 'always rewrite'
        behavior wasted an fsync + JSON serialize per request."""
        from unittest.mock import patch

        from simple_storage import pending_setups, pop_pending_setup, save_pending_setup

        pending_setups.clear()
        save_pending_setup("tok-real", {"omi_uid": "u-1"})
        save_pending_setup("tok-real-2", {"omi_uid": "u-2"})  # so the dict isn't emptied by the pop

        with patch("simple_storage._save") as mock_save:
            # Unknown token, no stale entries — must NOT call _save.
            result = pop_pending_setup("tok-forged")
            assert result is None
            assert mock_save.call_count == 0

        # A real pop still persists (writes the smaller dict).
        with patch("simple_storage._save") as mock_save:
            result = pop_pending_setup("tok-real")
            assert result is not None
            assert mock_save.call_count == 1

    def test_update_auto_reply(self):
        from simple_storage import save_user, update_auto_reply, get_user_by_chat_id, users

        users.clear()
        save_user(chat_id="42", omi_uid="u-1", persona_id="p-1", omi_dev_api_key="k-1", bot_token="bt")
        update_auto_reply("42", True)
        assert get_user_by_chat_id("42")["auto_reply_enabled"] is True
        update_auto_reply("42", False)
        assert get_user_by_chat_id("42")["auto_reply_enabled"] is False
