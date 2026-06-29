"""Simple JSON-file storage for the Telegram clone plugin.

Mirrors plugins/omi-slack-app/simple_storage.py in spirit: two in-memory dicts
with file persistence, so restarts don't lose users or pending setups.

Two stores:
- users: chat_id (str) -> user config (omi_uid, persona_id, api_key, bot_token, auto_reply_enabled)
- pending_setups: setup_token (str) -> setup payload (bot_token, omi_uid, persona_id, omi_dev_api_key, bot_username)
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

STORAGE_DIR = os.getenv("STORAGE_DIR", os.path.dirname(os.path.abspath(__file__)))
if os.path.exists("/app/data"):
    STORAGE_DIR = "/app/data"

USERS_FILE = os.path.join(STORAGE_DIR, "users_data.json")
PENDING_FILE = os.path.join(STORAGE_DIR, "pending_setups.json")

users: dict[str, dict] = {}
pending_setups: dict[str, dict] = {}


def load_storage() -> None:
    global users, pending_setups
    for path, target_name in ((USERS_FILE, "users"), (PENDING_FILE, "pending_setups")):
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    if target_name == "users":
                        users = json.load(f)
                    else:
                        pending_setups = json.load(f)
        except Exception as e:
            print(f"⚠️  Could not load {path}: {e}", flush=True)


def _save(path: str, payload: dict) -> None:
    """Atomically write payload to path. Write to <path>.tmp, fsync, then os.replace.

    A process crash mid-write leaves the original file untouched and a stray
    .tmp on disk for the next startup to clean up.

    Files are written with mode 0o600 (owner read/write only) because they
    contain user tokens and API keys. Identified by cubic (P1): without
    explicit restrictive perms, a shared host or permissive umask leaves
    the JSON readable by other users on the box.
    """
    tmp = path + ".tmp"
    try:
        # Ensure parent directory exists. Without this, the first save after
        # STORAGE_DIR change raises FileNotFoundError and the user is silently
        # never persisted. (cubic P1 on WhatsApp variant — same shape here.)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(payload, f, default=str, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            # Non-POSIX filesystem (e.g. some volumes); don't fail the save.
            pass
    except Exception as e:
        print(f"⚠️  Could not save {path}: {e}", flush=True)
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


load_storage()


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------
def save_user(
    chat_id: str,
    *,
    omi_uid: str,
    persona_id: str,
    omi_dev_api_key: str,
    bot_token: str,
    auto_reply_enabled: bool = False,
) -> None:
    existing = users.get(chat_id, {})
    users[chat_id] = {
        "chat_id": chat_id,
        "omi_uid": omi_uid,
        "persona_id": persona_id,
        "omi_dev_api_key": omi_dev_api_key,
        "bot_token": bot_token,
        "auto_reply_enabled": auto_reply_enabled,
        "created_at": existing.get("created_at", datetime.utcnow().isoformat()),
        "updated_at": datetime.utcnow().isoformat(),
        # last_nudge_at tracks when we last told the user their auto-reply was off,
        # so we don't spam them on every message. 4h cooldown; see main._NUDGE_COOLDOWN.
        "last_nudge_at": existing.get("last_nudge_at"),
    }
    _save(USERS_FILE, users)


def get_user_by_chat_id(chat_id: str) -> Optional[dict]:
    return users.get(str(chat_id))


def get_user_by_uid(uid: str) -> Optional[dict]:
    for u in users.values():
        if u.get("omi_uid") == uid:
            return u
    return None


def update_auto_reply(chat_id: str, enabled: bool) -> None:
    """Set auto_reply_enabled for chat_id. Raises KeyError if unknown.

    The caller is expected to have already verified the chat_id exists
    (e.g. via get_user_by_chat_id); we raise here to surface any bug in
    that assumption rather than silently no-oping.
    """
    if str(chat_id) not in users:
        raise KeyError(f"Unknown chat_id: {chat_id}")
    users[str(chat_id)]["auto_reply_enabled"] = enabled
    users[str(chat_id)]["updated_at"] = datetime.utcnow().isoformat()
    _save(USERS_FILE, users)


def should_nudge(user: dict, cooldown_seconds: float) -> bool:
    """True if it's been longer than cooldown_seconds since the last nudge.

    Returns True if last_nudge_at is missing/None (never nudged) or older than
    the cooldown window. Used by the webhook handler to throttle the
    "auto-reply is disabled" message.
    """
    last = user.get("last_nudge_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except (TypeError, ValueError):
        return True
    elapsed = (datetime.utcnow() - last_dt).total_seconds()
    return elapsed >= cooldown_seconds


def mark_nudged(chat_id: str) -> None:
    """Stamp last_nudge_at on a user so the next message skips the nudge."""
    if str(chat_id) in users:
        users[str(chat_id)]["last_nudge_at"] = datetime.utcnow().isoformat()
        users[str(chat_id)]["updated_at"] = datetime.utcnow().isoformat()
        _save(USERS_FILE, users)


# ---------------------------------------------------------------------------
# pending_setups — one-shot tokens used during the /setup handshake.
# ---------------------------------------------------------------------------
def save_pending_setup(token: str, payload: dict) -> None:
    pending_setups[token] = {
        **payload,
        "created_at": datetime.utcnow().isoformat(),
    }
    _save(PENDING_FILE, pending_setups)


def pop_pending_setup(token: str) -> Optional[dict]:
    """Return and remove the setup payload for this token. One-shot."""
    payload = pending_setups.pop(token, None)
    if pending_setups:
        _save(PENDING_FILE, pending_setups)
    else:
        # Empty dict — clear the file so it doesn't linger with stale data.
        try:
            if os.path.exists(PENDING_FILE):
                os.remove(PENDING_FILE)
        except Exception:
            pass
    return payload
