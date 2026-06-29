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
                # Tighten file perms to 0o600 on load if they're wider
                # (e.g. an older build created the file with default umask,
                # or the operator manually chmod'd it). Best-effort.
                try:
                    os.chmod(path, 0o600)
                except OSError:
                    pass
                with open(path, "r") as f:
                    if target_name == "users":
                        users = json.load(f)
                    else:
                        pending_setups = json.load(f)
        except Exception as e:
            print(f"⚠️  Could not load {path}: {e}", flush=True)


def _save(path: str, payload: dict) -> None:
    """Atomically write payload to path. Write to <path>.tmp, fsync, then os.replace.

    Permissions: file is created with mode 0o600 (owner read/write only).
    The file holds user-bound platform tokens (WhatsApp access_token,
    omidev_api_key) — must not be world-readable. Parent STORAGE_DIR is
    also chmod 0o700 (best-effort) so the file isn't accessible via
    path-traversal on a misconfigured share.

    P1 (cubic follow-up on PR #8528): the previous version used plain
    open() with the default umask, which on most systems creates files
    at 0o644 (world-readable). Anyone with read access to STORAGE_DIR
    could read user access_tokens off disk.

    P1 (cubic follow-up): the previous version swallowed all write
    failures via a broad `except Exception` that just printed a warning.
    If the disk was full or the dir was read-only, /setup would
    'succeed' (because no exception propagated to the caller) but
    the user data wouldn't be persisted. On the next restart the
    plugin would resurrect from the stale (or empty) file, and
    one-shot setup tokens could be re-redeemed indefinitely.

    Now: log the error AND raise OSError. The caller (/setup) maps
    OSError to a 5xx response so the user knows the setup failed.
    """
    tmp = path + ".tmp"
    try:
        # Open with explicit 0o600 so the file never briefly exists
        # with the default umask. O_CREAT|O_EXCL prevents the (rare)
        # race where a stale .tmp file already exists.
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, default=str, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        # Tighten parent dir perms on first write.
        parent = os.path.dirname(path)
        if parent:
            try:
                os.chmod(parent, 0o700)
            except OSError:
                pass
    except OSError as e:
        # Cleanup the .tmp file if it exists. Don't suppress the
        # error — the caller needs to know the write failed.
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        import logging
        logging.getLogger("omi-whatsapp-clone").error(
            "storage write failed for %s: %s", path, e
        )
        raise


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
    elapsed = (datetime.utcnow() - last_dt).total_seconds()
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


def pop_pending_setup(token: str) -> Optional[dict]:
    """Return and remove the setup payload for this token. One-shot."""
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
