"""Telegram user-account AI-Clone plugin — FastAPI service.

Routes (all bearer-gated except /health):
- GET  /health                                         — liveness
- GET  /status                                         — Telethon connection state
- GET  /recent_messages                                — recent chats
- GET  /recent_messages/{chat_id}/messages?limit=20    — per-chat history
- POST /persona_chat                                   — call persona + send reply
- POST /chat_memory                                    — append a turn

SECURITY (plan §7):
- Session string is read ONCE from stdin at startup. Never
  written to disk, never logged, never in any HTTP response.
- Discovery file (written by the lifespan) carries account
  metadata only — phone, name, device_label. NOT the session.
- All auth errors are sanitized before being returned in HTTP
  responses (cubic review 4614064929 P2: extractSanitizedDetail
  redaction).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Add plugins/_shared/ to sys.path so we can import auth + persona_client.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SHARED = os.path.abspath(os.path.join(_HERE, "..", "_shared"))
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import simple_storage  # noqa: E402
import telethon_client as _telethon_client  # noqa: E402  (read_session_from_stdin, TelethonClient)
from auth import require_bearer  # noqa: E402
from persona_client import chat as _persona_chat  # noqa: E402
import flood_control  # noqa: E402  (plan §8: rate limit + FLOOD_WAIT detection)

# Re-export the redactor so log records emitted during /persona_chat
# are also scrubbed (defense in depth on top of the per-emit
# `safe_log_message` in redact.py).
import redact  # noqa: E402

logger = logging.getLogger("omi-telegram-user-account")
# Ensure the logger emits at INFO even when uvicorn doesn't propagate it.
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

# Bearer auth (same config as the WhatsApp / Telegram bot plugins):
# AI_CLONE_PLUGIN_TOKEN env var is checked; OMI_DEV_MODE=1 bypasses
# (for local dev / tests).
OMI_DEV_MODE = os.getenv("OMI_DEV_MODE") == "1"

# Backend the persona API lives on (configurable so local dev can
# point at a localhost backend). The persona route is at
# /v2/integrations/{app_id}/user/persona-chat.
OMI_BASE_URL = os.getenv("OMI_BASE_URL", "https://api.omi.me")

# Telethon public app credentials. NOT secrets — these are visible
# to anyone with a my.telegram.org account. They identify the
# third-party app ("Omi Desktop") to Telegram, not the user.
TELEGRAM_API_ID = int(os.getenv("TELEGRAM_API_ID", "0"))
TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")

# Connection supervision: if the Telethon client disconnects, try to
# reconnect with exponential backoff. Pin the backoff base to keep
# test runs deterministic.
_RECONNECT_BACKOFF_BASE_SECONDS = 1.0
_RECONNECT_BACKOFF_MAX_SECONDS = 60.0

# Module-level state — the singleton Telethon client and the
# account metadata. The autouse isolation fixture in conftest.py
# clears simple_storage's three dicts at the start of every test
# but does NOT clear _client (which is a process-level singleton,
# not simple_storage's data). Tests that exercise the FastAPI app
# inject a mock client via the dependency-injection helpers below.
_client: Optional[_telethon_client.TelethonClient] = None
_account_meta: dict = {}


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _plugin_lifespan(app: FastAPI):
    """Startup: read the session from stdin, build the Telethon
    client, connect, populate simple_storage.account. Shutdown:
    disconnect cleanly.

    SECURITY: the session string is read once at startup, passed
    to Telethon's StringSession, then dropped from the local
    function frame. The `telethon_client._client` module-level
    reference holds the StringSession object, but NOT the raw
    string. The raw string lives only in this function's frame
    for the duration of the startup call, then is GC'd.
    """
    global _client, _account_meta

    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        logger.error(
            "TELEGRAM_API_ID and TELEGRAM_API_HASH must be set " "(my.telegram.org/app credentials, NOT secrets)."
        )
        # Don't fail startup — let /health report the error so the
        # operator sees it in the desktop UI.
    else:
        try:
            session_str = _telethon_client.read_session_from_stdin()
            _client = _telethon_client.TelethonClient(
                session_string=session_str,
                api_id=TELEGRAM_API_ID,
                api_hash=TELEGRAM_API_HASH,
            )
            try:
                _account_meta = await _client.connect()
                simple_storage.save_account_metadata(
                    phone=_account_meta.get("phone") or "",
                    name=_account_meta.get("name") or "",
                    device_label=_account_meta.get("device_label") or "",
                )
                logger.info(
                    "Connected to Telegram as %s",
                    _account_meta.get("name") or "(unknown)",
                )

                # Register the incoming-message handler so DMs
                # are auto-replied. This is the core "reply as me"
                # functionality — without this, the plugin only
                # replies when /persona_chat is called manually.
                _client.register_incoming_message_handler(_on_incoming_message)
                logger.info("auto-reply listener registered")
            except Exception as e:
                logger.error(
                    "Telethon connect failed: %s",
                    type(e).__name__,
                )
                # Leave _client set; is_connected() returns False.
        except Exception as e:
            logger.error(
                "Failed to read session from stdin: %s",
                type(e).__name__,
            )

    try:
        yield
    finally:
        if _client is not None:
            try:
                await _client.disconnect()
            except Exception as e:
                logger.warning("shutdown disconnect raised: %s", type(e).__name__)


# ---------------------------------------------------------------------------
# Incoming-message auto-reply handler
# ---------------------------------------------------------------------------


async def _on_incoming_message(event):
    """Auto-reply handler for incoming DMs.

    Registered as a Telethon ``NewMessage(incoming=True)`` handler
    in ``_plugin_lifespan``. When a contact DMs the user's
    personal account, this:

    1. Skips non-private (group/channel) messages.
    2. Skips messages without text (stickers, media-only).
    3. Records the incoming message in the ring buffer.
    4. Checks auto_reply_enabled + rate limit.
    5. Calls the persona API to generate a reply.
    6. Sends the reply via Telethon.
    7. Records the reply in the ring buffer.

    All exceptions are caught and logged — a handler exception
    must NOT crash the Telethon event loop (which would kill all
    future message processing).
    """
    try:
        # Only reply to private (1:1) chats, not groups/channels.
        if not event.is_private:
            return

        # Skip messages without text (stickers, photos, voice, etc.)
        msg_text = (event.message.text or "") if event.message else ""
        if not msg_text.strip():
            return

        chat_id = str(event.chat_id)

        # Resolve sender info for the persona context.
        sender_name = ""
        sender_username = ""
        try:
            sender = await event.get_sender()
            if sender is not None:
                first = getattr(sender, "first_name", None) or ""
                last = getattr(sender, "last_name", None) or ""
                sender_name = " ".join(filter(None, [first, last])).strip()
                sender_username = getattr(sender, "username", None) or ""
        except Exception:
            pass  # Non-fatal — we can still reply without the sender name

        logger.info(
            "incoming DM from chat_id=%s sender=%s (@%s): %s",
            chat_id,
            sender_name,
            sender_username,
            msg_text[:100],
        )

        # Record the incoming message in the ring buffer.
        simple_storage.append_message(chat_id, "human", msg_text)

        # Find the user record. For the user-account plugin, there's
        # typically one owner. If no user has auto_reply enabled, skip.
        user = None
        for u in simple_storage.users.values():
            if u.get("auto_reply_enabled", False):
                user = u
                break

        if user is None:
            logger.info("no user with auto_reply enabled; skipping")
            return

        # Rate-limit check (plan §8).
        if not flood_control.default_rate_limit.can_send():
            retry_after = flood_control.default_rate_limit.seconds_until_next_slot()
            logger.warning(
                "rate limit hit: %d sends in last hour, blocking for %ds (chat=%s)",
                flood_control.default_rate_limit.in_window_count(),
                retry_after,
                chat_id,
            )
            return

        # Build context from recent messages for the persona API.
        recent = simple_storage.get_recent_messages(chat_id)
        previous_messages = [{"role": m["role"], "text": m["text"]} for m in recent[-20:]]

        # If the ring buffer is thin, fetch real Telegram history
        # for language-aware context (same logic as /persona_chat).
        if len(previous_messages) < 5 and _client is not None:
            try:
                tg_msgs = await _client.get_chat_history(chat_id, limit=20)
                tg_history = [{"role": m["role"], "text": m["text"]} for m in tg_msgs if m.get("text", "").strip()]
                if tg_history:
                    previous_messages = tg_history[-20:]
            except Exception as e:
                logger.warning("could not fetch Telegram history: %s", type(e).__name__)

        # Call the persona API.
        reply = await _persona_chat(
            app_id=user["persona_id"],
            api_key=user["omi_dev_api_key"],
            omi_base=OMI_BASE_URL,
            text=msg_text,
            uid=user["omi_uid"],
            timeout_seconds=30.0,
            previous_messages=previous_messages,
        )

        if not reply:
            logger.warning("persona API returned empty reply for chat=%s", chat_id)
            return

        # Send the reply via Telethon.
        try:
            await _client.send_message(chat_id, reply)
        except Exception as e:
            flood_seconds = flood_control.detect_flood_wait(e)
            if flood_seconds is not None:
                flood_control.default_rate_limit.block_for_seconds(flood_seconds)
                logger.warning(
                    "FLOOD_WAIT from Telegram for chat=%s: wait %ds",
                    chat_id,
                    flood_seconds,
                )
            else:
                logger.error("send_message failed for chat=%s: %s", chat_id, type(e).__name__)
            return

        flood_control.default_rate_limit.record_send()
        simple_storage.append_message(chat_id, "ai", reply)
        logger.info(
            "auto-reply sent to chat=%s (%d chars)",
            chat_id,
            len(reply),
        )
    except Exception as e:
        # Catch-all: a handler exception must NOT crash the event
        # loop. Log and continue — the next message should still
        # be processed.
        logger.error(
            "auto-reply handler error: %s",
            type(e).__name__,
            exc_info=True,
        )


app = FastAPI(
    title="OMI Telegram User-Account AI-Clone",
    description="Self-hosted plugin that lets Omi reply on the user's " "personal Telegram account via Telethon.",
    version="0.1.0",
    lifespan=_plugin_lifespan,
)


# ---------------------------------------------------------------------------
# Dependency-injection helpers (overridable in tests)
# ---------------------------------------------------------------------------


def _get_client() -> _telethon_client.TelethonClient:
    """Dependency-injection helper. Tests override this to inject a
    mock Telethon client. Production reads the singleton.
    """
    if _client is None:
        raise HTTPException(
            status_code=503,
            detail="Telethon client not initialized (startup failed or session missing)",
        )
    return _client


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    """Liveness. No auth. Returns 200 even if Telethon isn't
    connected (that state shows up in /status)."""
    return {"status": "ok"}


@app.get("/status", dependencies=[Depends(require_bearer)])
async def status():
    """Telethon connection state + rate-limit + auto-reply state.
    Bearer-gated.

    Fields:
    - connected: bool          -- Telethon is_connected()
    - account_phone/name/device_label: str|None
    - auto_reply_enabled: bool -- aggregate across users
                                  (any user has auto-reply on
                                  == True). The user-account
                                  flow is single-account so
                                  "any" == the single user.
                                  The desktop's /status poll
                                  reads this to keep the
                                  toggle in sync.
    - rate_limit: {...}        -- plan §8: rolling 60-min
                                  window state + FLOOD_WAIT
                                  cooldown.
    - messages_sent_today: int -- in-memory exact counter,
                                  monotonic since local-time
                                  midnight (see
                                  flood_control.RateLimit).
    """
    rate = flood_control.default_rate_limit
    rl_state = {
        "max_per_hour": rate.max_per_hour,
        "in_window_count": rate.in_window_count(),
        "is_blocked": rate.is_blocked(),
        "seconds_until_next_slot": rate.seconds_until_next_slot(),
    }
    # Aggregate auto_reply_enabled across all users. The user-
    # account flow is single-account (one Telethon session per
    # desktop install), so "any user enabled" is the right
    # semantics for a global toggle. If the user collection is
    # empty (e.g. before first connect), we report False so the
    # desktop's UI starts in the "off" position.
    auto_reply_aggregate = any(u.get("auto_reply_enabled", False) for u in simple_storage.users.values())
    if _client is None:
        return {
            "connected": False,
            "account_phone": None,
            "account_name": None,
            "device_label": None,
            "auto_reply_enabled": auto_reply_aggregate,
            "rate_limit": rl_state,
            "messages_sent_today": rate.daily_count(),
        }
    connected = await _client.is_connected()
    return {
        "connected": connected,
        "account_phone": _account_meta.get("phone"),
        "account_name": _account_meta.get("name"),
        "device_label": _account_meta.get("device_label"),
        "auto_reply_enabled": auto_reply_aggregate,
        "rate_limit": rl_state,
        "messages_sent_today": rate.daily_count(),
    }


@app.get("/recent_messages", dependencies=[Depends(require_bearer)])
async def recent_messages(limit: int = Query(20, ge=1, le=100)):
    """List of recent chats. Bearer-gated."""
    client = _get_client()
    try:
        chats = await client.get_chats(limit=limit)
    except Exception as e:
        logger.error("get_chats failed: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="Telethon get_chats failed")
    return {"chats": chats}


@app.get(
    "/recent_messages/{chat_id}/messages",
    dependencies=[Depends(require_bearer)],
)
async def recent_messages_chat(
    chat_id: str,
    limit: int = Query(20, ge=1, le=100),
):
    """Per-chat history (oldest first). Bearer-gated."""
    client = _get_client()
    try:
        msgs = await client.get_chat_history(chat_id, limit=limit)
    except Exception as e:
        logger.error(
            "get_chat_history failed for chat_id=%s: %s",
            chat_id,
            type(e).__name__,
        )
        raise HTTPException(status_code=502, detail="Telethon get_chat_history failed")
    return {"chat_id": chat_id, "messages": msgs}


class ToggleRequest(BaseModel):
    """POST /toggle request body.

    The user-account flow keys storage by Telegram user
    handle (not chat id, as the bot plugin does). The
    desktop sends ``handle="all"`` for the global toggle.
    Per-handle toggles are reserved for future multi-account
    support and are not used by the current desktop UI.
    """

    handle: str = "all"
    enabled: bool


class ToggleResponse(BaseModel):
    """POST /toggle response body.

    auto_reply_enabled: the new aggregate state across users.
    affected_users: count of users whose record was updated
                    (handy for symmetry with the bot plugin's
                    per-chat_id response).
    """

    auto_reply_enabled: bool
    affected_users: int


@app.post(
    "/toggle",
    response_model=ToggleResponse,
    dependencies=[Depends(require_bearer)],
)
async def toggle_endpoint(req: ToggleRequest):
    """Enable or disable auto-reply for one user (or all users).

    Special case: ``handle="all"`` toggles every user in
    simple_storage. This is the desktop's normal call site.

    Returns 403 if the target handle is unknown OR if the
    "all" call has no users. The same 403 is returned for
    both unknown-handle and no-users so a probe cannot
    distinguish between "user exists with auto-reply off"
    and "user doesn't exist". The plugin bearer token
    already gates this endpoint; the per-handle check is
    defense-in-depth.
    """
    if req.handle == "all":
        affected = 0
        for telegram_user_id in list(simple_storage.users.keys()):
            simple_storage.update_auto_reply(telegram_user_id, req.enabled)
            affected += 1
        if affected == 0:
            raise HTTPException(status_code=403, detail="No users configured")
        return ToggleResponse(auto_reply_enabled=req.enabled, affected_users=affected)
    if req.handle not in simple_storage.users:
        raise HTTPException(status_code=403, detail="Unknown handle")
    simple_storage.update_auto_reply(req.handle, req.enabled)
    return ToggleResponse(auto_reply_enabled=req.enabled, affected_users=1)


class PersonaChatRequest(BaseModel):
    chat_id: str
    text: str
    sender_handle: Optional[str] = None  # currently unused; reserved


@app.post("/persona_chat", dependencies=[Depends(require_bearer)])
async def persona_chat_endpoint(body: PersonaChatRequest):
    """Call the persona API with the chat's recent messages, then
    send the reply via Telethon. Bearer-gated.

    SECURITY: this endpoint NEVER logs the session string. The
    request body is sent in the request; the response includes
    only the reply text and the sent message metadata — never the
    session string. The persona API call uses the per-user
    omi_dev_api_key (looked up from simple_storage), not the
    Telethon session.
    """
    client = _get_client()
    user = simple_storage.get_user_by_telegram_user_id(body.sender_handle or "")
    if user is None:
        # No user record for this Telegram handle. Without
        # omi_uid / persona_id / omi_dev_api_key we can't call the
        # persona API. Return 400 with a sanitized message.
        raise HTTPException(
            status_code=400,
            detail="No Omi account linked to this Telegram handle. "
            "Run 'Reply as me' setup in the Omi desktop first.",
        )

    # Gate on auto_reply_enabled. The desktop's "Reply as me"
    # section has a per-user toggle; if it's off, skip the
    # persona call entirely (saves LLM tokens). Default to
    # False so an old user record without the field behaves
    # safely on first deploy of this code -- the user must
    # explicitly opt in.
    if not user.get("auto_reply_enabled", False):
        logger.info(
            "auto_reply disabled for handle=%s; skipping persona call",
            body.sender_handle,
        )
        raise HTTPException(
            status_code=403,
            detail="Auto-reply is disabled. Enable it in the Omi desktop.",
        )

    recent = simple_storage.get_recent_messages(body.chat_id)
    # Map to the schema persona_client.chat expects.
    previous_messages = [{"role": m["role"], "text": m["text"]} for m in recent[-20:]]  # most recent 20

    # Language-aware context: if the ring buffer doesn't have enough
    # conversation history (e.g. first interaction with this contact),
    # fetch real messages from Telegram so the LLM can detect the
    # language and tone the user uses with this specific contact.
    # Without this, the LLM defaults to the persona's primary language
    # (e.g. Thai) even when the user has been chatting in English.
    #
    # TelethonClient.get_chat_history() already returns dicts with
    # {role: "human"|"ai", text: str, ts: str|None} in oldest-first
    # order, using m.outgoing to determine role. We consume those
    # fields directly.
    if len(previous_messages) < 5:
        try:
            tg_msgs = await client.get_chat_history(body.chat_id, limit=20)
            tg_history = [{"role": m["role"], "text": m["text"]} for m in tg_msgs if m.get("text", "").strip()]
            if tg_history:
                previous_messages = tg_history[-20:]
                logger.info(
                    "fetched %d messages from Telegram for language context (chat=%s)",
                    len(previous_messages),
                    body.chat_id,
                )
        except Exception as e:
            logger.warning("could not fetch Telegram history for context: %s", type(e).__name__)

    # plan §8: rate-limit cap BEFORE the persona call. Saves LLM
    # tokens when the cap is hit -- otherwise we'd call the
    # persona API only to discover we can't send. can_send is
    # non-mutating; record_send is called only on successful
    # outbound send.
    if not flood_control.default_rate_limit.can_send():
        retry_after = flood_control.default_rate_limit.seconds_until_next_slot()
        logger.warning(
            "rate limit hit: %d sends in last hour, blocking for %ds",
            flood_control.default_rate_limit.in_window_count(),
            retry_after,
        )
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit hit. Wait {retry_after}s before sending more.",
            headers={"Retry-After": str(retry_after)},
        )

    # Call the persona API. This is the same path the bot plugin
    # uses (shared persona_client.chat). We use the module-level
    # `_persona_chat` binding (imported at the top of this module)
    # rather than re-importing inside the function -- re-importing
    # inside the function would create a fresh binding that the
    # test's `patch.object(main_module, "_persona_chat", ...)`
    # wouldn't reach.
    reply = await _persona_chat(
        app_id=user["persona_id"],
        api_key=user["omi_dev_api_key"],
        omi_base=OMI_BASE_URL,
        text=body.text,
        uid=user["omi_uid"],
        timeout_seconds=30.0,
        previous_messages=previous_messages,
    )

    if not reply:
        raise HTTPException(status_code=502, detail="Persona API returned empty reply")

    # Send the reply via Telethon.
    try:
        sent = await client.send_message(body.chat_id, reply)
    except Exception as e:
        # plan §8: detect FLOOD_WAIT specifically. Telegram's
        # anti-flood systems return FLOOD_WAIT_* errors with a
        # `seconds` field; surfacing this in the log + response
        # lets the desktop show a clear "Telegram asked us to
        # wait" message instead of a generic 502.
        flood_seconds = flood_control.detect_flood_wait(e)
        if flood_seconds is not None:
            # cubic review 4617059500 P1: register the cooldown
            # with the local rate limiter so the next request
            # from this desktop is rejected at can_send() before
            # it reaches the persona API. Without this, the
            # caller could immediately retry, hit can_send()=True
            # (the rolling window is still empty), call the
            # persona API (wasting LLM tokens), and fail again
            # at the Telegram send_message stage. Now: the
            # local gate blocks retries for the duration
            # Telegram requested.
            flood_control.default_rate_limit.block_for_seconds(flood_seconds)
            logger.warning(
                "FLOOD_WAIT from Telegram for chat_id=%s: wait %ds. "
                "This is Telegram's anti-flood signal -- slow down. "
                "Local rate limiter blocked for %ds.",
                body.chat_id,
                flood_seconds,
                flood_seconds,
            )
            raise HTTPException(
                status_code=429,
                detail=f"Telegram FLOOD_WAIT: wait {flood_seconds}s before sending.",
                headers={"Retry-After": str(flood_seconds)},
            )
        logger.error(
            "send_message failed for chat_id=%s: %s",
            body.chat_id,
            type(e).__name__,
        )
        raise HTTPException(status_code=502, detail="Telethon send_message failed")

    # Only record_send on successful send. Failed sends do NOT
    # consume the budget (avoids rate-limiting on persistent
    # failures that need operator attention, not backoff).
    flood_control.default_rate_limit.record_send()

    # Persist the turn to the chat's ring buffer so the next call
    # has the AI's reply in its context.
    simple_storage.append_message(body.chat_id, "ai", reply)

    return {
        "chat_id": body.chat_id,
        "reply": reply,
        "sent": sent,
    }


class ChatMemoryRequest(BaseModel):
    chat_id: str
    role: str  # "human" | "ai"
    text: str


@app.post("/chat_memory", dependencies=[Depends(require_bearer)])
async def chat_memory(body: ChatMemoryRequest):
    """Append a turn to a chat's ring buffer. Bearer-gated.

    Used by the desktop's webhook-equivalent (the desktop polls
    /recent_messages and posts each new message via this endpoint)
    to keep the in-memory ring buffer in sync with Telegram.
    """
    if body.role not in ("human", "ai"):
        raise HTTPException(
            status_code=400,
            detail=f"role must be 'human' or 'ai', got {body.role!r}",
        )
    if not body.text:
        raise HTTPException(status_code=400, detail="text must be non-empty")
    simple_storage.append_message(body.chat_id, body.role, body.text)
    return {"ok": True}


# Auto-load simple_storage at module import (matches the convention
# used by the WhatsApp / Telegram bot plugins).
simple_storage.load_storage()
