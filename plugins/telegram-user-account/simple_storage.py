"""Simple JSON-file storage for the Telegram user-account AI-Clone plugin.

Schema (deliberately different from the bot plugin's storage — this
plugin authenticates as the user's PERSONAL Telegram account via
Telethon, so the storage is keyed by Telegram user id, not chat id,
and there's no bot_token / pending_setups concept):

- users: dict[str, dict] — Telegram user id (str) → user config
  {
    omi_uid, persona_id, omi_dev_api_key, auto_reply_enabled,
    chat_ids: [str, ...]   # chats where auto-reply is enabled for this user
  }

- chats: dict[str, dict] — chat id (str) → chat ring buffer
  {
    recent_messages: [
      {"role": "human" | "ai", "text": str, "ts": iso8601}
    ]
    # Capped at CHAT_HISTORY_MAX entries (FIFO via list slicing).
  }

- account: dict — account metadata populated from Telethon's get_me()
  {
    phone, name, device_label
  }

Files written to STORAGE_DIR with mode 0o600 (user tokens and session
data are sensitive). Atomic write via tmp file + os.replace + parent
fsync, matching the durability chain used by the WhatsApp and
Telegram bot plugins (P1 from cubic AI review on PR #8682).

SECURITY (pinned in test/test_session_never_logged.py):
- session_string: NEVER persisted to disk
- api_id, api_hash: NEVER persisted to disk (they're the App hash
  from my.telegram.org — public, but not the storage layer's
  concern)
- The session string is held in memory only and passed to Telethon
  via subprocess environment at startup. After that, Telethon
  manages it. Nothing in the plugin's storage layer ever sees it.
"""

from __future__ import annotations

import copy
import itertools
import json
import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# STORAGE_DIR resolution (P1 from cubic AI review on tests): the env
# var must win over the Docker-default `/app/data` so test fixtures
# can use `monkeypatch.setenv('TELEGRAM_USER_STORAGE_DIR', tmp_path)`
# to isolate storage. Same pattern as the WhatsApp + Telegram bot
# plugins for consistency.
_explicit_storage_dir = os.getenv("TELEGRAM_USER_STORAGE_DIR")
if _explicit_storage_dir:
    STORAGE_DIR = _explicit_storage_dir
elif os.path.exists("/app/data"):
    STORAGE_DIR = "/app/data"
else:
    STORAGE_DIR = os.path.dirname(os.path.abspath(__file__))

USERS_FILE = os.path.join(STORAGE_DIR, "users_data.json")
CHATS_FILE = os.path.join(STORAGE_DIR, "chats_data.json")
ACCOUNT_FILE = os.path.join(STORAGE_DIR, "account.json")

users: dict[str, dict] = {}
chats: dict[str, dict] = {}
account: dict = {}


# Per-process monotonic counter for atomic-write temp filenames.
# Each save() to the same path gets a unique tmp file so concurrent
# FastAPI handlers don't race on {pid}.tmp — both writers would
# truncate the first writer's in-flight data. cubic review
# 4615559812 P1 (same race was fixed in plugin_discovery.py per
# cubic review #8682). Imported here so load_storage's reset
# sees the same empty defaults the storage starts with.
_tmp_counter = itertools.count(1)


def load_storage() -> None:
    """Load USERS_FILE + CHATS_FILE + ACCOUNT_FILE into the in-memory dicts.

    Idempotent and clean-slate: each call RESETS ``users``/``chats``/
    ``account`` to empty dicts FIRST, then loads whatever is on disk.
    If a storage file has been deleted between calls, its global
    doesn't keep stale entries from the previous load.

    Tests should call this in their fixture if they need a clean
    slate (cubic review 4615559812 P1: the previous implementation
    only overwrote when the JSON file existed, so a deleted file
    left old in-memory state hanging around).
    """
    global users, chats, account
    # Reset to empty defaults so a missing file yields empty
    # state, not "whatever was here from the previous load".
    users = {}
    chats = {}
    account = {}
    for path, target_name in (
        (USERS_FILE, "users"),
        (CHATS_FILE, "chats"),
    ):
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    payload = json.load(f)
                if not isinstance(payload, dict):
                    print(
                        f"⚠️  {path} is not a dict (got {type(payload).__name__}); " "resetting to empty",
                        flush=True,
                    )
                    continue
                if target_name == "users":
                    users = payload
                else:
                    chats = payload
        except Exception as e:
            print(f"⚠️  Could not load {path}: {e}", flush=True)
    try:
        if os.path.exists(ACCOUNT_FILE):
            with open(ACCOUNT_FILE, "r") as f:
                payload = json.load(f)
            if isinstance(payload, dict):
                account = payload
    except Exception as e:
        print(f"⚠️  Could not load {ACCOUNT_FILE}: {e}", flush=True)


