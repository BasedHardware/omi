"""Server-side TaskAssistant: drives Gemini tool loop, delegates search to desktop."""

import base64
import logging
import os
import uuid
from typing import AsyncIterator

import httpx

from proactive.v1 import proactive_pb2 as pb2

logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL = 'gemini-2.0-flash'
GEMINI_API_URL = 'https://generativelanguage.googleapis.com/v1beta/models'
MAX_ITERATIONS = 5

# Tool declarations matching the desktop TaskAssistant's 5 tools
TOOL_DECLARATIONS = [
    {
        'name': 'search_similar',
        'description': 'Search for semantically similar existing tasks using vector similarity.',
        'parameters': {
            'type': 'OBJECT',
            'properties': {
                'query': {'type': 'STRING', 'description': 'Description of the potential task to search for'}
            },
            'required': ['query'],
        },
    },
    {
        'name': 'search_keywords',
        'description': 'Search for tasks using keyword/FTS matching.',
        'parameters': {
            'type': 'OBJECT',
            'properties': {'query': {'type': 'STRING', 'description': 'Keywords to search for in existing tasks'}},
            'required': ['query'],
        },
    },
    {
        'name': 'extract_task',
        'description': 'Extract and save a new task from the screen content.',
        'parameters': {
            'type': 'OBJECT',
            'properties': {
                'title': {'type': 'STRING', 'description': 'Concise task title'},
                'description': {'type': 'STRING', 'description': 'Detailed task description'},
                'priority': {'type': 'STRING', 'enum': ['high', 'medium', 'low']},
                'tags': {'type': 'ARRAY', 'items': {'type': 'STRING'}},
                'source_app': {'type': 'STRING'},
                'inferred_deadline': {'type': 'STRING', 'description': 'ISO date or empty'},
                'confidence': {'type': 'NUMBER'},
                'context_summary': {'type': 'STRING'},
                'current_activity': {'type': 'STRING'},
            },
            'required': ['title', 'context_summary', 'current_activity'],
        },
    },
    {
        'name': 'reject_task',
        'description': 'Reject extracting a task because it already exists or is a duplicate.',
        'parameters': {
            'type': 'OBJECT',
            'properties': {
                'reason': {'type': 'STRING'},
                'context_summary': {'type': 'STRING'},
                'current_activity': {'type': 'STRING'},
            },
            'required': ['reason', 'context_summary', 'current_activity'],
        },
    },
    {
        'name': 'no_task_found',
        'description': 'No actionable task detected on screen.',
        'parameters': {
            'type': 'OBJECT',
            'properties': {
                'context_summary': {'type': 'STRING'},
                'current_activity': {'type': 'STRING'},
            },
            'required': ['context_summary', 'current_activity'],
        },
    },
]


def _build_prompt(session_context: pb2.SessionContext, app_name: str) -> str:
    """Build the Gemini prompt with injected task context, mirroring desktop TaskAssistant."""
    parts = []
    parts.append(
        'You are a task extraction assistant. Analyze the screenshot and determine if there is '
        'an actionable task or request visible. Use the search tools to check for duplicates before extracting.'
    )
    parts.append(f'\nCurrent app: {app_name}')

    if session_context.active_tasks:
        parts.append('\nACTIVE TASKS (do not re-extract these):')
        for i, task in enumerate(session_context.active_tasks):
            score = f' [score={task.relevance_score}]' if task.relevance_score else ''
            parts.append(f'{i + 1}. {task.description}{score}')

    if session_context.completed_tasks:
        parts.append('\nRECENTLY COMPLETED TASKS (user engaged with these):')
        for i, task in enumerate(session_context.completed_tasks):
            parts.append(f'{i + 1}. {task.description}')

    if session_context.deleted_tasks:
        parts.append('\nUSER-DELETED TASKS (do not re-extract similar):')
        for i, task in enumerate(session_context.deleted_tasks):
            parts.append(f'{i + 1}. {task.description}')

    if session_context.goals:
        parts.append('\nACTIVE GOALS:')
        for i, goal in enumerate(session_context.goals):
            parts.append(f'{i + 1}. {goal.title}: {goal.description}')

    parts.append(
        '\nAnalyze this screenshot. If you see a potential request, search for duplicates first. '
        'If there is clearly no request on screen (~90% of screenshots), call no_task_found immediately.'
    )
    return '\n'.join(parts)


async def _call_gemini(contents: list, tools: list) -> dict:
    """Call Gemini generateContent API with function calling support."""
    url = f'{GEMINI_API_URL}/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}'
    body = {
        'contents': contents,
        'tools': [{'function_declarations': tools}],
        'tool_config': {'function_calling_config': {'mode': 'ANY'}},
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=body)
        resp.raise_for_status()
        return resp.json()


def _parse_function_call(response: dict) -> tuple:
    """Extract function call name and arguments from Gemini response.

    Returns (name, arguments_dict) or (None, None) if no function call.
    """
    candidates = response.get('candidates', [])
    if not candidates:
        return None, None
    parts = candidates[0].get('content', {}).get('parts', [])
    for part in parts:
        fc = part.get('functionCall')
        if fc:
            return fc.get('name'), fc.get('args', {})
    return None, None


