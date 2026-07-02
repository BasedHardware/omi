"""Tests for the FastAPI service in main.py.

Covers the route contracts and the security invariants:
- /health is unauthenticated and always returns 200
- /status requires bearer; returns connection state
- /recent_messages requires bearer; returns chat list
- /recent_messages/{chat_id}/messages requires bearer; per-chat history
- /persona_chat requires bearer; calls persona API + Telethon send
- /chat_memory requires bearer; appends to ring buffer
- The session string NEVER appears in any HTTP response body
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# A canonical session string for the never-in-HTTP-responses test.
TEST_SESSION_STRING = (
    "1AgAOMT946OxqWq3AAAAAAAAAAAAAAAAAAAAAAAAAAAAAGCh67gAdYrx3"
    "Jv9bV3X5nT8KwGf8hZK0qY7p7w2Hf9kZmQ3yH0P3JhL8sB6mE1cV4nR2tX9oF0aS"
    "iD5gK7eP4xN1mZ6yB2sC8hV0rJ3aT9wQ4eF6gH8iJ2kL4mN6oP8qR0sT2uV4wX6yZ8"
    "A1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0U1V2W3X4Y5Z6a7b8c9d0e1f2g3"
    "h4i5j6k7l8m9n0o1p2q3r4s5t6u7v8w9x0y1z2A3B4C5D6E7F8G9H0I1J2K3L4M5"
)


@pytest.fixture
def mock_app(monkeypatch):
    """Build a TestClient with a mocked Telethon client.

    Patches the module-level _client in main.py and pre-populates
    simple_storage with a test user record. Tests use this to make
    HTTP calls without touching the real Telethon.
    """
    # Default env vars so the FastAPI app can import cleanly.
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "fake-hash")
    monkeypatch.setenv("OMI_DEV_MODE", "0")
    monkeypatch.setenv("AI_CLONE_PLUGIN_TOKEN", "test-bearer-token")

    # Mock telethon at the module level BEFORE main.py is imported,
    # so the lifespan startup doesn't try to read from stdin.
    mock_telethon_module = MagicMock()
    mock_telethon_module.TelegramClient = MagicMock()
    mock_telethon_module.sessions.StringSession = MagicMock()
    monkeypatch.setitem(sys.modules, "telethon", mock_telethon_module)
    monkeypatch.setitem(sys.modules, "telethon.sessions", mock_telethon_module.sessions)

    # Now import main. The lifespan won't actually read stdin
    # because the Telethon client construction is mocked.
    if "main" in sys.modules:
        del sys.modules["main"]
    import main as main_module

    # CRITICAL: patch read_session_from_stdin in main.py BEFORE the
    # TestClient is constructed. Without this, the lifespan startup
    # calls sys.stdin.read() which BLOCKS in test contexts (no real
    # stdin pipe). The fixture would hang.
    monkeypatch.setattr(
        main_module._telethon_client,
        "read_session_from_stdin",
        lambda: "fake-session-string-for-tests",
    )

    # ALSO monkeypatch the TelethonClient CLASS in main's namespace
    # so the lifespan's `TelethonClient(...)` call returns a controlled
    # instance. Without this, the lifespan instantiates a fresh
    # MagicMock via `from telethon import TelegramClient` and calls
    # `.connect()` on it — which is a MagicMock attribute, not an
    # awaitable, and the lifespan hangs.
    mock_client = MagicMock()

    class _FakeTelethon:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self._connected = True

        async def connect(self):
            return {
                "phone": "+15550001111",
                "name": "Choguun Test",
                "device_label": "Omi Desktop",
            }

        async def disconnect(self):
            return None

        async def is_connected(self):
            return self._connected

        async def get_chats(self, limit):
            return []

        async def get_chat_history(self, chat_id, limit):
            return []

        async def send_message(self, chat_id, text):
            return {"id": 1, "chat_id": str(chat_id), "date": None}

    monkeypatch.setattr(main_module._telethon_client, "TelethonClient", _FakeTelethon)

    # The lifespan's `_client = TelethonClient(...)` now produces a
    # _FakeTelethon. After TestClient construction, replace the
    # singleton with a separate MagicMock for the tests' patching.

    from fastapi.testclient import TestClient

    try:
        client = TestClient(main_module.app)
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise
    # After TestClient construction, the lifespan has populated
    # main_module._client with the _FakeTelethon. Replace it with
    # the test's MagicMock so tests can patch the methods.
    main_module._client = mock_client
    # Also re-set _account_meta (the lifespan overwrote it with the
    # _FakeTelethon's connect() result). The /status endpoint reads
    # _account_meta directly.
    main_module._account_meta = {
        "phone": "+15550001111",
        "name": "Choguun Test",
        "device_label": "Omi Desktop",
    }

    # Default: mock is_connected returns True. Tests can override.
    async def async_is_connected_default():
        return True

    mock_client.is_connected = async_is_connected_default

    # Default async disconnect. cubic review 4615559812 P3: bare
    # MagicMock.disconnect() returns a MagicMock (not awaitable), so
    # the lifespan's `await _client.disconnect()` on teardown
    # raised a TypeError that was swallowed by the lifespan handler
    # but surfaced as a spurious warning. Pin the production
    # interface (async disconnect) on the mock.
    async def async_disconnect_default():
        return None

    mock_client.disconnect = async_disconnect_default

    # Default: mock the other methods so /status, /recent_messages,
    # etc. don't crash on default MagicMock callables.
    async def async_get_chats_default(limit):
        return []

    mock_client.get_chats = async_get_chats_default

    async def async_get_chat_history_default(chat_id, limit):
        return []

    mock_client.get_chat_history = async_get_chat_history_default

    async def async_send_message_default(chat_id, text):
        return {"id": 1, "chat_id": str(chat_id), "date": None}

    mock_client.send_message = async_send_message_default
    print(f"FIXTURE client id={id(client)} type={type(client).__name__}")
    try:
        yield client, mock_client, main_module
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Section 1: bearer auth
# ---------------------------------------------------------------------------


class TestBearerAuth:
    def test_health_does_not_require_bearer(self, mock_app):
        """Health is the only unauthenticated route — all other
        routes require the bearer token."""
        client, _, _ = mock_app
        print("client type:", type(client).__name__, "id:", id(client))
        print("mock_app[0] type:", type(mock_app[0]).__name__, "id:", id(mock_app[0]))
        # No Authorization header.
        r = client.get("/health")
        print("r type:", type(r).__name__)
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}

    def test_status_requires_bearer(self, mock_app):
        client, _, _ = mock_app
        r = client.get("/status")
        assert r.status_code == 401

    def test_status_accepts_valid_bearer(self, mock_app):
        client, mock_client, _ = mock_app
        import main as main_module

        print(f"  test sees _client={type(main_module._client).__name__}")
        r = client.get("/status", headers={"Authorization": "Bearer test-bearer-token"})
        assert r.status_code == 200
        data = r.json()
        assert data["connected"] is True
        assert data["account_phone"] == "+15550001111"
        assert data["account_name"] == "Choguun Test"
        # plan §8: /status also exposes rate_limit state and the
        # daily sent counter so the desktop can surface them.
        assert "rate_limit" in data
        rl = data["rate_limit"]
        assert "max_per_hour" in rl
        assert "in_window_count" in rl
        assert "is_blocked" in rl
        assert "seconds_until_next_slot" in rl
        assert "messages_sent_today" in data
        assert data["messages_sent_today"] >= 0

    def test_status_rate_limit_reflects_recorded_sends(self, mock_app, monkeypatch):
        # Pre-fill the rate limit and confirm /status surfaces it.
        import flood_control

        rl = flood_control.RateLimit(max_per_hour=5, window_seconds=3600)
        for _ in range(3):
            rl.record_send()
        monkeypatch.setattr(flood_control, "default_rate_limit", rl, raising=False)
        client, _, _ = mock_app
        r = client.get("/status", headers={"Authorization": "Bearer test-bearer-token"})
        assert r.status_code == 200
        data = r.json()
        assert data["rate_limit"]["max_per_hour"] == 5
        assert data["rate_limit"]["in_window_count"] == 3
        assert data["rate_limit"]["is_blocked"] is False
        assert data["rate_limit"]["seconds_until_next_slot"] == 0

    def test_status_rate_limit_reflects_blocked_state(self, mock_app, monkeypatch):
        import flood_control

        rl = flood_control.RateLimit(max_per_hour=10, window_seconds=3600)
        rl.block_for_seconds(120)
        monkeypatch.setattr(flood_control, "default_rate_limit", rl, raising=False)
        client, _, _ = mock_app
        r = client.get("/status", headers={"Authorization": "Bearer test-bearer-token"})
        assert r.status_code == 200
        data = r.json()
        assert data["rate_limit"]["is_blocked"] is True
        # seconds_until_next_slot returns the remaining cooldown
        # (≈ 120 since the fake clock doesn't advance).
        assert 100 <= data["rate_limit"]["seconds_until_next_slot"] <= 120

    def test_status_messages_sent_today_reflects_successful_sends(self, mock_app, monkeypatch):
        # plan §8: daily "messages sent today" counter. The
        # endpoint reports the in-memory daily counter on
        # RateLimit (NOT the per-chat ring buffer, which is
        # bounded by CHAT_HISTORY_MAX and undercounts on
        # very active chats -- cubic 4618627789 P2). The
        # daily counter is exact, monotonic since local-time
        # midnight, and bumped by record_send() on every
        # successful outbound send.
        import flood_control

        rl = flood_control.RateLimit(max_per_hour=1000)
        for _ in range(2):
            rl.record_send()
        monkeypatch.setattr(flood_control, "default_rate_limit", rl, raising=False)
        client, _, _ = mock_app
        r = client.get("/status", headers={"Authorization": "Bearer test-bearer-token"})
        assert r.status_code == 200
        assert r.json()["messages_sent_today"] == 2

    def test_status_messages_sent_today_is_exact_not_bounded(self, mock_app, monkeypatch):
        # cubic review 4618627789 P2: the previous counter
        # was bounded by the per-chat ring buffer
        # (CHAT_HISTORY_MAX = 10) and undercounted on very
        # active chats. The fix moves the source of truth
        # to flood_control.default_rate_limit.daily_count(),
        # which is an exact in-memory monotonic counter that
        # resets on local-time day rollover. This test pins
        # the new "exact, not bounded" contract: 15 record_send
        # calls produce 15 in messages_sent_today, regardless
        # of per-chat buffer state.
        import flood_control

        rl = flood_control.RateLimit(max_per_hour=1000)
        for _ in range(15):
            rl.record_send()
        monkeypatch.setattr(flood_control, "default_rate_limit", rl, raising=False)
        client, _, _ = mock_app
        r = client.get("/status", headers={"Authorization": "Bearer test-bearer-token"})
        assert r.status_code == 200
        assert r.json()["messages_sent_today"] == 15

    def test_recent_messages_requires_bearer(self, mock_app):
        client, _, _ = mock_app
        r = client.get("/recent_messages")
        assert r.status_code == 401

    def test_persona_chat_requires_bearer(self, mock_app):
        client, _, _ = mock_app
        r = client.post("/persona_chat", json={"chat_id": "1", "text": "hi"})
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Section 2: /recent_messages
# ---------------------------------------------------------------------------


class TestRecentMessages:
    def test_returns_chat_list(self, mock_app):
        client, mock_client, _ = mock_app

        async def async_get_chats(limit):
            return [
                {"chat_id": "100", "title": "Alice"},
                {"chat_id": "200", "title": "Bob"},
            ]

        mock_client.get_chats = async_get_chats
        r = client.get(
            "/recent_messages",
            headers={"Authorization": "Bearer test-bearer-token"},
        )
        assert r.status_code == 200
        assert r.json() == {
            "chats": [
                {"chat_id": "100", "title": "Alice"},
                {"chat_id": "200", "title": "Bob"},
            ]
        }


# ---------------------------------------------------------------------------
# Section 3: /recent_messages/{chat_id}/messages
# ---------------------------------------------------------------------------


class TestRecentMessagesChat:
    def test_returns_history(self, mock_app):
        client, mock_client, _ = mock_app

        async def async_get_chat_history(chat_id, limit):
            return [
                {"role": "human", "text": "hi", "ts": "2026-07-01T08:00:00"},
                {"role": "ai", "text": "hello", "ts": "2026-07-01T09:00:00"},
            ]

        mock_client.get_chat_history = async_get_chat_history
        r = client.get(
            "/recent_messages/100/messages",
            headers={"Authorization": "Bearer test-bearer-token"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["chat_id"] == "100"
        assert len(data["messages"]) == 2


# ---------------------------------------------------------------------------
# Section 4: /persona_chat
# ---------------------------------------------------------------------------


class TestPersonaChat:
    def test_returns_400_for_unknown_user(self, mock_app):
        """No simple_storage user record for the handle → 400."""
        client, _, _ = mock_app
        r = client.post(
            "/persona_chat",
            json={"chat_id": "1", "text": "hi", "sender_handle": "unknown"},
            headers={"Authorization": "Bearer test-bearer-token"},
        )
        # 400 because we don't have a per-user mapping for this handle.
        # (When the desktop wires up user resolution this becomes a
        # different code path.)
        assert r.status_code in (400, 502)

    def test_calls_persona_and_sends(self, mock_app):
        client, mock_client, main_module = mock_app
        # Seed a user record.
        import simple_storage

        simple_storage.users.clear()
        simple_storage.users["choguun_handle"] = {
            "telegram_user_id": "choguun_handle",
            "omi_uid": "test-uid",
            "persona_id": "persona-1",
            "omi_dev_api_key": "dev-key",
            "auto_reply_enabled": True,
        }
        # Seed a chat ring buffer.
        simple_storage.chats["1"] = {"chat_id": "1", "recent_messages": []}

        # Mock persona_client.chat to return a fixed reply.
        async def async_persona_chat(**kwargs):
            assert kwargs["app_id"] == "persona-1"
            assert kwargs["api_key"] == "dev-key"
            assert kwargs["uid"] == "test-uid"
            return "Hello from the persona!"

        # Mock the send_message to return metadata.
        async def async_send_message(chat_id, text):
            return {
                "id": 999,
                "chat_id": str(chat_id),
                "date": "2026-07-01T10:00:00",
            }

        mock_client.send_message = async_send_message

        with patch.object(main_module, "_persona_chat", side_effect=async_persona_chat):
            r = client.post(
                "/persona_chat",
                json={
                    "chat_id": "1",
                    "text": "hi there",
                    "sender_handle": "choguun_handle",
                },
                headers={"Authorization": "Bearer test-bearer-token"},
            )
        assert r.status_code == 200
        data = r.json()
        assert data["reply"] == "Hello from the persona!"
        assert data["sent"]["id"] == 999
        # The reply was appended to the chat's ring buffer.
        history = simple_storage.get_recent_messages("1")
        assert any(m["role"] == "ai" and m["text"] == "Hello from the persona!" for m in history)

    def test_passes_recent_messages_to_persona(self, mock_app):
        client, mock_client, main_module = mock_app
        import simple_storage

        simple_storage.users.clear()
        simple_storage.users["choguun_handle"] = {
            "telegram_user_id": "choguun_handle",
            "omi_uid": "test-uid",
            "persona_id": "persona-1",
            "omi_dev_api_key": "dev-key",
            "auto_reply_enabled": True,
        }
        # Pre-populate the ring buffer with 25 messages; the endpoint
        # should pass only the LAST 20 to the persona API.
        simple_storage.chats["1"] = {
            "chat_id": "1",
            "recent_messages": [
                {"role": "human" if i % 2 == 0 else "ai", "text": f"m-{i:02d}", "ts": None} for i in range(25)
            ],
        }

        async def async_send_message(chat_id, text):
            return {"id": 1, "chat_id": str(chat_id), "date": None}

        mock_client.send_message = async_send_message

        captured_kwargs = {}

        async def capture_persona_chat(**kwargs):
            captured_kwargs.update(kwargs)
            return "ok"

        with patch.object(main_module, "_persona_chat", side_effect=capture_persona_chat):
            r = client.post(
                "/persona_chat",
                json={
                    "chat_id": "1",
                    "text": "hi",
                    "sender_handle": "choguun_handle",
                },
                headers={"Authorization": "Bearer test-bearer-token"},
            )
        assert r.status_code == 200
        # The endpoint passes the most recent 20 (m-05..m-24).
        prev = captured_kwargs["previous_messages"]
        assert len(prev) == 20
        assert prev[0]["text"] == "m-05"
        assert prev[-1]["text"] == "m-24"


# ---------------------------------------------------------------------------
# Section 4b: flood control integration (plan §8)
# ---------------------------------------------------------------------------


class FloodWaitError(Exception):  # noqa: N801
    """Stand-in for telethon.errors.FloodWaitError, matched by
    class name in flood_control.detect_flood_wait.
    """

    def __init__(self, seconds: int):
        super().__init__(f"FLOOD_WAIT_{seconds}")
        self.seconds = seconds


class TestFloodControlIntegration:
    def test_returns_429_when_rate_limit_hit(self, mock_app, monkeypatch):
        import flood_control

        rl = flood_control.RateLimit(max_per_hour=1, window_seconds=3600)
        rl.record_send()
        monkeypatch.setattr(flood_control, "default_rate_limit", rl, raising=False)

        client, _, _ = mock_app
        import simple_storage

        simple_storage.users.clear()
        simple_storage.users["choguun_handle"] = {
            "telegram_user_id": "choguun_handle",
            "omi_uid": "test-uid",
            "persona_id": "persona-1",
            "omi_dev_api_key": "dev-key",
            "auto_reply_enabled": True,
        }
        simple_storage.chats["1"] = {"chat_id": "1", "recent_messages": []}

        r = client.post(
            "/persona_chat",
            json={"chat_id": "1", "text": "hi", "sender_handle": "choguun_handle"},
            headers={"Authorization": "Bearer test-bearer-token"},
        )
        assert r.status_code == 429
        assert "Retry-After" in r.headers
        assert int(r.headers["Retry-After"]) > 0

    def test_returns_429_with_flood_wait_seconds_on_telegram_flood(self, mock_app, monkeypatch):
        import flood_control

        monkeypatch.setattr(
            flood_control,
            "default_rate_limit",
            flood_control.RateLimit(max_per_hour=1000),
            raising=False,
        )

        client, mock_client, main_module = mock_app
        import simple_storage

        simple_storage.users.clear()
        simple_storage.users["choguun_handle"] = {
            "telegram_user_id": "choguun_handle",
            "omi_uid": "test-uid",
            "persona_id": "persona-1",
            "omi_dev_api_key": "dev-key",
            "auto_reply_enabled": True,
        }
        simple_storage.chats["1"] = {"chat_id": "1", "recent_messages": []}

        async def async_persona_chat(**kwargs):
            return "reply text"

        async def async_send_message_raises(chat_id, text):
            raise FloodWaitError(seconds=42)

        mock_client.send_message = async_send_message_raises

        with patch.object(main_module, "_persona_chat", side_effect=async_persona_chat):
            r = client.post(
                "/persona_chat",
                json={"chat_id": "1", "text": "hi", "sender_handle": "choguun_handle"},
                headers={"Authorization": "Bearer test-bearer-token"},
            )
        assert r.status_code == 429
        assert r.headers["Retry-After"] == "42"
        body = r.json()
        assert "FLOOD_WAIT" in body.get("detail", "") or "42" in body.get("detail", "")

    def test_successful_send_records_to_rate_limit(self, mock_app, monkeypatch):
        import flood_control

        rl = flood_control.RateLimit(max_per_hour=100, window_seconds=3600)
        monkeypatch.setattr(flood_control, "default_rate_limit", rl, raising=False)

        client, mock_client, main_module = mock_app
        import simple_storage

        simple_storage.users.clear()
        simple_storage.users["choguun_handle"] = {
            "telegram_user_id": "choguun_handle",
            "omi_uid": "test-uid",
            "persona_id": "persona-1",
            "omi_dev_api_key": "dev-key",
            "auto_reply_enabled": True,
        }
        simple_storage.chats["1"] = {"chat_id": "1", "recent_messages": []}

        async def async_persona_chat(**kwargs):
            return "ok"

        async def async_send_message_ok(chat_id, text):
            return {"id": 1, "chat_id": str(chat_id), "date": None}

        mock_client.send_message = async_send_message_ok

        with patch.object(main_module, "_persona_chat", side_effect=async_persona_chat):
            r = client.post(
                "/persona_chat",
                json={"chat_id": "1", "text": "hi", "sender_handle": "choguun_handle"},
                headers={"Authorization": "Bearer test-bearer-token"},
            )
        assert r.status_code == 200
        assert rl.in_window_count() == 1

    def test_failed_send_does_not_record_to_rate_limit(self, mock_app, monkeypatch):
        import flood_control

        rl = flood_control.RateLimit(max_per_hour=100, window_seconds=3600)
        monkeypatch.setattr(flood_control, "default_rate_limit", rl, raising=False)

        client, mock_client, main_module = mock_app
        import simple_storage

        simple_storage.users.clear()
        simple_storage.users["choguun_handle"] = {
            "telegram_user_id": "choguun_handle",
            "omi_uid": "test-uid",
            "persona_id": "persona-1",
            "omi_dev_api_key": "dev-key",
            "auto_reply_enabled": True,
        }
        simple_storage.chats["1"] = {"chat_id": "1", "recent_messages": []}

        async def async_persona_chat(**kwargs):
            return "ok"

        async def async_send_message_raises(chat_id, text):
            raise ValueError("Telethon transport blew up")

        mock_client.send_message = async_send_message_raises

        with patch.object(main_module, "_persona_chat", side_effect=async_persona_chat):
            r = client.post(
                "/persona_chat",
                json={"chat_id": "1", "text": "hi", "sender_handle": "choguun_handle"},
                headers={"Authorization": "Bearer test-bearer-token"},
            )
        assert r.status_code == 502
        assert rl.in_window_count() == 0


# ---------------------------------------------------------------------------
# Section 4c: /toggle (auto-reply on/off)
# ---------------------------------------------------------------------------


class TestToggle:
    """The desktop calls POST /toggle with
    {handle: "all", enabled: bool} to flip auto-reply. Storage
    updates via simple_storage.update_auto_reply().
    """

    def _seed_user(self, handle, **overrides):
        # Adds a user WITHOUT clearing existing ones -- useful
        # for tests that need multiple users. Tests that want
        # a clean slate should call simple_storage.users.clear()
        # themselves.
        import simple_storage

        record = {
            "telegram_user_id": handle,
            "omi_uid": f"uid-{handle}",
            "persona_id": "persona-1",
            "omi_dev_api_key": "dev-key",
            "auto_reply_enabled": False,
        }
        record.update(overrides)
        simple_storage.users[handle] = record

    def test_toggle_all_enables_auto_reply_for_all_users(self, mock_app):
        client, _, _ = mock_app
        self._seed_user("alice")
        self._seed_user("bob", auto_reply_enabled=True)
        r = client.post(
            "/toggle",
            json={"handle": "all", "enabled": True},
            headers={"Authorization": "Bearer test-bearer-token"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["auto_reply_enabled"] is True
        assert body["affected_users"] == 2
        import simple_storage

        assert simple_storage.users["alice"]["auto_reply_enabled"] is True
        assert simple_storage.users["bob"]["auto_reply_enabled"] is True

    def test_toggle_all_disables_auto_reply_for_all_users(self, mock_app):
        client, _, _ = mock_app
        self._seed_user("alice", auto_reply_enabled=True)
        self._seed_user("bob", auto_reply_enabled=True)
        r = client.post(
            "/toggle",
            json={"handle": "all", "enabled": False},
            headers={"Authorization": "Bearer test-bearer-token"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["auto_reply_enabled"] is False
        assert body["affected_users"] == 2

    def test_toggle_specific_handle_updates_one_user(self, mock_app):
        client, _, _ = mock_app
        self._seed_user("alice", auto_reply_enabled=True)
        self._seed_user("bob", auto_reply_enabled=True)
        r = client.post(
            "/toggle",
            json={"handle": "alice", "enabled": False},
            headers={"Authorization": "Bearer test-bearer-token"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["auto_reply_enabled"] is False
        assert body["affected_users"] == 1
        import simple_storage

        assert simple_storage.users["alice"]["auto_reply_enabled"] is False
        # Bob unchanged.
        assert simple_storage.users["bob"]["auto_reply_enabled"] is True

    def test_toggle_unknown_handle_returns_403(self, mock_app):
        client, _, _ = mock_app
        self._seed_user("alice")
        r = client.post(
            "/toggle",
            json={"handle": "nonexistent", "enabled": True},
            headers={"Authorization": "Bearer test-bearer-token"},
        )
        assert r.status_code == 403

    def test_toggle_all_with_no_users_returns_403(self, mock_app):
        client, _, _ = mock_app
        import simple_storage

        simple_storage.users.clear()
        r = client.post(
            "/toggle",
            json={"handle": "all", "enabled": True},
            headers={"Authorization": "Bearer test-bearer-token"},
        )
        assert r.status_code == 403

    def test_toggle_requires_bearer(self, mock_app):
        client, _, _ = mock_app
        self._seed_user("alice")
        r = client.post("/toggle", json={"handle": "all", "enabled": True})
        assert r.status_code == 401


# ---------------------------------------------------------------------------
# Section 4d: extended /status (auto_reply_enabled)
# ---------------------------------------------------------------------------


class TestStatusAutoReplyAggregate:
    """plan: /status exposes auto_reply_enabled as the aggregate
    across all users (any-true == on). The empty-users case is
    reported as False so the desktop starts in the off state.
    """

    def test_status_auto_reply_enabled_aggregate_off(self, mock_app):
        import simple_storage

        simple_storage.users.clear()
        simple_storage.users["alice"] = {
            "telegram_user_id": "alice",
            "auto_reply_enabled": False,
        }
        client, _, _ = mock_app
        r = client.get("/status", headers={"Authorization": "Bearer test-bearer-token"})
        assert r.status_code == 200
        assert r.json()["auto_reply_enabled"] is False

    def test_status_auto_reply_enabled_aggregate_on(self, mock_app):
        import simple_storage

        simple_storage.users.clear()
        simple_storage.users["alice"] = {
            "telegram_user_id": "alice",
            "auto_reply_enabled": True,
        }
        simple_storage.users["bob"] = {
            "telegram_user_id": "bob",
            "auto_reply_enabled": False,
        }
        client, _, _ = mock_app
        r = client.get("/status", headers={"Authorization": "Bearer test-bearer-token"})
        assert r.status_code == 200
        # any(user.enabled) == True -> aggregate is on.
        assert r.json()["auto_reply_enabled"] is True

    def test_status_auto_reply_enabled_empty_users(self, mock_app):
        import simple_storage

        simple_storage.users.clear()
        client, _, _ = mock_app
        r = client.get("/status", headers={"Authorization": "Bearer test-bearer-token"})
        assert r.status_code == 200
        assert r.json()["auto_reply_enabled"] is False


# ---------------------------------------------------------------------------
# Section 4e: /persona_chat gated on auto_reply_enabled
# ---------------------------------------------------------------------------


class TestPersonaChatGatedOnAutoReply:
    """plan: /persona_chat returns 403 when auto_reply_enabled
    is False. Default (no field) is False -- safe default on
    first deploy so users must opt in.
    """

    def test_returns_403_when_auto_reply_disabled(self, mock_app):
        client, _, _ = mock_app
        import simple_storage

        simple_storage.users.clear()
        simple_storage.users["choguun_handle"] = {
            "telegram_user_id": "choguun_handle",
            "omi_uid": "test-uid",
            "persona_id": "persona-1",
            "omi_dev_api_key": "dev-key",
            "auto_reply_enabled": False,
        }
        simple_storage.chats["1"] = {"chat_id": "1", "recent_messages": []}
        r = client.post(
            "/persona_chat",
            json={"chat_id": "1", "text": "hi", "sender_handle": "choguun_handle"},
            headers={"Authorization": "Bearer test-bearer-token"},
        )
        assert r.status_code == 403
        assert "Auto-reply is disabled" in r.json().get("detail", "")

    def test_returns_403_when_auto_reply_field_missing(self, mock_app):
        # Backwards compatibility: an old user record without
        # the auto_reply_enabled field behaves as False.
        client, _, _ = mock_app
        import simple_storage

        simple_storage.users.clear()
        # Note: NO auto_reply_enabled field at all.
        simple_storage.users["choguun_handle"] = {
            "telegram_user_id": "choguun_handle",
            "omi_uid": "test-uid",
            "persona_id": "persona-1",
            "omi_dev_api_key": "dev-key",
        }
        simple_storage.chats["1"] = {"chat_id": "1", "recent_messages": []}
        r = client.post(
            "/persona_chat",
            json={"chat_id": "1", "text": "hi", "sender_handle": "choguun_handle"},
            headers={"Authorization": "Bearer test-bearer-token"},
        )
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Section 5: /chat_memory
# ---------------------------------------------------------------------------


class TestChatMemory:
    def test_appends_to_ring_buffer(self, mock_app):
        client, _, _ = mock_app
        import simple_storage

        simple_storage.chats.clear()
        simple_storage.chats["1"] = {"chat_id": "1", "recent_messages": []}
        r = client.post(
            "/chat_memory",
            json={"chat_id": "1", "role": "human", "text": "hi"},
            headers={"Authorization": "Bearer test-bearer-token"},
        )
        assert r.status_code == 200
        history = simple_storage.get_recent_messages("1")
        assert len(history) == 1
        assert history[0]["text"] == "hi"

    def test_rejects_invalid_role(self, mock_app):
        client, _, _ = mock_app
        r = client.post(
            "/chat_memory",
            json={"chat_id": "1", "role": "system", "text": "x"},
            headers={"Authorization": "Bearer test-bearer-token"},
        )
        assert r.status_code == 400

    def test_rejects_empty_text(self, mock_app):
        client, _, _ = mock_app
        r = client.post(
            "/chat_memory",
            json={"chat_id": "1", "role": "human", "text": ""},
            headers={"Authorization": "Bearer test-bearer-token"},
        )
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Section 6: Session string never in HTTP responses
# ---------------------------------------------------------------------------


class TestSessionStringNeverInHttpResponses:
    """Plan §7: the session string must NEVER appear in any HTTP
    response body. This is the on-the-wire complement to
    test_session_never_logged.py (logs) and test_storage.py
    (on-disk).

    The paranoia is at the ENDPOINT code, not the underlying mock.
    If a Telethon bug returns a session string, the endpoint
    faithfully serializes it. What we pin is that the endpoint
    itself does not INJECT a session string into any response.
    """

    def test_route_handlers_dont_reference_session(self):
        """Walk every route handler. None of them should reference
        the Telethon session or any 'session' attribute that would
        leak it into a response."""
        import inspect
        import main as main_module

        # The set of route function names. The decorator names match
        # the path constants; we get them from the app's routes.
        for route in main_module.app.routes:
            endpoint = getattr(route, "endpoint", None)
            if endpoint is None or not callable(endpoint):
                continue
            try:
                src = inspect.getsource(endpoint)
            except (OSError, TypeError):
                continue
            # Look for direct session attribute access. We don't ban
            # the word "session" entirely because comments and doc
            # strings reference it.
            for forbidden in (
                "_session_string",
                "session.string",
                "_session.",
                "self._client._session",
                "TelethonClient._session",
            ):
                assert forbidden not in src, (
                    f"Route {endpoint.__name__} references {forbidden!r} "
                    f"in its source. The session string must not flow "
                    f"into any response."
                )
