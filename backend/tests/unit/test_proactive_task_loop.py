"""Unit tests for the server-side Gemini tool loop (ServerTaskAssistant).

Tests prompt building, function call parsing, terminal decisions,
and search tool delegation without hitting the Gemini API.
"""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from proactive.v1 import proactive_pb2 as pb2
from proactive.task_assistant import (
    GEMINI_API_URL,
    GEMINI_MODEL,
    ServerTaskAssistant,
    _build_prompt,
    _call_gemini,
    _parse_function_call,
    _parse_priority,
    _safe_int,
)

# ---------------------------------------------------------------------------
# _build_prompt tests
# ---------------------------------------------------------------------------


def test_build_prompt_empty_context():
    """Prompt with empty context should still include app name and instructions."""
    ctx = pb2.SessionContext()
    prompt = _build_prompt(ctx, 'Safari')
    assert 'Current app: Safari' in prompt
    assert 'task extraction assistant' in prompt
    assert 'ACTIVE TASKS' not in prompt


def test_build_prompt_with_active_tasks():
    """Active tasks should appear in the prompt."""
    ctx = pb2.SessionContext(
        active_tasks=[
            pb2.ActiveTask(task_id=1, description='Review PR #123', relevance_score=8),
            pb2.ActiveTask(task_id=2, description='Fix bug'),
        ],
    )
    prompt = _build_prompt(ctx, 'VS Code')
    assert 'ACTIVE TASKS' in prompt
    assert 'Review PR #123' in prompt
    assert '[score=8]' in prompt
    assert 'Fix bug' in prompt


def test_build_prompt_with_deleted_tasks():
    """Deleted tasks should appear with 'do not re-extract' warning."""
    ctx = pb2.SessionContext(
        deleted_tasks=[pb2.HistoricalTask(task_id=1, description='Spam task')],
    )
    prompt = _build_prompt(ctx, 'Slack')
    assert 'USER-DELETED TASKS' in prompt
    assert 'do not re-extract similar' in prompt
    assert 'Spam task' in prompt


def test_build_prompt_with_goals():
    """Goals should appear in the prompt."""
    ctx = pb2.SessionContext(
        goals=[pb2.Goal(goal_id='g1', title='Ship v2', description='Release version 2 by EOW')],
    )
    prompt = _build_prompt(ctx, 'Terminal')
    assert 'ACTIVE GOALS' in prompt
    assert 'Ship v2' in prompt


# ---------------------------------------------------------------------------
# _parse_function_call tests
# ---------------------------------------------------------------------------


def test_parse_function_call_with_call():
    """Should extract function name and arguments from a Gemini response."""
    response = {
        'candidates': [
            {
                'content': {
                    'parts': [
                        {
                            'functionCall': {
                                'name': 'no_task_found',
                                'args': {'context_summary': 'just browsing', 'current_activity': 'Safari'},
                            }
                        }
                    ]
                }
            }
        ]
    }
    name, args = _parse_function_call(response)
    assert name == 'no_task_found'
    assert args['context_summary'] == 'just browsing'


def test_parse_function_call_no_candidates():
    """Empty candidates should return (None, None)."""
    name, args = _parse_function_call({'candidates': []})
    assert name is None
    assert args is None


def test_parse_function_call_text_only():
    """Response with only text (no function call) should return (None, None)."""
    response = {'candidates': [{'content': {'parts': [{'text': 'Hello'}]}}]}
    name, args = _parse_function_call(response)
    assert name is None
    assert args is None


# ---------------------------------------------------------------------------
# _parse_priority tests
# ---------------------------------------------------------------------------


def test_parse_priority_values():
    """Priority strings should map to correct proto enum values."""
    assert _parse_priority('high') == pb2.PRIORITY_HIGH
    assert _parse_priority('medium') == pb2.PRIORITY_MEDIUM
    assert _parse_priority('low') == pb2.PRIORITY_LOW
    assert _parse_priority('HIGH') == pb2.PRIORITY_HIGH  # case insensitive
    assert _parse_priority('unknown') == pb2.PRIORITY_MEDIUM  # default


