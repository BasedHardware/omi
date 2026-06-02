import asyncio
import logging
import os

import websockets
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from utils.other.endpoints import get_current_user_uid_ws_listen

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
    """Return (url, headers) for the chosen provider, or (None, reason)."""
    if provider == "gemini":
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            return None, "GEMINI_API_KEY not configured"
        return (GEMINI_URL.format(key=key), {}), None
    if provider == "openai":
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            return None, "OPENAI_API_KEY not configured"
        url = OPENAI_URL.format(model=model or "gpt-realtime-2")
        return (url, {"Authorization": f"Bearer {key}"}), None
    return None, f"unsupported provider: {provider}"


@router.websocket("/v1/omni/relay")
async def omni_relay(websocket: WebSocket, uid: str = Depends(get_current_user_uid_ws_listen)):
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
