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
from plugin_discovery import (
    write_discovery,
    clear_discovery,
)  # noqa: E402  (write ~/.config/omi/ai-clone-plugin.json on startup)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("omi-telegram-clone")


# ---------------------------------------------------------------------------
# Webhook secret
# ---------------------------------------------------------------------------
# WEBHOOK_SECRET is the value Telegram sends back in X-Telegram-Bot-Api-Secret-Token
# on every webhook delivery. Set via env in production (so it survives restarts);
# fall back to a fresh random value at startup so dev installs work out of the box.
WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET") or secrets.token_urlsafe(32)
if os.getenv("TELEGRAM_WEBHOOK_SECRET"):
    logger.info("Webhook secret: configured via env")
else:
    logger.warning("Webhook secret: auto-generated (set TELEGRAM_WEBHOOK_SECRET to persist across restarts)")

# Base URL of the Omi backend that the persona API lives on. Defaults to prod.
OMI_BASE_URL = os.getenv("OMI_BASE_URL", "https://api.omi.me")

# How often we re-nudge a user who has auto-reply disabled. Default 4 hours.
try:
    _NUDGE_COOLDOWN_SECONDS = float(os.getenv("NUDGE_COOLDOWN_SECONDS", "14400"))
except ValueError:
    logger.warning("NUDGE_COOLDOWN_SECONDS is not a float; defaulting to 14400")
    _NUDGE_COOLDOWN_SECONDS = 14400.0


import uuid
from contextlib import asynccontextmanager

_PLUGIN_INSTANCE_ID = str(uuid.uuid4())


@asynccontextmanager
async def _plugin_lifespan(app: FastAPI):
    """Write the discovery file at startup, remove it at shutdown.

    Plugin URL: prefer PUBLIC_BASE_URL if set (the tunnel URL), else
    fall back to http://127.0.0.1:<port> where <port> comes from $PORT
    (uvicorn sets it) or defaults to 8000 (Docker) / 18800 (dev).

    Bearer token: the env var AI_CLONE_PLUGIN_TOKEN. We write it to the
    discovery file as a bootstrap convenience; the desktop moves it
    into the macOS Keychain on first read so it doesn't linger in a
    plaintext file.

    Dev mode: True if OMI_DEV_MODE=1. The desktop uses this flag to
    relax the "developer API key required" check (useful when the
    plugin is paired with the local persona mock).
    """
    port = os.getenv("PORT") or "8000"
    public_url = os.getenv("PUBLIC_BASE_URL")
    if not public_url:
        public_url = f"http://127.0.0.1:{port}"
    try:
        write_discovery(
            plugin_url=f"http://127.0.0.1:{port}",
            bearer_token=os.getenv("AI_CLONE_PLUGIN_TOKEN", ""),
            public_url=public_url,
            dev_mode=os.getenv("OMI_DEV_MODE") == "1",
            plugin_type="telegram",
            instance_id=_PLUGIN_INSTANCE_ID,
            omi_base_url=OMI_BASE_URL,
        )
        logger.info("wrote plugin discovery file (instance=%s)", _PLUGIN_INSTANCE_ID)
    except OSError as e:
        logger.warning("could not write plugin discovery file: %s", e)
    try:
        yield
    finally:
        # P2 (cubic, PR #8682): close the shared httpx client pool on
        # shutdown. telegram_client exposes a module-level
        # httpx.AsyncClient for connection pooling across webhook
        # calls; without this hook the pool stayed open until process
        # exit, leaking TCP/TLS sockets on long-running workers.
        try:
            await telegram_client.aclose()
        except Exception as e:
            logger.warning("telegram_client.aclose() raised during shutdown: %s", e)
        try:
            clear_discovery(plugin_type="telegram", instance_id=_PLUGIN_INSTANCE_ID)
            logger.info("cleared plugin discovery file (instance=%s)", _PLUGIN_INSTANCE_ID)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# /.well-known/omi-tools.json — Omi Chat Tools manifest
