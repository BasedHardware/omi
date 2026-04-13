"""ProactiveAI WebSocket router — server-side Gemini task extraction.

Replaces the standalone gRPC service with a FastAPI WebSocket endpoint,
enabling deployment via the shared backend Docker image (same pattern as
transcribe.py and other WebSocket routers).
"""

import asyncio
import json
import logging
import uuid

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from utils.other.endpoints import get_current_user_uid_ws_listen
from proactive.task_assistant import ServerTaskAssistant

logger = logging.getLogger(__name__)
router = APIRouter()

PROTOCOL_VERSION = '1.0'
MAX_MODEL_ITERATIONS = 5
_STREAM_END = object()


def _sanitize_uid(uid: str) -> str:
    """Truncate UID for log safety — show first 8 chars only."""
    return uid[:8] + '...' if len(uid) > 8 else uid


@router.websocket('/v1/proactive')
async def proactive_ws(websocket: WebSocket, uid: str = Depends(get_current_user_uid_ws_listen)):
    """Bidirectional WebSocket session for proactive task extraction.

    Protocol:
      Client sends JSON messages: client_hello, frame_event, tool_result, heartbeat
      Server sends JSON messages: session_ready, tool_call_request, analysis_outcome, server_error
    """
    await websocket.accept()

    async def send_event(event: dict):
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.send_text(json.dumps(event))

    async def receive_message():
        text = await websocket.receive_text()
        return json.loads(text)

    try:
        await handle_proactive_session(send_event, receive_message, uid)
    except WebSocketDisconnect:
        logger.info('ProactiveWS: Client disconnected uid=%s', _sanitize_uid(uid))
    except Exception:
        logger.exception('ProactiveWS: Unexpected error uid=%s', _sanitize_uid(uid))


