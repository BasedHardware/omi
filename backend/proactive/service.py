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

                    # Run the server-side task extraction loop
                    async for server_event in task_assistant.analyze_frame(
                        frame=frame,
                        session_context=cached_context,
                        frame_id=frame_id,
                        uid=uid,
                        send_tool_request=_make_tool_sender(context),
                        receive_tool_result=_make_tool_receiver(request_iterator, frame_id),
                    ):
                        yield server_event

                elif event_type == 'heartbeat':
                    pass  # Heartbeats keep the stream alive; no response needed

                elif event_type == 'tool_result':
                    # Tool results are consumed inside analyze_frame via the receiver
                    logger.debug(
                        'Unexpected standalone tool_result for request_id=%s', client_event.tool_result.request_id
                    )

        except asyncio.CancelledError:
            logger.info('Session cancelled: uid=%s session=%s', uid, session_id)
        except Exception as e:
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


def _make_tool_sender(context):
    """Create a callback that sends ToolCallRequest to the client stream."""

    async def send_tool_request(tool_request: pb2.ToolCallRequest):
        # In bidi streaming, we yield from the generator — but since the service
        # method is the generator, we return events from analyze_frame instead.
        # This is a no-op; tool requests are yielded inline from analyze_frame.
        pass

    return send_tool_request


def _make_tool_receiver(request_iterator, expected_frame_id):
    """Create a callback that waits for a ToolResult from the client."""

    async def receive_tool_result(request_id: str, timeout_ms: int = 10000) -> pb2.ToolResult:
        # In the bidi stream, the next message from the client should be the ToolResult.
        # This is handled by the task_assistant's analyze_frame loop which reads
        # directly from a queue. For PR1, we use a simple inline approach.
        raise NotImplementedError('Tool result reception is handled inline in analyze_frame')

    return receive_tool_result