# ---------------------------------------------------------------------------
# Per docs/doc/developer/apps/ChatTools.mdx, AI Clone plugins expose a
# static manifest at this well-known path so the Omi desktop/mobile app
# can discover the tools on install. Each plugin owns its own manifest
# (TOOLS_MANIFEST in main.py) because the JSON-Schema properties must
# exactly match the plugin's /toggle ToggleRequest field names — the chat
# assistant will faithfully build the request from this schema.
# Unauthenticated — manifest discovery is public; the underlying /toggle
# endpoint is auth-gated by the plugin bearer token (sent via the
# `Authorization: Bearer` header, enforced by the shared
# plugins/_shared/auth.require_bearer dependency). The request body
# carries only the chat_id (a NON-SECRET identifier the plugin uses
# to look up the user bound during the /start handshake); the bot
# token stays in the plugin's storage and is NEVER requested from
# or transmitted through chat — that keeps long-lived platform
# credentials out of chat history, tool-call logs, traces, and model
# context. (Identified by maintainer security review on PR #8531.)

app = FastAPI(
    title="OMI Telegram AI-Clone",
    description="Self-hosted Telegram plugin that lets Omi reply on the user's behalf.",
    version="0.1.0",
    lifespan=_plugin_lifespan,
)


@app.get("/.well-known/omi-tools.json", include_in_schema=False)
async def omi_tools_manifest():
    """Return the Omi Chat Tools manifest for this plugin.

    No auth: the manifest is public metadata. Each tool declared here
    is gated by the plugin bearer token (Authorization: Bearer header)
    at call time, NOT by request-body credentials — that's the entire
    reason `chat_messages.enabled` is False in v0.1: long-lived
    platform secrets must never transit through chat.
    """
    from fastapi.responses import JSONResponse

    return JSONResponse(content=get_omi_tools_manifest())


# ---------------------------------------------------------------------------
# /.well-known/omi-tools.json — Omi Chat Tools manifest
# ---------------------------------------------------------------------------
# Per docs/doc/developer/apps/ChatTools.mdx, AI Clone plugins expose a
# static manifest at this well-known path so the Omi desktop/mobile app
# can discover the tools on install. Each plugin owns its own manifest
# (TOOLS_MANIFEST in main.py) because the JSON-Schema properties must
# exactly match the plugin's /toggle ToggleRequest field names — the chat
# assistant will faithfully build the request from this schema.
# Unauthenticated — manifest discovery is public; the underlying /toggle
# endpoint is auth-gated by the plugin bearer token (sent via the
# `Authorization: Bearer` header, enforced by the shared
# plugins/_shared/auth.require_bearer dependency). The request body
# carries only the chat_id (a NON-SECRET identifier the plugin uses
# to look up the user bound during the /start handshake); the bot
# token stays in the plugin's storage and is NEVER requested from
# or transmitted through chat — that keeps long-lived platform
# credentials out of chat history, tool-call logs, traces, and model
# context. (Identified by maintainer security review on PR #8531.)
@app.get("/.well-known/omi-tools.json", include_in_schema=False)
async def omi_tools_manifest():
    """Return the Omi Chat Tools manifest for this plugin.

    No auth: the manifest is public metadata. Each tool declared here
    is gated by the plugin bearer token (Authorization: Bearer header)
    at call time, NOT by request-body credentials — that's the entire
    reason `chat_messages.enabled` is False in v0.1: long-lived
    platform secrets must never transit through chat.
    """
    from fastapi.responses import JSONResponse

    return JSONResponse(content=get_omi_tools_manifest())


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "service": "omi-telegram-clone", "version": "0.1.0"}