async def handle_proactive_session(send_event, receive_message, uid):
    """Core session logic — decoupled from WebSocket for testability.

    Args:
        send_event: async callable to send a dict message to the client.
        receive_message: async callable returning the next dict from the client (raises on disconnect).
        uid: authenticated user ID.
    """
    safe_uid = _sanitize_uid(uid)
    session_id = str(uuid.uuid4())
    logger.info('Session opened: uid=%s session=%s', safe_uid, session_id)

    cached_context = None
    context_version = None
    task_assistant = ServerTaskAssistant()
    tool_result_queue = asyncio.Queue(maxsize=4)

    client_queue = asyncio.Queue()

    async def _pump_client():
        try:
            while True:
                msg = await receive_message()
                await client_queue.put(msg)
        except Exception:
            pass
        finally:
            await client_queue.put(_STREAM_END)

    pump_task = asyncio.create_task(_pump_client())

    async def _receive_tool_result(request_id: str, timeout_ms: int = 10000) -> dict:
        timeout_s = timeout_ms / 1000.0
        deadline = asyncio.get_event_loop().time() + timeout_s
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                raise TimeoutError(f'ToolResult timeout after {timeout_ms}ms for request_id={request_id}')
            try:
                result = await asyncio.wait_for(tool_result_queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                raise TimeoutError(f'ToolResult timeout after {timeout_ms}ms for request_id={request_id}')
            if result.get('request_id') == request_id:
                return result
            logger.warning(
                'ToolResult request_id mismatch: expected=%s got=%s uid=%s — discarding',
                request_id,
                result.get('request_id'),
                safe_uid,
            )

    try:
        while True:
            client_msg = await client_queue.get()
            if client_msg is _STREAM_END:
                break

            msg_type = client_msg.get('type')

            if msg_type == 'client_hello':
                cached_context = client_msg.get('session_context')
                context_version = client_msg.get('context_version')
                logger.info(
                    'ClientHello: uid=%s session=%s version=%s tasks=%d goals=%d',
                    safe_uid,
                    session_id,
                    client_msg.get('app_version', ''),
                    len(cached_context.get('active_tasks', [])) if cached_context else 0,
                    len(cached_context.get('goals', [])) if cached_context else 0,
                )
                await send_event(
                    {
                        'type': 'session_ready',
                        'session_id': session_id,
                        'protocol_version': PROTOCOL_VERSION,
                        'context_version': context_version or '',
                        'max_model_iterations': MAX_MODEL_ITERATIONS,
                        'supported_tool_kinds': ['search_similar', 'search_keywords'],
                    }
                )

            elif msg_type == 'frame_event':
                frame_id = client_msg.get('screenshot_id') or str(client_msg.get('frame_number', 0))

                new_ctx = client_msg.get('session_context')
                new_ver = client_msg.get('context_version')
                if new_ctx and new_ver and new_ver != context_version:
                    cached_context = new_ctx
                    context_version = new_ver
                    logger.info('Context refreshed: uid=%s version=%s', safe_uid, context_version)

                if cached_context is None:
                    await send_event(
                        {
                            'type': 'server_error',
                            'code': 'NO_CONTEXT',
                            'message': 'No session context available. Send client_hello first.',
                            'retryable': True,
                            'frame_id': frame_id,
                        }
                    )
                    continue

                output_queue = asyncio.Queue()
                gen = task_assistant.analyze_frame(
                    frame=client_msg,
                    session_context=cached_context,
                    frame_id=frame_id,
                    uid=uid,
                    receive_tool_result=_receive_tool_result,
                )
                gen_task = asyncio.create_task(_run_generator(gen, output_queue))

                awaiting_tool_result = False
                while True:
                    if awaiting_tool_result:
                        output_get = asyncio.ensure_future(output_queue.get())
                        client_read = asyncio.ensure_future(client_queue.get())
                        done, pending = await asyncio.wait(
                            {output_get, client_read},
                            timeout=30.0,
                            return_when=asyncio.FIRST_COMPLETED,
                        )

                        if not done:
                            for p in pending:
                                p.cancel()
                            logger.warning('Both output and client read timed out: uid=%s', safe_uid)
                            gen_task.cancel()
                            break

                        for p in pending:
                            p.cancel()

                        if output_get in done:
                            event = output_get.result()
                            if event is None:
                                break
                            await send_event(event)
                            awaiting_tool_result = event.get('type') == 'tool_call_request'

                        if client_read in done:
                            next_msg = client_read.result()
                            if next_msg is _STREAM_END:
                                logger.warning('Client disconnected during tool wait: uid=%s', safe_uid)
                                gen_task.cancel()
                                await client_queue.put(_STREAM_END)
                                break
                            next_type = next_msg.get('type') if isinstance(next_msg, dict) else None
                            if next_type == 'tool_result':
                                await tool_result_queue.put(next_msg)
                            elif next_type == 'heartbeat':
                                pass
                            else:
                                logger.warning('Unexpected %s during tool wait: uid=%s', next_type, safe_uid)
                    else:
                        try:
                            event = await asyncio.wait_for(output_queue.get(), timeout=60.0)
                        except asyncio.TimeoutError:
                            logger.warning('Analysis timed out: uid=%s frame=%s', safe_uid, frame_id)
                            gen_task.cancel()
                            break
                        if event is None:
                            break
                        await send_event(event)
                        awaiting_tool_result = event.get('type') == 'tool_call_request'

                if not gen_task.done():
                    gen_task.cancel()
                    try:
                        await gen_task
                    except asyncio.CancelledError:
                        pass

            elif msg_type == 'heartbeat':
                pass

            elif msg_type == 'tool_result':
                try:
                    tool_result_queue.put_nowait(client_msg)
                except asyncio.QueueFull:
                    logger.debug('Dropped standalone tool_result for request_id=%s', client_msg.get('request_id'))

    except asyncio.CancelledError:
        logger.info('Session cancelled: uid=%s session=%s', safe_uid, session_id)
    except Exception:
        logger.exception('Session error: uid=%s session=%s', safe_uid, session_id)
        await send_event(
            {
                'type': 'server_error',
                'code': 'INTERNAL',
                'message': 'Internal server error',
                'retryable': False,
            }
        )
    finally:
        pump_task.cancel()
        logger.info('Session closed: uid=%s session=%s', safe_uid, session_id)


async def _run_generator(gen, output_queue: asyncio.Queue):
    """Drain an async generator into a queue, sending None when done."""
    try:
        async for event in gen:
            await output_queue.put(event)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.exception('Generator error: %s', type(e).__name__)
        await output_queue.put(
            {
                'type': 'server_error',
                'code': 'INTERNAL',
                'message': f'Analysis failed ({type(e).__name__})',
                'retryable': True,
            }
        )
    finally:
        await output_queue.put(None)
