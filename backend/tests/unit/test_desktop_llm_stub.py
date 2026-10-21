"""Unit tests for the hermetic desktop LLM stub (OMI_LLM_STUB)."""

from __future__ import annotations

import json

import pytest

from utils.chat_followup import FOLLOWUP_DELIMITER, split_followup_tail
from utils.llm import desktop_llm_stub as stub


def _user_body(text: str, *, tools: list[str] | None = None, stream: bool = False) -> dict:
    body: dict = {
        'model': 'omi-sonnet',
        'messages': [{'role': 'user', 'content': text}],
        'stream': stream,
    }
    if tools:
        body['tools'] = [
            {'type': 'function', 'function': {'name': name, 'parameters': {'type': 'object'}}} for name in tools
        ]
    return body


def test_llm_stub_flag_truthy_values():
    assert stub.llm_stub_flag_is_truthy('1')
    assert stub.llm_stub_flag_is_truthy('true')
    assert stub.llm_stub_flag_is_truthy('YES')
    assert not stub.llm_stub_flag_is_truthy('0')
    assert not stub.llm_stub_flag_is_truthy('false')
    assert stub.llm_stub_enabled({'OMI_LLM_STUB': '1'})
    assert not stub.llm_stub_enabled({})


def test_chat_hermetic_exact_reply_token():
    body = _user_body('Reply with exactly [[MARKER:chat-hermetic]]')
    directive = stub.stub_directive(body)
    assert isinstance(directive, stub._TextDirective)
    assert directive.text == 'MARKER:chat-hermetic'


def test_floating_bar_marker_echo():
    body = _user_body('Hermetic floating bar [[MARKER:floating-bar]]')
    directive = stub.stub_directive(body)
    assert isinstance(directive, stub._TextDirective)
    assert directive.text == 'Stub saw marker: floating-bar'


def test_kernel_user_message_boundary_ignores_history_markers():
    wrapped = 'Prior context with [[MARKER:old]]\n\n# User Message\n' 'Reply with exactly [[MARKER:chat-hermetic]]'
    body = _user_body(wrapped)
    directive = stub.stub_directive(body)
    assert isinstance(directive, stub._TextDirective)
    assert directive.text == 'MARKER:chat-hermetic'


def test_gauntlet_spawn_emits_tool_call():
    body = _user_body(
        'Use spawn_agent now to start a visible background agent titled "Recall Page". '
        'Objective: track marker GAUNTLET-SPAWN-ABC and wait silently.',
        tools=['spawn_agent'],
    )
    directive = stub.stub_directive(body)
    assert isinstance(directive, stub._ToolCallDirective)
    assert directive.name == 'spawn_agent'
    assert directive.arguments['title'] == 'Recall Page'
    assert 'GAUNTLET-SPAWN-ABC' in directive.arguments['objective']


def test_json_and_stream_payloads_for_marker_echo():
    body = _user_body('Hermetic floating bar [[MARKER:floating-bar]]', stream=False)
    payload = stub.stub_chat_completions_json(body)
    assert payload['choices'][0]['message']['content'] == 'Stub saw marker: floating-bar'
    assert payload['choices'][0]['finish_reason'] == 'stop'


@pytest.mark.asyncio
async def test_stream_emits_openai_chunks_for_exact_reply():
    body = _user_body('Reply with exactly [[MARKER:chat-hermetic]]', stream=True)
    chunks = [chunk async for chunk in stub.stub_chat_completions_stream(body)]
    assert chunks[-1] == 'data: [DONE]\n\n'
    first = json.loads(chunks[0][6:])
    assert first['choices'][0]['delta']['content'] == 'MARKER:chat-hermetic'


def test_gemini_proxy_stub_echoes_marker():
    body = json.dumps(
        {
            'contents': [
                {'role': 'user', 'parts': [{'text': 'hello [[MARKER:gemini-stub]]'}]},
            ]
        }
    )
    payload = stub.stub_gemini_proxy_json(body)
    assert payload['candidates'][0]['content']['parts'][0]['text'] == 'Stub saw marker: gemini-stub'


def test_followup_probe_emits_a_separable_tail():
    """The one stub answer `chat-hermetic.yaml` drives its follow-up chip from.

    Asserted against the shared splitter, not against a hand-written expectation:
    a tail the backend's own rules reject is a tail the desktop client rejects
    too, and the flow would then assert a chip that never appears.
    """
    body = _user_body('Recap the storage migration and end with a grounded follow-up question.')
    directive = stub.stub_directive(body)
    assert isinstance(directive, stub._TextDirective)
    assert FOLLOWUP_DELIMITER in directive.text

    visible, question = split_followup_tail(directive.text)
    assert visible == stub.FOLLOWUP_PROBE_ANSWER
    assert question == stub.FOLLOWUP_PROBE_QUESTION
    # The flow asserts the visible answer verbatim; the question must not survive
    # anywhere inside it, which is the defect the chip exists to prevent.
    assert stub.FOLLOWUP_PROBE_QUESTION not in visible


def test_followup_probe_beats_the_exact_reply_path():
    """`exact_reply_token` strips the trailing `?`, so it must not claim this query."""
    body = _user_body('Reply with a recap and end with a grounded follow-up question.')
    directive = stub.stub_directive(body)
    assert isinstance(directive, stub._TextDirective)
    assert directive.text == stub.followup_probe_answer()