# ---------------------------------------------------------------------------
# ServerTaskAssistant.analyze_frame tests
# ---------------------------------------------------------------------------


async def _collect_events(assistant, frame, ctx, receive_tool_result=None, **kwargs):
    """Run analyze_frame and collect all yielded events."""
    if receive_tool_result is None:
        receive_tool_result = AsyncMock()
    events = []
    async for ev in assistant.analyze_frame(
        frame=frame,
        session_context=ctx,
        frame_id='test-frame',
        uid='test-uid',
        receive_tool_result=receive_tool_result,
        **kwargs,
    ):
        events.append(ev)
    return events


@pytest.mark.asyncio
async def test_no_task_found_terminal():
    """Gemini returning no_task_found should yield a single NO_TASK_FOUND outcome."""
    gemini_response = {
        'candidates': [
            {
                'content': {
                    'parts': [
                        {
                            'functionCall': {
                                'name': 'no_task_found',
                                'args': {'context_summary': 'idle desktop', 'current_activity': 'Finder'},
                            }
                        }
                    ]
                }
            }
        ]
    }

    assistant = ServerTaskAssistant()
    frame = pb2.FrameEvent(app_name='Finder', frame_number=1)
    ctx = pb2.SessionContext()

    with patch('proactive.task_assistant._call_gemini', new_callable=AsyncMock, return_value=gemini_response):
        events = await _collect_events(assistant, frame, ctx)

    assert len(events) == 1
    assert events[0].WhichOneof('event') == 'analysis_outcome'
    assert events[0].analysis_outcome.outcome_kind == pb2.NO_TASK_FOUND
    assert events[0].analysis_outcome.context_summary == 'idle desktop'


@pytest.mark.asyncio
async def test_extract_task_terminal():
    """Gemini returning extract_task should yield an EXTRACT_TASK outcome with task details."""
    gemini_response = {
        'candidates': [
            {
                'content': {
                    'parts': [
                        {
                            'functionCall': {
                                'name': 'extract_task',
                                'args': {
                                    'title': 'Review PR #456',
                                    'description': 'Code review requested in Slack',
                                    'priority': 'high',
                                    'tags': ['code-review', 'slack'],
                                    'source_app': 'Slack',
                                    'confidence': 0.92,
                                    'context_summary': 'Slack message with review request',
                                    'current_activity': 'Slack',
                                },
                            }
                        }
                    ]
                }
            }
        ]
    }

    assistant = ServerTaskAssistant()
    frame = pb2.FrameEvent(app_name='Slack', frame_number=1)
    ctx = pb2.SessionContext()

    with patch('proactive.task_assistant._call_gemini', new_callable=AsyncMock, return_value=gemini_response):
        events = await _collect_events(assistant, frame, ctx)

    assert len(events) == 1
    outcome = events[0].analysis_outcome
    assert outcome.outcome_kind == pb2.EXTRACT_TASK
    assert outcome.task.title == 'Review PR #456'
    assert outcome.task.priority == pb2.PRIORITY_HIGH
    assert outcome.task.confidence == pytest.approx(0.92)
    assert 'code-review' in outcome.task.tags


@pytest.mark.asyncio
async def test_reject_task_terminal():
    """Gemini returning reject_task should yield a REJECT_TASK outcome."""
    gemini_response = {
        'candidates': [
            {
                'content': {
                    'parts': [
                        {
                            'functionCall': {
                                'name': 'reject_task',
                                'args': {
                                    'reason': 'Duplicate of existing task #5',
                                    'context_summary': 'Similar task already tracked',
                                    'current_activity': 'Email',
                                },
                            }
                        }
                    ]
                }
            }
        ]
    }

    assistant = ServerTaskAssistant()
    frame = pb2.FrameEvent(app_name='Email', frame_number=1)
    ctx = pb2.SessionContext()

    with patch('proactive.task_assistant._call_gemini', new_callable=AsyncMock, return_value=gemini_response):
        events = await _collect_events(assistant, frame, ctx)

    assert len(events) == 1
    assert events[0].analysis_outcome.outcome_kind == pb2.REJECT_TASK
    assert events[0].analysis_outcome.reason == 'Duplicate of existing task #5'


