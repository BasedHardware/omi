"""Thin async wrapper around the Telethon client.

The Telethon session string is the user's phone-number authentication
— anyone with it can read all of the user's Telegram chats, send as
the user, and the only revocation path is Settings → Devices on the
user's phone. Security model (plan §7):

- The session string is read ONCE from stdin at process startup.
  After that, it lives only in Telethon's StringSession internal
  state. This process holds it in memory only.
- The local read variable is overwritten with None before return
  to help GC. Defense in depth — Python's string interning could
  in theory allow a determined attacker to recover bytes from
  freed memory, but the PRIMARY protection is that the session
  string never leaves this process (no log, no file, no HTTP).
- The api_id / api_hash are PUBLIC App credentials from
  my.telegram.org (not secrets). They come from env vars
  (TELEGRAM_API_ID / TELEGRAM_API_HASH) and are passed to Telethon
  on init. The plan explicitly excludes them from the
  "never-on-disk" invariant.

SECURITY (pinned in test_telethon_client.py):
- read_session_from_stdin reads ONCE; the variable is cleared after
- The TelethonClient constructor takes session_string as a
  keyword-only argument and overwrites the local binding before
  returning; the only surviving copy is in Telethon's StringSession
- No method on TelethonClient returns or logs the session string
- No exception message includes the session string
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Optional

logger = logging.getLogger(__name__)


def read_session_from_stdin() -> str:
    """Read the Telethon session string from stdin (one-shot pipe).

    Called ONCE at process startup, before any other code touches
    the session. The session is consumed and held in this process's
    memory only. After this function returns, the caller should
    immediately construct a TelethonClient and discard the return
    value to minimize stack-frame lifetime.

    SECURITY: stdin is closed after reading so the parent process
    can detect EOF and continue. The local `raw` variable is
    overwritten with None to help GC. PRIMARY protection is that
    the session string only ever lives in:
      1. Telethon's StringSession internal state
      2. This process's memory (no log, no file, no network
         persistence)

    Returns:
        The Telethon session string (Telethon StringSession format,
        a base64-encoded blob prefixed with a version byte).
    """
    raw = sys.stdin.read()
    if not raw or not raw.strip():
        raise RuntimeError(
            "No Telethon session string provided via stdin. "
            "The plugin must be launched with the session piped in "
            "(see the desktop's stack-runner)."
        )
    s = raw.strip()
    # Close stdin so the parent process can detect EOF and continue.
    sys.stdin.close()
    # Overwrite the local read variable to help GC. Defense in
    # depth — the PRIMARY protection is the absence of any log /
    # file / network path that could capture this string.
    raw = None
    return s


class TelethonClient:
    """Async wrapper around the Telethon client.

    Constructed once at process startup. The session string is
    consumed by the constructor; after construction it lives only
    in the underlying Telethon StringSession. No setter exists; the
    session can't be replaced or read back from this object.

    Args:
        session_string: Telethon StringSession format string
            (base64-encoded, version byte prefix). Held by Telethon
            after construction; the local binding is overwritten
            with None before the constructor returns.
        api_id: Telethon API ID (public, from my.telegram.org).
        api_hash: Telethon API hash (public, from my.telegram.org).
        device_model: Label shown in the user's Telegram app under
            Settings → Devices. Default "Omi Desktop".
        system_version: System version label. Default "1.0".
        app_version: App version label. Default "1.0".
    """

    def __init__(
        self,
        *,
        session_string: str,
        api_id: int,
        api_hash: str,
        device_model: str = "Omi Desktop",
        system_version: str = "1.0",
        app_version: str = "1.0",
    ):
        # Telethon imports are inside the constructor so tests can
        # mock them at module import time. Production code imports
        # the real Telethon.
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        self._api_id = api_id
        self._api_hash = api_hash
        self._device_model = device_model

        self._client = TelegramClient(
            StringSession(session_string),
            api_id=api_id,
            api_hash=api_hash,
            device_model=device_model,
            system_version=system_version,
            app_version=app_version,
        )
        # Overwrite the local session_string parameter so the
        # session doesn't survive in this function's stack frame.
        # Telethon's StringSession has its own copy.
        session_string = None

    # -- Connection lifecycle ------------------------------------------------

    async def connect(self) -> dict:
        """Connect to Telegram. Returns account metadata for the
        discovery file.

        Raises ``RuntimeError("Telethon session is not authorized")``
        if ``get_me()`` returns ``None`` — which is Telethon's signal
        that the session string is invalid, revoked (user logged out
        via Settings → Devices on their phone), or the auth key was
        broken in transit. Per cubic review #4615559812 P1: we MUST
        NOT dereference ``me`` (it's None) — that would raise
        ``AttributeError`` and surface as an opaque 500 instead of
        the controlled auth-failure UX.
        """
        await self._client.connect()
        me = await self._client.get_me()
        if me is None:
            await self._client.disconnect()
            raise RuntimeError(
                "Telethon session is not authorized — the session "
                "string may be invalid, revoked, or the auth key "
                "could not be decrypted. Sign in again from the "
                "desktop to generate a new session."
            )
        full_name = " ".join(filter(None, [me.first_name, me.last_name])).strip()

        # Populate Telethon's entity cache by fetching dialogs.
        # Without this, get_messages / send_message fail with
        # "Could not find the input entity for PeerUser(user_id=N)"
        # because the session's entity cache is empty on first
        # connect. Fetching dialogs resolves all recent contacts
        # and groups into the cache so subsequent operations work.
        self._entity_cache_ready = False
        try:
            await self._client.get_dialogs(limit=100)
            self._entity_cache_ready = True
            logger.info("entity cache populated from dialogs")
        except Exception as e:
            logger.warning(
                "could not populate entity cache: %s; " "send_message/get_chat_history may fail for some contacts",
                type(e).__name__,
            )

        return {
            "phone": getattr(me, "phone", None),
            "name": full_name or (getattr(me, "username", None) or "Unknown"),
            "device_label": self._device_model,
        }

    @property
    def entity_cache_ready(self) -> bool:
        """True if the Telethon entity cache was populated during
        connect(). When False, get_messages/send_message may fail
        with 'Could not find the input entity for PeerUser(...)'.
        Callers can check this to surface a degraded-state warning."""
        return getattr(self, "_entity_cache_ready", False)

    async def disconnect(self) -> None:
        try:
            await self._client.disconnect()
        except Exception as e:
            # Don't raise on shutdown — the disconnect might fail
            # mid-shutdown, and the process is exiting anyway.
            logger.warning("disconnect raised: %s", type(e).__name__)

    async def is_connected(self) -> bool:
        try:
            return bool(self._client.is_connected())
        except Exception:
            return False

    # -- Telegram operations -------------------------------------------------

    async def get_chats(self, limit: int = 20) -> list:
        """Return recent chats with metadata for the desktop's
        recent_messages list.

        Returns a list of dicts:
        {chat_id (str), title, is_user, unread_count,
         last_message_date (iso8601 or None),
         last_message_preview (str, truncated to 200 chars)}.
        """
        dialogs = await self._client.get_dialogs(limit=limit)
        result = []
        for d in dialogs:
            last_msg = getattr(d, "message", None)
            preview = ""
            if last_msg is not None:
                # Telethon Message has .text; some messages (stickers,
                # media) have empty .text. Truncate to 200 chars.
                preview = (last_msg.text or "")[:200]
            result.append(
                {
                    "chat_id": str(d.id),
                    "title": d.title or d.name or "Unknown",
                    "is_user": bool(d.is_user),
                    "unread_count": int(d.unread_count or 0),
                    "last_message_date": (last_msg.date.isoformat() if (last_msg and last_msg.date) else None),
                    "last_message_preview": preview,
                }
            )
        return result

    async def get_chat_history(self, chat_id: str | int, limit: int = 20) -> list:
        """Return recent messages for a chat, oldest first.

        The list of dicts matches the schema in simple_storage:
        {role: "human"|"ai", text: str, ts: iso8601 or None}.
        """
        messages = await self._client.get_messages(int(chat_id), limit=limit)
        # Telethon returns newest first; reverse for oldest-first.
        return [
            {
                "role": "ai" if m.outgoing else "human",
                "text": m.text or "",
                "ts": m.date.isoformat() if (m.date and m.message) else None,
            }
            for m in reversed(messages)
        ]

    async def send_message(self, chat_id: str | int, text: str) -> dict:
        """Send a message and return the sent-message metadata.

        Returns:
            {id (int), chat_id (str), date (iso8601 or None)}.
        """
        sent = await self._client.send_message(int(chat_id), text)
        return {
            "id": int(sent.id) if sent.id else 0,
            "chat_id": str(sent.chat_id),
            "date": sent.date.isoformat() if sent.date else None,
        }

    def register_incoming_message_handler(self, callback) -> None:
        """Register a callback for incoming NewMessage events.

        The callback receives a Telethon ``NewMessage.Event``. The
        handler is filtered to ``incoming=True`` so our own sends
        don't trigger it.

        Must be called after ``connect()``.
        """
        from telethon import events

        self._client.add_event_handler(callback, events.NewMessage(incoming=True))

    async def get_entity(self, entity_id: int):
        """Fetch a Telethon entity (user/chat) by ID.

        Used by the auto-reply handler to resolve sender metadata
        (name, username) for the persona context.
        """
        return await self._client.get_entity(entity_id)

    # -- No session-string accessor ---------------------------------------

    # The session string lives in Telethon's StringSession. We do NOT
    # expose a getter — there is no legitimate reason to read it back
    # from this process, and any such getter would be a credential
    # exfiltration vector. Pinned in test_telethon_client.py.
