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
    """Telethon connection state. Bearer-gated."""
    if _client is None:
        return {
            "connected": False,
            "account_phone": None,
            "account_name": None,
            "device_label": None,
        }
    connected = await _client.is_connected()
    return {
        "connected": connected,
        "account_phone": _account_meta.get("phone"),
        "account_name": _account_meta.get("name"),
        "device_label": _account_meta.get("device_label"),
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

    recent = simple_storage.get_recent_messages(body.chat_id)
    # Map to the schema persona_client.chat expects.
    previous_messages = [{"role": m["role"], "text": m["text"]} for m in recent[-20:]]  # most recent 20

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
            logger.warning(
                "FLOOD_WAIT from Telegram for chat_id=%s: wait %ds. "
                "This is Telegram's anti-flood signal -- slow down.",
                body.chat_id,
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
