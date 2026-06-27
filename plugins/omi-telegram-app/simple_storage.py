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
    try:
        with open(path, "w") as f:
            json.dump(payload, f, default=str, indent=2)
    except Exception as e:
        print(f"⚠️  Could not save {path}: {e}", flush=True)


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
    users[chat_id] = {
        "chat_id": chat_id,
        "omi_uid": omi_uid,
        "persona_id": persona_id,
        "omi_dev_api_key": omi_dev_api_key,
        "bot_token": bot_token,
        "auto_reply_enabled": auto_reply_enabled,
        "created_at": users.get(chat_id, {}).get("created_at", datetime.utcnow().isoformat()),
        "updated_at": datetime.utcnow().isoformat(),
    }
    _save(USERS_FILE, users)


def get_user_by_chat_id(chat_id: str) -> Optional[dict]:
    return users.get(str(chat_id))


def get_user_by_uid(uid: str) -> Optional[dict]:
    for u in users.values():
        if u.get("omi_uid") == uid:
            return u
    return None


def update_auto_reply(chat_id: str, enabled: bool) -> bool:
    if str(chat_id) in users:
        users[str(chat_id)]["auto_reply_enabled"] = enabled
        users[str(chat_id)]["updated_at"] = datetime.utcnow().isoformat()
        _save(USERS_FILE, users)
        return True
    return False


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
