"""Tests for review fixes (T-001..T-004 follow-up).

Covers:
- C2  Nudge cooldown: should_nudge + mark_nudged behavior at the webhook level.
- C3  Atomic file writes: _save uses os.replace and writes to .tmp.
- W6  Reply truncation: telegram_client.send_message truncates > 4096 chars.
- W8  /start with no token: silently 200s, no sendMessage.
- Malformed JSON in webhook: silently 200s, no crash.
"""

import json
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


def _send_message_calls(calls):
    return [c for c in calls if "sendMessage" in (c.get("url") or "")]


def _seed_user(chat_id, *, auto_reply_enabled=True):
    from simple_storage import save_user, users

    users.clear()
    save_user(
        chat_id=str(chat_id),
        omi_uid="u-1",
        persona_id="p-1",
        omi_dev_api_key="k",
        bot_token="bt",
        auto_reply_enabled=auto_reply_enabled,
    )


def _post_webhook(update, *, secret="default", raw_body=None, content_type=None):
    from fastapi.testclient import TestClient

    from main import WEBHOOK_SECRET, app

    client = TestClient(app)
    headers = {}
    if secret == "default":
        headers["X-Telegram-Bot-Api-Secret-Token"] = WEBHOOK_SECRET
    elif secret != "none":
        headers["X-Telegram-Bot-Api-Secret-Token"] = secret
    if raw_body is not None:
        if content_type:
            headers["Content-Type"] = content_type
        return client.post("/webhook", content=raw_body, headers=headers)
    return client.post("/webhook", json=update, headers=headers)


def _make_update(chat_id, text, **kwargs):
    return {
        "update_id": 1,
        "message": {
            "message_id": 1,
            "from": {"id": chat_id, "first_name": "A", "is_bot": False},
            "chat": {"id": chat_id, "type": kwargs.get("chat_type", "private")},
            "text": text,
            "date": 1700000000,
        },
    }


# ---------------------------------------------------------------------------
# C2 — Nudge cooldown
# ---------------------------------------------------------------------------
class TestNudgeCooldown:
    def test_first_message_with_auto_reply_disabled_nudges(self, telegram_api):
        from simple_storage import users

        users.clear()
        _seed_user(555, auto_reply_enabled=False)
        resp = _post_webhook(_make_update(555, "hi"))
        assert resp.status_code == 200
        assert len(_send_message_calls(telegram_api["calls"])) == 1

    def test_second_message_within_cooldown_does_not_nudge(self, telegram_api):
        from simple_storage import users

        users.clear()
        _seed_user(555, auto_reply_enabled=False)
        # First message -> nudge
        _post_webhook(_make_update(555, "hi 1"))
        # Second message immediately after -> no nudge (cooldown active)
        _post_webhook(_make_update(555, "hi 2"))
        sends = _send_message_calls(telegram_api["calls"])
        assert len(sends) == 1, f"expected exactly 1 nudge, got {len(sends)}"

    def test_message_after_cooldown_nudges_again(self, telegram_api):
        from simple_storage import users

        users.clear()
        _seed_user(555, auto_reply_enabled=False)
        # First nudge
        _post_webhook(_make_update(555, "hi 1"))
        # Simulate long elapsed time by rewriting last_nudge_at to the past
        from datetime import datetime, timedelta

        users["555"]["last_nudge_at"] = (datetime.utcnow() - timedelta(hours=5)).isoformat()
        # Next message -> cooldown elapsed -> nudge again
        _post_webhook(_make_update(555, "hi 2"))
        sends = _send_message_calls(telegram_api["calls"])
        assert len(sends) == 2, f"expected 2 nudges after cooldown, got {len(sends)}"

    def test_should_nudge_helper_returns_true_for_missing(self):
        from simple_storage import should_nudge

        assert should_nudge({}, 60) is True
        assert should_nudge({"last_nudge_at": None}, 60) is True

    def test_should_nudge_helper_returns_false_within_window(self):
        from datetime import datetime

        from simple_storage import should_nudge

        user = {"last_nudge_at": datetime.utcnow().isoformat()}
        assert should_nudge(user, 60) is False

    def test_should_nudge_helper_returns_true_after_window(self):
        from datetime import datetime, timedelta

        from simple_storage import should_nudge

        user = {"last_nudge_at": (datetime.utcnow() - timedelta(seconds=120)).isoformat()}
        assert should_nudge(user, 60) is True


# ---------------------------------------------------------------------------
# C3 — Atomic file writes
# ---------------------------------------------------------------------------
class TestAtomicWrites:
    def test_save_writes_via_tmp_and_replace(self, tmp_path, monkeypatch):
        from simple_storage import _save

        target = tmp_path / "users_data.json"
        captured: dict = {}

        real_replace = os.replace

        def _spy_replace(src, dst):
            captured["src"] = src
            captured["dst"] = dst
            return real_replace(src, dst)

        monkeypatch.setattr("simple_storage.os.replace", _spy_replace)

        _save(str(target), {"a": 1})

        # Verify .tmp was used as the source and was cleaned up after replace
        assert captured.get("dst") == str(target)
        assert not os.path.exists(str(target) + ".tmp")
        # Verify final file content
        with open(target) as f:
            assert json.load(f) == {"a": 1}

    def test_save_cleans_up_tmp_on_failure(self, tmp_path, monkeypatch):
        from simple_storage import _save

        target = tmp_path / "users_data.json"

        def _boom(*_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr("simple_storage.json.dump", _boom)

        _save(str(target), {"a": 1})

        # Tmp should not be left behind
        assert not os.path.exists(str(target) + ".tmp")
        # Original file should not exist (since we never wrote it)
        assert not os.path.exists(str(target))


# ---------------------------------------------------------------------------
# W6 — Reply truncation
# ---------------------------------------------------------------------------
class TestReplyTruncation:
    @pytest.mark.asyncio
    async def test_short_text_passed_through(self, telegram_api):
        from telegram_client import send_message

        result = await send_message("bt", 555, "hello")
        assert result is not None
        sends = _send_message_calls(telegram_api["calls"])
        assert sends[0]["json"]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_text_over_4096_truncated_with_ellipsis(self, telegram_api):
        from telegram_client import send_message

        long_text = "a" * 5000
        await send_message("bt", 555, long_text)
        sends = _send_message_calls(telegram_api["calls"])
        sent_text = sends[0]["json"]["text"]
        assert len(sent_text) == 4096
        # Last char is the ellipsis (U+2026)
        assert sent_text[-1] == "\u2026"
        # Original text was truncated
        assert sent_text.startswith("a" * 100)


# ---------------------------------------------------------------------------
# W8 — /start without token
# ---------------------------------------------------------------------------
class TestStartNoToken:
    def test_bare_start_does_not_send_message(self, telegram_api):
        # Bare /start with no token -> falls through to regular message path,
        # user not in storage -> silently 200.
        resp = _post_webhook(_make_update(999, "/start"))
        assert resp.status_code == 200
        assert _send_message_calls(telegram_api["calls"]) == []


# ---------------------------------------------------------------------------
# Malformed JSON
# ---------------------------------------------------------------------------
class TestMalformedBody:
    def test_malformed_json_returns_200(self, telegram_api):
        resp = _post_webhook(None, raw_body=b"not json {{{", content_type="application/json")
        assert resp.status_code == 200
        assert _send_message_calls(telegram_api["calls"]) == []

    def test_non_dict_json_returns_200(self, telegram_api):
        resp = _post_webhook(None, raw_body=b'"just a string"', content_type="application/json")
        assert resp.status_code == 200
        assert _send_message_calls(telegram_api["calls"]) == []
