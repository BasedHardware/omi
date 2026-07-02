"""Tests for the Telethon wrapper.

Pins the security invariants from plan §7:
- Session string is read once from stdin
- The constructor overwrites the local session_string binding
- No method returns the session string
- No method logs the session string
- The api_id/api_hash are PUBLIC and can be in env vars

The real Telethon client makes network calls, so we mock the
telethon module. The point of these tests is to verify the wrapper's
contract, not Telethon's behavior.
"""

from __future__ import annotations

import io
import logging
import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Section 1: read_session_from_stdin
# ---------------------------------------------------------------------------


class TestReadSessionFromStdin:
    def test_reads_session_string(self, monkeypatch):
        """Pipes a session string into stdin; the function returns it
        stripped of leading/trailing whitespace."""
        session_str = "1AgAOMT946OxqWq3" + "A" * 200
        monkeypatch.setattr(sys, "stdin", io.StringIO(session_str + "\n\n"))
        from telethon_client import read_session_from_stdin

        result = read_session_from_stdin()
        assert result == session_str

    def test_raises_on_empty_stdin(self, monkeypatch):
        """No session piped in is a configuration error — raise."""
        from telethon_client import read_session_from_stdin

        monkeypatch.setattr(sys, "stdin", io.StringIO(""))
        with pytest.raises(RuntimeError, match="No Telethon session string"):
            read_session_from_stdin()

    def test_raises_on_whitespace_only(self, monkeypatch):
        from telethon_client import read_session_from_stdin

        monkeypatch.setattr(sys, "stdin", io.StringIO("   \n\n  \n"))
        with pytest.raises(RuntimeError, match="No Telethon session string"):
            read_session_from_stdin()

    def test_strips_trailing_newline(self, monkeypatch):
        """Real session strings from StringSession.save() end with a
        newline; strip it so the Telethon client can load them."""
        from telethon_client import read_session_from_stdin

        monkeypatch.setattr(sys, "stdin", io.StringIO("SESSION\n"))
        assert read_session_from_stdin() == "SESSION"

    def test_does_not_log_session(self, monkeypatch, caplog):
        """The read function must NOT log the session string. Logging
        would defeat the entire security model — the session is
        never-on-disk AND never-in-logs."""
        from telethon_client import read_session_from_stdin

        session_str = "SESSIONSECRET" + "X" * 100
        monkeypatch.setattr(sys, "stdin", io.StringIO(session_str))
        with caplog.at_level(logging.DEBUG):
            read_session_from_stdin()
        for record in caplog.records:
            assert session_str not in record.getMessage(), f"Session string leaked into log: {record.getMessage()!r}"


# ---------------------------------------------------------------------------
# Section 2: TelethonClient constructor
# ---------------------------------------------------------------------------


class TestTelethonClientConstructor:
    def test_constructor_does_not_persist_session_parameter(self):
        """The session_string parameter is consumed by the
        constructor. After construction, the local binding should
        be overwritten with None — verify the source does this."""
        import inspect
        from telethon_client import TelethonClient

        source = inspect.getsource(TelethonClient.__init__)
        assert "session_string = None" in source, (
            "TelethonClient.__init__ must overwrite the session_string "
            "parameter with None after constructing the Telethon client. "
            "Otherwise the session lives in the constructor's stack frame "
            "indefinitely (until the frame is GC'd)."
        )

    def test_session_string_does_not_appear_in_source(self):
        """Pin that no real session string appears in the production
        source. Catches copy-paste leaks that the redactor/Filter
        cannot help with (the source code itself is checked in to
        git)."""
        import inspect
        from telethon_client import TelethonClient

        source = inspect.getsource(TelethonClient)
        sentinel = "SESSIONSECRET"
        assert sentinel not in source, (
            f"Test sentinel {sentinel!r} found in telethon_client.py " f"source. This indicates a copy-paste leak."
        )

    def test_constructor_uses_string_session(self):
        """Pins the session type: Telethon's StringSession (in-memory
        string-backed), not FileSession (writes to disk). The plan
        requires the session is held in memory only."""
        import inspect
        from telethon_client import TelethonClient

        source = inspect.getsource(TelethonClient.__init__)
        assert "StringSession" in source, (
            "TelethonClient must use StringSession (in-memory). "
            "FileSession would write the session to disk, violating "
            "the never-on-disk invariant."
        )
        assert "FileSession" not in source, "FileSession reference found — it would write to disk."

    def test_constructor_does_not_accept_session_via_other_param(self):
        """The session string must come through the keyword-only
        `session_string` parameter. No alias or alternate name."""
        import inspect
        from telethon_client import TelethonClient

        sig = inspect.signature(TelethonClient.__init__)
        params = list(sig.parameters.keys())
        assert "session_string" in params
        for forbidden in ("session", "telethon_session", "token", "auth"):
            assert forbidden not in params, (
                f"TelethonClient.__init__ must not accept a '{forbidden}' " f"parameter (use 'session_string' only)."
            )

    def test_no_method_returns_session_string(self):
        """Pin that no public method returns the session string.
        There's no legitimate reason to read it back from this
        process — any such getter would be a credential
        exfiltration vector."""
        import inspect
        from telethon_client import TelethonClient

        for name, method in inspect.getmembers(TelethonClient, predicate=inspect.isfunction):
            if name.startswith("_") or name == "__init__":
                continue
            try:
                source = inspect.getsource(method)
            except (OSError, TypeError):
                continue
            assert "session_string" not in source, (
                f"Method {name} references 'session_string' in its "
                f"source. The session is meant to be consumed at "
                f"__init__ — no other method should touch it."
            )


# ---------------------------------------------------------------------------
# Section 3: TelethonClient methods (mocked)
# ---------------------------------------------------------------------------