@pytest.mark.asyncio
async def test_search_tool_yields_tool_call_request():
    """Gemini requesting search_similar should yield a ToolCallRequest, then await tool result."""
    search_response = {
        'candidates': [
            {'content': {'parts': [{'functionCall': {'name': 'search_similar', 'args': {'query': 'review PR'}}}]}}
        ]
    }
    no_task_response = {
        'candidates': [
            {
                'content': {
                    'parts': [
                        {
                            'functionCall': {
                                'name': 'no_task_found',
                                'args': {'context_summary': 'no match', 'current_activity': 'GitHub'},
                            }
                        }
                    ]
                }
            }
        ]
    }

    mock_gemini = AsyncMock(side_effect=[search_response, no_task_response])
    tool_result = pb2.ToolResult(request_id='test', result=pb2.SearchResults(items=[]))
    mock_receive = AsyncMock(return_value=tool_result)

    assistant = ServerTaskAssistant()
    frame = pb2.FrameEvent(app_name='GitHub', frame_number=1)
    ctx = pb2.SessionContext()

    with patch('proactive.task_assistant._call_gemini', mock_gemini):
        events = await _collect_events(assistant, frame, ctx, receive_tool_result=mock_receive)

    # First event: ToolCallRequest, second: AnalysisOutcome (no_task_found)
    assert len(events) == 2
    assert events[0].WhichOneof('event') == 'tool_call_request'
    req = events[0].tool_call_request
    assert req.tool_kind == pb2.SEARCH_SIMILAR
    assert req.arguments.query == 'review PR'
    assert req.request_id  # non-empty UUID
    assert req.deadline_ms == 10000
    assert events[1].analysis_outcome.outcome_kind == pb2.NO_TASK_FOUND


@pytest.mark.asyncio
async def test_gemini_error_yields_server_error():
    """Gemini API failure should yield a retryable ServerError."""
    assistant = ServerTaskAssistant()
    frame = pb2.FrameEvent(app_name='Safari', frame_number=1)
    ctx = pb2.SessionContext()

    with patch(
        'proactive.task_assistant._call_gemini', new_callable=AsyncMock, side_effect=Exception('connection timeout')
    ):
        events = await _collect_events(assistant, frame, ctx)

    assert len(events) == 1
    assert events[0].WhichOneof('event') == 'server_error'
    assert events[0].server_error.code == 'GEMINI_ERROR'
    assert events[0].server_error.retryable is True


@pytest.mark.asyncio
async def test_no_function_call_yields_no_task():
    """Gemini response with no function call should fallback to NO_TASK_FOUND."""
    gemini_response = {'candidates': [{'content': {'parts': [{'text': 'I see a desktop'}]}}]}

    assistant = ServerTaskAssistant()
    frame = pb2.FrameEvent(app_name='Desktop', frame_number=1)
    ctx = pb2.SessionContext()

    with patch('proactive.task_assistant._call_gemini', new_callable=AsyncMock, return_value=gemini_response):
        events = await _collect_events(assistant, frame, ctx)

    assert len(events) == 1
    assert events[0].analysis_outcome.outcome_kind == pb2.NO_TASK_FOUND