def _save(path: str, payload: dict) -> None:
    """Atomic write with full durability chain.

    Same implementation as the WhatsApp and Telegram bot plugins:
    tmp file + fsync + os.replace + parent fsync. Cubic review
    4614271733 P1 (already applied in the WhatsApp variant): write
    failures are NOT swallowed. The exception propagates so the
    caller can surface a 5xx to the desktop instead of silently
    reporting success.

    The tmp filename uses ``{pid}.{counter}.tmp`` (per-process
    monotonic counter) instead of just ``{pid}.tmp``. The
    deterministic-by-pid scheme would race when two FastAPI
    request handlers save to the same path within one process
    (concurrent chat reply -> /recent_messages save). cubic review
    4615559812 P1: adopted the same fix already applied to
    plugin_discovery.py in PR #8682.
    """
    tmp = f"{path}.{os.getpid()}.{next(_tmp_counter)}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(payload, f, default=str, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        try:
            dir_path = os.path.dirname(path)
            if dir_path:
                dir_fd = os.open(dir_path, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
        except OSError:
            pass
    except Exception as e:
        logger.error(
            "Could not save %s (raised to caller so the failure is visible): %s",
            path,
            type(e).__name__,
        )
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        raise


# ---------------------------------------------------------------------------
# users — keyed by Telegram user id
# ---------------------------------------------------------------------------


def save_user(
    telegram_user_id: str,
    *,
    omi_uid: str,
    persona_id: str,
    omi_dev_api_key: str,
    auto_reply_enabled: bool = False,
) -> None:
    """Persist per-user config.

    SECURITY: this function's signature intentionally has NO
    `session_string` parameter. The session string is held only in
    memory by the Telethon client; it is never written to disk. If
    a future change adds a session parameter, the regression
    test will fail loudly.
    """
    existing = users.get(telegram_user_id, {})
    preserved_chat_ids = list(existing.get("chat_ids", []))
    users[telegram_user_id] = {
        "telegram_user_id": telegram_user_id,
        "omi_uid": omi_uid,
        "persona_id": persona_id,
        "omi_dev_api_key": omi_dev_api_key,
        "auto_reply_enabled": auto_reply_enabled,
        "chat_ids": preserved_chat_ids,
        "created_at": existing.get("created_at", datetime.utcnow().isoformat()),
        "updated_at": datetime.utcnow().isoformat(),
    }
    _save(USERS_FILE, users)


def get_user_by_telegram_user_id(telegram_user_id: str) -> Optional[dict]:
    return users.get(telegram_user_id)


def update_auto_reply(telegram_user_id: str, enabled: bool) -> None:
    if telegram_user_id not in users:
        raise KeyError(f"Unknown telegram_user_id: {telegram_user_id}")
    users[telegram_user_id]["auto_reply_enabled"] = enabled
    users[telegram_user_id]["updated_at"] = datetime.utcnow().isoformat()
    _save(USERS_FILE, users)


# ---------------------------------------------------------------------------
# chats — keyed by chat id
# ---------------------------------------------------------------------------
CHAT_HISTORY_MAX = 10


def ensure_chat(chat_id: str) -> None:
    """Create a chat entry if it doesn't exist.

    Called by the auto-reply handler for incoming DMs from new
    contacts that haven't been pre-registered.
    """
    if chat_id not in chats:
        chats[chat_id] = {"recent_messages": [], "created_at": datetime.utcnow().isoformat()}
        _save(CHATS_FILE, chats)


def append_message(chat_id: str, role: str, text: str) -> None:
    if chat_id not in chats:
        ensure_chat(chat_id)
    if role not in ("human", "ai"):
        logger.warning(f"append_message: invalid role {role!r} for chat {chat_id}, ignoring")
        return
    if not isinstance(text, str) or not text:
        return
    history = chats[chat_id].setdefault("recent_messages", [])
    history.append({"role": role, "text": text, "ts": datetime.utcnow().isoformat()})
    if len(history) > CHAT_HISTORY_MAX:
        chats[chat_id]["recent_messages"] = history[-CHAT_HISTORY_MAX:]
    chats[chat_id]["updated_at"] = datetime.utcnow().isoformat()
    _save(CHATS_FILE, chats)


def get_recent_messages(chat_id: str) -> list[dict]:
    chat = chats.get(chat_id)
    if chat is None:
        return []
    return copy.deepcopy(chat.get("recent_messages", []))


def clear_recent_messages(chat_id: str) -> None:
    if chat_id not in chats:
        return
    chats[chat_id]["recent_messages"] = []
    chats[chat_id]["updated_at"] = datetime.utcnow().isoformat()
    _save(CHATS_FILE, chats)


# ---------------------------------------------------------------------------
# account — populated from Telethon's get_me()
# ---------------------------------------------------------------------------


def save_account_metadata(phone: str, name: str, device_label: str) -> None:
    global account
    account = {
        "phone": phone,
        "name": name,
        "device_label": device_label,
        "updated_at": datetime.utcnow().isoformat(),
    }
    _save(ACCOUNT_FILE, account)


def get_account_metadata() -> dict:
    return dict(account)


load_storage()
