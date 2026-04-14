"""Server-side TaskAssistant: drives Gemini tool loop, delegates search to desktop.

All messages are plain dicts — no protobuf dependency. The WebSocket router
serializes these dicts to JSON for the wire.
"""

import base64
import logging
import os
import uuid
from typing import AsyncIterator, Callable, Awaitable

import httpx

logger = logging.getLogger(__name__)


def _sanitize_uid(uid: str) -> str:
    """Truncate UID for log safety — show first 8 chars only."""
    return uid[:8] + '...' if len(uid) > 8 else uid


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
                'source_category': {'type': 'STRING', 'description': 'Origin category (e.g. communication, code)'},
                'source_subcategory': {'type': 'STRING', 'description': 'Origin subcategory'},
                'relevance_score': {'type': 'INTEGER', 'description': '0-100 relevance ranking'},
                'context_summary': {'type': 'STRING'},
                'current_activity': {'type': 'STRING'},
            },
            'required': [
                'title',
                'description',
                'priority',
                'tags',
                'source_app',
                'inferred_deadline',
                'confidence',
                'context_summary',
                'current_activity',
                'source_category',
                'source_subcategory',
                'relevance_score',
            ],
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


def _build_prompt(session_context: dict, app_name: str) -> str:
    """Build the Gemini prompt with injected task context, mirroring desktop TaskAssistant."""
    parts = []
    parts.append(
        'You are a task extraction assistant. Analyze the screenshot and determine if there is '
        'an actionable task or request visible. Use the search tools to check for duplicates before extracting.'
    )
    parts.append(f'\nCurrent app: {app_name}')

    active_tasks = session_context.get('active_tasks', [])
    if active_tasks:
        parts.append('\nACTIVE TASKS (do not re-extract these):')
        for i, task in enumerate(active_tasks):
            score = f' [score={task.get("relevance_score", "")}]' if task.get('relevance_score') else ''
            parts.append(f'{i + 1}. {task.get("description", "")}{score}')

    completed_tasks = session_context.get('completed_tasks', [])
    if completed_tasks:
        parts.append('\nRECENTLY COMPLETED TASKS (user engaged with these):')
        for i, task in enumerate(completed_tasks):
            parts.append(f'{i + 1}. {task.get("description", "")}')

    deleted_tasks = session_context.get('deleted_tasks', [])
    if deleted_tasks:
        parts.append('\nUSER-DELETED TASKS (do not re-extract similar):')
        for i, task in enumerate(deleted_tasks):
            parts.append(f'{i + 1}. {task.get("description", "")}')

    goals = session_context.get('goals', [])
    if goals:
        parts.append('\nACTIVE GOALS:')
        for i, goal in enumerate(goals):
            parts.append(f'{i + 1}. {goal.get("title", "")}: {goal.get("description", "")}')

    parts.append(
        '\nAnalyze this screenshot. If you see a potential request, search for duplicates first. '
        'If there is clearly no request on screen (~90% of screenshots), call no_task_found immediately.'
    )
    return '\n'.join(parts)


