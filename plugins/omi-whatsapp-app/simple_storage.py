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

import copy
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# STORAGE_DIR resolution (P1 from cubic AI review on tests): the env var
# must win over the Docker-default `/app/data` so test fixtures can use
# `monkeypatch.setenv('STORAGE_DIR', tmp_path)` to isolate storage. The
# previous order unconditionally overrode STORAGE_DIR whenever
# `/app/data` existed — fine in production, but it broke test isolation
# any time the test environment happened to have that path mounted.
# Order: explicit env > /app/data (Docker production) > this file's dir
# (local dev fallback).
_explicit_storage_dir = os.getenv("STORAGE_DIR")
if _explicit_storage_dir:
    STORAGE_DIR = _explicit_storage_dir
elif os.path.exists("/app/data"):
    STORAGE_DIR = "/app/data"
else:
    STORAGE_DIR = os.path.dirname(os.path.abspath(__file__))

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
    """Atomically write payload to path. Write to <path>.tmp, fsync, rename, fsync parent.

    Full durability chain (P1 from cubic AI review on PR #8682):
      1. fsync the tmp file's contents — ensures the new file's bytes
         are on stable storage before the rename.
      2. os.replace the tmp file over the target — atomic directory
         entry swap on POSIX (the new inode is now visible).
      3. fsync the parent directory — ensures the rename itself is
         durable. Without this, on ext4 with `data=writeback` a power
         loss after step 2 can leave the directory entry pointing
         either at the old inode OR at a dangling tmp, depending on
         the journal state. The file fsync is not enough.

    Files are written with mode 0o600 (owner read/write only) because
    they contain user access_tokens and verify_tokens. Identified by
    cubic (P1): without explicit restrictive perms, a shared host or
    permissive umask leaves the JSON readable by other users on the box.

    Also ensures the parent directory exists before opening the tmp file —
    without this the first save after a fresh STORAGE_DIR change fails with
    FileNotFoundError and the user is silently never persisted. (cubic P1.)

    Why fsync unconditionally (P1 follow-up from cubic AI review on
    PR #8682): an earlier round tried to skip fsync on history writes
    to avoid blocking the webhook event loop for 5-30ms per turn on
    slow disks. That was unsafe — USERS_FILE holds BOTH credentials
    AND recent_messages, so a skipped-fsync history append could leave
    the entire credential-bearing file as zeros/garbage on power loss.
    The split was illusory at the file level. For now we accept the
    5-30ms fsync cost (negligible compared to the 200-1000ms LLM
    call right before it) and deliver actual power-loss durability.
    Splitting storage into a credential file and a history file is
    the long-term right fix; tracked separately. Mirrors the
    Telegram plugin's `_save`.
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
        # fsync the parent directory so the rename itself is durable.
        # See step (3) in the function docstring. Silently best-effort:
        # some volumes (Windows, NFS) don't support dir fsync, and we
        # don't want to fail the save over a defense-in-depth detail.
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
        # Cubic review 4614064929 P1: the previous behavior was to
        # print a warning and swallow the error, so callers (and
        # ultimately API endpoints) reported success even when the
        # disk write failed. For credential-bearing records that's
        # a silent data-loss bug: a /setup that "succeeded" but
        # didn't persist leaves the user with no recoverable
        # session. Fix: log the error AND re-raise so callers can
        # surface a 5xx and the caller knows persistence failed.
        logger.error(
            "Could not save %s (raised to caller so the failure is visible): %s",
            path,
            e,
        )
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
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
    # Cross-identity history leak (P1 from cubic AI review): if the phone
    # is being rebound to a DIFFERENT persona or omi_uid, the previous
    # owner's conversation history MUST NOT carry over — that would let
    # user A's chat history leak into user B's persona prompt. Wipe on
    # any identity change; only preserve the buffer across re-saves of
    # the same persona (e.g., token rotation, nudge cooldown updates).
    same_identity = existing.get("omi_uid") == omi_uid and existing.get("persona_id") == persona_id
    preserved_history = list(existing.get("recent_messages", [])) if same_identity else []
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
        # T-020: ring buffer of recent conversation turns, oldest first.
        # Mirrors plugins/omi-telegram-app/simple_storage.py so a future
        # shared base class can host both. Phone-keyed (vs chat_id-keyed)
        # because WhatsApp identifies chats by phone number, not chat id.
        # Wiped on identity change above so a rebound phone doesn't
        # inherit the old owner's turns.
        "recent_messages": preserved_history,
    }
    # Credential-bearing record — fsync so a power loss doesn't lose
    # the user's access_token / verify_token / omi_dev_api_key and
    # force a full /setup redo.
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
    # Setup credentials (access_token, phone_number_id, verify_token,
    # omi_uid, persona_id, omi_dev_api_key, phone). fsync so a power
    # loss doesn't strand the user mid-/setup.
    _save(PENDING_FILE, pending_setups)


PENDING_SETUP_TTL_SECONDS = 3600  # 1 hour


def pop_pending_setup(token: str) -> Optional[dict]:
    """Return and remove the setup payload for this token. One-shot.

    Also purges stale entries older than PENDING_SETUP_TTL_SECONDS.
    Identified by maintainer review: setup records contain credentials.
    """
    # Cubic review 4614064929 P1: `datetime.utcnow()` is naive
    # (no tzinfo). In Python 3.11+, `datetime.fromisoformat("...Z")`
    # parses trailing `Z` as timezone-aware. Subtracting an aware
    # datetime from a naive one raises `TypeError`, which was caught
    # with `pass` below — so a `created_at` ending in `Z` would
    # silently NEVER be purged, persisting credential-bearing
    # setup records indefinitely. Fix: use
    # `datetime.now(timezone.utc).replace(tzinfo=None)` for `now`
    # (still naive, so the subtraction works) and strip tzinfo
    # from `created_dt` before comparison.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    stale_tokens = []
    for t, payload in pending_setups.items():
        created = payload.get("created_at")
        if created:
            try:
                created_dt = datetime.fromisoformat(created)
                # Normalize: strip tzinfo if present so the
                # subtraction with `now` (naive) doesn't TypeError.
                if created_dt.tzinfo is not None:
                    created_dt = created_dt.replace(tzinfo=None)
                if (now - created_dt).total_seconds() > PENDING_SETUP_TTL_SECONDS:
                    stale_tokens.append(t)
            except (TypeError, ValueError):
                # Malformed timestamp: don't purge (conservative —
                # we don't know how stale it is). Same as the
                # previous behavior; the P1 fix only addresses
                # the aware-datetime path.
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


# ---------------------------------------------------------------------------
# Recent conversation turns (T-020)
# ---------------------------------------------------------------------------
# Phone-keyed ring buffer (vs chat_id-keyed for Telegram). The Meta WhatsApp
# Cloud API identifies a 1:1 conversation by the sender's phone number, so
# this buffer is keyed by phone. The shape and semantics mirror the Telegram
# plugin so the persona-chat endpoint doesn't need to know which platform
# produced the prior messages.
#
# Buffer size: 10 entries (5 turns). Same rationale as the Telegram plugin.
CHAT_HISTORY_MAX = 10


def get_recent_messages(phone: str) -> list[dict]:
    """Return the recent-message list for a phone (oldest first).

    Returns [] if the phone isn't bound or the buffer is empty.
    The returned list is a deep copy — mutating it (or any nested dict /
    str inside it) does not change what's persisted; use append_message()
    for that. (P2 from cubic AI review: shallow list() copies silently
    corrupt stored history when callers mutate nested fields.)
    """
    user = users.get(str(phone))
    if user is None:
        return []
    return copy.deepcopy(user.get("recent_messages", []))


def append_message(phone: str, role: str, text: str) -> None:
    """Append a turn to the phone's ring buffer (FIFO at CHAT_HISTORY_MAX).

    No-op with a warning if the phone isn't bound — append_message
    shouldn't run before the /start handshake.

    Atomic-turn save (P2 from cubic AI review): the webhook handler calls
    append_message twice per reply (human + ai). The first call writes
    to disk; if the second call crashes / SIGTERMs / fails to write
    between them, we persist a half-turn that the persona will see on
    the next dispatch. To prevent that, callers should pass both turns
    via append_turn() instead. This function remains for the legacy
    single-append callers and writes immediately.
    """
    user = users.get(str(phone))
    if user is None:
        logger.warning(f"append_message: unknown phone {phone!r}, ignoring")
        return
    if role not in ("human", "ai"):
        logger.warning(f"append_message: invalid role {role!r} for phone {phone}, ignoring")
        return
    if not isinstance(text, str) or not text:
        return
    history = user.setdefault("recent_messages", [])
    history.append({"role": role, "text": text, "ts": datetime.utcnow().isoformat()})
    if len(history) > CHAT_HISTORY_MAX:
        user["recent_messages"] = history[-CHAT_HISTORY_MAX:]
    user["updated_at"] = datetime.utcnow().isoformat()
    # History write — skip fsync so the webhook handler doesn't block
    # the asyncio event loop. Credentials in USERS_FILE were already
    # durably committed by save_user() before this call ran. (See
    # _save docstring for the credential-vs-history split.)
    _save(USERS_FILE, users)


def append_turn(phone: str, *, human_text: str, ai_text: str) -> None:
    """Append a complete human→ai turn atomically in a single save.

    P2 from cubic AI review: see append_message docstring — separate
    calls risk persisting a half-turn on crash / SIGTERM. This helper
    appends BOTH entries and persists exactly once, so either both land
    or neither does.

    No-op (with a warning) on invalid input or unknown phone; same
    contract as append_message.
    """
    user = users.get(str(phone))
    if user is None:
        logger.warning(f"append_turn: unknown phone {phone!r}, ignoring")
        return
    if not isinstance(human_text, str) or not human_text:
        return
    if not isinstance(ai_text, str) or not ai_text:
        return
    now = datetime.utcnow().isoformat()
    history = user.setdefault("recent_messages", [])
    history.append({"role": "human", "text": human_text, "ts": now})
    history.append({"role": "ai", "text": ai_text, "ts": now})
    if len(history) > CHAT_HISTORY_MAX:
        user["recent_messages"] = history[-CHAT_HISTORY_MAX:]
    user["updated_at"] = now
    # History write — skip fsync (same reason as append_message).
    _save(USERS_FILE, users)


def clear_recent_messages(phone: str) -> None:
    """Wipe the phone's ring buffer. Exposed for tests / future UI affordance."""
    user = users.get(str(phone))
    if user is None:
        return
    user["recent_messages"] = []
    user["updated_at"] = datetime.utcnow().isoformat()
    # History wipe — skip fsync (same reason as append_turn).
    _save(USERS_FILE, users)