class TestTelethonClientMethods:
    """The methods on TelethonClient wrap Telethon's async client.
    Mock telethon at module level so we can verify the wrapper's
    shape (which methods it calls, with what args) without making
    real network calls.
    """

    def _make_client(self, monkeypatch):
        """Build a TelethonClient with a mocked Telethon module."""
        from telethon_client import TelethonClient

        mock_telethon = MagicMock()
        mock_client = MagicMock()
        mock_telethon.TelegramClient.return_value = mock_client

        # Patch the imports inside the constructor. The constructor
        # does `from telethon import TelegramClient` and
        # `from telethon.sessions import StringSession` at call time.
        # We patch sys.modules so those imports return our mocks.
        monkeypatch.setitem(sys.modules, "telethon", mock_telethon)
        monkeypatch.setitem(sys.modules, "telethon.sessions", mock_telethon.sessions)

        client = TelethonClient(
            session_string="fake-session",
            api_id=12345,
            api_hash="fake-hash",
        )
        return client, mock_client

    @pytest.mark.asyncio
    async def test_connect_returns_account_metadata(self, monkeypatch):
        client, mock_client = self._make_client(monkeypatch)

        # Make mock_client.connect() and get_me() awaitable.
        async def async_connect():
            return None

        mock_client.connect = async_connect
        mock_me = MagicMock()
        mock_me.phone = "+15550001111"
        mock_me.first_name = "Choguun"
        mock_me.last_name = "Test"
        mock_me.username = "choguun_test"

        async def async_get_me():
            return mock_me

        mock_client.get_me = async_get_me

        result = await client.connect()
        assert result["phone"] == "+15550001111"
        assert result["name"] == "Choguun Test"
        assert result["device_label"] == "Omi Desktop"

    async def test_connect_raises_when_get_me_returns_none(self, monkeypatch):
        # cubic review 4615559812 P1: an invalid/revoked Telethon
        # session returns get_me() == None. The previous code
        # would crash with AttributeError on me.first_name. The
        # contract: connect() raises RuntimeError with an
        # actionable message, AND calls disconnect() first so
        # the underlying client doesn't leak a connection.
        client, mock_client = self._make_client(monkeypatch)

        async def async_connect():
            return None

        mock_client.connect = async_connect

        async def async_get_me():
            return None  # revoked / invalid session

        mock_client.get_me = async_get_me

        disconnect_calls = []

        async def async_disconnect():
            disconnect_calls.append(True)

        mock_client.disconnect = async_disconnect

        with pytest.raises(RuntimeError, match="not authorized"):
            await client.connect()
        assert disconnect_calls == [True], (
            "connect() must call disconnect() before raising when "
            "get_me() returns None — otherwise the underlying "
            "Telethon client leaks an open connection."
        )

    @pytest.mark.asyncio
    async def test_get_chats_returns_dialogs(self, monkeypatch):
        client, mock_client = self._make_client(monkeypatch)
        d1 = MagicMock()
        d1.id = 100
        d1.title = "Alice"
        d1.name = "Alice"
        d1.is_user = True
        d1.unread_count = 2
        d1.message = MagicMock()
        d1.message.text = "hi there"
        d1.message.date = MagicMock()
        d1.message.date.isoformat.return_value = "2026-07-01T10:00:00"
        d2 = MagicMock()
        d2.id = 200
        d2.title = "Bob"
        d2.name = "Bob"
        d2.is_user = True
        d2.unread_count = 0
        d2.message = None

        async def async_get_dialogs(limit):
            return [d1, d2]

        mock_client.get_dialogs = async_get_dialogs

        result = await client.get_chats(limit=10)
        assert len(result) == 2
        assert result[0]["chat_id"] == "100"
        assert result[0]["title"] == "Alice"
        assert result[0]["unread_count"] == 2
        assert result[0]["last_message_preview"] == "hi there"
        assert result[1]["chat_id"] == "200"
        assert result[1]["last_message_preview"] == ""
        assert result[1]["last_message_date"] is None

    @pytest.mark.asyncio
    async def test_get_chat_history_returns_oldest_first(self, monkeypatch):
        client, mock_client = self._make_client(monkeypatch)
        # Telethon returns newest first; our wrapper reverses.
        m1 = MagicMock()
        m1.outgoing = False
        m1.text = "first"
        m1.date = MagicMock()
        m1.date.isoformat.return_value = "2026-07-01T08:00:00"
        m2 = MagicMock()
        m2.outgoing = True
        m2.text = "second"
        m2.date = MagicMock()
        m2.date.isoformat.return_value = "2026-07-01T09:00:00"
        m3 = MagicMock()
        m3.outgoing = False
        m3.text = "third"
        m3.date = MagicMock()
        m3.date.isoformat.return_value = "2026-07-01T10:00:00"

        async def async_get_messages(chat_id, limit):
            return [m3, m2, m1]

        mock_client.get_messages = async_get_messages

        result = await client.get_chat_history(chat_id=42, limit=20)
        assert [m["text"] for m in result] == ["first", "second", "third"]
        assert [m["role"] for m in result] == ["human", "ai", "human"]

    @pytest.mark.asyncio
    async def test_send_message_returns_metadata(self, monkeypatch):
        client, mock_client = self._make_client(monkeypatch)
        sent = MagicMock()
        sent.id = 999
        sent.chat_id = 42
        sent.date = MagicMock()
        sent.date.isoformat.return_value = "2026-07-01T10:00:00"

        async def async_send_message(chat_id, text):
            return sent

        mock_client.send_message = async_send_message

        result = await client.send_message(chat_id=42, text="hello")
        assert result["id"] == 999
        assert result["chat_id"] == "42"
        assert result["date"] == "2026-07-01T10:00:00"