@app.get("/status", dependencies=[Depends(require_bearer)])
def status():
    """Return connected chat count + auto-reply state + first chat_id.

    Used by the desktop's PluginCard to show Connected/Not Connected,
    the current auto-reply toggle state, and the chat_id to use for
    /toggle calls. The bearer auth gates this.
    """
    chat_ids = list(simple_storage.users.keys())
    chat_count = len(chat_ids)
    any_auto_reply = any(u.get("auto_reply_enabled") for u in simple_storage.users.values())
    # Include bot_username from the first connected user's setup record
    first_user = simple_storage.users.get(chat_ids[0], {}) if chat_ids else {}
    bot_username = first_user.get("bot_username", "")
    return {
        "connected_chats": chat_count,
        "auto_reply_enabled": any_auto_reply,
        "first_chat_id": chat_ids[0] if chat_ids else None,
        "bot_username": bot_username,
        "service": "omi-telegram-clone",
    }


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

    # When the plugin uses a LOCAL backend (OMI_BASE_URL is localhost),
    # ALWAYS force the persona_id + API key from persona.json regardless
    # of what the desktop sends. The desktop may send stale prod values
    # (from a previous Connect) which won't work on the local backend.
    # The local backend only has the test persona + test API key.
    omi_base = os.getenv("OMI_BASE_URL", "https://api.omi.me")
    is_local_backend = "localhost" in omi_base or "127.0.0.1" in omi_base
    if is_local_backend:
        persona_file = "/tmp/omi-py-backend/persona.json"
        try:
            with open(persona_file) as f:
                pdata = json.load(f)
            effective_persona_id = pdata.get("app_id", req.persona_id)
            effective_dev_api_key = pdata.get("api_key", req.omi_dev_api_key)
            logger.info(
                "setup: local backend detected, forced persona from %s (id=%s, key=%s...)",
                persona_file,
                effective_persona_id,
                effective_dev_api_key[:8],
            )
        except (OSError, json.JSONDecodeError):
            effective_persona_id = req.persona_id
            effective_dev_api_key = req.omi_dev_api_key
            logger.warning("setup: local backend but persona.json missing, using desktop-provided values")
    else:
        effective_persona_id = req.persona_id
        effective_dev_api_key = req.omi_dev_api_key

    simple_storage.save_pending_setup(
        setup_token,
        {
            "omi_uid": req.omi_uid,
            "persona_id": effective_persona_id,
            "omi_dev_api_key": effective_dev_api_key,
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
            bot_username=payload.get("bot_username", ""),
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
    await _dispatch_auto_reply(user, str(chat_id), text, sender=update.get("message", {}).get("from"))
    return {"ok": True}


async def _dispatch_auto_reply(user: dict, chat_id: str, text: str, sender: Optional[dict] = None) -> None:
    """Call the persona API and send the reply back to Telegram.

    T-020 wiring: passes the sender profile (name, username) as `context`
    so the persona knows who it's talking to, and the per-chat ring buffer
    of recent turns as `previous_messages` so the persona has continuity
    across webhook calls. Both are appended to after a successful reply.

    Empty replies (timeout/connect error) and HTTP errors are logged but do not
    raise — the webhook must always return 200 to Telegram. The except clause
    is narrowed to httpx + asyncio errors so genuine bugs in our code surface
    via FastAPI's error middleware rather than being silently swallowed.
    """
    # Build the context dict from the Telegram `from` object. Telegram sends
    # {id, is_bot, first_name, last_name?, username?, language_code?} for
    # private chats. We only forward the fields the persona renderer
    # recognizes (sender_name, sender_username); unknown fields are
    # silently dropped server-side. We deliberately don't forward `id`
    # (numeric Telegram user id) — that's a stable identifier but the
    # persona doesn't need it and it would be PII in logs / model context.
    ctx: Optional[dict] = None
    if isinstance(sender, dict):
        first = (sender.get("first_name") or "").strip()
        last = (sender.get("last_name") or "").strip()
        sender_name = " ".join(p for p in (first, last) if p) or None
        sender_username = (sender.get("username") or "").strip() or None
        if sender_name or sender_username:
            ctx = {
                "sender_name": sender_name,
                "sender_username": sender_username,
                "chat_type": "private",  # _is_group_or_channel already gated this
                "platform": "telegram",
            }

    # Load recent turns. Oldest first so the model sees the conversation
    # in chronological order.
    previous_messages = simple_storage.get_recent_messages(chat_id)

    try:
        reply = await _persona_chat(
            app_id=user["persona_id"],
            api_key=user["omi_dev_api_key"],
            omi_base=OMI_BASE_URL,
            text=text,
            uid=user["omi_uid"],
            context=ctx,
            previous_messages=previous_messages,
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
        # Don't append empty replies to history — they poison subsequent context.
        return

    await telegram_client.send_message(user["bot_token"], chat_id, reply)
    logger.info("auto-reply sent to chat %s (%d chars)", chat_id, len(reply))

    # T-020: record both sides of the exchange AFTER successful send so a
    # mid-flight failure doesn't poison subsequent context with a half-turn.
    # Use append_turn (atomic — single fsync) so a crash between the two
    # writes can't persist a human-without-ai or ai-without-human entry.
    simple_storage.append_turn(chat_id, human_text=text, ai_text=reply)


# ---------------------------------------------------------------------------
# Omi Chat Tools manifest — served at `GET /.well-known/omi-tools.json`.
# Schema per docs/doc/developer/apps/ChatTools.mdx. Each plugin has its own
# manifest because the parameter NAMES must match that plugin's /toggle
# ToggleRequest model.
#
# SECURITY: the manifest is public discovery metadata read by the chat
# assistant. It must NEVER advertise long-lived platform credentials as
# tool parameters — the chat assistant would faithfully prompt the user
# to paste them in chat, and those secrets would then live in chat
# history, tool-call logs, traces, screenshots, and model context.
#
# The plugin bearer token (in `Authorization: Bearer`) gates the call.
# The chat_id / phone is a NON-SECRET reference the plugin uses to look
# up which user the call applies to (the binding was made at /start
# handshake time). The platform credential is held by the plugin in
# its storage; the chat tool never sees it.
# ---------------------------------------------------------------------------
TOOLS_MANIFEST = {
    "tools": [
        {
            "name": "toggle_auto_reply",
            "description": (
                "Turn the AI Clone auto-reply on or off for a connected "
                "Telegram chat. Use this when the user wants to enable or "
                "disable Omi's automatic responses in a specific Telegram "
                "conversation."
            ),
            "endpoint": "/toggle",
            "method": "POST",
            "parameters": {
                "properties": {
                    "chat_id": {
                        "type": "string",
                        "description": (
                            "Telegram chat_id of the conversation. The "
                            "plugin uses this to look up the bound user "
                            "from the prior /start handshake — it is NOT "
                            "a secret and never identifies the user."
                        ),
                    },
                    "enabled": {
                        "type": "boolean",
                        "description": ("True to enable AI Clone auto-reply for the " "chat, false to disable it."),
                    },
                },
                "required": ["chat_id", "enabled"],
            },
            "auth_required": True,
            "status_message": "Toggling Telegram auto-reply...",
        }
    ],
    "chat_messages": {
        "enabled": False,
        "target": "app",
        "notify": False,
    },
}


def get_omi_tools_manifest() -> dict:
    """Return a fresh deep copy of the manifest so callers can't mutate
    the shared constant. v0.1 manifest is <1KB so copy cost is trivial."""
    import copy

    return copy.deepcopy(TOOLS_MANIFEST)


# ---------------------------------------------------------------------------
# Omi Chat Tools manifest — served at `GET /.well-known/omi-tools.json`.
# Schema per docs/doc/developer/apps/ChatTools.mdx. Each plugin has its own
# manifest because the parameter NAMES must match that plugin's /toggle
# ToggleRequest model.
#
# SECURITY: the manifest is public discovery metadata read by the chat
# assistant. It must NEVER advertise long-lived platform credentials as
# tool parameters — the chat assistant would faithfully prompt the user
# to paste them in chat, and those secrets would then live in chat
# history, tool-call logs, traces, screenshots, and model context.
#
# The plugin bearer token (in `Authorization: Bearer`) gates the call.
# The chat_id / phone is a NON-SECRET reference the plugin uses to look
# up which user the call applies to (the binding was made at /start
# handshake time). The platform credential is held by the plugin in
# its storage; the chat tool never sees it.
# ---------------------------------------------------------------------------
TOOLS_MANIFEST = {
    "tools": [
        {
            "name": "toggle_auto_reply",
            "description": (
                "Turn the AI Clone auto-reply on or off for a connected "
                "Telegram chat. Use this when the user wants to enable or "
                "disable Omi's automatic responses in a specific Telegram "
                "conversation."
            ),
            "endpoint": "/toggle",
            "method": "POST",
            "parameters": {
                "properties": {
                    "chat_id": {
                        "type": "string",
                        "description": (
                            "Telegram chat_id of the conversation. The "
                            "plugin uses this to look up the bound user "
                            "from the prior /start handshake — it is NOT "
                            "a secret and never identifies the user."
                        ),
                    },
                    "enabled": {
                        "type": "boolean",
                        "description": ("True to enable AI Clone auto-reply for the " "chat, false to disable it."),
                    },
                },
                "required": ["chat_id", "enabled"],
            },
            "auth_required": True,
            "status_message": "Toggling Telegram auto-reply...",
        }
    ],
    "chat_messages": {
        "enabled": False,
        "target": "app",
        "notify": False,
    },
}


def get_omi_tools_manifest() -> dict:
    """Return a fresh deep copy of the manifest so callers can't mutate
    the shared constant. v0.1 manifest is <1KB so copy cost is trivial."""
    import copy

    return copy.deepcopy(TOOLS_MANIFEST)


def _is_group_or_channel(update: dict) -> bool:
    chat = (update.get("message") or update.get("edited_message") or {}).get("chat") or {}
    return chat.get("type") in {"group", "supergroup", "channel"}


def _is_bot_sender(update: dict) -> bool:
    sender = (update.get("message") or update.get("edited_message") or {}).get("from") or {}
    return bool(sender.get("is_bot"))


# ---------------------------------------------------------------------------
# /toggle — flips auto_reply_enabled for a chat (called by Chat Tools).
#
# Auth model: the caller must hold a valid plugin bearer token (via the
# `Authorization: Bearer` header, enforced by the shared
# plugins/_shared/auth.require_bearer dependency). The chat_id parameter
# identifies which user/chat the call applies to — the plugin looks up
# the user bound to chat_id from its storage (set at /start handshake
# time). The platform bot_token is held by the plugin and is NEVER
# requested from or transmitted through chat — that keeps long-lived
# credentials out of chat history, tool-call logs, traces, and model
# context. (Identified by maintainer security review on PR #8528.)
# ---------------------------------------------------------------------------
class ToggleRequest(BaseModel):
    chat_id: str
    enabled: bool


class ToggleResponse(BaseModel):
    chat_id: str
    auto_reply_enabled: bool


@app.post("/toggle", response_model=ToggleResponse, dependencies=[Depends(require_bearer)])
async def toggle(req: ToggleRequest):
    """Enable or disable auto-reply for the given chat_id.

    Special case: chat_id='all' toggles ALL connected chats at once.
    This is used by the desktop's global auto-reply toggle when the
    user has multiple connected chats (or when the desktop doesn't
    know which specific chat_id to target).

    Called by the Chat Tools manifest entry `toggle_auto_reply`.
    """
    if req.chat_id == "all":
        # Toggle all connected chats
        if not simple_storage.users:
            raise HTTPException(status_code=403, detail="No connected chats")
        for cid in list(simple_storage.users.keys()):
            simple_storage.update_auto_reply(cid, req.enabled)
        # Return the first chat_id as representative
        first_cid = next(iter(simple_storage.users.keys()))
        return ToggleResponse(chat_id=first_cid, auto_reply_enabled=req.enabled)
    user = simple_storage.get_user_by_chat_id(req.chat_id)
    # Look up the user by chat_id alone — no platform credential is
    # required because (a) the plugin bearer token already gates this
    # endpoint and (b) the user-to-chat binding was established at
    # /start handshake time. See the maintainer security note above.
    user = simple_storage.get_user_by_chat_id(req.chat_id)
    if user is None:
        # Bearer auth already gates this endpoint; the bearer holder
        # can pass any chat_id they know. Returning 403 with a generic
        # message is fine — chat_ids aren't secret and an attacker
        # without the bearer can't even reach this code path.
        raise HTTPException(status_code=403, detail="Unknown chat_id")
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
