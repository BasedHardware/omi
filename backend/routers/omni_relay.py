import asyncio
import logging
import os
from typing import cast
from urllib.parse import quote

import websockets
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, WebSocketException

from database import redis_db
from utils.byok import (
    BYOK_HEADERS,
    extract_byok_from_websocket,
    get_byok_key,
    set_byok_keys,
    validate_byok_websocket,
)
from utils.executors import critical_executor, db_executor, run_blocking
from utils.llm.gateway_client import raise_if_gateway_feature_mode_blocks_direct_model_surface
from utils.other.endpoints import check_rate_limit_inline
from utils.other.endpoints import _verify_ws_auth  # type: ignore[reportPrivateUsage]  # shared WS auth helper, intentionally reused cross-module
from utils.subscription import is_trial_paywalled

router = APIRouter()
logger = logging.getLogger(__name__)


# Realtime "omni" relay.
#
# The desktop floating bar connects here (authenticated, like /v4/listen) and we
# pipe every frame, verbatim, to the chosen provider's realtime WebSocket. This
# exists because:
#   1) Apple's WebSocket stacks (URLSessionWebSocketTask / Network.framework)
#      cannot hold a direct connection to Gemini's Live endpoint (Google's
#      frontend resets them); a server-side `websockets` client connects fine.
#   2) Provider API keys stay server-side instead of shipping in the client.
#
# Protocol is provider-native and opaque to the relay — the desktop speaks raw
# OpenAI Realtime / Gemini Live JSON; we just forward bytes both ways.

GEMINI_URL = (
    "wss://generativelanguage.googleapis.com/ws/"
    "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent?key={key}"
)
OPENAI_URL = "wss://api.openai.com/v1/realtime?model={model}"

# A relay session bills the platform provider key for as long as it stays open,
# so bound both how many a single uid may hold and how long any one may live.
# The slot key TTL is the session cap plus a grace margin so a crashed backend
# instance cannot strand slots forever.
_MAX_CONCURRENT_RELAYS = 3
_MAX_SESSION_SECONDS = 30 * 60
_SLOT_TTL_SECONDS = _MAX_SESSION_SECONDS + 120


def _slot_key(uid: str) -> str:
    return f'omni_relay:conns:{uid}'


def _acquire_relay_slot(uid: str) -> bool:
    """Reserve one concurrent-relay slot for uid. Fail-closed on Redis errors."""
    key = _slot_key(uid)
    count = int(redis_db.r.incr(key))
    if count > _MAX_CONCURRENT_RELAYS:
        redis_db.r.decr(key)
        return False
    # Only arm the TTL on the counter's first holder. Re-arming on every acquire
    # (including rejected ones) lets a reconnect loop keep a stuck counter alive
    # indefinitely, which locks the uid out until the key is deleted by hand.
    if count == 1:
        redis_db.r.expire(key, _SLOT_TTL_SECONDS)
    return True


def _release_relay_slot(uid: str) -> None:
    key = _slot_key(uid)
    if int(redis_db.r.decr(key)) < 0:
        redis_db.r.set(key, 0, ex=_SLOT_TTL_SECONDS)


def _upstream(provider: str, model: str | None) -> tuple[tuple[str, dict[str, str]], None] | tuple[None, str]:
    """Return (url, headers) for the chosen provider, or (None, reason).

    Prefers the caller's BYOK key (so BYOK users pay their own way, same as the
    rest of the API); falls back to the platform key for entitled non-BYOK users.
    """
    if provider == "gemini":
        key = get_byok_key("gemini") or os.getenv("GEMINI_API_KEY")
        if not key:
            return None, "no Gemini key (BYOK or platform)"
        return (GEMINI_URL.format(key=key), {}), None
    if provider == "openai":
        key = get_byok_key("openai") or os.getenv("OPENAI_API_KEY")
        if not key:
            return None, "no OpenAI key (BYOK or platform)"
        # URL-encode the client-supplied model so it can't inject extra query params.
        url = OPENAI_URL.format(model=quote(model or "gpt-realtime-2", safe=""))
        return (url, {"Authorization": f"Bearer {key}"}), None
    return None, f"unsupported provider: {provider}"