# ---------------------------------------------------------------------------
# Tool result continuation loop tests (Issue 2 fix)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_then_extract_full_loop():
    """search_similar → ToolResult → extract_task: full bidi loop."""
    search_response = {
        'candidates': [
            {'content': {'parts': [{'functionCall': {'name': 'search_similar', 'args': {'query': 'deploy v2'}}}]}}
        ]
    }
    extract_response = {
        'candidates': [
            {
                'content': {
                    'parts': [
                        {
                            'functionCall': {
                                'name': 'extract_task',
                                'args': {
                                    'title': 'Deploy v2 to staging',
                                    'description': 'Deploy new version',
                                    'priority': 'high',
                                    'source_category': 'devops',
                                    'source_subcategory': 'deployment',
                                    'relevance_score': 85,
                                    'context_summary': 'Slack deploy request',
                                    'current_activity': 'Slack',
                                },
                            }
                        }
                    ]
                }
            }
        ]
    }

    # Mock: first call returns search, second returns extract
    mock_gemini = AsyncMock(side_effect=[search_response, extract_response])

    # Mock tool result from desktop
    tool_result = pb2.ToolResult(
        request_id='will-be-overwritten',
        result=pb2.SearchResults(items=[]),
    )
    mock_receive = AsyncMock(return_value=tool_result)

    assistant = ServerTaskAssistant()
    frame = pb2.FrameEvent(app_name='Slack', frame_number=1)
    ctx = pb2.SessionContext()

    with patch('proactive.task_assistant._call_gemini', mock_gemini):
        events = await _collect_events(assistant, frame, ctx, receive_tool_result=mock_receive)

    # Should yield ToolCallRequest then AnalysisOutcome
    assert len(events) == 2
    assert events[0].WhichOneof('event') == 'tool_call_request'
    assert events[0].tool_call_request.tool_kind == pb2.SEARCH_SIMILAR
    assert events[1].WhichOneof('event') == 'analysis_outcome'
    assert events[1].analysis_outcome.outcome_kind == pb2.EXTRACT_TASK
    assert events[1].analysis_outcome.task.title == 'Deploy v2 to staging'

    # Verify receive_tool_result was called
    mock_receive.assert_called_once()
    # Verify Gemini was called twice (search + extract)
    assert mock_gemini.call_count == 2


@pytest.mark.asyncio
async def test_search_then_reject_full_loop():
    """search_keywords → ToolResult (match found) → reject_task."""
    search_response = {
        'candidates': [
            {'content': {'parts': [{'functionCall': {'name': 'search_keywords', 'args': {'query': 'deploy'}}}]}}
        ]
    }
    reject_response = {
        'candidates': [
            {
                'content': {
                    'parts': [
                        {
                            'functionCall': {
                                'name': 'reject_task',
                                'args': {
                                    'reason': 'Duplicate: deploy task already exists',
                                    'context_summary': 'Found existing deploy task',
                                    'current_activity': 'Slack',
                                },
                            }
                        }
                    ]
                }
            }
        ]
    }

    mock_gemini = AsyncMock(side_effect=[search_response, reject_response])
    tool_result = pb2.ToolResult(
        request_id='test',
        result=pb2.SearchResults(
            items=[
                pb2.SearchResult(
                    task_id=42,
                    description='Deploy v2 to staging',
                    status=pb2.TASK_STATUS_ACTIVE,
                    similarity=0.95,
                    match_type=pb2.MATCH_TYPE_FTS,
                )
            ]
        ),
    )
    mock_receive = AsyncMock(return_value=tool_result)

    assistant = ServerTaskAssistant()
    frame = pb2.FrameEvent(app_name='Slack', frame_number=1)
    ctx = pb2.SessionContext()

    with patch('proactive.task_assistant._call_gemini', mock_gemini):
        events = await _collect_events(assistant, frame, ctx, receive_tool_result=mock_receive)

    assert len(events) == 2
    assert events[0].WhichOneof('event') == 'tool_call_request'
    assert events[1].analysis_outcome.outcome_kind == pb2.REJECT_TASK
    assert 'Duplicate' in events[1].analysis_outcome.reason


@pytest.mark.asyncio
async def test_tool_result_timeout_yields_no_task():
    """If desktop doesn't respond to search, yield NO_TASK_FOUND."""
    search_response = {
        'candidates': [
            {'content': {'parts': [{'functionCall': {'name': 'search_similar', 'args': {'query': 'test'}}}]}}
        ]
    }

    mock_gemini = AsyncMock(return_value=search_response)
    mock_receive = AsyncMock(side_effect=TimeoutError('timeout'))

    assistant = ServerTaskAssistant()
    frame = pb2.FrameEvent(app_name='Safari', frame_number=1)
    ctx = pb2.SessionContext()

    with patch('proactive.task_assistant._call_gemini', mock_gemini):
        events = await _collect_events(assistant, frame, ctx, receive_tool_result=mock_receive)

    assert len(events) == 2
    assert events[0].WhichOneof('event') == 'tool_call_request'
    assert events[1].analysis_outcome.outcome_kind == pb2.NO_TASK_FOUND
    assert 'timed out' in events[1].analysis_outcome.context_summary


