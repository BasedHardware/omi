"""Unit tests for ProactiveAI gRPC session handling.

Tests the SessionReady handshake, context caching, error handling,
and auth verification without hitting external services.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from proactive.v1 import proactive_pb2 as pb2
from proactive.service import ProactiveAIServicer

# ---------------------------------------------------------------------------
# Helper: simulate a bidi stream with a list of ClientEvents
# ---------------------------------------------------------------------------


async def _run_session(events, *, uid='test-uid'):
    """Feed a list of ClientEvent messages through a Session and collect ServerEvents."""
    servicer = ProactiveAIServicer()

    async def request_iter():
        for ev in events:
            yield ev

    context = MagicMock()
    context.invocation_metadata.return_value = [('authorization', f'Bearer fake-token')]
    context.abort = AsyncMock()

    with patch('proactive.service.extract_uid_from_metadata', return_value=uid):
        results = []
        async for server_event in servicer.Session(request_iter(), context):
            results.append(server_event)
    return results


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_client_hello_returns_session_ready():
    """ClientHello should produce a SessionReady with session_id and protocol version."""
    hello = pb2.ClientEvent(
        client_hello=pb2.ClientHello(
            protocol_version='1.0',
            app_version='0.1.0',
            os_version='macOS 15.0',
            context_version='v1',
            session_context=pb2.SessionContext(
                active_tasks=[],
                completed_tasks=[],
                deleted_tasks=[],
                goals=[],
            ),
        )
    )

    results = await _run_session([hello])

    assert len(results) == 1
    event_type = results[0].WhichOneof('event')
    assert event_type == 'session_ready'
    ready = results[0].session_ready
    assert ready.session_id  # non-empty UUID
    assert ready.protocol_version == '1.0'
    assert ready.context_version == 'v1'
    assert ready.max_model_iterations == 5
    assert pb2.SEARCH_SIMILAR in ready.supported_tool_kinds
    assert pb2.SEARCH_KEYWORDS in ready.supported_tool_kinds


@pytest.mark.asyncio
async def test_frame_without_hello_returns_error():
    """A FrameEvent before ClientHello should yield a server error."""
    frame = pb2.ClientEvent(
        frame_event=pb2.FrameEvent(
            app_name='Safari',
            frame_number=1,
            screenshot_id='f1',
        )
    )

    results = await _run_session([frame])

    assert len(results) == 1
    event_type = results[0].WhichOneof('event')
    assert event_type == 'server_error'
    assert results[0].server_error.code == 'NO_CONTEXT'


@pytest.mark.asyncio
async def test_heartbeat_is_silent():
    """Heartbeat messages should not produce any server response."""
    hello = pb2.ClientEvent(
        client_hello=pb2.ClientHello(
            protocol_version='1.0',
            context_version='v1',
            session_context=pb2.SessionContext(),
        )
    )
    heartbeat = pb2.ClientEvent(heartbeat=pb2.Heartbeat())

    results = await _run_session([hello, heartbeat])

    # Only the SessionReady from hello — heartbeat produces nothing
    assert len(results) == 1
    assert results[0].WhichOneof('event') == 'session_ready'


@pytest.mark.asyncio
async def test_context_refresh_on_frame():
    """FrameEvent with a new context_version should update cached context."""
    hello = pb2.ClientEvent(
        client_hello=pb2.ClientHello(
            protocol_version='1.0',
            context_version='v1',
            session_context=pb2.SessionContext(
                active_tasks=[pb2.ActiveTask(task_id=1, description='old task')],
            ),
        )
    )
    frame = pb2.ClientEvent(
        frame_event=pb2.FrameEvent(
            app_name='Slack',
            frame_number=1,
            screenshot_id='f1',
            context_version='v2',
            session_context=pb2.SessionContext(
                active_tasks=[
                    pb2.ActiveTask(task_id=1, description='old task'),
                    pb2.ActiveTask(task_id=2, description='new task'),
                ],
            ),
        )
    )

    # Mock analyze_frame to capture what context was passed
    captured_contexts = []

    async def mock_analyze_frame(*, frame, session_context, frame_id, uid, send_tool_request, receive_tool_result):
        captured_contexts.append(session_context)
        yield pb2.ServerEvent(
            analysis_outcome=pb2.AnalysisOutcome(
                outcome_kind=pb2.NO_TASK_FOUND,
                context_summary='test',
                current_activity='Slack',
                frame_id=frame_id,
            )
        )

    with patch('proactive.service.ServerTaskAssistant') as MockTA:
        MockTA.return_value.analyze_frame = mock_analyze_frame
        results = await _run_session([hello, frame])

    # Should have SessionReady + AnalysisOutcome
    assert len(results) == 2
    # The context passed to analyze_frame should have 2 tasks (the refreshed context)
    assert len(captured_contexts) == 1
    assert len(captured_contexts[0].active_tasks) == 2


@pytest.mark.asyncio
async def test_auth_failure_aborts():
    """Failed auth should call context.abort with UNAUTHENTICATED."""
    servicer = ProactiveAIServicer()

    async def empty_iter():
        return
        yield  # make it an async generator

    context = MagicMock()
    context.invocation_metadata.return_value = [('authorization', 'Bearer bad-token')]
    context.abort = AsyncMock()

    with patch('proactive.service.extract_uid_from_metadata', side_effect=ValueError('bad token')):
        results = []
        async for ev in servicer.Session(empty_iter(), context):
            results.append(ev)

    context.abort.assert_called_once()
    args = context.abort.call_args
    # grpc.StatusCode.UNAUTHENTICATED
    import grpc

    assert args[0][0] == grpc.StatusCode.UNAUTHENTICATED
