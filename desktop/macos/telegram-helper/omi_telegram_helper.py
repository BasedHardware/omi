#!/usr/bin/env python3
"""Omi Telegram helper — on-device MTProto client.

Runs as a long-lived subprocess of the macOS app. Speaks newline-delimited JSON
over stdio:

  * stdin  — one command object per line (see COMMANDS below)
  * stdout — one event object per line (see EVENTS below)
  * stderr — human-readable diagnostics only (never protocol)

The app (TelegramClientService.swift) owns the lifecycle. This helper never
touches the network except through Telethon, and only after an explicit
`bootstrap`/`connect`. It never auto-sends — it sends only on an explicit `send`
command from the app (which the app issues only for opted-in auto-reply chats or
a user tap).

Why a Python helper: Telegram has no local message DB (unlike iMessage's
chat.db), so reading/sending must go over MTProto. OpenTele converts the already
logged-in Telegram Desktop `tdata` into a Telethon session (no phone-code login),
and Telethon gives event-driven near-real-time read + send.

COMMANDS (stdin):
  {"cmd":"ping"}
  {"cmd":"bootstrap","tdata_path":"…","passcode":"…"?}   # tdata -> session, saved to --session-file
  {"cmd":"connect"}                                       # connect using an existing --session-file
  {"cmd":"start_listening","backfill_days":90}
  {"cmd":"send","chat_id":"123","text":"…"}
  {"cmd":"shutdown"}

EVENTS (stdout):
  {"event":"ready"}                                        # emitted once at startup
  {"event":"pong"}
  {"event":"bootstrapped","me":{"id":…,"username":…}}
  {"event":"connected","me":{…}}
  {"event":"auth_needed","reason":"passcode_required|session_invalid|no_session"}
  {"event":"listening"}
  {"event":"new_message","thread":{…}}                     # normalized TelegramThread + latest_message_id/awaiting_reply
  {"event":"sent","chat_id":"123","message_id":"…"}
  {"event":"error","message":"…","fatal":false}
"""

import argparse
import asyncio
import json
import os
import sys
import threading
from datetime import timezone

# Telethon / OpenTele are imported lazily inside the functions that need them so
# `--selftest` (and error reporting) work even when they're not installed.

THREAD_CONTEXT_LIMIT = 25  # recent messages included per new_message thread snapshot

# On-device cache for downloaded message media (photos), surfaced to the app as
# absolute `image_path`s the inbox renders inline. Kept out of the session dir so
# it can be cleared independently.
MEDIA_CACHE_DIR = os.path.expanduser("~/Library/Caches/omi-telegram-media")


async def _download_photo(message, chat_id) -> str:
    """Download a message's photo to the media cache and return its absolute path,
    or "" when the message has no photo or the download fails. Cached by message id
    so re-runs (backfills) don't re-download."""
    if getattr(message, "photo", None) is None:
        return ""
    try:
        os.makedirs(MEDIA_CACHE_DIR, exist_ok=True)
        dest = os.path.join(MEDIA_CACHE_DIR, f"{chat_id}_{message.id}.jpg")
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            return dest
        written = await message.download_media(file=dest)
        return written or ""
    except Exception as e:  # never let media failure break the thread snapshot
        log(f"photo download failed for {chat_id}/{message.id}: {e}")
        return ""


async def _download_avatar(client, entity, chat_id) -> str:
    """Download a chat/user's profile photo to the media cache; return its absolute
    path, or "" when there's none. Cached per chat and re-fetched only if missing."""
    try:
        os.makedirs(MEDIA_CACHE_DIR, exist_ok=True)
        dest = os.path.join(MEDIA_CACHE_DIR, f"avatar_{chat_id}.jpg")
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            return dest
        written = await client.download_profile_photo(entity, file=dest)
        return written or ""
    except Exception as e:
        log(f"avatar download failed for {chat_id}: {e}")
        return ""


def emit(event: dict) -> None:
    """Write one event as a single JSON line to stdout and flush immediately."""
    sys.stdout.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def log(msg: str) -> None:
    sys.stderr.write(f"[omi-telegram-helper] {msg}\n")
    sys.stderr.flush()


