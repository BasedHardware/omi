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
import json
import logging
import os
import sys
import urllib.parse
from typing import Optional

# Add plugins/_shared to sys.path so `from persona_client import chat` works.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SHARED = os.path.abspath(os.path.join(_HERE, "..", "_shared"))
if _SHARED not in sys.path:
    sys.path.insert(0, _SHARED)

import httpx  # noqa: E402
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response  # noqa: E402
from pydantic import BaseModel  # noqa: E402

import simple_storage  # noqa: E402
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


app = FastAPI(
    title="OMI WhatsApp AI-Clone",
    description="Self-hosted WhatsApp plugin that lets Omi reply on the user's behalf.",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {"status": "ok", "service": "omi-whatsapp-clone", "version": "0.1.0"}


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
    import simple_storage  # local import to avoid pulling storage into /health

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
        import hmac
        import hashlib

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
            logger.warning(
                "webhook signature mismatch (presented=%s expected=%s)",
                presented_sig,
                expected_sig,
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
    for msg in inbound_messages:
        await _handle_inbound_message(msg)

    return {"ok": True}


async def _handle_inbound_message(msg: dict) -> None:
    """Handle a single inbound Meta WhatsApp message (text only in v0.1)."""
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

    await _dispatch_auto_reply(user, str(from_phone), text)


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


async def _dispatch_auto_reply(user: dict, phone: str, text: str) -> None:
    """Call the persona API and send the reply back to WhatsApp.

    Empty replies (timeout/connect error) and HTTP errors are logged but do not
    raise — the webhook must always return 200. The except clause is narrowed
    to httpx + asyncio errors so genuine bugs in our code surface via FastAPI's
    error middleware rather than being silently swallowed.
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


@app.post("/setup", response_model=SetupResponse)
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

    # Generate a one-shot setup token. The user clicks the deep link, sends
    # /start <token> to our WhatsApp number, and we know which phone maps
    # to which user.
    setup_token = secrets.token_urlsafe(16)

    # We don't know the user's phone (E.164 number) until they send us the
    # /start message. So we store the setup payload without a phone — the
    # webhook handler will bind phone -> user when the message arrives.
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

    # Deep link: https://wa.me/<E.164_phone>?text=/start%20<token>
    # The phone_number_id is an internal Meta Graph ID — NOT dialable, can't be
    # used in a wa.me link. We must fetch display_phone_number (the actual
    # E.164 number) and normalize it. If we can't get a valid phone, we fail
    # the setup rather than return a broken link the user can't click.
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

    deep_link = f"https://wa.me/{display_phone}?text={urllib.parse.quote(f'/start {setup_token}')}"

    logger.info(
        "setup complete for user %s (phone_number_id=%s, token=%s...)",
        req.omi_uid,
        req.phone_number_id,
        setup_token[:8],
    )

    return SetupResponse(deep_link=deep_link, phone_number_id=req.phone_number_id, setup_token=setup_token)


# ---------------------------------------------------------------------------
# /toggle
# ---------------------------------------------------------------------------
class ToggleRequest(BaseModel):
    phone: str
    enabled: bool
    access_token: str


class ToggleResponse(BaseModel):
    phone: str
    auto_reply_enabled: bool


@app.post("/toggle", response_model=ToggleResponse)
async def toggle(req: ToggleRequest):
    """Enable or disable auto-reply for the given phone.

    Auth: requires the access_token that was registered for that phone. The
    access_token is a real secret (only the user has it; calling Meta's API
    with the wrong token fails at Meta). Phone alone is NOT sufficient — phone
    numbers are exposed in Meta update payloads and could be guessed.

    Returns 403 with a generic message for both unknown phone AND wrong
    access_token, so callers can't enumerate which phones are registered by
    distinguishing 404 (unknown) from 403 (wrong token).
    """
    user = simple_storage.get_user_by_phone(req.phone)
    # Same response for both 'unknown phone' and 'wrong access_token' so the
    # endpoint doesn't leak which phones exist (phone numbers are exposed in
    # Meta update payloads and could be enumerated otherwise).
    if user is None or not secrets.compare_digest(req.access_token, user["access_token"]):
        raise HTTPException(status_code=403, detail="Invalid phone or access_token")
    simple_storage.update_auto_reply(req.phone, req.enabled)
    return ToggleResponse(phone=req.phone, auto_reply_enabled=req.enabled)
