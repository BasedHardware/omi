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
        # Queue for passing tool results from the bidi stream into analyze_frame
        tool_result_queue = asyncio.Queue(maxsize=1)

        async def receive_tool_result(request_id: str, timeout_ms: int = 10000) -> pb2.ToolResult:
            """Wait for a ToolResult from the client stream (fed by the main loop)."""
            timeout_s = timeout_ms / 1000.0
            try:
                result = await asyncio.wait_for(tool_result_queue.get(), timeout=timeout_s)
            except asyncio.TimeoutError:
                raise TimeoutError(f'ToolResult timeout after {timeout_ms}ms for request_id={request_id}')
            if result.request_id != request_id:
                logger.warning(
                    'ToolResult request_id mismatch: expected=%s got=%s uid=%s',
                    request_id,
                    result.request_id,
                    uid,
                )
            return result

        try:
            async for client_event in request_iterator:
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

                    # Update context if client sent a refresh
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

                    # Run the server-side task extraction loop.
                    # analyze_frame is an async generator that yields ServerEvents.
                    # When it needs a tool result, it yields a ToolCallRequest and then
                    # awaits receive_tool_result(). The bidi stream pauses here while
                    # waiting — the client sends back a ToolResult which we feed into
                    # the queue from the tool_result branch below.
                    #
                    # However, because this is a bidi generator (we yield AND read from
                    # request_iterator), we need to interleave: the analyze_frame generator
                    # blocks on receive_tool_result while the main loop needs to read the
                    # next client message. We solve this with asyncio.create_task.
                    analysis_task = asyncio.create_task(
                        self._drain_analysis(task_assistant, frame, cached_context, frame_id, uid, receive_tool_result)
                    )
                    # The analysis task will put events into an output queue
                    # We need a different approach — use an output queue too
                    # Actually, let's use a simpler model: collect events one at a time
                    # by running the generator in a task that writes to an output queue.
                    analysis_task.cancel()  # Cancel the placeholder

                    # Simpler approach: run analyze_frame inline. When it yields a
                    # ToolCallRequest, we yield it to the client, then read the next
                    # client message inline (it must be a tool_result).
                    gen = task_assistant.analyze_frame(
                        frame=frame,
                        session_context=cached_context,
                        frame_id=frame_id,
                        uid=uid,
                        receive_tool_result=receive_tool_result,
                    )
                    # We can't iterate the generator with async for because it blocks
                    # on receive_tool_result which needs us to read from request_iterator.
                    # Instead, we run the generator in a background task and shuttle events.
                    output_queue = asyncio.Queue()
                    gen_task = asyncio.create_task(self._run_generator(gen, output_queue))

                    # Drain events: yield ServerEvents and feed ToolResults
                    while True:
                        try:
                            event = await asyncio.wait_for(output_queue.get(), timeout=60.0)
                        except asyncio.TimeoutError:
                            logger.warning('Analysis timed out: uid=%s frame=%s', uid, frame_id)
                            break
                        if event is None:
                            break  # Generator finished
                        yield event
                        # If we just yielded a ToolCallRequest, read the next client
                        # message which should be the ToolResult
                        if event.WhichOneof('event') == 'tool_call_request':
                            try:
                                next_msg = await asyncio.wait_for(
                                    request_iterator.__aiter__().__anext__(), timeout=15.0
                                )
                            except (StopAsyncIteration, asyncio.TimeoutError):
                                logger.warning('Client disconnected while waiting for ToolResult: uid=%s', uid)
                                gen_task.cancel()
                                break
                            if next_msg.WhichOneof('event') == 'tool_result':
                                await tool_result_queue.put(next_msg.tool_result)
                            else:
                                logger.warning(
                                    'Expected tool_result, got %s: uid=%s', next_msg.WhichOneof('event'), uid
                                )
                                gen_task.cancel()
                                break

                    if not gen_task.done():
                        gen_task.cancel()
                        try:
                            await gen_task
                        except asyncio.CancelledError:
                            pass

                elif event_type == 'heartbeat':
                    pass  # Heartbeats keep the stream alive; no response needed

                elif event_type == 'tool_result':
                    # Standalone tool_result outside of a frame analysis — feed it to the queue
                    # in case the analysis is still waiting
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
        finally:
            await output_queue.put(None)

    @staticmethod
    async def _drain_analysis(task_assistant, frame, cached_context, frame_id, uid, receive_tool_result):
        """Placeholder — not used. Kept for documentation."""
        pass
