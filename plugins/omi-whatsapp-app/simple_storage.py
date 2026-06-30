"""Simple JSON-file storage for the WhatsApp clone plugin.

Identical shape to plugins/omi-telegram-app/simple_storage.py — two in-memory
dicts with file persistence. The only field-name difference: `chat_id` →
`phone` (WhatsApp identifiers are E.164 phone numbers, e.g. "15550001111").

Three stores:
- users: phone (str, E.164) -> user config (omi_uid, persona_id, omi_dev_api_key,
                                access_token, phone_number_id, verify_token,
                                auto_reply_enabled)
- pending_setups: setup_token (str) -> setup payload (access_token, phone_number_id,
                                          verify_token, omi_uid, persona_id,
                                          omi_dev_api_key, phone)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
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

    Files are written with mode 0o600 (owner read/write only) because they
    contain user access_tokens and verify_tokens. Identified by cubic (P1):
    without explicit restrictive perms, a shared host or permissive umask
    leaves the JSON readable by other users on the box.

    Also ensures the parent directory exists before opening the tmp file —
    without this the first save after a fresh STORAGE_DIR change fails with
    FileNotFoundError and the user is silently never persisted. (cubic P1.)
    """
    tmp = f"{path}.{os.getpid()}.tmp"
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
    phone: str,
    *,
    omi_uid: str,
    persona_id: str,
    omi_dev_api_key: str,
    access_token: str,
    phone_number_id: str,
    verify_token: str,
    auto_reply_enabled: bool = False,
) -> None:
    existing = users.get(phone, {})
    users[phone] = {
        "phone": phone,
        "omi_uid": omi_uid,
        "persona_id": persona_id,
        "omi_dev_api_key": omi_dev_api_key,
        "access_token": access_token,
        "phone_number_id": phone_number_id,
        "verify_token": verify_token,
        "auto_reply_enabled": auto_reply_enabled,
        "created_at": existing.get("created_at", datetime.utcnow().isoformat()),
        "updated_at": datetime.utcnow().isoformat(),
        "last_nudge_at": existing.get("last_nudge_at"),
    }
    _save(USERS_FILE, users)


def get_user_by_phone(phone: str) -> Optional[dict]:
    return users.get(str(phone))


def user_with_verify_token_exists(verify_token: str) -> bool:
    """True if any registered user has this verify_token (for /webhook GET)."""
    return any(u.get("verify_token") == verify_token for u in users.values())


def update_auto_reply(phone: str, enabled: bool) -> None:
    """Set auto_reply_enabled for phone. Raises KeyError if unknown."""
    if str(phone) not in users:
        raise KeyError(f"Unknown phone: {phone}")
    users[str(phone)]["auto_reply_enabled"] = enabled
    users[str(phone)]["updated_at"] = datetime.utcnow().isoformat()
    _save(USERS_FILE, users)


def should_nudge(user: dict, cooldown_seconds: float) -> bool:
    """True if it's been longer than cooldown_seconds since the last nudge."""
    last = user.get("last_nudge_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except (TypeError, ValueError):
        return True
    # Normalize to naive UTC for the subtraction. datetime.fromisoformat
    # in Python 3.11+ parses a trailing 'Z' as tz-aware; subtracting an
    # aware datetime from datetime.utcnow() (naive) raises TypeError.
    # P2 (cubic): this would 500 on production webhooks that re-load
    # an old user file where the timestamp was written by a newer Python.
    if last_dt.tzinfo is not None:
        last_dt = last_dt.astimezone(timezone.utc).replace(tzinfo=None)
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    elapsed = (now_naive - last_dt).total_seconds()
    return elapsed >= cooldown_seconds


def mark_nudged(phone: str) -> None:
    """Stamp last_nudge_at on a user so the next message skips the nudge."""
    if str(phone) in users:
        users[str(phone)]["last_nudge_at"] = datetime.utcnow().isoformat()
        users[str(phone)]["updated_at"] = datetime.utcnow().isoformat()
        _save(USERS_FILE, users)


# ---------------------------------------------------------------------------
# pending_setups
# ---------------------------------------------------------------------------
def save_pending_setup(token: str, payload: dict) -> None:
    pending_setups[token] = {
        **payload,
        "created_at": datetime.utcnow().isoformat(),
    }
    _save(PENDING_FILE, pending_setups)


PENDING_SETUP_TTL_SECONDS = 3600  # 1 hour


def pop_pending_setup(token: str) -> Optional[dict]:
    """Return and remove the setup payload for this token. One-shot.

    Also purges stale entries older than PENDING_SETUP_TTL_SECONDS.
    Identified by maintainer review: setup records contain credentials.
    """
    now = datetime.utcnow()
    stale_tokens = []
    for t, payload in pending_setups.items():
        created = payload.get("created_at")
        if created:
            try:
                created_dt = datetime.fromisoformat(created)
                if (now - created_dt).total_seconds() > PENDING_SETUP_TTL_SECONDS:
                    stale_tokens.append(t)
            except (TypeError, ValueError):
                pass
    for t in stale_tokens:
        pending_setups.pop(t, None)
    if stale_tokens and pending_setups:
        _save(PENDING_FILE, pending_setups)
    elif stale_tokens:
        try:
            if os.path.exists(PENDING_FILE):
                os.remove(PENDING_FILE)
        except Exception:
            pass

    payload = pending_setups.pop(token, None)
    if pending_setups:
        _save(PENDING_FILE, pending_setups)
    else:
        try:
            if os.path.exists(PENDING_FILE):
                os.remove(PENDING_FILE)
        except Exception:
            pass
    return payload


def pending_setups_match_verify_token(verify_token: str) -> bool:
    """True if any pending setup has this verify_token (for /webhook GET)."""
    return any(p.get("verify_token") == verify_token for p in pending_setups.values())