@router.websocket("/v1/omni/relay")
async def omni_relay(websocket: WebSocket):
    try:
        raise_if_gateway_feature_mode_blocks_direct_model_surface('omni_realtime.provider_websocket')
    except RuntimeError as exc:
        await websocket.close(code=1013, reason=str(exc)[:120])
        return

    # Manual auth (read the header directly so we control logging and avoid any
    # WS header-DI surprises). Token first, then BYOK validate, then the gate.
    authz = websocket.headers.get("authorization")
    byok_present = [p for p, h in BYOK_HEADERS.items() if websocket.headers.get(h)]
    logger.info(
        f"omni relay connect: auth_present={bool(authz)} byok={byok_present} "
        f"provider={websocket.query_params.get('provider')}"
    )
    try:
        uid = await run_blocking(critical_executor, _verify_ws_auth, cast(str, authz))
    except WebSocketException as e:
        logger.warning(f"omni relay auth rejected: code={e.code} reason={e.reason}")
        await websocket.close(code=e.code, reason=e.reason or "unauthorized")
        return

    # BYOK: validate forwarded keys (same as /v4/listen). Keys then resolve via get_byok_key.
    byok = extract_byok_from_websocket(websocket)
    if byok:
        set_byok_keys(byok)
        byok_err = await run_blocking(critical_executor, validate_byok_websocket, uid)
        if byok_err:
            logger.warning(f"omni relay BYOK invalid uid={uid}: {byok_err}")
            await websocket.close(code=4003, reason=byok_err)
            return

    # Same desktop gate as /v4/listen: Operator/Architect + BYOK pass; un-entitled
    # desktop users past their trial are paywalled.
    if await run_blocking(db_executor, is_trial_paywalled, uid, "desktop"):
        logger.info(f"omni relay paywalled uid={uid}")
        await websocket.close(code=1008, reason="trial_expired")
        return

    # Connect-rate cap. Reuses the shared per-UID policy table so the relay is
    # tunable with every other metered surface (RATE_LIMIT_BOOST / shadow mode).
    try:
        await run_blocking(critical_executor, check_rate_limit_inline, uid, "omni:relay")
    except HTTPException as e:
        logger.info(f"omni relay rate limited uid={uid}")
        await websocket.close(code=1008, reason=str(e.detail)[:120])
        return

    provider = websocket.query_params.get("provider", "gemini")
    model = websocket.query_params.get("model")
    upstream_cfg, err = _upstream(provider, model)
    if err:
        await websocket.close(code=1011, reason=err)
        return
    url, headers = cast(tuple[str, dict[str, str]], upstream_cfg)

    # Concurrent-session cap. Acquired last so no earlier rejection path can leak
    # a slot, and released unconditionally in the finally below.
    try:
        slot_acquired = await run_blocking(critical_executor, _acquire_relay_slot, uid)
    except Exception as e:
        logger.error(f"omni relay slot check failed uid={uid}: {e}")
        await websocket.close(code=1013, reason="relay capacity check unavailable")
        return
    if not slot_acquired:
        logger.info(f"omni relay concurrency cap hit uid={uid}")
        await websocket.close(code=1008, reason="too many concurrent relay sessions")
        return

    try:
        # accept() lives inside the try so a failed handshake still releases the slot.
        await websocket.accept()
        async with websockets.connect(
            url, extra_headers=headers or None, max_size=None, ping_interval=20, ping_timeout=20
        ) as upstream:

            async def client_to_upstream():
                while True:
                    msg = await websocket.receive()
                    if msg.get("type") == "websocket.disconnect":
                        return
                    if (text := msg.get("text")) is not None:
                        await upstream.send(text)
                    elif (data := msg.get("bytes")) is not None:
                        await upstream.send(data)

            async def upstream_to_client():
                async for message in upstream:
                    if isinstance(message, (bytes, bytearray)):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            t1 = asyncio.create_task(client_to_upstream(), name=f"ws:{uid}:omni_c2u")
            t2 = asyncio.create_task(upstream_to_client(), name=f"ws:{uid}:omni_u2c")
            # Hard session-duration cap: an idle-but-open relay still holds a
            # provider session, so time it out instead of waiting on the peers.
            done, pending = await asyncio.wait(
                {t1, t2}, timeout=_MAX_SESSION_SECONDS, return_when=asyncio.FIRST_COMPLETED
            )
            for t in pending:
                t.cancel()
            if not done:
                logger.info(f"omni relay session duration cap reached uid={uid}")
            for t in done:
                if t.exception():
                    logger.warning(f"omni relay task ended: {t.exception()}")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"omni relay error (uid={uid}, provider={provider}): {e}")
    finally:
        try:
            await run_blocking(critical_executor, _release_relay_slot, uid)
        except Exception as e:
            logger.warning(f"omni relay slot release failed uid={uid}: {e}")
        try:
            await websocket.close()
        except Exception:
            pass
