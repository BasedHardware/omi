"""Unit tests for ProactiveAI gRPC session handling.

Tests the SessionReady handshake, context caching, error handling,
and auth verification without hitting external services.
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import grpc
import pytest

from proactive.v1 import proactive_pb2 as pb2
from proactive.auth import extract_uid_from_metadata
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

    async def mock_analyze_frame(*, frame, session_context, frame_id, uid, receive_tool_result):
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
    assert args[0][0] == grpc.StatusCode.UNAUTHENTICATED


# ---------------------------------------------------------------------------
# P1: auth.py extract_uid_from_metadata tests
# ---------------------------------------------------------------------------


def test_auth_extract_uid_success():
    """P1: extract_uid_from_metadata should verify token and return uid."""
    metadata = [('authorization', 'Bearer valid-token')]
    with patch('proactive.auth.auth.verify_id_token', return_value={'uid': 'user-123'}):
        uid = extract_uid_from_metadata(metadata)
    assert uid == 'user-123'


def test_auth_extract_uid_missing_header():
    """P1: Missing Authorization header should raise ValueError."""
    metadata = [('other-header', 'value')]
    with pytest.raises(ValueError, match='Missing or malformed'):
        extract_uid_from_metadata(metadata)


def test_auth_extract_uid_no_bearer():
    """P1: Non-Bearer auth should raise ValueError."""
    metadata = [('authorization', 'Basic abc123')]
    with pytest.raises(ValueError, match='Missing or malformed'):
        extract_uid_from_metadata(metadata)


def test_auth_extract_uid_missing_uid_claim():
    """P1: Token without uid claim should raise ValueError."""
    metadata = [('authorization', 'Bearer valid-token')]
    with patch('proactive.auth.auth.verify_id_token', return_value={'email': 'test@example.com'}):
        with pytest.raises(ValueError, match='Token missing uid'):
            extract_uid_from_metadata(metadata)


# ---------------------------------------------------------------------------
# P6: Session-level bidi tool result routing tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_bidi_tool_result_routing():
    """P6: Session should route tool_result from client to analyze_frame via tool_result_queue."""
    tool_call_request_id = None

    async def mock_analyze_frame(*, frame, session_context, frame_id, uid, receive_tool_result):
        nonlocal tool_call_request_id
        # Yield a ToolCallRequest
        tool_call_request_id = 'req-abc-123'
        yield pb2.ServerEvent(
            tool_call_request=pb2.ToolCallRequest(
                request_id=tool_call_request_id,
                tool_kind=pb2.SEARCH_SIMILAR,
                arguments=pb2.ToolCallArguments(query='test query'),
                deadline_ms=10000,
                frame_id=frame_id,
            )
        )
        # Wait for the tool result from the session
        result = await receive_tool_result(tool_call_request_id, 5000)
        # Yield final outcome using the result
        yield pb2.ServerEvent(
            analysis_outcome=pb2.AnalysisOutcome(
                outcome_kind=pb2.NO_TASK_FOUND,
                context_summary=f'got result for {result.request_id}',
                current_activity='test',
                frame_id=frame_id,
            )
        )

    hello = pb2.ClientEvent(
        client_hello=pb2.ClientHello(
            protocol_version='1.0',
            context_version='v1',
            session_context=pb2.SessionContext(),
        )
    )
    frame = pb2.ClientEvent(frame_event=pb2.FrameEvent(app_name='Safari', frame_number=1, screenshot_id='f1'))
    tool_result = pb2.ClientEvent(
        tool_result=pb2.ToolResult(request_id='req-abc-123', result=pb2.SearchResults(items=[]))
    )

    servicer = ProactiveAIServicer()

    async def request_iter():
        yield hello
        yield frame
        # Wait briefly for the ToolCallRequest to be yielded before sending tool_result
        await asyncio.sleep(0.1)
        yield tool_result
        # Keep stream alive so service can drain the output before detecting disconnect
        await asyncio.sleep(0.5)

    context = MagicMock()
    context.invocation_metadata.return_value = [('authorization', 'Bearer fake')]
    context.abort = AsyncMock()

    with patch('proactive.service.extract_uid_from_metadata', return_value='test-uid'):
        with patch('proactive.service.ServerTaskAssistant') as MockTA:
            MockTA.return_value.analyze_frame = mock_analyze_frame
            results = []
            async for ev in servicer.Session(request_iter(), context):
                results.append(ev)

    # SessionReady + ToolCallRequest + AnalysisOutcome
    assert len(results) == 3
    assert results[0].WhichOneof('event') == 'session_ready'
    assert results[1].WhichOneof('event') == 'tool_call_request'
    assert results[1].tool_call_request.request_id == 'req-abc-123'
    assert results[2].WhichOneof('event') == 'analysis_outcome'
    assert 'req-abc-123' in results[2].analysis_outcome.context_summary


# ---------------------------------------------------------------------------
# P15: Startup guard tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_startup_guard_missing_gemini_key():
    """P15: serve() should raise RuntimeError when GEMINI_API_KEY is missing."""
    from proactive.main import serve

    with patch.dict(os.environ, {'GEMINI_API_KEY': ''}, clear=False):
        with pytest.raises(RuntimeError, match='GEMINI_API_KEY'):
            await serve()


# ---------------------------------------------------------------------------
# P16: Generator error surfacing tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generator_error_surfaces_as_server_error():
    """P16: _run_generator should put ServerError on queue when generator raises."""

    async def failing_generator():
        raise ValueError('something broke')
        yield  # make it an async generator

    output_queue = asyncio.Queue()
    await ProactiveAIServicer._run_generator(failing_generator(), output_queue)

    events = []
    while not output_queue.empty():
        events.append(output_queue.get_nowait())

    # Should have ServerError + None sentinel
    assert len(events) == 2
    assert events[0].WhichOneof('event') == 'server_error'
    assert events[0].server_error.code == 'INTERNAL'
    assert 'ValueError' in events[0].server_error.message
    assert events[0].server_error.retryable is True
    assert events[1] is None


# ---------------------------------------------------------------------------
# Boundary: request_id mismatch in receive_tool_result
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_result_request_id_mismatch_discarded():
    """receive_tool_result should discard mismatched request_ids and wait for correct one."""
    received_result = None

    async def mock_analyze_frame(*, frame, session_context, frame_id, uid, receive_tool_result):
        nonlocal received_result
        yield pb2.ServerEvent(
            tool_call_request=pb2.ToolCallRequest(
                request_id='correct-id',
                tool_kind=pb2.SEARCH_SIMILAR,
                arguments=pb2.ToolCallArguments(query='test'),
                deadline_ms=10000,
                frame_id=frame_id,
            )
        )
        received_result = await receive_tool_result('correct-id', 5000)
        yield pb2.ServerEvent(
            analysis_outcome=pb2.AnalysisOutcome(
                outcome_kind=pb2.NO_TASK_FOUND,
                context_summary='done',
                current_activity='test',
                frame_id=frame_id,
            )
        )

    hello = pb2.ClientEvent(
        client_hello=pb2.ClientHello(protocol_version='1.0', context_version='v1', session_context=pb2.SessionContext())
    )
    frame = pb2.ClientEvent(frame_event=pb2.FrameEvent(app_name='Test', frame_number=1, screenshot_id='f1'))
    wrong_result = pb2.ClientEvent(tool_result=pb2.ToolResult(request_id='wrong-id', result=pb2.SearchResults(items=[])))
    correct_result = pb2.ClientEvent(
        tool_result=pb2.ToolResult(request_id='correct-id', result=pb2.SearchResults(items=[]))
    )

    servicer = ProactiveAIServicer()

    async def request_iter():
        yield hello
        yield frame
        await asyncio.sleep(0.1)
        yield wrong_result
        await asyncio.sleep(0.05)
        yield correct_result
        await asyncio.sleep(0.5)

    context = MagicMock()
    context.invocation_metadata.return_value = [('authorization', 'Bearer fake')]
    context.abort = AsyncMock()

    with patch('proactive.service.extract_uid_from_metadata', return_value='test-uid'):
        with patch('proactive.service.ServerTaskAssistant') as MockTA:
            MockTA.return_value.analyze_frame = mock_analyze_frame
            results = []
            async for ev in servicer.Session(request_iter(), context):
                results.append(ev)

    assert received_result is not None
    assert received_result.request_id == 'correct-id'


# ---------------------------------------------------------------------------
# Boundary: standalone tool_result queue overflow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_standalone_tool_result_queue_overflow():
    """Standalone tool_results beyond queue capacity (4) should be silently dropped."""
    hello = pb2.ClientEvent(
        client_hello=pb2.ClientHello(protocol_version='1.0', context_version='v1', session_context=pb2.SessionContext())
    )
    # Send 6 standalone tool_results (queue maxsize=4)
    tool_results = [
        pb2.ClientEvent(tool_result=pb2.ToolResult(request_id=f'standalone-{i}', result=pb2.SearchResults(items=[])))
        for i in range(6)
    ]

    results = await _run_session([hello] + tool_results)
    # Should get SessionReady and NOT crash — overflow is silently dropped
    assert len(results) >= 1
    assert results[0].WhichOneof('event') == 'session_ready'


# ---------------------------------------------------------------------------
# Boundary: tool_result timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_result_timeout_in_receive():
    """receive_tool_result should raise TimeoutError when no result arrives in time."""
    timed_out = False

    async def mock_analyze_frame(*, frame, session_context, frame_id, uid, receive_tool_result):
        nonlocal timed_out
        yield pb2.ServerEvent(
            tool_call_request=pb2.ToolCallRequest(
                request_id='timeout-test',
                tool_kind=pb2.SEARCH_SIMILAR,
                arguments=pb2.ToolCallArguments(query='test'),
                deadline_ms=100,
                frame_id=frame_id,
            )
        )
        try:
            await receive_tool_result('timeout-test', 100)
        except TimeoutError:
            timed_out = True
        yield pb2.ServerEvent(
            analysis_outcome=pb2.AnalysisOutcome(
                outcome_kind=pb2.NO_TASK_FOUND,
                context_summary='timed out',
                current_activity='test',
                frame_id=frame_id,
            )
        )

    hello = pb2.ClientEvent(
        client_hello=pb2.ClientHello(protocol_version='1.0', context_version='v1', session_context=pb2.SessionContext())
    )
    frame = pb2.ClientEvent(frame_event=pb2.FrameEvent(app_name='Test', frame_number=1, screenshot_id='f1'))

    servicer = ProactiveAIServicer()

    async def request_iter():
        yield hello
        yield frame
        # Don't send any tool result — let it timeout
        await asyncio.sleep(0.5)

    context = MagicMock()
    context.invocation_metadata.return_value = [('authorization', 'Bearer fake')]
    context.abort = AsyncMock()

    with patch('proactive.service.extract_uid_from_metadata', return_value='test-uid'):
        with patch('proactive.service.ServerTaskAssistant') as MockTA:
            MockTA.return_value.analyze_frame = mock_analyze_frame
            results = []
            async for ev in servicer.Session(request_iter(), context):
                results.append(ev)

    assert timed_out


# ---------------------------------------------------------------------------
# Boundary: client disconnect during tool wait
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_heartbeat_during_tool_wait_is_ignored():
    """Heartbeat messages during tool wait should be silently consumed, not crash."""

    async def mock_analyze_frame(*, frame, session_context, frame_id, uid, receive_tool_result):
        yield pb2.ServerEvent(
            tool_call_request=pb2.ToolCallRequest(
                request_id='heartbeat-test',
                tool_kind=pb2.SEARCH_SIMILAR,
                arguments=pb2.ToolCallArguments(query='test'),
                deadline_ms=5000,
                frame_id=frame_id,
            )
        )
        result = await receive_tool_result('heartbeat-test', 5000)
        yield pb2.ServerEvent(
            analysis_outcome=pb2.AnalysisOutcome(
                outcome_kind=pb2.NO_TASK_FOUND,
                context_summary=f'got {result.request_id}',
                current_activity='test',
                frame_id=frame_id,
            )
        )

    hello = pb2.ClientEvent(
        client_hello=pb2.ClientHello(protocol_version='1.0', context_version='v1', session_context=pb2.SessionContext())
    )
    frame = pb2.ClientEvent(frame_event=pb2.FrameEvent(app_name='Test', frame_number=1, screenshot_id='f1'))
    heartbeat = pb2.ClientEvent(heartbeat=pb2.Heartbeat())
    tool_result = pb2.ClientEvent(
        tool_result=pb2.ToolResult(request_id='heartbeat-test', result=pb2.SearchResults(items=[]))
    )

    servicer = ProactiveAIServicer()

    async def request_iter():
        yield hello
        yield frame
        await asyncio.sleep(0.1)
        yield heartbeat  # heartbeat during tool wait should be ignored
        yield tool_result
        await asyncio.sleep(0.5)

    context = MagicMock()
    context.invocation_metadata.return_value = [('authorization', 'Bearer fake')]
    context.abort = AsyncMock()

    with patch('proactive.service.extract_uid_from_metadata', return_value='test-uid'):
        with patch('proactive.service.ServerTaskAssistant') as MockTA:
            MockTA.return_value.analyze_frame = mock_analyze_frame
            results = []
            async for ev in servicer.Session(request_iter(), context):
                results.append(ev)

    assert len(results) == 3
    assert results[0].WhichOneof('event') == 'session_ready'
    assert results[1].WhichOneof('event') == 'tool_call_request'
    assert results[2].WhichOneof('event') == 'analysis_outcome'