async def _call_gemini(contents: list, tools: list) -> dict:
    """Call Gemini generateContent API with function calling support."""
    url = f'{GEMINI_API_URL}/{GEMINI_MODEL}:generateContent'
    headers = {'x-goog-api-key': GEMINI_API_KEY}
    body = {
        'contents': contents,
        'tools': [{'function_declarations': tools}],
        'tool_config': {'function_calling_config': {'mode': 'ANY'}},
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(url, json=body, headers=headers)
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


def _format_search_results(tool_result: dict) -> str:
    """Format search results dict for Gemini context injection."""
    error = tool_result.get('error')
    if error:
        return f'Search error: {error}'
    results = tool_result.get('results', [])
    if not results:
        return 'No matching tasks found.'
    lines = []
    for item in results:
        status = item.get('status', 'unknown')
        sim = item.get('similarity', 0.0)
        lines.append(f'- [{status}] (sim={sim:.2f}) {item.get("description", "")}')
    return '\n'.join(lines)


class ServerTaskAssistant:
    """Server-side task extraction loop that mirrors the desktop TaskAssistant."""

    async def analyze_frame(
        self,
        frame: dict,
        session_context: dict,
        frame_id: str,
        uid: str,
        receive_tool_result: Callable[[str, int], Awaitable[dict]],
    ) -> AsyncIterator[dict]:
        """Run the Gemini tool loop for one frame.

        Yields dict messages (tool_call_request or analysis_outcome).
        When a search tool is needed, yields a tool_call_request, then awaits
        receive_tool_result() to get the desktop's response. The result is
        injected back into the Gemini conversation and the loop continues.
        """
        safe_uid = _sanitize_uid(uid)
        app_name = frame.get('app_name', '')
        prompt = _build_prompt(session_context, app_name)

        # Build initial Gemini contents with image
        jpeg_b64 = frame.get('jpeg_base64', '')
        contents = [
            {
                'role': 'user',
                'parts': [
                    {'text': prompt},
                ],
            }
        ]
        if jpeg_b64:
            contents[0]['parts'].append({'inline_data': {'mime_type': 'image/jpeg', 'data': jpeg_b64}})

        for iteration in range(MAX_ITERATIONS):
            try:
                response = await _call_gemini(contents, TOOL_DECLARATIONS)
            except Exception as e:
                # Sanitize error — httpx includes full URL (with API key) in HTTPStatusError
                error_type = type(e).__name__
                logger.error(
                    'Gemini call failed: uid=%s frame=%s iter=%d error_type=%s',
                    safe_uid,
                    frame_id,
                    iteration,
                    error_type,
                )
                yield {
                    'type': 'server_error',
                    'code': 'GEMINI_ERROR',
                    'message': f'Gemini API error ({error_type})',
                    'retryable': True,
                    'frame_id': frame_id,
                }
                return

            func_name, func_args = _parse_function_call(response)
            if not func_name:
                logger.warning('No function call in Gemini response: uid=%s frame=%s', safe_uid, frame_id)
                yield {
                    'type': 'analysis_outcome',
                    'outcome_kind': 'no_task_found',
                    'context_summary': 'Model returned no function call',
                    'current_activity': app_name,
                    'frame_id': frame_id,
                }
                return

            # Terminal decisions (server-side only, no desktop round-trip)
            if func_name == 'no_task_found':
                yield {
                    'type': 'analysis_outcome',
                    'outcome_kind': 'no_task_found',
                    'context_summary': func_args.get('context_summary', ''),
                    'current_activity': func_args.get('current_activity', ''),
                    'frame_id': frame_id,
                }
                return

            if func_name == 'reject_task':
                yield {
                    'type': 'analysis_outcome',
                    'outcome_kind': 'reject_task',
                    'reason': func_args.get('reason', ''),
                    'context_summary': func_args.get('context_summary', ''),
                    'current_activity': func_args.get('current_activity', ''),
                    'frame_id': frame_id,
                }
                return

            if func_name == 'extract_task':
                yield {
                    'type': 'analysis_outcome',
                    'outcome_kind': 'extract_task',
                    'task': {
                        'title': func_args.get('title', ''),
                        'description': func_args.get('description', ''),
                        'priority': func_args.get('priority', 'medium'),
                        'tags': func_args.get('tags', []),
                        'source_app': func_args.get('source_app', app_name),
                        'inferred_deadline': func_args.get('inferred_deadline', ''),
                        'confidence': func_args.get('confidence', 0.0),
                        'source_category': func_args.get('source_category', ''),
                        'source_subcategory': func_args.get('source_subcategory', ''),
                        'relevance_score': _safe_int(func_args.get('relevance_score', 0)),
                    },
                    'context_summary': func_args.get('context_summary', ''),
                    'current_activity': func_args.get('current_activity', ''),
                    'frame_id': frame_id,
                }
                return

            # Search tools: delegate to desktop via WebSocket, then resume model loop
            if func_name in ('search_similar', 'search_keywords'):
                request_id = str(uuid.uuid4())

                # Yield tool_call_request to client
                yield {
                    'type': 'tool_call_request',
                    'request_id': request_id,
                    'tool_kind': func_name,
                    'query': func_args.get('query', ''),
                    'deadline_ms': 10000,
                    'frame_id': frame_id,
                }

                # Wait for desktop to respond with search results
                try:
                    tool_result = await receive_tool_result(request_id, 10000)
                except Exception as e:
                    logger.warning(
                        'Tool result timeout/error: uid=%s request_id=%s error=%s',
                        safe_uid,
                        request_id,
                        type(e).__name__,
                    )
                    yield {
                        'type': 'analysis_outcome',
                        'outcome_kind': 'no_task_found',
                        'context_summary': f'Search tool timed out ({func_name})',
                        'current_activity': app_name,
                        'frame_id': frame_id,
                    }
                    return

                # Inject the tool result into Gemini conversation and continue the loop
                result_text = _format_search_results(tool_result)
                # Append the model's function call
                contents.append(
                    {
                        'role': 'model',
                        'parts': [{'functionCall': {'name': func_name, 'args': func_args}}],
                    }
                )
                # Append the function response
                contents.append(
                    {
                        'role': 'user',
                        'parts': [{'functionResponse': {'name': func_name, 'response': {'result': result_text}}}],
                    }
                )
                continue  # Re-enter the loop — Gemini will now decide extract/reject/no_task

            # Unknown function
            logger.warning('Unknown function call: %s uid=%s', func_name, safe_uid)
            yield {
                'type': 'analysis_outcome',
                'outcome_kind': 'no_task_found',
                'context_summary': f'Unknown function: {func_name}',
                'current_activity': app_name,
                'frame_id': frame_id,
            }
            return

        # Max iterations reached
        logger.warning('Max iterations reached: uid=%s frame=%s', safe_uid, frame_id)
        yield {
            'type': 'analysis_outcome',
            'outcome_kind': 'no_task_found',
            'context_summary': 'Max model iterations reached',
            'current_activity': app_name,
            'frame_id': frame_id,
        }


def _safe_int(value, default: int = 0) -> int:
    """Safely convert model output to int, returning default on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default