def _aware(dt):
    """Return a tz-aware UTC datetime (Telethon dates are already aware; guard anyway)."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt) -> str:
    """ISO8601 UTC with fractional seconds, matching the backend/Swift contract."""
    return _aware(dt).astimezone(timezone.utc).isoformat()


def _tg_handle(user_id) -> str:
    """Canonical Telegram handle used to key a Person on the backend."""
    return f"tg:{user_id}"


class Helper:
    """Owns the Telethon client and translates commands <-> events."""

    def __init__(self, api_id: int, api_hash: str, session_file: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_file = session_file
        self.client = None  # telethon.TelegramClient
        self.me = None
        self._listening = False
        self._login_phone = None
        self._login_hash = None

    # --- session helpers ---------------------------------------------------

    def _read_session(self):
        try:
            with open(self.session_file, "r", encoding="utf-8") as f:
                s = f.read().strip()
                return s or None
        except FileNotFoundError:
            return None

    def _write_session(self, session_str: str) -> None:
        with open(self.session_file, "w", encoding="utf-8") as f:
            f.write(session_str or "")

    def _me_dict(self):
        if not self.me:
            return None
        return {"id": self.me.id, "username": getattr(self.me, "username", None)}

    # --- lifecycle ---------------------------------------------------------

    async def bootstrap(self, tdata_path: str, passcode: str = None) -> None:
        """Convert Telegram Desktop tdata into a Telethon StringSession (reusing the
        existing authorization, no phone-code login), persist it, and connect."""
        from opentele.td import TDesktop
        from opentele.api import API, UseCurrentSession
        from telethon.sessions import StringSession

        tdesk = TDesktop(tdata_path, passcode=passcode) if passcode else TDesktop(tdata_path)
        if not tdesk.isLoaded():
            # Loaded=False almost always means an unentered Local Passcode.
            emit({"event": "auth_needed", "reason": "passcode_required"})
            return

        # UseCurrentSession keeps the desktop's existing login; the desktop app's
        # own API identity is the natural choice so Telegram sees a known client.
        client = await tdesk.ToTelethon(
            session=StringSession(),
            flag=UseCurrentSession,
            api=API.TelegramDesktop.Generate(),
        )
        await client.connect()
        if not await client.is_user_authorized():
            emit({"event": "auth_needed", "reason": "session_invalid"})
            return
        self._write_session(StringSession.save(client.session))
        self.client = client
        self.me = await client.get_me()
        emit({"event": "bootstrapped", "me": self._me_dict()})

    async def connect(self) -> None:
        """Connect using a previously saved session file."""
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        session_str = self._read_session()
        if not session_str:
            emit({"event": "auth_needed", "reason": "no_session"})
            return
        client = TelegramClient(StringSession(session_str), self.api_id, self.api_hash)
        await client.connect()
        if not await client.is_user_authorized():
            emit({"event": "auth_needed", "reason": "session_invalid"})
            return
        self.client = client
        self.me = await client.get_me()
        emit({"event": "connected", "me": self._me_dict()})

    # --- phone-code login (no tdata; e.g. native macOS Telegram users) ------

    async def send_code(self, phone: str) -> None:
        """Step 1: request a login code. Keeps a live client for sign_in."""
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        self._login_phone = phone
        client = TelegramClient(StringSession(), self.api_id, self.api_hash)
        await client.connect()
        sent = await client.send_code_request(phone)
        self._login_hash = sent.phone_code_hash
        self.client = client  # reused by sign_in
        emit({"event": "code_sent"})

    async def sign_in(self, code: str) -> None:
        """Step 2: sign in with the code; may require a 2FA password."""
        from telethon.errors import SessionPasswordNeededError

        if self.client is None:
            emit({"event": "error", "message": "no login in progress", "fatal": False})
            return
        try:
            await self.client.sign_in(
                self._login_phone, code, phone_code_hash=getattr(self, "_login_hash", None)
            )
        except SessionPasswordNeededError:
            emit({"event": "password_required"})
            return
        await self._finish_login()

    async def sign_in_password(self, password: str) -> None:
        """Step 3 (only if 2FA): finish sign-in with the account password."""
        if self.client is None:
            emit({"event": "error", "message": "no login in progress", "fatal": False})
            return
        await self.client.sign_in(password=password)
        await self._finish_login()

    async def _finish_login(self) -> None:
        from telethon.sessions import StringSession

        self._write_session(StringSession.save(self.client.session))
        self.me = await self.client.get_me()
        emit({"event": "connected", "me": self._me_dict()})

    # --- reading -----------------------------------------------------------

    async def _thread_snapshot(self, chat_id, latest_msg) -> dict:
        """Build a normalized thread (recent context) for a chat, matching the
        backend TelegramThread + fields the app needs to draft/auto-reply.
        ``chat_id`` is Telethon's marked chat id (an int)."""
        from telethon import utils as tl_utils

        entity = await self.client.get_entity(chat_id)
        is_group = not _is_private(entity)
        display_name = tl_utils.get_display_name(entity) or None
        avatar_path = await _download_avatar(self.client, entity, chat_id)

        messages = []
        async for m in self.client.iter_messages(chat_id, limit=THREAD_CONTEXT_LIMIT):
            text = (m.message or "").strip()
            # Download an inline photo (if any) for the visual inbox. Photo-only
            # messages (no caption) are kept so images still render; other media
            # (video/doc/etc.) without text are still skipped for now.
            image_path = await _download_photo(m, chat_id)
            if not text and not image_path:
                continue
            is_from_me = bool(m.out)
            handle = None if (is_from_me or m.sender_id is None) else _tg_handle(m.sender_id)
            msg = {
                "message_id": str(m.id),
                "text": text,
                "is_from_me": is_from_me,
                "timestamp": _iso(m.date),
                "handle": handle,
            }
            if image_path:
                msg["image_path"] = image_path
            messages.append(msg)
        messages.reverse()  # oldest -> newest

        return {
            "chat_id": str(chat_id),
            "display_name": display_name,
            "is_group": is_group,
            "avatar_path": avatar_path or "",
            "latest_message_id": str(latest_msg.id),
            "awaiting_reply": not bool(latest_msg.out),
            "messages": messages,
        }

    async def start_listening(self, backfill_days: int = 90) -> None:
        from telethon import events

        if self.client is None:
            emit({"event": "error", "message": "not connected", "fatal": False})
            return
        if self._listening:
            emit({"event": "listening"})
            return

        @self.client.on(events.NewMessage(incoming=True))
        async def _on_new(event):  # noqa: ANN001
            try:
                snap = await self._thread_snapshot(event.chat_id, event.message)
                emit({"event": "new_message", "thread": snap})
            except Exception as e:  # never let a handler crash the loop
                emit({"event": "error", "message": f"new_message handler: {e}", "fatal": False})

        self._listening = True
        emit({"event": "listening"})
        # Backfill recent 1:1 chats so the inbox is populated immediately and Omi
        # learns each person's history. Emitted as "backfill" (not "new_message")
        # so the app shows them WITHOUT auto-drafting/replying to old threads.
        await self._backfill(backfill_days=backfill_days)

    async def _backfill(self, backfill_days: int = 90, limit: int = 20) -> None:
        from datetime import timedelta
        from telethon.tl.types import User

        try:
            cutoff = None
            try:
                from datetime import datetime as _dt

                cutoff = _dt.now(timezone.utc) - timedelta(days=max(1, backfill_days))
            except Exception:
                cutoff = None
            count = 0
            async for d in self.client.iter_dialogs(limit=100):
                ent = d.entity
                # 1:1 human chats only (skip bots, groups, channels) for the reply feature.
                if not isinstance(ent, User) or getattr(ent, "bot", False):
                    continue
                if not d.message or not (d.message.message or "").strip():
                    continue
                if cutoff is not None and d.message.date and _aware(d.message.date) < cutoff:
                    continue
                try:
                    snap = await self._thread_snapshot(d.id, d.message)
                except Exception as e:
                    emit({"event": "error", "message": f"backfill snapshot: {e}", "fatal": False})
                    continue
                emit({"event": "backfill", "thread": snap})
                count += 1
                if count >= limit:
                    break
        except Exception as e:
            emit({"event": "error", "message": f"backfill: {e}", "fatal": False})

    # --- sending -----------------------------------------------------------

    async def send(self, chat_id: str, text: str) -> None:
        if self.client is None:
            emit({"event": "error", "message": "not connected", "fatal": False})
            return
        try:
            peer = int(chat_id)
        except (TypeError, ValueError):
            peer = chat_id
        sent = await self.client.send_message(peer, text)
        emit({"event": "sent", "chat_id": str(chat_id), "message_id": str(sent.id)})

    # --- command dispatch --------------------------------------------------

    async def handle(self, cmd: dict) -> bool:
        """Return False to request shutdown."""
        name = cmd.get("cmd")
        if name == "ping":
            emit({"event": "pong"})
        elif name == "bootstrap":
            await self.bootstrap(cmd["tdata_path"], cmd.get("passcode"))
        elif name == "connect":
            await self.connect()
        elif name == "send_code":
            await self.send_code(str(cmd["phone"]))
        elif name == "sign_in":
            await self.sign_in(str(cmd["code"]))
        elif name == "sign_in_password":
            await self.sign_in_password(str(cmd["password"]))
        elif name == "start_listening":
            await self.start_listening(int(cmd.get("backfill_days", 90)))
        elif name == "send":
            await self.send(str(cmd["chat_id"]), str(cmd["text"]))
        elif name == "shutdown":
            return False
        else:
            emit({"event": "error", "message": f"unknown command: {name!r}", "fatal": False})
        return True


