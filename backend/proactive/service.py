"""ProactiveAI gRPC service implementation."""

import asyncio
import logging
import uuid

import grpc

from proactive.v1 import proactive_pb2 as pb2
from proactive.v1 import proactive_pb2_grpc as pb2_grpc

from proactive.auth import extract_uid_from_metadata, current_uid
from proactive.task_assistant import ServerTaskAssistant

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = '1.0'
MAX_MODEL_ITERATIONS = 5

_STREAM_END = object()


class ProactiveAIServicer(pb2_grpc.ProactiveAIServicer):
    """Handles bidirectional Session streams from desktop clients."""

    async def Session(self, request_iterator, context):
        # --- Auth: verify Firebase token from metadata ---
        metadata = context.invocation_metadata()
        try:
            uid = extract_uid_from_metadata(metadata)
        except Exception as e:
            logger.warning('Session auth failed: %s', e)
            await context.abort(grpc.StatusCode.UNAUTHENTICATED, str(e))
            return

        current_uid.set(uid)
        session_id = str(uuid.uuid4())
        logger.info('Session opened: uid=%s session=%s', uid, session_id)

        # Session state
        cached_context = None
        context_version = None
        task_assistant = ServerTaskAssistant()
        tool_result_queue = asyncio.Queue(maxsize=4)

        # Pump client messages into a queue so we can read from it concurrently
        # without conflicting with async-for iteration.
        client_queue = asyncio.Queue()

        async def _pump_client():
            try:
                async for msg in request_iterator:
                    await client_queue.put(msg)
            except Exception:
                pass
            finally:
                await client_queue.put(_STREAM_END)

        pump_task = asyncio.create_task(_pump_client())

        async def receive_tool_result(request_id: str, timeout_ms: int = 10000) -> pb2.ToolResult:
            """Wait for a ToolResult matching request_id from the client stream."""
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
                if result.request_id == request_id:
                    return result
                logger.warning(
                    'ToolResult request_id mismatch: expected=%s got=%s uid=%s — discarding',
                    request_id,
                    result.request_id,
                    uid,
                )

        try:
            while True:
                client_event = await client_queue.get()
                if client_event is _STREAM_END:
                    break

                event_type = client_event.WhichOneof('event')

                if event_type == 'client_hello':
                    hello = client_event.client_hello
                    cached_context = hello.session_context
                    context_version = hello.context_version
                    logger.info(
                        'ClientHello: uid=%s session=%s version=%s app=%s tasks=%d goals=%d',
                        uid,
                        session_id,
                        hello.app_version,
                        hello.os_version,
                        len(cached_context.active_tasks) if cached_context else 0,
                        len(cached_context.goals) if cached_context else 0,
                    )
                    yield pb2.ServerEvent(
                        session_ready=pb2.SessionReady(
                            session_id=session_id,
                            protocol_version=PROTOCOL_VERSION,
                            context_version=context_version or '',
                            max_model_iterations=MAX_MODEL_ITERATIONS,
                            supported_tool_kinds=[pb2.SEARCH_SIMILAR, pb2.SEARCH_KEYWORDS],
                        )
                    )

                elif event_type == 'frame_event':
                    frame = client_event.frame_event
                    frame_id = frame.screenshot_id or str(frame.frame_number)

                    if frame.HasField('session_context') and frame.context_version != context_version:
                        cached_context = frame.session_context
                        context_version = frame.context_version
                        logger.info('Context refreshed: uid=%s version=%s', uid, context_version)

                    if not cached_context:
                        yield pb2.ServerEvent(
                            server_error=pb2.ServerError(
                                code='NO_CONTEXT',
                                message='No session context available. Send ClientHello first.',
                                retryable=True,
                                frame_id=frame_id,
                            )
                        )
                        continue

                    output_queue = asyncio.Queue()
                    gen = task_assistant.analyze_frame(
                        frame=frame,
                        session_context=cached_context,
                        frame_id=frame_id,
                        uid=uid,
                        receive_tool_result=receive_tool_result,
                    )
                    gen_task = asyncio.create_task(self._run_generator(gen, output_queue))

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
                                logger.warning('Both output and client read timed out: uid=%s', uid)
                                gen_task.cancel()
                                break

                            for p in pending:
                                p.cancel()

                            if client_read in done:
                                next_msg = client_read.result()
                                if next_msg is _STREAM_END:
                                    logger.warning('Client disconnected during tool wait: uid=%s', uid)
                                    gen_task.cancel()
                                    break
                                msg_type = next_msg.WhichOneof('event')
                                if msg_type == 'tool_result':
                                    await tool_result_queue.put(next_msg.tool_result)
                                elif msg_type == 'heartbeat':
                                    pass
                                else:
                                    logger.warning('Unexpected %s during tool wait: uid=%s', msg_type, uid)

                            if output_get in done:
                                event = output_get.result()
                                if event is None:
                                    break
                                yield event
                                awaiting_tool_result = event.WhichOneof('event') == 'tool_call_request'
                        else:
                            try:
                                event = await asyncio.wait_for(output_queue.get(), timeout=60.0)
                            except asyncio.TimeoutError:
                                logger.warning('Analysis timed out: uid=%s frame=%s', uid, frame_id)
                                gen_task.cancel()
                                break
                            if event is None:
                                break
                            yield event
                            awaiting_tool_result = event.WhichOneof('event') == 'tool_call_request'

                    if not gen_task.done():
                        gen_task.cancel()
                        try:
                            await gen_task
                        except asyncio.CancelledError:
                            pass

                elif event_type == 'heartbeat':
                    pass

                elif event_type == 'tool_result':
                    try:
                        tool_result_queue.put_nowait(client_event.tool_result)
                    except asyncio.QueueFull:
                        logger.debug(
                            'Dropped standalone tool_result for request_id=%s', client_event.tool_result.request_id
                        )

        except asyncio.CancelledError:
            logger.info('Session cancelled: uid=%s session=%s', uid, session_id)
        except Exception:
            logger.exception('Session error: uid=%s session=%s', uid, session_id)
            yield pb2.ServerEvent(
                server_error=pb2.ServerError(
                    code='INTERNAL',
                    message='Internal server error',
                    retryable=False,
                )
            )
        finally:
            pump_task.cancel()
            logger.info('Session closed: uid=%s session=%s', uid, session_id)

    @staticmethod
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
                pb2.ServerEvent(
                    server_error=pb2.ServerError(
                        code='INTERNAL',
                        message=f'Analysis failed ({type(e).__name__})',
                        retryable=True,
                    )
                )
            )
        finally:
            await output_queue.put(None)