# ---------------------------------------------------------------------------
# ExtractedTask schema parity tests (Issue 3 fix)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_task_includes_source_category_and_relevance():
    """ExtractedTask must populate source_category, source_subcategory, relevance_score."""
    gemini_response = {
        'candidates': [
            {
                'content': {
                    'parts': [
                        {
                            'functionCall': {
                                'name': 'extract_task',
                                'args': {
                                    'title': 'Review design doc',
                                    'description': 'Review Q3 design document',
                                    'priority': 'medium',
                                    'source_app': 'Google Docs',
                                    'source_category': 'documentation',
                                    'source_subcategory': 'design-review',
                                    'relevance_score': 72,
                                    'confidence': 0.88,
                                    'context_summary': 'Google Docs with design doc',
                                    'current_activity': 'Google Docs',
                                },
                            }
                        }
                    ]
                }
            }
        ]
    }

    assistant = ServerTaskAssistant()
    frame = pb2.FrameEvent(app_name='Google Docs', frame_number=1)
    ctx = pb2.SessionContext()

    with patch('proactive.task_assistant._call_gemini', new_callable=AsyncMock, return_value=gemini_response):
        events = await _collect_events(assistant, frame, ctx)

    assert len(events) == 1
    task = events[0].analysis_outcome.task
    assert task.source_category == 'documentation'
    assert task.source_subcategory == 'design-review'
    assert task.relevance_score == 72


# ---------------------------------------------------------------------------
# Error sanitization test (Issue 1 fix)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gemini_error_does_not_leak_api_key():
    """Error messages sent to client must not contain the API key."""
    assistant = ServerTaskAssistant()
    frame = pb2.FrameEvent(app_name='Safari', frame_number=1)
    ctx = pb2.SessionContext()

    # Simulate an httpx error that includes the URL (with API key)
    error = httpx.HTTPStatusError(
        'Client error',
        request=httpx.Request('POST', 'https://api.example.com?key=SECRET_KEY_123'),
        response=httpx.Response(400),
    )

    with patch('proactive.task_assistant._call_gemini', new_callable=AsyncMock, side_effect=error):
        events = await _collect_events(assistant, frame, ctx)

    assert len(events) == 1
    error_msg = events[0].server_error.message
    assert 'SECRET_KEY_123' not in error_msg
    assert 'HTTPStatusError' in error_msg


# ---------------------------------------------------------------------------
# _safe_int tests
# ---------------------------------------------------------------------------


def test_safe_int_valid():
    """Valid int values should convert normally."""
    assert _safe_int(42) == 42
    assert _safe_int('85') == 85
    assert _safe_int(0) == 0


def test_safe_int_invalid():
    """Invalid values should return the default."""
    assert _safe_int('not-an-int') == 0
    assert _safe_int('not-an-int', default=50) == 50
    assert _safe_int(None) == 0
    assert _safe_int(None, default=-1) == -1


# ---------------------------------------------------------------------------
# extract_task with bad relevance_score (robustness)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_extract_task_with_bad_relevance_score():
    """Model returning non-integer relevance_score should still produce a valid ExtractedTask."""
    gemini_response = {
        'candidates': [
            {
                'content': {
                    'parts': [
                        {
                            'functionCall': {
                                'name': 'extract_task',
                                'args': {
                                    'title': 'Test task',
                                    'description': 'A test',
                                    'priority': 'low',
                                    'confidence': 0.5,
                                    'relevance_score': 'not-a-number',
                                    'context_summary': 'test',
                                    'current_activity': 'Safari',
                                },
                            }
                        }
                    ]
                }
            }
        ]
    }

    assistant = ServerTaskAssistant()
    frame = pb2.FrameEvent(app_name='Safari', frame_number=1)
    ctx = pb2.SessionContext()

    with patch('proactive.task_assistant._call_gemini', new_callable=AsyncMock, return_value=gemini_response):
        events = await _collect_events(assistant, frame, ctx)

    assert len(events) == 1
    assert events[0].analysis_outcome.outcome_kind == pb2.EXTRACT_TASK
    assert events[0].analysis_outcome.task.relevance_score == 0  # safe default