def _is_private(entity) -> bool:
    # A telethon User (1:1) vs Chat/Channel (group).
    return entity.__class__.__name__ == "User"


def _stdin_reader(loop, queue: "asyncio.Queue") -> None:
    """Blocking stdin reader running on a daemon thread; each line -> the queue."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        asyncio.run_coroutine_threadsafe(queue.put(line), loop)
    # EOF on stdin -> parent went away; enqueue a shutdown sentinel.
    asyncio.run_coroutine_threadsafe(queue.put(None), loop)


async def _run(helper: Helper) -> None:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    threading.Thread(target=_stdin_reader, args=(loop, queue), daemon=True).start()
    emit({"event": "ready"})
    while True:
        line = await queue.get()
        if line is None:
            break
        try:
            cmd = json.loads(line)
        except json.JSONDecodeError as e:
            emit({"event": "error", "message": f"bad json: {e}", "fatal": False})
            continue
        try:
            if not await helper.handle(cmd):
                break
        except KeyError as e:
            emit({"event": "error", "message": f"missing field: {e}", "fatal": False})
        except Exception as e:
            emit({"event": "error", "message": str(e), "fatal": False})
    if helper.client is not None:
        try:
            await helper.client.disconnect()
        except Exception:
            pass


def _emit_fake_thread(cmd: dict) -> None:
    """Emit one synthetic incoming `new_message` (selftest only)."""
    emit(
        {
            "event": "new_message",
            "thread": {
                "chat_id": cmd.get("chat_id", "999"),
                "display_name": cmd.get("display_name", "Selftest Contact"),
                "is_group": False,
                "latest_message_id": "2",
                "awaiting_reply": True,
                "messages": [
                    {
                        "message_id": "1",
                        "text": "hey are you around?",
                        "is_from_me": False,
                        "timestamp": "2026-01-01T00:00:00+00:00",
                        "handle": "tg:12345",
                    },
                    {
                        "message_id": "2",
                        "text": cmd.get("text", "wanna grab food later?"),
                        "is_from_me": False,
                        "timestamp": "2026-01-01T00:00:05+00:00",
                        "handle": "tg:12345",
                    },
                ],
            },
        }
    )


async def _selftest() -> None:
    """Exercise the stdio protocol with NO Telegram/network. Lets the Swift side be
    integration-tested against a fake: bootstrap/connect/send emit deterministic
    fake events; a fake `new_message` is auto-emitted shortly after start_listening
    (and on demand via {"cmd":"emit_fake"})."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    threading.Thread(target=_stdin_reader, args=(loop, queue), daemon=True).start()
    emit({"event": "ready"})
    while True:
        line = await queue.get()
        if line is None:
            break
        try:
            cmd = json.loads(line)
        except json.JSONDecodeError as e:
            emit({"event": "error", "message": f"bad json: {e}", "fatal": False})
            continue
        name = cmd.get("cmd")
        if name == "ping":
            emit({"event": "pong"})
        elif name == "bootstrap":
            emit({"event": "bootstrapped", "me": {"id": 1, "username": "selftest"}})
        elif name == "connect":
            emit({"event": "connected", "me": {"id": 1, "username": "selftest"}})
        elif name == "start_listening":
            emit({"event": "listening"})
            # Self-drive: emit one fake incoming message a moment later so the app's
            # store/inbox path (new_message -> chat -> predraft/auto-reply -> send)
            # can be integration-tested end to end with no Telegram/network.
            async def _auto_emit():
                await asyncio.sleep(1.2)
                _emit_fake_thread({})

            asyncio.create_task(_auto_emit())
        elif name == "emit_fake":
            _emit_fake_thread(cmd)
        elif name == "send":
            emit({"event": "sent", "chat_id": str(cmd.get("chat_id", "999")), "message_id": "9001"})
        elif name == "shutdown":
            break
        else:
            emit({"event": "error", "message": f"unknown command: {name!r}", "fatal": False})


def main() -> None:
    parser = argparse.ArgumentParser(description="Omi Telegram MTProto helper")
    parser.add_argument("--api-id", type=int, default=0)
    parser.add_argument("--api-hash", default="")
    parser.add_argument("--session-file", default="")
    parser.add_argument("--selftest", action="store_true", help="run the stdio protocol with no Telegram/network")
    args = parser.parse_args()

    if args.selftest:
        asyncio.run(_selftest())
        return

    if not (args.api_id and args.api_hash and args.session_file):
        emit({"event": "error", "message": "missing --api-id/--api-hash/--session-file", "fatal": True})
        sys.exit(2)

    helper = Helper(args.api_id, args.api_hash, args.session_file)
    asyncio.run(_run(helper))


if __name__ == "__main__":
    main()
