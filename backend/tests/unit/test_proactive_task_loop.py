"""Unit tests for the server-side Gemini tool loop (ServerTaskAssistant).

Tests prompt building, function call parsing, terminal decisions,
and search tool delegation without hitting the Gemini API.
"""

from unittest.mock import AsyncMock, patch

import pytest

from proactive.v1 import proactive_pb2 as pb2
from proactive.task_assistant import ServerTaskAssistant, _build_prompt, _parse_function_call, _parse_priority

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


async def _collect_events(assistant, frame, ctx, **kwargs):
    """Run analyze_frame and collect all yielded events."""
    events = []
    async for ev in assistant.analyze_frame(
        frame=frame,
        session_context=ctx,
        frame_id='test-frame',
        uid='test-uid',
        send_tool_request=AsyncMock(),
        receive_tool_result=AsyncMock(),
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
    """Gemini requesting search_similar should yield a ToolCallRequest to the client."""
    gemini_response = {
        'candidates': [
            {
                'content': {
                    'parts': [
                        {
                            'functionCall': {
                                'name': 'search_similar',
                                'args': {'query': 'review PR'},
                            }
                        }
                    ]
                }
            }
        ]
    }

    assistant = ServerTaskAssistant()
    frame = pb2.FrameEvent(app_name='GitHub', frame_number=1)
    ctx = pb2.SessionContext()

    with patch('proactive.task_assistant._call_gemini', new_callable=AsyncMock, return_value=gemini_response):
        events = await _collect_events(assistant, frame, ctx)

    assert len(events) == 1
    assert events[0].WhichOneof('event') == 'tool_call_request'
    req = events[0].tool_call_request
    assert req.tool_kind == pb2.SEARCH_SIMILAR
    assert req.arguments.query == 'review PR'
    assert req.request_id  # non-empty UUID
    assert req.deadline_ms == 10000


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