# ---------------------------------------------------------------------------
# P5: _call_gemini request construction tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_gemini_uses_header_not_query_param():
    """P5: _call_gemini should send API key in x-goog-api-key header, not URL query."""
    captured_requests = []

    async def mock_post(url, json=None, headers=None):
        captured_requests.append({'url': url, 'headers': headers, 'json': json})
        mock_resp = httpx.Response(200, json={'candidates': []})
        mock_resp._request = httpx.Request('POST', url)
        return mock_resp

    with patch('proactive.task_assistant.GEMINI_API_KEY', 'test-key-abc'):
        with patch('httpx.AsyncClient') as MockClient:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client

            await _call_gemini([{'role': 'user', 'parts': [{'text': 'test'}]}], [])

    assert len(captured_requests) == 1
    req = captured_requests[0]
    # URL should NOT contain the API key
    assert 'test-key-abc' not in req['url']
    assert 'key=' not in req['url']
    # URL should be the expected endpoint
    assert f'{GEMINI_API_URL}/{GEMINI_MODEL}:generateContent' == req['url']
    # Header should contain the API key
    assert req['headers']['x-goog-api-key'] == 'test-key-abc'


# ---------------------------------------------------------------------------
# Boundary: unknown function call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_function_yields_no_task():
    """An unknown function name from Gemini should yield NO_TASK_FOUND."""
    gemini_response = {
        'candidates': [
            {
                'content': {
                    'parts': [{'functionCall': {'name': 'unknown_function', 'args': {'query': 'test'}}}]
                }
            }
        ]
    }

    ta = ServerTaskAssistant()
    frame = pb2.FrameEvent(app_name='Safari', frame_number=1, screenshot_id='f1')
    ctx = pb2.SessionContext()

    with patch('proactive.task_assistant.GEMINI_API_KEY', 'test-key'):
        with patch('proactive.task_assistant._call_gemini', new_callable=AsyncMock, return_value=gemini_response):
            events = []
            async for ev in ta.analyze_frame(
                frame=frame,
                session_context=ctx,
                frame_id='f1',
                uid='test-uid',
                receive_tool_result=AsyncMock(),
            ):
                events.append(ev)

    assert len(events) == 1
    assert events[0].analysis_outcome.outcome_kind == pb2.NO_TASK_FOUND
    assert 'Unknown function' in events[0].analysis_outcome.context_summary


# ---------------------------------------------------------------------------
# Boundary: max iterations exhaustion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_iterations_yields_no_task():
    """When Gemini keeps requesting tools past MAX_ITERATIONS, should yield NO_TASK_FOUND."""
    # Each Gemini response requests a search — will hit the max iteration cap
    search_response = {
        'candidates': [
            {
                'content': {
                    'parts': [{'functionCall': {'name': 'search_similar', 'args': {'query': 'test'}}}]
                }
            }
        ]
    }

    call_count = 0

    async def fake_call_gemini(contents, tools):
        nonlocal call_count
        call_count += 1
        return search_response

    async def fake_receive_tool_result(request_id, timeout_ms=10000):
        return pb2.ToolResult(request_id=request_id, result=pb2.SearchResults(items=[]))

    ta = ServerTaskAssistant()
    frame = pb2.FrameEvent(app_name='Safari', frame_number=1, screenshot_id='f1')
    ctx = pb2.SessionContext()

    with patch('proactive.task_assistant.GEMINI_API_KEY', 'test-key'):
        with patch('proactive.task_assistant._call_gemini', side_effect=fake_call_gemini):
            events = []
            async for ev in ta.analyze_frame(
                frame=frame,
                session_context=ctx,
                frame_id='f1',
                uid='test-uid',
                receive_tool_result=fake_receive_tool_result,
            ):
                events.append(ev)

    # Should have tool_call_requests + final NO_TASK_FOUND
    final = events[-1]
    assert final.analysis_outcome.outcome_kind == pb2.NO_TASK_FOUND
    assert 'Max model iterations' in final.analysis_outcome.context_summary
    # Gemini was called MAX_ITERATIONS times (5)
    assert call_count == 5
