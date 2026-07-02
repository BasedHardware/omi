"""OMI WhatsApp AI-Clone plugin (v0.1).

Routes:
- GET  /health
- GET  /webhook   Meta webhook verification (hub.mode=subscribe).
- POST /webhook   Meta webhook delivery: /start handshake + auto-reply.
- POST /setup     Register the user's WhatsApp Business API creds, return deep link.
- POST /toggle    Flip auto_reply_enabled for a phone (called by Chat Tools).

Mechanical copy of plugins/omi-telegram-app/main.py with the Telegram Bot API
swapped for the Meta WhatsApp Business Cloud API (graph.facebook.com/v22.0).
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import sys
import urllib.parse
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import Optional, AsyncIterator

# Add plugins/_shared to sys.path so `from persona_client import chat` works.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SHARED = os.path.abspath(os.path.join(_HERE, "..", "_shared"))
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import httpx  # noqa: E402
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import simple_storage  # noqa: E402
from auth import require_bearer  # noqa: E402  (shared bearer-token auth — see plugins/_shared/auth.py)
import whatsapp_client  # noqa: E402
from persona_client import chat as _persona_chat  # noqa: E402
import secrets  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("omi-whatsapp-clone")

# Base URL of the Omi backend that the persona API lives on. Defaults to prod.
OMI_BASE_URL = os.getenv("OMI_BASE_URL", "https://api.omi.me")

# How often we re-nudge a user who has auto-reply disabled. Default 4 hours.
try:
    _NUDGE_COOLDOWN_SECONDS = float(os.getenv("NUDGE_COOLDOWN_SECONDS", "14400"))
except ValueError:
    logger.warning("NUDGE_COOLDOWN_SECONDS is not a float; defaulting to 14400")
    _NUDGE_COOLDOWN_SECONDS = 14400.0

# Webhook HMAC verification. WHATSAPP_APP_SECRET must be set unless the operator
# has explicitly opted into dev mode by setting OMI_DEV_MODE=1. Production
# misconfiguration would otherwise leave /webhook accepting unsigned POSTs
# (anyone with the public URL could forge messages and trigger persona
# dispatch + outbound sends).
_WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET")
_OMI_DEV_MODE = os.getenv("OMI_DEV_MODE") == "1"
if not _WHATSAPP_APP_SECRET and not _OMI_DEV_MODE:
    raise RuntimeError(
        "WHATSAPP_APP_SECRET must be set. Meta signs every webhook delivery with "
        "HMAC-SHA256(APP_SECRET, body); without it, anyone with the public URL "
        "can forge messages. To run without verification in dev only, set "
        "OMI_DEV_MODE=1."
    )
if not _WHATSAPP_APP_SECRET:
    logger.warning(
        "WHATSAPP_APP_SECRET unset and OMI_DEV_MODE=1 \u2014 webhook signature "
        "verification is DISABLED. Do not use this in production."
    )


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """P2 (cubic, PR #8682): close the shared httpx client pool on shutdown.

    whatsapp_client exposes a module-level httpx.AsyncClient for connection
    pooling across webhook calls. Without this lifespan hook, the pool
    stayed open until process exit — on long-running workers this leaks
    TCP/TLS sockets and can starve the file-descriptor table. Mirrors
    plugins/omi-telegram-app/main.py so both plugins share the same
    lifecycle contract.
    """
    yield
    import contextlib

    with contextlib.suppress(Exception):
        await whatsapp_client.aclose()


app = FastAPI(
    title="OMI WhatsApp AI-Clone",
    description="Self-hosted WhatsApp plugin that lets Omi reply on the user's behalf.",
    version="0.1.0",
    lifespan=_lifespan,
)


# ---------------------------------------------------------------------------
# /.well-known/omi-tools.json — Omi Chat Tools manifest
# ---------------------------------------------------------------------------
# Per docs/doc/developer/apps/ChatTools.mdx, AI Clone plugins expose a
# static manifest at this well-known path so the Omi desktop/mobile app
# can discover the tools on install. Each plugin owns its own manifest
# (TOOLS_MANIFEST in main.py) because the JSON-Schema properties must
# exactly match the plugin's /toggle ToggleRequest field names.
#
# Unauthenticated — manifest discovery is public; the underlying /toggle
# endpoint is auth-gated by the SHARED plugin bearer token
# (`Authorization: Bearer`, enforced by
# plugins/_shared/auth.require_bearer). The ManifestRequest body for
# `toggle_auto_reply` deliberately omits any access_token / bot_token
# field: long-lived platform credentials are held by the plugin and
# must NEVER be requested from or transmitted through chat. (Identified
# by maintainer security review on PR #8531.)
@app.get("/.well-known/omi-tools.json", include_in_schema=False)
async def omi_tools_manifest():
    """Return the Omi Chat Tools manifest for this plugin.

    No auth: the manifest is public metadata. Each tool declared here
    has its own `auth_required` flag and uses request-body credentials for
    actual authorization.
    """
    from fastapi.responses import JSONResponse

    return JSONResponse(content=get_omi_tools_manifest())


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "service": "omi-whatsapp-clone", "version": "0.1.0"}


# ---------------------------------------------------------------------------
# /status — connected-phone count + auto-reply state.
#
# Used by the Omi desktop's ConnectSheet to gate the handshake on a
# genuine user-side setup completion (a reachable /status with
# connected_phones >= 1 proves the user sent a message to the bot, the
# plugin bound a phone, and the persona will respond). /health alone
# proves only that the plugin process is running — see ConnectSheet
# for the corresponding gating change (P1 from cubic AI review on PR
# #8682). Mirrors plugins/omi-telegram-app/main.py /status.
# ---------------------------------------------------------------------------
@app.get("/status", dependencies=[Depends(require_bearer)])
def status():
    phones = list(simple_storage.users.keys())
    phone_count = len(phones)
    any_auto_reply = any(u.get("auto_reply_enabled") for u in simple_storage.users.values())
    first_user = simple_storage.users.get(phones[0], {}) if phones else {}
    return {
        "connected_phones": phone_count,
        "auto_reply_enabled": any_auto_reply,
        "first_phone": phones[0] if phones else None,
        "service": "omi-whatsapp-clone",
        "version": "0.1.0",
    }


# ---------------------------------------------------------------------------
# /webhook — GET (Meta verification) + POST (delivery)
# ---------------------------------------------------------------------------
@app.get("/webhook")
async def webhook_verify(
    hub_mode: Optional[str] = Query(default=None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(default=None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(default=None, alias="hub.challenge"),
):
    """Meta's webhook verification handshake.

    Meta sends `GET ?hub.mode=subscribe&hub.verify_token=<token>&hub.challenge=<random>`
    when the user first configures the webhook in the Meta Business dashboard.
    We must echo the challenge back as plain text if the verify_token matches
    one we registered (per user, via /setup). Otherwise 403.

    Meta retries verification indefinitely on non-2xx, so 403 is the right
    response to a wrong token (lets the user know their config is bad).
    """
    if hub_mode != "subscribe":
        # Not a verification request — could be a manual GET. Treat as 404.
        raise HTTPException(status_code=404, detail="Not Found")

    if not hub_verify_token or not hub_challenge:
        raise HTTPException(status_code=400, detail="Missing hub.verify_token or hub.challenge")

    # Look up which user registered this verify_token. There can be many users
    # (each with their own phone_number_id + access_token + verify_token). We
    # match the verify_token against pending_setups and registered users.
    # If a pending_setup matches, return the challenge (so the user can then
    # send the /start message to complete the binding).
    if simple_storage.pending_setups_match_verify_token(hub_verify_token):
        return Response(content=hub_challenge, media_type="text/plain")
    if simple_storage.user_with_verify_token_exists(hub_verify_token):
        return Response(content=hub_challenge, media_type="text/plain")

    raise HTTPException(status_code=403, detail="Invalid verify_token")


@app.post("/webhook")
async def webhook_delivery(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(default=None, alias="X-Hub-Signature-256"),
):
    """Receive a WhatsApp webhook delivery. Always returns 200 on success, 401 on bad signature.

    Paths:
    - `/start <setup_token>` from a phone that completed /setup: bind phone to user.
    - Regular text from a known phone with auto_reply enabled: dispatch to persona,
      send the reply.
    - Regular text from a known phone with auto_reply disabled: nudge (rate-limited).
    - Status updates (delivery receipts, etc.): silently 200.
    - Anything else: silently 200 (Meta retries indefinitely on non-2xx).
    """
    raw_body = await request.body()

    # Optional HMAC verification. If WHATSAPP_APP_SECRET is set, we verify the
    # signature. If unset (dev), we skip — production must set this.
    if _WHATSAPP_APP_SECRET:
        if not x_hub_signature_256:
            raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256")
        # Header format: "sha256=<hex>"
        if not x_hub_signature_256.startswith("sha256="):
            raise HTTPException(status_code=401, detail="Malformed X-Hub-Signature-256")
        presented_sig = x_hub_signature_256[len("sha256=") :]
        expected_sig = hmac.new(
            _WHATSAPP_APP_SECRET.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(presented_sig, expected_sig):
            # Do NOT log the full presented/expected sigs — they are
            # derived from WHATSAPP_APP_SECRET and should not appear in
            # logs (any reader of /tmp/omi-dev.log could correlate them
            # back to the secret). A generic mismatch + short correlation
            # id is enough for debugging. Maintainer-flagged on PR #8528.
            correlation_id = presented_sig[:8]
            logger.warning(
                "webhook signature mismatch (correlation_id=%s, len_presented=%d)",
                correlation_id,
                len(presented_sig),
            )
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Meta's webhook sends JSON; if the body is malformed, log and 200 (don't retry).
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        logger.warning("webhook received malformed JSON, ignoring")
        return {"ok": True}
    if not isinstance(payload, dict):
        logger.warning("webhook received non-dict JSON, ignoring")
        return {"ok": True}

    # Meta batches webhook events: a single POST can contain multiple entries,
    # each with multiple changes, each with multiple messages and/or statuses.
    # We MUST process ALL messages, even when the same payload also contains
    # statuses (delivery/read receipts) — dropping the whole payload on any
    # status would silently lose real user messages under load.
    inbound_messages = list(_iter_inbound_messages(payload))

    if not inbound_messages:
        # No new user messages (purely status updates, malformed, etc.). 200 OK.
        return {"ok": True}

    # Process each inbound message independently. /start handshake binds
    # the phone; subsequent messages dispatch to the persona.
    #
    # Skip messages whose wamid we have already seen — Meta retries carry the
    # same id and we don't want to fire the persona twice for one user
    # message. See _already_processed for the bounded FIFO set.
    contacts = payload.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("contacts") or []
    for msg in inbound_messages:
        wamid = msg.get("id")
        if wamid and _already_processed(wamid):
            logger.info("skipping duplicate wamid=%s", wamid)
            continue
        # T-020: pass the contact profile (display name) so the persona
        # knows who it's talking to. We do a per-message lookup by wa_id
        # since multiple contacts can share one webhook POST.
        await _handle_inbound_message(msg, contacts=contacts)

    return {"ok": True}


async def _handle_inbound_message(msg: dict, contacts: Optional[list] = None) -> None:
    """Handle a single inbound Meta WhatsApp message (text only in v0.1).

    T-020: `contacts` is the entry's contacts[] array (one element per
    sender). We use it to look up the sender's display name for the
    persona's context. Contacts are optional — Meta sometimes omits
    them (e.g. for messages from unsaved numbers), in which case we
    just send the phone number as the sender_name.
    """
    from_phone = msg.get("from")
    text = _extract_text(msg)
    if not from_phone:
        return

    # /start handshake — bind phone to user.
    is_start, setup_token = _is_setup_start(text or "")
    if is_start:
        payload_data = simple_storage.pop_pending_setup(setup_token)
        if payload_data is None:
            # Stale or forged token. Reply if we have a record of this phone
            # so the user knows setup didn't work; otherwise we have no token
            # to reply with.
            user = simple_storage.get_user_by_phone(str(from_phone))
            if user:
                await whatsapp_client.send_message(
                    user["phone_number_id"],
                    user["access_token"],
                    str(from_phone),
                    "This setup link is invalid or already used. Please re-run setup from the Omi desktop.",
                )
            return

        simple_storage.save_user(
            phone=str(from_phone),
            omi_uid=payload_data["omi_uid"],
            persona_id=payload_data["persona_id"],
            omi_dev_api_key=payload_data["omi_dev_api_key"],
            access_token=payload_data["access_token"],
            phone_number_id=payload_data["phone_number_id"],
            verify_token=payload_data["verify_token"],
            auto_reply_enabled=False,
        )
        # Send confirmation via the user-supplied creds.
        await whatsapp_client.send_message(
            payload_data["phone_number_id"],
            payload_data["access_token"],
            str(from_phone),
            "Connected! Open the Omi desktop and toggle AI Clone \u2192 WhatsApp to start receiving auto-replies.",
        )
        logger.info("setup handshake complete: phone=%s user=%s", from_phone, payload_data["omi_uid"])
        return

    # Regular text from a known phone: dispatch or nudge.
    user = simple_storage.get_user_by_phone(str(from_phone))
    if user is None:
        return

    if not text:
        # Non-text messages (images, voice, etc.) are not handled in v0.1.
        return

    if not user.get("auto_reply_enabled"):
        if simple_storage.should_nudge(user, _NUDGE_COOLDOWN_SECONDS):
            await _send_auto_reply_disabled_notice(user, str(from_phone))
            simple_storage.mark_nudged(str(from_phone))
        return

    # T-020: look up the sender's profile name (if Meta included it) so the
    # persona knows who they're talking to. We only forward name/wa_id; the
    # raw contacts[] object stays in the plugin.
    sender_name = None
    if isinstance(contacts, list):
        for contact in contacts:
            if not isinstance(contact, dict):
                continue
            if contact.get("wa_id") == str(from_phone):
                profile = contact.get("profile") or {}
                if isinstance(profile.get("name"), str) and profile["name"].strip():
                    sender_name = profile["name"].strip()
                break
    # Doc-vs-code mismatch (P2 from cubic AI review): when Meta omits
    # `contacts` (common for unsaved numbers) or the contact lacks a
    # profile name, we promised the persona "at least the phone number"
    # so it knows who it's talking to. Fall back to the wa_id rather
    # than sending the inbound message with no sender identity at all.
    if not sender_name:
        sender_name = str(from_phone)

    await _dispatch_auto_reply(user, str(from_phone), text, sender_name=sender_name)


# ---------------------------------------------------------------------------
# Inbound-message deduplication.
#
# Meta's webhook delivery is at-least-once: a webhook that returns non-2xx (or
# times out before Meta sees the response) is retried, potentially forever.
# The retry carries the same `wamid` — Meta's unique message id. Without
# dedup, a flaky network or a webhook handler that crashed after we
# dispatched to the persona would trigger a duplicate persona call and a
# duplicate outbound reply on every retry. Identified by cubic (P2).
#
# We keep a bounded in-memory OrderedDict of recently-seen wamids. FIFO
# eviction at MAX_SEEN_WAMIDS bounds memory at ~10k entries, well under 1
# MB and large enough to cover any plausible retry burst. On plugin restart
# the set is empty — a restart is rare enough that re-firing one or two
# persona calls is acceptable, and persisting dedup state to disk would
# risk replaying messages that were already replied to in a previous
# process lifetime.
# ---------------------------------------------------------------------------
MAX_SEEN_WAMIDS = 10_000
_seen_wamids: "OrderedDict[str, None]" = OrderedDict()


def _already_processed(wamid: str) -> bool:
    """True if `wamid` was processed recently. Marks it as seen on first call."""
    if wamid in _seen_wamids:
        # Touch to keep most-recent order.
        _seen_wamids.move_to_end(wamid)
        return True
    _seen_wamids[wamid] = None
    while len(_seen_wamids) > MAX_SEEN_WAMIDS:
        _seen_wamids.popitem(last=False)
    return False


def _iter_inbound_messages(payload: dict):
    """Yield every inbound text message from a Meta webhook payload.

    Walks entry[] -> changes[] -> value.messages[] (skipping status updates
    and non-text payloads). Handles mixed/batched payloads correctly: a single
    POST with 5 messages + 3 statuses yields all 5 messages, not zero.
    """
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            messages = value.get("messages")
            if not (messages and isinstance(messages, list)):
                continue
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                # v0.1 only handles text messages. Image/voice/etc are
                # silently skipped (we still 200 so Meta doesn't retry).
                if msg.get("type") != "text":
                    continue
                yield msg


def _normalize_e164(raw: Optional[str]) -> Optional[str]:
    """Normalize a phone number to E.164 digits-only form (no '+', no formatting).

    Meta returns display_phone_number with formatting like "+1 555-000-1111" or
    "(555) 000-1111". wa.me links require E.164 digits only (no '+', no
    whitespace, no dashes, no parens). We strip all non-digit characters.

    Returns None if the result is empty or contains non-digit junk.
    """
    if not raw or not isinstance(raw, str):
        return None
    digits = "".join(c for c in raw if c.isdigit())
    # Heuristic: require 7+ digits. Anything shorter is malformed.
    if len(digits) < 7:
        return None
    return digits


def _extract_text(msg: dict) -> Optional[str]:
    """Pull the text body from a message dict. None for non-text messages."""
    text = msg.get("text")
    if isinstance(text, dict):
        return text.get("body")
    return None


def _is_setup_start(text: str) -> tuple[bool, Optional[str]]:
    """If text is `/start <token>`, return (True, token). Else (False, None)."""
    if not text or not text.startswith("/start"):
        return False, None
    parts = text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1]:
        return False, None
    return True, parts[1].strip()


async def _send_auto_reply_disabled_notice(user: dict, phone: str) -> None:
    """Tell the user the auto-reply toggle is off. Cheap reassurance; not spammy."""
    await whatsapp_client.send_message(
        user["phone_number_id"],
        user["access_token"],
        phone,
        "Auto-reply is currently disabled for this chat. Open the Omi desktop "
        "and turn on AI Clone \u2192 WhatsApp to enable replies.",
    )


async def _dispatch_auto_reply(user: dict, phone: str, text: str, sender_name: Optional[str] = None) -> None:
    """Call the persona API and send the reply back to WhatsApp.

    T-020 wiring: passes the sender's display name (from Meta's contacts[]
    array) as `context` so the persona knows who they're talking to, and
    the per-phone ring buffer as `previous_messages` for continuity.

    Empty replies (timeout/connect error) and HTTP errors are logged but do not
    raise — the webhook must always return 200. The except clause is narrowed
    to httpx + asyncio errors so genuine bugs in our code surface via FastAPI's
    error middleware rather than being silently swallowed.
    """
    ctx: Optional[dict] = None
    if sender_name:
        ctx = {
            "sender_name": sender_name,
            "chat_type": "private",
            "platform": "whatsapp",
        }

    previous_messages = simple_storage.get_recent_messages(phone)

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
        # httpx.HTTPStatusError.__str__ includes the request URL. The URL
        # contains app_id and uid, but never the api_key (which is in the
        # Authorization header). Still, log only the status code.
        logger.error("persona chat HTTP error for phone %s: HTTP %s", phone, e.response.status_code)
        return
    except httpx.HTTPError as e:
        logger.error("persona chat HTTP error for phone %s: %s", phone, type(e).__name__)
        return
    except asyncio.TimeoutError as e:
        logger.error("persona chat timeout for phone %s: %s", phone, type(e).__name__)
        return

    if not reply:
        logger.info("persona chat returned empty reply for phone %s (skipping send)", phone)
        return

    sent = await whatsapp_client.send_message(user["phone_number_id"], user["access_token"], phone, reply)
    if sent is None:
        # whatsapp_client.send_message already logs the failure; nothing else to do.
        return
    logger.info("auto-reply sent to phone %s (%d chars)", phone, len(reply))

    # T-020: record both sides of the exchange AFTER successful send so a
    # mid-flight failure doesn't poison subsequent context with a half-turn.
    # Use append_turn (atomic — single fsync) so a crash between the two
    # writes can't persist a human-without-ai or ai-without-human entry.
    simple_storage.append_turn(phone, human_text=text, ai_text=reply)


# ---------------------------------------------------------------------------
# /setup
# ---------------------------------------------------------------------------
class SetupRequest(BaseModel):
    access_token: str
    phone_number_id: str
    verify_token: str
    omi_uid: str
    persona_id: str
    omi_dev_api_key: str
    public_base_url: str  # where Meta will POST updates (e.g. https://clone.example.com)


class SetupResponse(BaseModel):
    deep_link: str
    phone_number_id: str
    setup_token: str


@app.post("/setup", response_model=SetupResponse, dependencies=[Depends(require_bearer)])
async def setup(req: SetupRequest):
    """Register the user's WhatsApp Business API creds and return a one-shot deep link.

    Two Meta API calls (in this order):
    1. POST /{phone_number_id}/subscribed_apps — register the app subscription
       so Meta delivers webhook updates for this phone.
    2. POST /{phone_number_id}/messages with type=template — NOT called here.
       (We need a pre-approved template to send the first proactive message;
       we just respond to user-initiated messages, so no template needed.)

    Storage:
    - Save the user-supplied creds in pending_setups keyed by a fresh
      setup_token. The deep link contains this token; when the user sends
      the deep-link text back, the webhook handler binds their phone.

    Returns: {deep_link, phone_number_id, setup_token}.
    """
    # IMPORTANT: never log str(e) or include it in the HTTP detail. For
    # httpx.HTTPStatusError, str(e) contains the full request URL — which
    # contains the phone_number_id (NOT the access_token, which is in the
    # Authorization header). Still, log only the status code for safety.
    try:
        await whatsapp_client.subscribe_app(req.phone_number_id, req.access_token)
    except httpx.HTTPStatusError as e:
        logger.error("subscribe_app failed: HTTP %s", e.response.status_code)
        raise HTTPException(status_code=502, detail="WhatsApp subscribe_app failed")
    except httpx.HTTPError as e:
        logger.error("subscribe_app failed: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="WhatsApp subscribe_app failed")

    # Deep link: https://wa.me/<E.164_phone>?text=/start%20<token>
    # The phone_number_id is an internal Meta Graph ID — NOT dialable, can't be
    # used in a wa.me link. We must fetch display_phone_number (the actual
    # E.164 number) and normalize it BEFORE saving the pending setup, so a
    # failed phone lookup doesn't leave orphaned pending_setup data on disk.
    try:
        info = await whatsapp_client.get_phone_number_info(req.phone_number_id, req.access_token)
        display_phone = _normalize_e164(info.get("display_phone_number"))
    except (httpx.HTTPError, json.JSONDecodeError, KeyError) as e:
        logger.error("get_phone_number_info failed: %s", type(e).__name__)
        raise HTTPException(
            status_code=502,
            detail="Could not fetch your WhatsApp phone number from Meta. "
            "Check that the access_token has whatsapp_business_management permissions.",
        )

    if not display_phone:
        # Meta returned a phone we couldn't normalize to E.164.
        logger.error("display_phone_number missing or invalid: %r", info.get("display_phone_number"))
        raise HTTPException(
            status_code=502,
            detail="Meta returned an invalid phone number. Please contact support.",
        )

    # Phone validated. NOW generate the setup token and persist the pending
    # setup. Order matters: persisting before the phone lookup would leave
    # orphaned pending_setup data on disk if the lookup failed.
    setup_token = secrets.token_urlsafe(16)
    simple_storage.save_pending_setup(
        setup_token,
        {
            "omi_uid": req.omi_uid,
            "persona_id": req.persona_id,
            "omi_dev_api_key": req.omi_dev_api_key,
            "access_token": req.access_token,
            "phone_number_id": req.phone_number_id,
            "verify_token": req.verify_token,
        },
    )

    deep_link = f"https://wa.me/{display_phone}?text={urllib.parse.quote(f'/start {setup_token}')}"

    logger.info(
        "setup complete for user %s (phone_number_id=%s, token=%s...)",
        req.omi_uid,
        req.phone_number_id,
        setup_token[:8],
    )

    return SetupResponse(deep_link=deep_link, phone_number_id=req.phone_number_id, setup_token=setup_token)


# ---------------------------------------------------------------------------
# Omi Chat Tools manifest — served at `GET /.well-known/omi-tools.json`.
# Schema per docs/doc/developer/apps/ChatTools.mdx. Each plugin owns its
# own manifest (TOOLS_MANIFEST) because the JSON-Schema `properties` keys
# MUST match the plugin's /toggle ToggleRequest field names.
#
# SECURITY: the manifest is public discovery metadata read by the chat
# assistant. It must NEVER advertise long-lived platform credentials as
# tool parameters — the chat assistant would faithfully prompt the user
# to paste them in chat, and those secrets would then live in chat
# history, tool-call logs, traces, screenshots, and model context.
#
# The plugin bearer token (in `Authorization: Bearer`) gates the call.
# The phone is a NON-SECRET reference the plugin uses to look up which
# user the call applies to (the binding was made at /start handshake
# time). The platform access_token is held by the plugin in its
# storage; the chat tool never sees it.
# ---------------------------------------------------------------------------
TOOLS_MANIFEST = {
    "tools": [
        {
            "name": "toggle_auto_reply",
            "description": (
                "Turn the AI Clone auto-reply on or off for a connected "
                "WhatsApp phone number. Use this when the user wants to "
                "enable or disable Omi's automatic responses in a specific "
                "WhatsApp conversation."
            ),
            "endpoint": "/toggle",
            "method": "POST",
            "parameters": {
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": (
                            "WhatsApp phone number in E.164 format "
                            "(e.g. 15550001111). The plugin uses this "
                            "to look up the bound user from the prior "
                            "/start handshake — it is NOT a secret."
                        ),
                    },
                    "enabled": {
                        "type": "boolean",
                        "description": (
                            "True to enable AI Clone auto-reply for the " "phone number, false to disable it."
                        ),
                    },
                },
                "required": ["phone", "enabled"],
            },
            "auth_required": True,
            "status_message": "Toggling WhatsApp auto-reply...",
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
# /toggle — flips auto_reply_enabled for a phone (called by Chat Tools).
#
# Auth model: the caller must hold a valid plugin bearer token (via the
# `Authorization: Bearer` header, enforced by the shared
# plugins/_shared/auth.require_bearer dependency). The phone parameter
# identifies which user/chat the call applies to — the plugin looks up
# the user bound to the phone from its storage (set at /start handshake
# time). The platform access_token is held by the plugin and is NEVER
# requested from or transmitted through chat — that keeps long-lived
# credentials out of chat history, tool-call logs, traces, and model
# context. (Identified by maintainer security review on PR #8528.)
# ---------------------------------------------------------------------------
class ToggleRequest(BaseModel):
    phone: str
    enabled: bool


class ToggleResponse(BaseModel):
    phone: str
    auto_reply_enabled: bool


@app.post("/toggle", response_model=ToggleResponse, dependencies=[Depends(require_bearer)])
async def toggle(req: ToggleRequest):
    """Enable or disable auto-reply for the given phone.

    Auth: enforced upstream by the shared plugin bearer dependency
    (plugins/_shared/auth.require_bearer, applied via
    `dependencies=[Depends(require_bearer)]`). The request body is
    ONLY `phone` + `enabled` — no access_token field — because the
    WhatsApp access_token is a long-lived Meta secret held by the
    plugin, and chat tools MUST NEVER echo it back through chat
    history, tool-call logs, traces, or model context. (Identified
    by maintainer security review on PR #8531; see the block comment
    above the `ToggleRequest` model for the full threat model.)

    Phone acts as an authorization hint: the bearer holder is
    already authenticated, and the phone identifies which user
    state to flip. Returning 403 with a generic message on unknown
    phone prevents bearer holders from enumerating which phones
    are registered, even though phone numbers aren't strictly
    secret (they appear in Meta webhook payloads).
    """
    # Identified by cubic (P2): the previous version did an exact string
    # match on `req.phone`, so users passing an E.164 variant (`+15550001111`,
    # formatted with dashes / parens, etc.) would get a 403 even though their
    # phone is registered. Normalize to digits-only before lookup; if the
    # normalized form is too short to be a real number, reject with 403.
    normalized = _normalize_e164(req.phone)
    if not normalized:
        # Auth is already enforced upstream by the bearer dependency, so
        # this is purely a request-validation 403 — no enumeration signal,
        # no credential wording to leak the actual auth model.
        raise HTTPException(status_code=403, detail="Invalid phone")
    user = simple_storage.get_user_by_phone(normalized)
    # 403 (not 404) on unknown phone so the endpoint doesn't leak which
    # phones are registered. The bearer holder is already authenticated;
    # the message hides whether the phone was the failure point. (Phone
    # numbers are exposed in Meta webhook payloads and could be enumerated
    # otherwise.)
    if user is None:
        raise HTTPException(status_code=403, detail="Unknown phone")
    simple_storage.update_auto_reply(normalized, req.enabled)
    return ToggleResponse(phone=normalized, auto_reply_enabled=req.enabled)
