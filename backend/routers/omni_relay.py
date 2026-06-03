import asyncio
import logging
import os
from urllib.parse import quote

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, WebSocketException

from utils.byok import (
    BYOK_HEADERS,
    extract_byok_from_websocket,
    get_byok_key,
    set_byok_keys,
    validate_byok_websocket,
)
from utils.executors import critical_executor, run_blocking
from utils.other.endpoints import _verify_ws_auth
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


def _upstream(provider: str, model: str | None):
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
    # Manual auth (read the header directly so we control logging and avoid any
    # WS header-DI surprises). Token first, then BYOK validate, then the gate.
    authz = websocket.headers.get("authorization")
    byok_present = [p for p, h in BYOK_HEADERS.items() if websocket.headers.get(h)]
    logger.info(
        f"omni relay connect: auth_present={bool(authz)} byok={byok_present} "
        f"provider={websocket.query_params.get('provider')}"
    )
    try:
        uid = await run_blocking(critical_executor, _verify_ws_auth, authz)
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
    if is_trial_paywalled(uid, "desktop"):
        logger.info(f"omni relay paywalled uid={uid}")
        await websocket.close(code=1008, reason="trial_expired")
        return

    provider = websocket.query_params.get("provider", "gemini")
    model = websocket.query_params.get("model")
    upstream_cfg, err = _upstream(provider, model)
    if err:
        await websocket.close(code=1011, reason=err)
        return
    url, headers = upstream_cfg

    await websocket.accept()
    try:
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
            done, pending = await asyncio.wait({t1, t2}, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            for t in done:
                if t.exception():
                    logger.warning(f"omni relay task ended: {t.exception()}")
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"omni relay error (uid={uid}, provider={provider}): {e}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