class ServerTaskAssistant:
    """Server-side task extraction loop that mirrors the desktop TaskAssistant."""

    async def analyze_frame(
        self,
        frame: pb2.FrameEvent,
        session_context: pb2.SessionContext,
        frame_id: str,
        uid: str,
        send_tool_request,
        receive_tool_result,
    ) -> AsyncIterator[pb2.ServerEvent]:
        """Run the Gemini tool loop for one frame.

        Yields ServerEvent messages (ToolCallRequest or AnalysisOutcome).
        When a ToolCallRequest is yielded, the caller must send it to the client
        and feed the ToolResult back by sending it on the bidi stream. The next
        client message after a ToolCallRequest must be a ToolResult.
        """
        prompt = _build_prompt(session_context, frame.app_name)

        # Build initial Gemini contents with image
        image_b64 = base64.b64encode(frame.jpeg_bytes).decode('ascii') if frame.jpeg_bytes else ''
        contents = [
            {
                'role': 'user',
                'parts': [
                    {'text': prompt},
                ],
            }
        ]
        if image_b64:
            contents[0]['parts'].append({'inline_data': {'mime_type': 'image/jpeg', 'data': image_b64}})

        search_count = 0
        for iteration in range(MAX_ITERATIONS):
            try:
                response = await _call_gemini(contents, TOOL_DECLARATIONS)
            except Exception as e:
                logger.error('Gemini call failed: uid=%s frame=%s iter=%d error=%s', uid, frame_id, iteration, e)
                yield pb2.ServerEvent(
                    server_error=pb2.ServerError(
                        code='GEMINI_ERROR',
                        message=f'Gemini API error: {e}',
                        retryable=True,
                        frame_id=frame_id,
                    )
                )
                return

            func_name, func_args = _parse_function_call(response)
            if not func_name:
                logger.warning('No function call in Gemini response: uid=%s frame=%s', uid, frame_id)
                yield pb2.ServerEvent(
                    analysis_outcome=pb2.AnalysisOutcome(
                        outcome_kind=pb2.NO_TASK_FOUND,
                        context_summary='Model returned no function call',
                        current_activity=frame.app_name,
                        frame_id=frame_id,
                    )
                )
                return

            # Terminal decisions (server-side only, no desktop round-trip)
            if func_name == 'no_task_found':
                yield pb2.ServerEvent(
                    analysis_outcome=pb2.AnalysisOutcome(
                        outcome_kind=pb2.NO_TASK_FOUND,
                        context_summary=func_args.get('context_summary', ''),
                        current_activity=func_args.get('current_activity', ''),
                        frame_id=frame_id,
                    )
                )
                return

            if func_name == 'reject_task':
                yield pb2.ServerEvent(
                    analysis_outcome=pb2.AnalysisOutcome(
                        outcome_kind=pb2.REJECT_TASK,
                        reason=func_args.get('reason', ''),
                        context_summary=func_args.get('context_summary', ''),
                        current_activity=func_args.get('current_activity', ''),
                        frame_id=frame_id,
                    )
                )
                return

            if func_name == 'extract_task':
                task = pb2.ExtractedTask(
                    title=func_args.get('title', ''),
                    description=func_args.get('description', ''),
                    priority=_parse_priority(func_args.get('priority', 'medium')),
                    tags=func_args.get('tags', []),
                    source_app=func_args.get('source_app', frame.app_name),
                    inferred_deadline=func_args.get('inferred_deadline', ''),
                    confidence=func_args.get('confidence', 0.0),
                )
                yield pb2.ServerEvent(
                    analysis_outcome=pb2.AnalysisOutcome(
                        outcome_kind=pb2.EXTRACT_TASK,
                        task=task,
                        context_summary=func_args.get('context_summary', ''),
                        current_activity=func_args.get('current_activity', ''),
                        frame_id=frame_id,
                    )
                )
                return

            # Search tools: delegate to desktop via gRPC stream
            if func_name in ('search_similar', 'search_keywords'):
                search_count += 1
                request_id = str(uuid.uuid4())
                tool_kind = pb2.SEARCH_SIMILAR if func_name == 'search_similar' else pb2.SEARCH_KEYWORDS

                # Yield the tool call request — the bidi stream handler sends this to the client
                yield pb2.ServerEvent(
                    tool_call_request=pb2.ToolCallRequest(
                        request_id=request_id,
                        tool_kind=tool_kind,
                        arguments=pb2.ToolCallArguments(query=func_args.get('query', '')),
                        deadline_ms=10000,
                        frame_id=frame_id,
                    )
                )

                # The caller (service.py) will feed the ToolResult back.
                # For now, signal that we need a tool result by setting a sentinel.
                # The actual result handling is done in the service layer.
                self._pending_request_id = request_id
                self._pending_func_name = func_name
                return  # Service layer will resume the loop when tool result arrives

            # Unknown function
            logger.warning('Unknown function call: %s uid=%s', func_name, uid)
            yield pb2.ServerEvent(
                analysis_outcome=pb2.AnalysisOutcome(
                    outcome_kind=pb2.NO_TASK_FOUND,
                    context_summary=f'Unknown function: {func_name}',
                    current_activity=frame.app_name,
                    frame_id=frame_id,
                )
            )
            return

        # Max iterations reached
        logger.warning('Max iterations reached: uid=%s frame=%s', uid, frame_id)
        yield pb2.ServerEvent(
            analysis_outcome=pb2.AnalysisOutcome(
                outcome_kind=pb2.NO_TASK_FOUND,
                context_summary='Max model iterations reached',
                current_activity=frame.app_name,
                frame_id=frame_id,
            )
        )


def _parse_priority(priority_str: str) -> int:
    """Convert priority string to proto enum value."""
    mapping = {
        'high': pb2.PRIORITY_HIGH,
        'medium': pb2.PRIORITY_MEDIUM,
        'low': pb2.PRIORITY_LOW,
    }
    return mapping.get(priority_str.lower(), pb2.PRIORITY_MEDIUM)
