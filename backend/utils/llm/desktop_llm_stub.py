"""Deterministic LLM responses for hermetic desktop E2E (OMI_LLM_STUB=1).

Ported from the retired Rust `llm_stub.rs` after the Python desktop-backend
cutover. Returns OpenAI-compatible JSON / SSE instead of calling upstream
providers, and echoes any ``[[MARKER:...]]`` token found in the latest user turn.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from utils.chat_followup import FOLLOWUP_DELIMITER

DEFAULT_ASSISTANT_TEXT = 'Hermetic LLM stub response.'
EXACT_MEMORY_AGENT_REQUEST = "Have an agent look through my memories today and surface one surprising insight."

# The one deterministic answer that carries a grounded follow-up tail.
#
# Every other steerable path here is unusable for the follow-up chip:
# ``exact_reply_token`` strips trailing non-alphanumerics, so it cannot even
# produce the ``?`` a chip question requires, and no other branch emits the
# delimiter at all. Without this the hermetic chat lane could never produce a
# chip, so nothing about the tail — that the question leaves the prose, that the
# chip carries it, that tapping it is attributed — was reachable from an e2e
# flow. Both halves are asserted verbatim by ``chat-hermetic.yaml``: change them
# and change the flow in the same commit.
FOLLOWUP_PROBE_TRIGGER = 'end with a grounded follow-up question'
FOLLOWUP_PROBE_ANSWER = 'Priya flagged the storage migration in the Tuesday review.'
FOLLOWUP_PROBE_QUESTION = 'What did Priya say about the storage migration?'

_USER_MESSAGE_BOUNDARY = '\n\n# User Message\n'
_HARNESS_TOKEN_RE = re.compile(r'(?:GAUNTLET|RESILIENCE)-[A-Z0-9_-]*')
_MARKER_RE = re.compile(r'\[\[MARKER:([^\]]+)\]\]')


@dataclass(frozen=True)
class _TextDirective:
    text: str
    kind: Literal['text'] = 'text'


@dataclass(frozen=True)
class _ToolCallDirective:
    name: str
    arguments: dict[str, Any]
    kind: Literal['tool_call'] = 'tool_call'


StubDirective = _TextDirective | _ToolCallDirective


def llm_stub_flag_is_truthy(value: str) -> bool:
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def llm_stub_enabled(environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return llm_stub_flag_is_truthy(env.get('OMI_LLM_STUB', ''))


def _message_text(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ''
    parts: list[str] = []
    for part in content:
        if isinstance(part, Mapping) and isinstance(part.get('text'), str):
            parts.append(part['text'])
    return '\n'.join(parts)


def _messages(body: Mapping[str, object]) -> list[Mapping[str, object]]:
    messages = body.get('messages')
    if not isinstance(messages, list):
        return []
    return [message for message in messages if isinstance(message, Mapping)]


def extract_latest_user_text(body: Mapping[str, object]) -> str:
    """Marker tokens from the latest user turn only.

    The desktop kernel wraps immutable context and the actual user input in one
    adapter message. Historical turns in that projection are untrusted context —
    route only on the canonical ``# User Message`` suffix when present.
    """
    for message in reversed(_messages(body)):
        if message.get('role') != 'user':
            continue
        text = _message_text(message.get('content'))
        if _USER_MESSAGE_BOUNDARY in text:
            return text.rsplit(_USER_MESSAGE_BOUNDARY, 1)[1]
        return text
    return ''


def _latest_user_index(body: Mapping[str, object]) -> int | None:
    for index in range(len(_messages(body)) - 1, -1, -1):
        if _messages(body)[index].get('role') == 'user':
            return index
    return None


def _exposes_tool(body: Mapping[str, object], name: str) -> bool:
    tools = body.get('tools')
    if not isinstance(tools, list):
        return False
    for tool in tools:
        if not isinstance(tool, Mapping) or tool.get('type') != 'function':
            continue
        function = tool.get('function')
        if isinstance(function, Mapping) and function.get('name') == name:
            return True
    return False


def _latest_tool_result_after_user(body: Mapping[str, object]) -> tuple[str, str] | None:
    user_index = _latest_user_index(body)
    if user_index is None:
        return None
    messages = _messages(body)
    tool_names_by_id: dict[str, str] = {}
    latest: tuple[str, str] | None = None
    for message in messages[user_index + 1 :]:
        role = message.get('role')
        if role == 'assistant':
            tool_calls = message.get('tool_calls')
            if not isinstance(tool_calls, list):
                continue
            for call in tool_calls:
                if not isinstance(call, Mapping):
                    continue
                call_id = call.get('id')
                function = call.get('function')
                if isinstance(call_id, str) and isinstance(function, Mapping) and isinstance(function.get('name'), str):
                    tool_names_by_id[call_id] = function['name']
        elif role == 'tool':
            tool_call_id = message.get('tool_call_id')
            name = tool_names_by_id.get(tool_call_id, 'unknown') if isinstance(tool_call_id, str) else 'unknown'
            latest = (name, _message_text(message.get('content')))
    return latest


def harness_tokens(text: str) -> list[str]:
    return _HARNESS_TOKEN_RE.findall(text)


def last_harness_token(body: Mapping[str, object], predicate) -> str | None:
    for message in reversed(_messages(body)):
        text = _message_text(message.get('content'))
        for token in reversed(harness_tokens(text)):
            if predicate(token):
                return token
    return None


def exact_reply_token(user_text: str) -> str | None:
    lowercase = user_text.lower()
    marker = 'reply with exactly'
    start = lowercase.find(marker)
    if start < 0:
        return None
    suffix = user_text[start + len(marker) :].lstrip(': \t')
    token = suffix.split(None, 1)[0] if suffix.strip() else ''
    while token and not (token[0].isalnum() or token[0] == '_'):
        token = token[1:]
    while token and not (token[-1].isalnum() or token[-1] == '_'):
        token = token[:-1]
    return token or None


def followup_probe_answer() -> str:
    """A grounded answer plus one follow-up tail, in the model's own wire shape.

    The delimiter is imported from ``utils.chat_followup`` rather than repeated
    so a change to the marker cannot leave the stub emitting the old one and the
    flow silently asserting a chip that no longer appears.
    """
    return f'{FOLLOWUP_PROBE_ANSWER}\n\n{FOLLOWUP_DELIMITER} {FOLLOWUP_PROBE_QUESTION}'


def quoted_title(user_text: str) -> str | None:
    lowercase = user_text.lower()
    marker_start = lowercase.find('background agent titled')
    if marker_start < 0:
        return None
    suffix = user_text[marker_start:]
    quote_start = suffix.find('"')
    if quote_start < 0:
        return None
    quote_end = suffix.find('"', quote_start + 1)
    if quote_end < 0:
        return None
    title = suffix[quote_start + 1 : quote_end].strip()
    return title or None


def first_chunk_delay_ms(user_text: str) -> int:
    if 'take about twenty seconds' in user_text.lower():
        return 1_500
    return 0


def memory_tool_arguments_for_date(day: str) -> dict[str, Any]:
    return {'limit': 50, 'start_date': day, 'end_date': day}


def today_memory_tool_arguments() -> dict[str, Any]:
    return memory_tool_arguments_for_date(date.today().isoformat())


def extract_markers(text: str) -> list[str]:
    markers: list[str] = []
    for match in _MARKER_RE.finditer(text):
        marker = match.group(1)
        if marker not in markers:
            markers.append(marker)
    return markers


def stub_assistant_text(body: str) -> str:
    markers = extract_markers(body)
    if not markers:
        return DEFAULT_ASSISTANT_TEXT
    return ' '.join(f'Stub saw marker: {marker}' for marker in markers)


def response_after_tool(body: Mapping[str, object], name: str, result: str) -> str:
    if name == 'get_memories':
        return (
            "One surprising insight is that your strongest themes become clearer "
            "when today's memories are reviewed together."
        )
    if name == 'spawn_agent':
        marker = last_harness_token(body, lambda _: True)
        if marker:
            return f'Started the background agent for {marker}.'
        return 'Started the requested background agent.'
    if name == 'list_agent_sessions':
        marker = harness_tokens(result)[-1:] or []
        if not marker:
            found = last_harness_token(body, lambda _: True)
            marker = [found] if found else []
        if marker and marker[0]:
            return f'The background agent for {marker[0]} is active.'
        return 'The background agent is active.'
    if name == 'execute_sql':
        return '0'
    if name == 'get_daily_recap':
        return "Yesterday's activity recap is ready."
    return DEFAULT_ASSISTANT_TEXT


def stub_directive(body: Mapping[str, object]) -> StubDirective:
    user_text = extract_latest_user_text(body)
    normalized = user_text.lower()

    tool_result = _latest_tool_result_after_user(body)
    if tool_result is not None:
        name, result = tool_result
        return _TextDirective(response_after_tool(body, name, result))

    memory_probe = (
        user_text.strip() == EXACT_MEMORY_AGENT_REQUEST
        or ('look through my memories today' in normalized and 'surprising insight' in normalized)
        or ('call get_memories again for today' in normalized)
    )
    if memory_probe and _exposes_tool(body, 'get_memories'):
        return _ToolCallDirective('get_memories', today_memory_tool_arguments())

    if ('use spawn_agent now' in normalized or 'spawn a background agent' in normalized) and _exposes_tool(
        body, 'spawn_agent'
    ):
        arguments: dict[str, Any] = {'objective': user_text, 'visible': True}
        title = quoted_title(user_text)
        if title:
            arguments['title'] = title
        return _ToolCallDirective('spawn_agent', arguments)

    if 'status of the background agent' in normalized and _exposes_tool(body, 'list_agent_sessions'):
        return _ToolCallDirective('list_agent_sessions', {})

    if 'use execute_sql to count the rows in the memories table' in normalized and _exposes_tool(body, 'execute_sql'):
        return _ToolCallDirective('execute_sql', {'query': 'SELECT COUNT(*) AS count FROM memories'})

    if 'what did i do yesterday' in normalized and _exposes_tool(body, 'get_daily_recap'):
        return _ToolCallDirective('get_daily_recap', {'days_ago': 1})

    if 'single word probe only' in normalized:
        return _TextDirective('PROBE')

    # Checked before `exact_reply_token` because that path would otherwise claim
    # a probe query that also contains "reply with".
    if FOLLOWUP_PROBE_TRIGGER in normalized:
        return _TextDirective(followup_probe_answer())

    exact = exact_reply_token(user_text)
    if exact:
        return _TextDirective(exact)

    if 'earlier push-to-talk voice turn' in normalized:
        marker = last_harness_token(body, lambda token: token.endswith('-PTT'))
        if marker:
            return _TextDirective(marker)

    if 'what was the last thing i asked you for' in normalized:
        marker = last_harness_token(body, lambda token: token.endswith('-FLOAT'))
        if marker:
            return _TextDirective(f'The last request was the background-agent task tagged {marker}.')

    harness = harness_tokens(user_text)
    if harness:
        return _TextDirective(f'Stub saw marker: {harness[-1]}')

    if 'zebulon quarkfinder' in normalized:
        return _TextDirective("I don't know them yet—tell me a little about them.")

    return _TextDirective(stub_assistant_text(user_text))


def _sse(payload: dict[str, object]) -> str:
    return f'data: {json.dumps(payload, separators=(",", ":"))}\n\n'


def text_completion_payload(text: str) -> dict[str, object]:
    return {
        'id': 'chatcmpl-stub',
        'object': 'chat.completion',
        'created': 0,
        'model': 'omi-stub',
        'choices': [
            {
                'index': 0,
                'message': {'role': 'assistant', 'content': text},
                'finish_reason': 'stop',
            }
        ],
    }


def tool_call_completion_payload(name: str, arguments: Mapping[str, Any]) -> dict[str, object]:
    return {
        'id': 'chatcmpl-stub',
        'object': 'chat.completion',
        'created': 0,
        'model': 'omi-stub',
        'choices': [
            {
                'index': 0,
                'message': {
                    'role': 'assistant',
                    'content': None,
                    'tool_calls': [
                        {
                            'id': f'call_omi_stub_{name}',
                            'type': 'function',
                            'function': {
                                'name': name,
                                'arguments': json.dumps(arguments, separators=(',', ':')),
                            },
                        }
                    ],
                },
                'finish_reason': 'tool_calls',
            }
        ],
    }


def text_stream_chunks(text: str) -> list[str]:
    return [
        _sse(
            {
                'id': 'chatcmpl-stub',
                'object': 'chat.completion.chunk',
                'created': 0,
                'model': 'omi-stub',
                'choices': [
                    {
                        'index': 0,
                        'delta': {'role': 'assistant', 'content': text},
                        'finish_reason': None,
                    }
                ],
            }
        ),
        _sse(
            {
                'id': 'chatcmpl-stub',
                'object': 'chat.completion.chunk',
                'created': 0,
                'model': 'omi-stub',
                'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}],
            }
        ),
        'data: [DONE]\n\n',
    ]


def tool_call_stream_chunks(name: str, arguments: Mapping[str, Any]) -> list[str]:
    call_id = f'call_omi_stub_{name}'
    return [
        _sse(
            {
                'id': 'chatcmpl-stub',
                'object': 'chat.completion.chunk',
                'created': 0,
                'model': 'omi-stub',
                'choices': [
                    {
                        'index': 0,
                        'delta': {
                            'role': 'assistant',
                            'tool_calls': [
                                {
                                    'index': 0,
                                    'id': call_id,
                                    'type': 'function',
                                    'function': {
                                        'name': name,
                                        'arguments': json.dumps(arguments, separators=(',', ':')),
                                    },
                                }
                            ],
                        },
                        'finish_reason': None,
                    }
                ],
            }
        ),
        _sse(
            {
                'id': 'chatcmpl-stub',
                'object': 'chat.completion.chunk',
                'created': 0,
                'model': 'omi-stub',
                'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'tool_calls'}],
            }
        ),
        'data: [DONE]\n\n',
    ]


def stub_chat_completions_json(body: Mapping[str, object]) -> dict[str, object]:
    directive = stub_directive(body)
    if isinstance(directive, _ToolCallDirective):
        return tool_call_completion_payload(directive.name, directive.arguments)
    return text_completion_payload(directive.text)


async def stub_chat_completions_stream(body: Mapping[str, object]) -> AsyncIterator[str]:
    import asyncio

    user_text = extract_latest_user_text(body)
    directive = stub_directive(body)
    if isinstance(directive, _ToolCallDirective):
        chunks = tool_call_stream_chunks(directive.name, directive.arguments)
    else:
        chunks = text_stream_chunks(directive.text)
    delay_ms = first_chunk_delay_ms(user_text)
    for index, chunk in enumerate(chunks):
        if index == 0 and delay_ms:
            await asyncio.sleep(delay_ms / 1000.0)
        yield chunk


def extract_latest_gemini_user_text(body_text: str) -> str:
    try:
        value = json.loads(body_text)
    except ValueError:
        return ''
    contents = value.get('contents') if isinstance(value, Mapping) else None
    if not isinstance(contents, list):
        return ''
    for content in reversed(contents):
        if not isinstance(content, Mapping) or content.get('role') == 'model':
            continue
        parts = content.get('parts')
        if not isinstance(parts, list):
            continue
        texts = [part['text'] for part in parts if isinstance(part, Mapping) and isinstance(part.get('text'), str)]
        if texts:
            return '\n'.join(texts)
    return ''


def gemini_json_payload(text: str) -> dict[str, object]:
    return {
        'candidates': [
            {
                'content': {'parts': [{'text': text}], 'role': 'model'},
                'finishReason': 'STOP',
            }
        ]
    }


def gemini_stream_chunks(text: str) -> list[str]:
    return [
        _sse({'candidates': [{'content': {'parts': [{'text': text}], 'role': 'model'}}]}),
        _sse(
            {
                'candidates': [
                    {
                        'content': {'parts': [{'text': ''}], 'role': 'model'},
                        'finishReason': 'STOP',
                    }
                ]
            }
        ),
        'data: [DONE]\n\n',
    ]


def stub_gemini_proxy_json(body_text: str) -> dict[str, object]:
    return gemini_json_payload(stub_assistant_text(extract_latest_gemini_user_text(body_text)))


def stub_gemini_proxy_stream_chunks(body_text: str) -> Sequence[str]:
    return gemini_stream_chunks(stub_assistant_text(extract_latest_gemini_user_text(body_text)))
