"""Unit tests for ProactiveAI WebSocket session handling.

Tests the SessionReady handshake, context caching, error handling,
and tool result routing without hitting external services.
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from routers.proactive import handle_proactive_session, _run_generator

# ---------------------------------------------------------------------------
# Helper: simulate a session with a list of client messages (dicts)
# ---------------------------------------------------------------------------


async def _run_session(messages, *, uid='test-uid'):
    """Feed a list of dict messages through handle_proactive_session and collect sent events."""
    sent_events = []
    msg_index = 0

    async def send_event(event):
        sent_events.append(event)

    async def receive_message():
        nonlocal msg_index
        if msg_index < len(messages):
            msg = messages[msg_index]
            msg_index += 1
            return msg
        # Stay "connected" briefly so the generator can finish processing
        # before _pump_client queues _STREAM_END.
        await asyncio.sleep(0.2)
        raise Exception('client disconnected')

    await handle_proactive_session(send_event, receive_message, uid)
    return sent_events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_client_hello_returns_session_ready():
    """ClientHello should produce a SessionReady with session_id and protocol version."""
    hello = {
        'type': 'client_hello',
        'protocol_version': '1.0',
        'app_version': '0.1.0',
        'os_version': 'macOS 15.0',
        'context_version': 'v1',
        'session_context': {
            'active_tasks': [],
            'completed_tasks': [],
            'deleted_tasks': [],
            'goals': [],
        },
    }

    results = await _run_session([hello])

    assert len(results) == 1
    assert results[0]['type'] == 'session_ready'
    assert results[0]['session_id']  # non-empty UUID
    assert results[0]['protocol_version'] == '1.0'
    assert results[0]['context_version'] == 'v1'
    assert results[0]['max_model_iterations'] == 5
    assert 'search_similar' in results[0]['supported_tool_kinds']
    assert 'search_keywords' in results[0]['supported_tool_kinds']


@pytest.mark.asyncio
async def test_frame_without_hello_returns_error():
    """A frame_event before client_hello should yield a server error."""
    frame = {
        'type': 'frame_event',
        'app_name': 'Safari',
        'frame_number': 1,
        'screenshot_id': 'f1',
    }

    results = await _run_session([frame])

    assert len(results) == 1
    assert results[0]['type'] == 'server_error'
    assert results[0]['code'] == 'NO_CONTEXT'


@pytest.mark.asyncio
async def test_heartbeat_is_silent():
    """Heartbeat messages should not produce any server response."""
    hello = {
        'type': 'client_hello',
        'protocol_version': '1.0',
        'context_version': 'v1',
        'session_context': {},
    }
    heartbeat = {'type': 'heartbeat'}

    results = await _run_session([hello, heartbeat])

    # Only the SessionReady from hello -- heartbeat produces nothing
    assert len(results) == 1
    assert results[0]['type'] == 'session_ready'


@pytest.mark.asyncio
async def test_context_refresh_on_frame():
    """frame_event with a new context_version should update cached context."""
    hello = {
        'type': 'client_hello',
        'protocol_version': '1.0',
        'context_version': 'v1',
        'session_context': {
            'active_tasks': [{'task_id': 1, 'description': 'old task'}],
        },
    }
    frame = {
        'type': 'frame_event',
        'app_name': 'Slack',
        'frame_number': 1,
        'screenshot_id': 'f1',
        'context_version': 'v2',
        'session_context': {
            'active_tasks': [
                {'task_id': 1, 'description': 'old task'},
                {'task_id': 2, 'description': 'new task'},
            ],
        },
    }

    # Mock analyze_frame to capture what context was passed
    captured_contexts = []

    async def mock_analyze_frame(*, frame, session_context, frame_id, uid, receive_tool_result):
        captured_contexts.append(session_context)
        yield {
            'type': 'analysis_outcome',
            'outcome_kind': 'no_task_found',
            'context_summary': 'test',
            'current_activity': 'Slack',
            'frame_id': frame_id,
        }

    with patch('routers.proactive.ServerTaskAssistant') as MockTA:
        MockTA.return_value.analyze_frame = mock_analyze_frame
        results = await _run_session([hello, frame])

    # Should have SessionReady + AnalysisOutcome
    assert len(results) == 2
    # The context passed to analyze_frame should have 2 tasks (the refreshed context)
    assert len(captured_contexts) == 1
    assert len(captured_contexts[0]['active_tasks']) == 2


# ---------------------------------------------------------------------------
# P6: Session-level bidi tool result routing tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_bidi_tool_result_routing():
    """Session should route tool_result from client to analyze_frame via tool_result_queue.

    Messages are pre-loaded: _pump_client reads them eagerly and puts them on
    client_queue. The inner bidi loop picks up the tool_result from client_queue
    when it enters the awaiting_tool_result branch.
    """

    async def mock_analyze_frame(*, frame, session_context, frame_id, uid, receive_tool_result):
        yield {
            'type': 'tool_call_request',
            'request_id': 'req-abc-123',
            'tool_kind': 'search_similar',
            'query': 'test query',
            'deadline_ms': 10000,
            'frame_id': frame_id,
        }
        result = await receive_tool_result('req-abc-123', 5000)
        yield {
            'type': 'analysis_outcome',
            'outcome_kind': 'no_task_found',
            'context_summary': f'got result for {result.get("request_id")}',
            'current_activity': 'test',
            'frame_id': frame_id,
        }

    hello = {'type': 'client_hello', 'protocol_version': '1.0', 'context_version': 'v1', 'session_context': {}}
    frame = {'type': 'frame_event', 'app_name': 'Safari', 'frame_number': 1, 'screenshot_id': 'f1'}
    tool_result = {'type': 'tool_result', 'request_id': 'req-abc-123', 'results': []}

    with patch('routers.proactive.ServerTaskAssistant') as MockTA:
        MockTA.return_value.analyze_frame = mock_analyze_frame
        results = await _run_session([hello, frame, tool_result])

    # SessionReady + ToolCallRequest + AnalysisOutcome
    assert len(results) == 3
    assert results[0]['type'] == 'session_ready'
    assert results[1]['type'] == 'tool_call_request'
    assert results[1]['request_id'] == 'req-abc-123'
    assert results[2]['type'] == 'analysis_outcome'
    assert 'req-abc-123' in results[2]['context_summary']


# ---------------------------------------------------------------------------
# P16: Generator error surfacing tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generator_error_surfaces_as_server_error():
    """_run_generator should put server_error on queue when generator raises."""

    async def failing_generator():
        raise ValueError('something broke')
        yield  # make it an async generator

    output_queue = asyncio.Queue()
    await _run_generator(failing_generator(), output_queue)

    events = []
    while not output_queue.empty():
        events.append(output_queue.get_nowait())

    # Should have server_error + None sentinel
    assert len(events) == 2
    assert events[0]['type'] == 'server_error'
    assert events[0]['code'] == 'INTERNAL'
    assert 'ValueError' in events[0]['message']
    assert events[0]['retryable'] is True
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
        yield {
            'type': 'tool_call_request',
            'request_id': 'correct-id',
            'tool_kind': 'search_similar',
            'query': 'test',
            'deadline_ms': 10000,
            'frame_id': frame_id,
        }
        received_result = await receive_tool_result('correct-id', 5000)
        yield {
            'type': 'analysis_outcome',
            'outcome_kind': 'no_task_found',
            'context_summary': 'done',
            'current_activity': 'test',
            'frame_id': frame_id,
        }

    hello = {'type': 'client_hello', 'protocol_version': '1.0', 'context_version': 'v1', 'session_context': {}}
    frame = {'type': 'frame_event', 'app_name': 'Test', 'frame_number': 1, 'screenshot_id': 'f1'}
    wrong_result = {'type': 'tool_result', 'request_id': 'wrong-id', 'results': []}
    correct_result = {'type': 'tool_result', 'request_id': 'correct-id', 'results': []}

    with patch('routers.proactive.ServerTaskAssistant') as MockTA:
        MockTA.return_value.analyze_frame = mock_analyze_frame
        results = await _run_session([hello, frame, wrong_result, correct_result])

    assert received_result is not None
    assert received_result.get('request_id') == 'correct-id'


# ---------------------------------------------------------------------------
# Boundary: standalone tool_result queue overflow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_standalone_tool_result_queue_overflow():
    """Standalone tool_results beyond queue capacity (4) should be silently dropped."""
    hello = {'type': 'client_hello', 'protocol_version': '1.0', 'context_version': 'v1', 'session_context': {}}
    # Send 6 standalone tool_results (queue maxsize=4)
    tool_results = [{'type': 'tool_result', 'request_id': f'standalone-{i}', 'results': []} for i in range(6)]

    results = await _run_session([hello] + tool_results)
    # Should get SessionReady and NOT crash -- overflow is silently dropped
    assert len(results) >= 1
    assert results[0]['type'] == 'session_ready'


# ---------------------------------------------------------------------------
# Boundary: tool_result timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_result_timeout_in_receive():
    """receive_tool_result should raise TimeoutError when no result arrives in time."""
    timed_out = False

    async def mock_analyze_frame(*, frame, session_context, frame_id, uid, receive_tool_result):
        nonlocal timed_out
        yield {
            'type': 'tool_call_request',
            'request_id': 'timeout-test',
            'tool_kind': 'search_similar',
            'query': 'test',
            'deadline_ms': 100,
            'frame_id': frame_id,
        }
        try:
            await receive_tool_result('timeout-test', 100)
        except TimeoutError:
            timed_out = True
        yield {
            'type': 'analysis_outcome',
            'outcome_kind': 'no_task_found',
            'context_summary': 'timed out',
            'current_activity': 'test',
            'frame_id': frame_id,
        }

    hello = {'type': 'client_hello', 'protocol_version': '1.0', 'context_version': 'v1', 'session_context': {}}
    frame = {'type': 'frame_event', 'app_name': 'Test', 'frame_number': 1, 'screenshot_id': 'f1'}

    # Don't send any tool_result -- let it timeout
    with patch('routers.proactive.ServerTaskAssistant') as MockTA:
        MockTA.return_value.analyze_frame = mock_analyze_frame
        results = await _run_session([hello, frame])

    assert timed_out


# ---------------------------------------------------------------------------
# Boundary: heartbeat during tool wait
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_heartbeat_during_tool_wait_is_ignored():
    """Heartbeat messages during tool wait should be silently consumed, not crash."""

    async def mock_analyze_frame(*, frame, session_context, frame_id, uid, receive_tool_result):
        yield {
            'type': 'tool_call_request',
            'request_id': 'heartbeat-test',
            'tool_kind': 'search_similar',
            'query': 'test',
            'deadline_ms': 5000,
            'frame_id': frame_id,
        }
        result = await receive_tool_result('heartbeat-test', 5000)
        yield {
            'type': 'analysis_outcome',
            'outcome_kind': 'no_task_found',
            'context_summary': f'got {result.get("request_id")}',
            'current_activity': 'test',
            'frame_id': frame_id,
        }

    hello = {'type': 'client_hello', 'protocol_version': '1.0', 'context_version': 'v1', 'session_context': {}}
    frame = {'type': 'frame_event', 'app_name': 'Test', 'frame_number': 1, 'screenshot_id': 'f1'}
    heartbeat = {'type': 'heartbeat'}
    tool_result = {'type': 'tool_result', 'request_id': 'heartbeat-test', 'results': []}

    # heartbeat arrives before tool_result -- should be ignored in the bidi wait branch
    with patch('routers.proactive.ServerTaskAssistant') as MockTA:
        MockTA.return_value.analyze_frame = mock_analyze_frame
        results = await _run_session([hello, frame, heartbeat, tool_result])

    assert len(results) == 3
    assert results[0]['type'] == 'session_ready'
    assert results[1]['type'] == 'tool_call_request'
    assert results[2]['type'] == 'analysis_outcome'


# ---------------------------------------------------------------------------
# Boundary: 30s bidi wait timeout (both output and client read stall)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bidi_wait_timeout_cancels_generator():
    """When both output_queue and client_queue stall past _BIDI_WAIT_TIMEOUT_S, generator is cancelled."""

    async def mock_analyze_frame(*, frame, session_context, frame_id, uid, receive_tool_result):
        yield {
            'type': 'tool_call_request',
            'request_id': 'stall-test',
            'tool_kind': 'search_similar',
            'query': 'test',
            'deadline_ms': 60000,
            'frame_id': frame_id,
        }
        # Block forever — will be cancelled by the bidi wait timeout
        await receive_tool_result('stall-test', 60000)
        yield {
            'type': 'analysis_outcome',
            'outcome_kind': 'no_task_found',
            'context_summary': 'should not reach',
            'current_activity': 'test',
            'frame_id': frame_id,
        }

    hello = {'type': 'client_hello', 'protocol_version': '1.0', 'context_version': 'v1', 'session_context': {}}
    frame = {'type': 'frame_event', 'app_name': 'Test', 'frame_number': 1, 'screenshot_id': 'f1'}

    # Patch _BIDI_WAIT_TIMEOUT_S to 0.05s and keep client alive (10s sleep)
    # so we hit the timeout path, not the _STREAM_END path.
    sent_events = []
    msg_index = 0
    messages = [hello, frame]

    async def send_event(event):
        sent_events.append(event)

    async def receive_message():
        nonlocal msg_index
        if msg_index < len(messages):
            msg = messages[msg_index]
            msg_index += 1
            return msg
        # Stay "connected" long enough for timeout to fire
        await asyncio.sleep(10)
        raise Exception('client disconnected')

    with patch('routers.proactive.ServerTaskAssistant') as MockTA:
        MockTA.return_value.analyze_frame = mock_analyze_frame
        with patch('routers.proactive._BIDI_WAIT_TIMEOUT_S', 0.05):
            await asyncio.wait_for(
                handle_proactive_session(send_event, receive_message, 'test-uid'),
                timeout=5.0,
            )

    assert sent_events[0]['type'] == 'session_ready'
    assert sent_events[1]['type'] == 'tool_call_request'
    # analysis_outcome is never reached — generator cancelled by bidi timeout
    assert len(sent_events) == 2


# ---------------------------------------------------------------------------
# Boundary: _ANALYSIS_TIMEOUT_S (non-bidi path)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analysis_timeout_cancels_generator():
    """When generator produces no event within _ANALYSIS_TIMEOUT_S, session cancels cleanly."""

    async def mock_analyze_frame(*, frame, session_context, frame_id, uid, receive_tool_result):
        # Block forever — never yield anything
        await asyncio.Event().wait()
        yield {}  # make it an async generator

    hello = {'type': 'client_hello', 'protocol_version': '1.0', 'context_version': 'v1', 'session_context': {}}
    frame = {'type': 'frame_event', 'app_name': 'Test', 'frame_number': 1, 'screenshot_id': 'f1'}

    sent_events = []
    msg_index = 0
    messages = [hello, frame]

    async def send_event(event):
        sent_events.append(event)

    async def receive_message():
        nonlocal msg_index
        if msg_index < len(messages):
            msg = messages[msg_index]
            msg_index += 1
            return msg
        await asyncio.sleep(10)
        raise Exception('client disconnected')

    with patch('routers.proactive.ServerTaskAssistant') as MockTA:
        MockTA.return_value.analyze_frame = mock_analyze_frame
        with patch('routers.proactive._ANALYSIS_TIMEOUT_S', 0.05):
            await asyncio.wait_for(
                handle_proactive_session(send_event, receive_message, 'test-uid'),
                timeout=5.0,
            )

    # Should get SessionReady only — generator never yielded
    assert len(sent_events) == 1
    assert sent_events[0]['type'] == 'session_ready'


# ---------------------------------------------------------------------------
# Boundary: standalone tool_result queue retains first 4, drops rest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_standalone_tool_result_queue_retains_first_four():
    """tool_result_queue(maxsize=4): first 4 retained, 5th+ dropped via QueueFull."""
    queue = asyncio.Queue(maxsize=4)

    # Simulate the router's standalone tool_result handling (put_nowait + catch QueueFull)
    for i in range(6):
        try:
            queue.put_nowait({'request_id': f'r-{i}', 'results': []})
        except asyncio.QueueFull:
            pass

    assert queue.qsize() == 4
    retained_ids = [queue.get_nowait()['request_id'] for _ in range(4)]
    assert retained_ids == ['r-0', 'r-1', 'r-2', 'r-3']
    assert queue.empty()
