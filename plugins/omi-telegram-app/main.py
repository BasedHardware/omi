"""OMI Telegram AI-Clone plugin.

Routes:
- GET  /health
- POST /setup     Register a new bot token, return a deep-link URL.
- POST /webhook   Receive Telegram updates: handle /start handshake, dispatch
                  to persona if auto-reply is on, otherwise nudge (rate-limited).
- POST /toggle    Flip auto_reply_enabled for a chat (called by Chat Tools).

The plugin is intentionally minimal: no framework, no async lifecycle beyond
FastAPI's request handler. Mirrors plugins/omi-slack-app/main.py in shape.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import sys
import errno
import fcntl
from typing import Optional

# Add plugins/_shared to sys.path so `from persona_client import chat` works.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SHARED = os.path.abspath(os.path.join(_HERE, "..", "_shared"))
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import httpx  # noqa: E402
from fastapi import Depends, FastAPI, Header, HTTPException, Request  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import simple_storage  # noqa: E402
import telegram_client  # noqa: E402
from auth import require_bearer  # noqa: E402  (shared bearer-token auth — see plugins/_shared/auth.py)
from persona_client import chat as _persona_chat  # noqa: E402  (re-export of plugins/_shared/persona_client.chat)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("omi-telegram-clone")


# ---------------------------------------------------------------------------
# Webhook secret
# ---------------------------------------------------------------------------
# WEBHOOK_SECRET is the value Telegram sends back in X-Telegram-Bot-Api-Secret-Token
# on every webhook delivery. Resolution order:
#   1. TELEGRAM_WEBHOOK_SECRET env var (production — operator-managed)
#   2. <STORAGE_DIR>/webhook_secret (auto-generated, persisted on first run;
#      survives restarts so Telegram's stored secret stays in sync)
#   3. secrets.token_urlsafe(32) (first run, dev installs) — and immediately
#      written to <STORAGE_DIR>/webhook_secret so the next start picks it up.
#
# P1 (cubic): previously, when TELEGRAM_WEBHOOK_SECRET was unset, the plugin
# generated a fresh random secret on every startup. Telegram's stored
# webhook secret (set via setWebhook) then no longer matched incoming
# deliveries' X-Telegram-Bot-Api-Secret-Token header, and every webhook
# request got a 401 until the user re-ran /setup. Persisting the auto-
# generated secret to a file makes the first-run experience stable
# across restarts; production still has the option of env-var override.
#
# Storage path: default to the PLUGIN's own directory (not /tmp) so the
# secret survives reboots. /tmp is ephemeral on most systems — using it
# as the default would defeat the whole "survive restarts" goal. The
# STORAGE_DIR env var overrides this (same convention as the plugin's
# simple_storage.py).
def _resolve_webhook_secret():
    """Return (secret, source_description). Side effect: may write the
    freshly generated secret to <STORAGE_DIR>/webhook_secret with mode
    0o600 (best-effort; logged on failure).

    Security:
    - File is opened with O_NOFOLLOW so a pre-existing symlink at the
      target path can't redirect the write to an attacker-controlled
      location (P1 cubic follow-up: pre-fix version used O_CREAT only
      and followed symlinks, allowing a local attacker to pre-create
      a symlink and exfiltrate the secret).
    - File is opened with O_EXCL to atomically claim the path —
      prevents two processes from racing on first startup and ending
      up with different in-memory secrets (P1 cubic follow-up:
      pre-fix version used O_CREAT|O_TRUNC which overwrites any
      in-progress writer's file).
    - File is created with mode 0o600 (owner read/write only) so the
      secret isn't world-readable.
    - A short-lived flock on the path serializes concurrent first-run
      processes. The first to grab the lock writes; the second sees
      the freshly-written file and reads it.
    """
    env_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET")
    if env_secret:
        return env_secret, "configured via env"

    # Default to a persistent path (the plugin's own directory) so the
    # webhook secret survives reboots. /tmp/omi-tg-e2e is the LEGACY
    # default and is still honored for back-compat with existing installs.
    default_storage_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data"
    )
    if not os.path.exists(default_storage_dir):
        # Plugin shipped without a data/ subdir; fall back to the
        # plugin dir itself (which is git-ignored, persistent).
        default_storage_dir = os.path.dirname(os.path.abspath(__file__))
    legacy_storage_dir = "/tmp/omi-tg-e2e"

    storage_dir = os.getenv("STORAGE_DIR") or default_storage_dir
    secret_path = os.path.join(storage_dir, "webhook_secret")

    # Try the active path first
    persisted = _read_secret_safely(secret_path)
    if persisted:
        return persisted, f"loaded from {secret_path}"

    # Active path missing/empty — also try the legacy /tmp path on the
    # theory that an older install has a secret there. If found, copy
    # it to the active path so future reads use the persistent store.
    if storage_dir != legacy_storage_dir:
        legacy_path = os.path.join(legacy_storage_dir, "webhook_secret")
        legacy = _read_secret_safely(legacy_path)
        if legacy:
            # Migrate from /tmp to the persistent path so the next
            # restart doesn't need the legacy fallback.
            _write_secret_atomically(secret_path, legacy)
            return legacy, f"loaded from {legacy_path} (migrated to {secret_path})"

    # First run: generate + persist. The flock is held by whichever
    # process wins the race; the others will see the freshly-written
    # file on the next check.
    secret = secrets.token_urlsafe(32)
    _write_secret_atomically(secret_path, secret)
    return secret, f"auto-generated and persisted to {secret_path}"


def _read_secret_safely(path: str):
    """Read a webhook-secret file if it exists. Returns the secret
    string or None. O_NOFOLLOW on open refuses symlinks (the
    caller would be a local attacker pointing the path at, e.g.,
    /dev/stdin to read what the process then writes)."""
    try:
        # O_RDONLY | O_NOFOLLOW: read the file, error if it's a symlink.
        # The secret is small (43 chars from token_urlsafe(32)) so the
        # read syscall returns it all at once.
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as e:
        if e.errno == errno.ENOENT:
            return None  # not present
        # ELOOP means path is a symlink (O_NOFOLLOW refused). Don't
        # follow it — that's the whole point. Treat as missing.
        if e.errno == errno.ELOOP:
            logger.warning("webhook secret path %s is a symlink \u2014 refusing to read", path)
            return None
        # Any other error (EACCES, EIO, ...): the file exists but we
        # can't read it. Log so operators can debug perm/mount issues,
        # then fall back to generating a new secret.
        logger.warning("webhook secret file %s unreadable: %s", path, e)
        return None
    try:
        with os.fdopen(fd, "r") as f:
            return f.read().strip() or None
    except OSError:
        return None


def _write_secret_atomically(path: str, secret: str) -> bool:
    """Write secret to path with mode 0o600, atomically. Returns True
    on success. P1 (cubic follow-up): uses O_CREAT|O_EXCL|O_NOFOLLOW
    to atomically claim the path AND refuse symlinks. A short-lived
    flock serializes concurrent first-run writers — whichever process
    wins the lock writes; the others see the file on the next read."""
    import errno
    import fcntl
    import tempfile

    parent = os.path.dirname(path)
    if parent:
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError:
            return False

    # Serialize concurrent writers. A short blocking flock so the
    # second process waits for the first to finish, then re-reads.
    # We use a sidecar .lock file because we can't flock() a path
    # that may not exist yet.
    lock_path = path + ".lock"
    lock_fd = None
    try:
        lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
    except OSError as e:
        if lock_fd is not None:
            os.close(lock_fd)
        return False

    try:
        # Re-check: another process may have just written the file
        # while we were waiting for the lock.
        existing = _read_secret_safely(path)
        if existing:
            # Someone else already wrote; don't overwrite their secret.
            return True  # but the caller will read it on its own
        # Open the file. O_CREAT|O_EXCL means we fail if the file
        # already exists (race against another process that beat us
        # to it between the re-check and the open). O_NOFOLLOW means
        # we error out if the path is a symlink (local attacker could
        # have pre-created a symlink at this path to exfiltrate the
        # secret to an attacker-readable location).
        try:
            fd = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
            )
        except OSError as e:
            if e.errno == errno.EEXIST:
                # Another process wrote between the re-check and
                # the open. Their file is fine; let them keep it.
                return True
            return False
        with os.fdopen(fd, "w") as f:
            f.write(secret)
        # Tighten parent dir perms so the file isn't accessible via
        # path-traversal on a misconfigured share.
        try:
            os.chmod(parent, 0o700)
        except OSError:
            pass
        return True
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(lock_fd)
        except OSError:
            pass


WEBHOOK_SECRET, _webhook_source = _resolve_webhook_secret()
if _webhook_source == "configured via env":
    logger.info("Webhook secret: configured via env")
elif _webhook_source == "loaded from $STORAGE_DIR/webhook_secret":
    logger.info("Webhook secret: loaded from $STORAGE_DIR/webhook_secret")
else:
    logger.warning(
        "Webhook secret: auto-generated and persisted "
        "(set TELEGRAM_WEBHOOK_SECRET to override)"
    )

# Base URL of the Omi backend that the persona API lives on. Defaults to prod.
OMI_BASE_URL = os.getenv("OMI_BASE_URL", "https://api.omi.me")

# How often we re-nudge a user who has auto-reply disabled. Default 4 hours.
try:
    _NUDGE_COOLDOWN_SECONDS = float(os.getenv("NUDGE_COOLDOWN_SECONDS", "14400"))
except ValueError:
    logger.warning("NUDGE_COOLDOWN_SECONDS is not a float; defaulting to 14400")
    _NUDGE_COOLDOWN_SECONDS = 14400.0


app = FastAPI(
    title="OMI Telegram AI-Clone",
    description="Self-hosted Telegram plugin that lets Omi reply on the user's behalf.",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "service": "omi-telegram-clone", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# /setup
# ---------------------------------------------------------------------------
class SetupRequest(BaseModel):
    bot_token: str
    omi_uid: str
    persona_id: str
    omi_dev_api_key: str
    public_base_url: str  # where Telegram will POST updates (e.g. https://clone.example.com)


class SetupResponse(BaseModel):
    deep_link: str
    bot_username: str
    setup_token: str


@app.post("/setup", response_model=SetupResponse, dependencies=[Depends(require_bearer)])
async def setup(req: SetupRequest):
    """Register the user's bot and return a one-time deep link for the user to click."""
    webhook_url = f"{req.public_base_url.rstrip('/')}/webhook"

    # setWebhook — tells Telegram where to POST updates. The secret_token is
    # what Telegram echoes back in X-Telegram-Bot-Api-Secret-Token; we use it
    # to verify requests actually came from Telegram.
    #
    # IMPORTANT: never log str(e) or include it in the HTTP detail. For
    # httpx.HTTPStatusError, str(e) contains the full request URL — which
    # includes the bot token. We log only the status code and return a
    # generic 502 message.
    try:
        await telegram_client.set_webhook(req.bot_token, webhook_url, WEBHOOK_SECRET)
    except httpx.HTTPStatusError as e:
        logger.error("set_webhook failed: HTTP %s", e.response.status_code)
        raise HTTPException(status_code=502, detail="Telegram setWebhook failed")
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
        logger.error("set_webhook failed: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="Telegram setWebhook failed")

    # getMe — fetch the bot's username so we can build the deep link.
    try:
        me = await telegram_client.get_me(req.bot_token)
        bot_username = (me.get("result") or {}).get("username") or "bot"
    except httpx.HTTPStatusError as e:
        logger.error("getMe failed: HTTP %s", e.response.status_code)
        raise HTTPException(status_code=502, detail="Telegram getMe failed")
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
        logger.error("getMe failed: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="Telegram getMe failed")

    # Generate a one-shot setup token. The user clicks the deep link, sends
    # /start <token> to the bot, and we know which chat_id maps to which user.
    setup_token = secrets.token_urlsafe(16)

    simple_storage.save_pending_setup(
        setup_token,
        {
            "omi_uid": req.omi_uid,
            "persona_id": req.persona_id,
            "omi_dev_api_key": req.omi_dev_api_key,
            "bot_token": req.bot_token,
            "bot_username": bot_username,
        },
    )

    deep_link = f"https://t.me/{bot_username}?start={setup_token}"
    logger.info("setup complete for user %s (bot=%s, token=%s...)", req.omi_uid, bot_username, setup_token[:8])

    return SetupResponse(deep_link=deep_link, bot_username=bot_username, setup_token=setup_token)


# ---------------------------------------------------------------------------
# /webhook
# ---------------------------------------------------------------------------
async def _send_auto_reply_disabled_notice(bot_token: str, chat_id: int | str) -> None:
    """Tell the user the auto-reply toggle is off. Cheap reassurance; not spammy."""
    await telegram_client.send_message(
        bot_token,
        chat_id,
        "Auto-reply is currently disabled for this chat. Open the Omi desktop "
        "and turn on AI Clone → Telegram to enable replies.",
    )


def _extract_text_and_chat(update: dict) -> tuple[Optional[int | str], Optional[str]]:
    """Pull chat_id and text from a Telegram update payload. Returns (None, None) if absent."""
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return None, None
    chat = msg.get("chat") or {}
    return chat.get("id"), msg.get("text")


def _is_setup_start(text: str) -> tuple[bool, Optional[str]]:
    """If text is `/start <token>`, return (True, token). Else (False, None)."""
    if not text or not text.startswith("/start"):
        return False, None
    parts = text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1]:
        return False, None
    return True, parts[1].strip()


@app.post("/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
):
    """Receive a Telegram update. Always returns 200 on success, 401 on bad secret.

    Paths:
    - `/start <setup_token>` from a chat that completed /setup: register chat_id.
    - Regular text from a known private chat with auto_reply enabled: dispatch
      to the persona, send the reply.
    - Regular text from a known private chat with auto_reply disabled: nudge
      (rate-limited by last_nudge_at).
    - Anything else (unknown chat, group/channel, bot sender, no text,
      malformed JSON): silently return 200.

    Telegram retries indefinitely on non-2xx, so we never raise from here
    unless the secret is wrong (then 401).
    """
    # Auth: Telegram echoes the secret_token we set at setWebhook time.
    # Use secrets.compare_digest for constant-time comparison.
    presented = x_telegram_bot_api_secret_token or ""
    if not secrets.compare_digest(presented, WEBHOOK_SECRET):
        raise HTTPException(status_code=401, detail="Invalid or missing Telegram webhook secret")

    # Telegram's webhook sends JSON; if the body is malformed, log and 200 (don't retry).
    try:
        update = await request.json()
    except json.JSONDecodeError:
        logger.warning("webhook received malformed JSON, ignoring")
        return {"ok": True}
    if not isinstance(update, dict):
        logger.warning("webhook received non-dict JSON, ignoring")
        return {"ok": True}

    chat_id, text = _extract_text_and_chat(update)
    if chat_id is None:
        return {"ok": True}

    # Path 1: /start handshake — bind chat_id to the user who clicked the deep link.
    is_start, setup_token = _is_setup_start(text or "")
    if is_start:
        payload = simple_storage.pop_pending_setup(setup_token)
        if payload is None:
            # Stale or forged token. Reply so the user knows setup didn't work,
            # but don't leak that the token is invalid vs. unknown.
            await telegram_client.send_message(
                _bot_token_for_unknown_chat(chat_id),
                chat_id,
                "This setup link is invalid or already used. Please re-run the " "setup from the Omi desktop.",
            )
            return {"ok": True}

        simple_storage.save_user(
            chat_id=str(chat_id),
            omi_uid=payload["omi_uid"],
            persona_id=payload["persona_id"],
            omi_dev_api_key=payload["omi_dev_api_key"],
            bot_token=payload["bot_token"],
            auto_reply_enabled=False,
        )
        await telegram_client.send_message(
            payload["bot_token"],
            chat_id,
            "Connected! Open the Omi desktop and toggle AI Clone → Telegram " "to start receiving auto-replies.",
        )
        logger.info("setup handshake complete: chat_id=%s user=%s", chat_id, payload["omi_uid"])
        return {"ok": True}

    # Path 2: regular message. Look up the user; if known and auto_reply is off,
    # nudge. Otherwise (unknown chat, group, or auto_reply on) we fall through
    # to T-004.
    # Safety filters for the auto-reply path: skip groups/channels (out of scope
    # for v1), skip bot senders (own-message safety), skip non-text payloads.
    if _is_group_or_channel(update):
        return {"ok": True}
    if _is_bot_sender(update):
        return {"ok": True}
    if not text:
        return {"ok": True}

    user = simple_storage.get_user_by_chat_id(str(chat_id))
    if user is None:
        return {"ok": True}

    # Auto-reply disabled -> nudge (rate-limited) instead of spamming the user.
    if not user.get("auto_reply_enabled"):
        if simple_storage.should_nudge(user, _NUDGE_COOLDOWN_SECONDS):
            await _send_auto_reply_disabled_notice(user["bot_token"], chat_id)
            simple_storage.mark_nudged(str(chat_id))
        return {"ok": True}

    # Auto-reply on -> call the persona, send the reply.
    await _dispatch_auto_reply(user, str(chat_id), text)
    return {"ok": True}


async def _dispatch_auto_reply(user: dict, chat_id: str, text: str) -> None:
    """Call the persona API and send the reply back to Telegram.

    Empty replies (timeout/connect error) and HTTP errors are logged but do not
    raise — the webhook must always return 200 to Telegram. The except clause
    is narrowed to httpx + asyncio errors so genuine bugs in our code surface
    via FastAPI's error middleware rather than being silently swallowed.
    """
    try:
        reply = await _persona_chat(
            app_id=user["persona_id"],
            api_key=user["omi_dev_api_key"],
            omi_base=OMI_BASE_URL,
            text=text,
            uid=user["omi_uid"],
        )
    except httpx.HTTPStatusError as e:
        # httpx.HTTPStatusError.__str__ includes the request URL (which contains
        # the API key in the query string). Log only the status code to keep
        # the key out of logs.
        logger.error("persona chat HTTP error for chat %s: HTTP %s", chat_id, e.response.status_code)
        return
    except httpx.HTTPError as e:
        # Other HTTP errors (connect, timeout). Log exception type name only.
        logger.error("persona chat HTTP error for chat %s: %s", chat_id, type(e).__name__)
        return
    except asyncio.TimeoutError as e:
        logger.error("persona chat timeout for chat %s: %s", chat_id, type(e).__name__)
        return

    if not reply:
        logger.info("persona chat returned empty reply for chat %s (skipping send)", chat_id)
        return

    await telegram_client.send_message(user["bot_token"], chat_id, reply)
    logger.info("auto-reply sent to chat %s (%d chars)", chat_id, len(reply))


def _is_group_or_channel(update: dict) -> bool:
    chat = (update.get("message") or update.get("edited_message") or {}).get("chat") or {}
    return chat.get("type") in {"group", "supergroup", "channel"}


def _is_bot_sender(update: dict) -> bool:
    sender = (update.get("message") or update.get("edited_message") or {}).get("from") or {}
    return bool(sender.get("is_bot"))


# ---------------------------------------------------------------------------
# /toggle — flips auto_reply_enabled for a chat (called by Chat Tools).
#
# Auth: the request must include the bot_token that was registered for that
# chat_id. The bot_token is a real secret (only the user has it; calling
# setWebhook with the wrong token fails at Telegram). chat_id alone is NOT
# sufficient — it's exposed in Telegram update payloads and could be guessed
# by anyone scraping a public channel. Pairing the two raises the bar from
# "knows chat_id" to "knows chat_id AND bot_token".
# ---------------------------------------------------------------------------
class ToggleRequest(BaseModel):
    chat_id: str
    enabled: bool
    bot_token: str  # required: must match the stored token for chat_id


class ToggleResponse(BaseModel):
    chat_id: str
    auto_reply_enabled: bool


@app.post("/toggle", response_model=ToggleResponse, dependencies=[Depends(require_bearer)])
async def toggle(req: ToggleRequest):
    """Enable or disable auto-reply for the given chat_id.

    Returns 403 with a generic message for both unknown chat_id AND wrong
    bot_token, so callers can't enumerate which chat_ids are registered by
    distinguishing 404 (unknown) from 403 (wrong token).

    Called by the Chat Tools manifest entry `toggle_auto_reply` (T-008).
    """
    user = simple_storage.get_user_by_chat_id(req.chat_id)
    # Same response for both 'unknown chat_id' and 'wrong bot_token' so the
    # endpoint doesn't leak which chat_ids exist (chat_ids are exposed in
    # Telegram update payloads and could be enumerated otherwise).
    if user is None or not secrets.compare_digest(req.bot_token, user["bot_token"]):
        raise HTTPException(status_code=403, detail="Invalid chat_id or bot_token")
    simple_storage.update_auto_reply(req.chat_id, req.enabled)
    return ToggleResponse(chat_id=req.chat_id, auto_reply_enabled=req.enabled)


def _bot_token_for_unknown_chat(chat_id: int | str) -> str:
    """Look up the bot token for any user whose chat_id matches; empty if none.

    Used only to send the "invalid setup token" notice to a chat we otherwise
    don't recognize. If we have no record we can't reply (no token), so the
    function returns "" — telegram_client.send_message will then silently fail.
    """
    user = simple_storage.get_user_by_chat_id(str(chat_id))
    return user["bot_token"] if user else ""
