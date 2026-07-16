"""Simple JSON-file storage for the Telegram clone plugin.

Mirrors plugins/omi-slack-app/simple_storage.py in spirit: two in-memory dicts
with file persistence, so restarts don't lose users or pending setups.

Two stores:
- users: chat_id (str) -> user config (omi_uid, persona_id, api_key, bot_token, auto_reply_enabled)
- pending_setups: setup_token (str) -> setup payload (bot_token, omi_uid, persona_id, omi_dev_api_key, bot_username)
"""

from __future__ import annotations

import copy
import json
import logging
import os
from datetime import datetime
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

    A process crash mid-write leaves the original file untouched and
    a stray .tmp on disk for the next startup to clean up.

    Files are written with mode 0o600 (owner read/write only) because
    they contain user tokens and API keys. Identified by cubic (P1):
    without explicit restrictive perms, a shared host or permissive
    umask leaves the JSON readable by other users on the box.

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
    the long-term right fix; tracked separately.
    """
    tmp = f"{path}.{os.getpid()}.tmp"
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
    bot_username: str = "",
) -> None:
    existing = users.get(chat_id, {})
    # Cross-identity history leak (P1 from cubic AI review): if the chat
    # is being rebound to a DIFFERENT persona or omi_uid, the previous
    # owner's conversation history MUST NOT carry over — that would let
    # user A's chat history leak into user B's persona prompt. Wipe on
    # any identity change; only preserve the buffer across re-saves of
    # the same persona (e.g., token rotation, nudge cooldown updates).
    same_identity = existing.get("omi_uid") == omi_uid and existing.get("persona_id") == persona_id
    preserved_history = list(existing.get("recent_messages", [])) if same_identity else []
    users[chat_id] = {
        "chat_id": chat_id,
        "omi_uid": omi_uid,
        "persona_id": persona_id,
        "omi_dev_api_key": omi_dev_api_key,
        "bot_token": bot_token,
        "auto_reply_enabled": auto_reply_enabled,
        "bot_username": bot_username or existing.get("bot_username", ""),
        "created_at": existing.get("created_at", datetime.utcnow().isoformat()),
        "updated_at": datetime.utcnow().isoformat(),
        # last_nudge_at tracks when we last told the user their auto-reply was off,
        # so we don't spam them on every message. 4h cooldown; see main._NUDGE_COOLDOWN.
        "last_nudge_at": existing.get("last_nudge_at"),
        # T-020: ring buffer of recent conversation turns, oldest first.
        # Pre-seeded as empty list on user-create so callers don't need to
        # handle the missing-key case. Appended to on every persona dispatch
        # and trimmed to CHAT_HISTORY_MAX by append_message(). Wiped on
        # identity change above so a rebound chat doesn't inherit the old
        # owner's turns.
        "recent_messages": preserved_history,
    }
    # Credential-bearing record — fsync so a power loss doesn't lose
    # the user's bot_token / omi_dev_api_key and force a full /setup
    # redo. (See _save docstring for the credential-vs-history split.)
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
    # Setup credentials (bot_token, omi_uid, persona_id, omi_dev_api_key).
    # fsync so a power loss doesn't strand the user mid-/setup.
    _save(PENDING_FILE, pending_setups)


PENDING_SETUP_TTL_SECONDS = 3600  # 1 hour — setup links expire after this


def pop_pending_setup(token: str) -> Optional[dict]:
    """Return and remove the setup payload for this token. One-shot.

    Also purges stale entries older than PENDING_SETUP_TTL_SECONDS.
    These one-shot records contain platform credentials and Omi
    developer API keys, so abandoned/leaked setup links should not
    remain redeemable indefinitely. Identified by maintainer review.

    P2 from cubic AI review (PR #8682): the previous version
    unconditionally called _save at the end even when nothing
    changed — if the requested token was unknown AND there were
    no stale entries to purge, we'd still rewrite (or remove)
    the on-disk file. The webhook can hit this path with an
    unknown / forged token; that's exactly the case where we
    want the cheapest possible response. Track a `changed` flag
    and only persist when state actually moved.
    """
    # Purge stale entries first
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
        logger.info(f"purged stale setup token {t[:8]}... (expired)")
    if stale_tokens and pending_setups:
        _save(PENDING_FILE, pending_setups)
    elif stale_tokens:
        try:
            if os.path.exists(PENDING_FILE):
                os.remove(PENDING_FILE)
        except Exception:
            pass

    # Pop the requested token. Track whether the pop actually removed
    # anything so we don't rewrite the file when both the pop AND the
    # purge were no-ops (e.g. unknown token, no stale entries).
    payload = pending_setups.pop(token, None)
    if payload is not None:
        # Pop succeeded — persist the updated (smaller) dict or clear
        # the file if it's now empty. fsync=True: setup credentials
        # aren't rebuildable from the platform API; we want this
        # durable.
        if pending_setups:
            _save(PENDING_FILE, pending_setups)
        else:
            try:
                if os.path.exists(PENDING_FILE):
                    os.remove(PENDING_FILE)
            except Exception:
                pass
    # If payload is None AND no stale tokens were purged, the in-memory
    # dict and on-disk file are both unchanged — skip the IO entirely.
    return payload


# ---------------------------------------------------------------------------
# Recent conversation turns (T-020)
# ---------------------------------------------------------------------------
# Per-chat ring buffer so the persona has continuity across webhook calls.
# Telegram sends each message as a fresh POST; without this buffer the
# LLM has zero memory of what the user said 30 seconds ago and answers
# like "yo / what's up / I'm looking for a coffee shop in Asok" lose the
# thread after the second message.
#
# Storage shape: list[{"role": "human"|"ai", "text": str, "ts": iso8601}]
#   - role == "human" for inbound Telegram messages
#   - role == "ai" for the persona's outbound replies
#   - ts is when we observed the message (UTC, ISO format)
#
# Buffer size: 10 entries (5 turns). Older entries drop FIFO via list
# slicing in append_message. 5 turns is enough for short text-message
# threads; we deliberately don't keep long histories because the model
# has a token budget and the persona doesn't need a 100-message
# transcript to answer "what's my favorite coffee?".
CHAT_HISTORY_MAX = 10


def get_recent_messages(chat_id: str) -> list[dict]:
    """Return the recent-message list for a chat (oldest first).

    Returns [] if the chat isn't bound, the user record has no
    recent_messages key (legacy data from before T-020), or the buffer
    is empty. The returned list is a deep copy — mutating it (or any
    nested dict / str inside it) does not change what's persisted;
    use append_message() for that. (P2 from cubic AI review: shallow
    list() copies silently corrupt stored history when callers mutate
    nested fields.)
    """
    user = users.get(str(chat_id))
    if user is None:
        return []
    return copy.deepcopy(user.get("recent_messages", []))


def append_message(chat_id: str, role: str, text: str) -> None:
    """Append a turn to the chat's ring buffer.

    Args:
        chat_id: Telegram chat id (str-coerced for dict key consistency).
        role: 'human' for inbound messages, 'ai' for the persona's reply.
        text: The message text. Not truncated here — the inbound text
            path already caps at Telegram's 4096-char limit, and replies
            are bounded by the LLM output. We trim on append to keep
            the buffer at CHAT_HISTORY_MAX entries (FIFO).

    No-op (with a warning) if the chat_id isn't bound — append_message
    shouldn't be called before the /start handshake, but if it is, we'd
    rather log and continue than raise into the webhook.

    Atomic-turn save (P2 from cubic AI review): the webhook handler calls
    append_message twice per reply (human + ai). The first call writes
    to disk; if the second call crashes / SIGTERMs / fails to write
    between them, we persist a half-turn that the persona will see on
    the next dispatch. To prevent that, callers should pass both turns
    via append_turn() instead. This function remains for the legacy
    single-append callers and writes immediately.
    """
    user = users.get(str(chat_id))
    if user is None:
        logger.warning(f"append_message: unknown chat_id {chat_id!r}, ignoring")
        return
    if role not in ("human", "ai"):
        logger.warning(f"append_message: invalid role {role!r} for chat {chat_id}, ignoring")
        return
    if not isinstance(text, str) or not text:
        return
    history = user.setdefault("recent_messages", [])
    history.append({"role": role, "text": text, "ts": datetime.utcnow().isoformat()})
    # FIFO trim. Slicing keeps the last CHAT_HISTORY_MAX entries.
    if len(history) > CHAT_HISTORY_MAX:
        user["recent_messages"] = history[-CHAT_HISTORY_MAX:]
    user["updated_at"] = datetime.utcnow().isoformat()
    # History write — skip fsync so the webhook handler doesn't block
    # the asyncio event loop for 5-30ms per reply turn on slow disks.
    # The history buffer is rebuildable from the Telegram API on
    # power loss (we just lose the last few turns of context). The
    # credentials in USERS_FILE were already durably committed by
    # save_user() before this call ran. (See _save docstring.)
    _save(USERS_FILE, users)


def append_turn(chat_id: str, *, human_text: str, ai_text: str) -> None:
    """Append a complete human→ai turn atomically in a single save.

    P2 from cubic AI review: the webhook calls append_message twice per
    reply (once for the inbound text, once for the persona reply). With
    separate calls, a crash / SIGTERM / disk-full between the two writes
    leaves the buffer with a half-turn (human with no matching ai),
    which the persona then sees on the next dispatch and may treat as a
    prompt to "answer". This helper appends BOTH entries and persists
    exactly once, so either both land or neither does.

    No-op (with a warning) on invalid input or unknown chat_id; same
    contract as append_message.
    """
    user = users.get(str(chat_id))
    if user is None:
        logger.warning(f"append_turn: unknown chat_id {chat_id!r}, ignoring")
        return
    if not isinstance(human_text, str) or not human_text:
        return
    if not isinstance(ai_text, str) or not ai_text:
        # Refuse to persist a half-turn even when called via the atomic
        # helper. Caller must invoke append_message directly for an
        # ai-only / human-only update.
        return
    now = datetime.utcnow().isoformat()
    history = user.setdefault("recent_messages", [])
    history.append({"role": "human", "text": human_text, "ts": now})
    history.append({"role": "ai", "text": ai_text, "ts": now})
    if len(history) > CHAT_HISTORY_MAX:
        user["recent_messages"] = history[-CHAT_HISTORY_MAX:]
    user["updated_at"] = now
    # History write — skip fsync so the webhook handler doesn't block
    # the asyncio event loop. See append_message above.
    _save(USERS_FILE, users)


def clear_recent_messages(chat_id: str) -> None:
    """Wipe the chat's ring buffer. Not used in v0.1 but exposed for tests
    and for a future "reset conversation" UI affordance."""
    user = users.get(str(chat_id))
    if user is None:
        return
    user["recent_messages"] = []
    user["updated_at"] = datetime.utcnow().isoformat()
    # History wipe — skip fsync (same reason as append_turn).
    _save(USERS_FILE, users)
