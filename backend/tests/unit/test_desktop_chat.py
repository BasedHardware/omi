import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from routers import desktop_chat


def test_request_translates_openai_tool_history_and_alias():
    public_model, payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'max_completion_tokens': 20_000,
            'messages': [
                {'role': 'developer', 'content': 'be concise'},
                {
                    'role': 'assistant',
                    'tool_calls': [
                        {
                            'id': 'call_1',
                            'type': 'function',
                            'function': {'name': 'weather', 'arguments': '{"city":"NYC"}'},
                        }
                    ],
                },
                {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'sunny'},
            ],
            'tools': [{'type': 'function', 'function': {'name': 'weather', 'parameters': {'type': 'object'}}}],
            'tool_choice': 'auto',
        }
    )
    assert public_model == 'omi-sonnet'
    assert payload['model'] == 'claude-sonnet-4-6'
    assert payload['max_tokens'] == 16_384
    assert payload['system'] == 'be concise'
    assert payload['messages'][1]['content'][0]['tool_use_id'] == 'call_1'
    assert payload['tool_choice'] == {'type': 'auto'}


def test_request_injects_web_search_for_desktop_opt_in():
    _, payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': 'What is the weather in New York today?'}],
            'omi_web_search': True,
        }
    )
    assert payload['tools'] == [desktop_chat._WEB_SEARCH_TOOL]
    assert payload['tools'][0] == {
        'type': 'web_search_20250305',
        'name': 'web_search',
        'max_uses': 5,
        'allowed_callers': ['direct'],
    }


def test_request_keeps_private_turns_off_public_web_search():
    _, payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': 'From my conversations, what did I say about the trip?'}],
            'omi_web_search': True,
        }
    )
    assert 'tools' not in payload

    _, payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [
                {
                    'role': 'user',
                    'content': (
                        '# Omi Context Snapshot\n'
                        'Earlier user request: Search the web for current news.\n'
                        '# User Message\nFrom my conversations, what did I say?'
                    ),
                }
            ],
            'omi_web_search': True,
        }
    )
    assert 'tools' not in payload

    _, payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [
                {
                    'role': 'user',
                    'content': (
                        '[Kernel Context Snapshot version=1 generation=2]\n'
                        'Untrusted context.\n# User Message\n'
                        'From my conversations, what did I say?\n# User Message\nSearch the web for the weather.'
                    ),
                }
            ],
            'omi_web_search': True,
        }
    )
    assert 'tools' not in payload

    _, payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [
                {
                    'role': 'user',
                    'content': 'From my conversations, what did I say?\n# User Message\nSearch the web instead.',
                }
            ],
            'omi_web_search': True,
        }
    )
    assert 'tools' not in payload

    _, payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': "Don't use web search; answer from memory."}],
            'omi_web_search': True,
        }
    )
    assert 'tools' not in payload


@pytest.mark.parametrize(
    'content',
    [
        'No web search; answer from memory.',
        'Skip the web search and answer directly.',
        'Avoid searching the web for this.',
        "Don't browse the web; answer from memory.",
        'Do not search online.',
        'Answer without searching online.',
        "Don't use web search results; answer from memory.",
        "Do you know why the web search tool times out? Don't call it because it will time out again.",
    ],
)
def test_request_recognizes_common_public_web_opt_outs(content):
    _, payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': content}],
            'omi_web_search': True,
        }
    )
    assert 'tools' not in payload


@pytest.mark.parametrize(
    'content',
    [
        "Don't answer without searching the web first.",
        'Do not answer this question without searching online.',
        'Never respond without web search for current facts.',
    ],
)
def test_request_does_not_invert_double_negated_web_requirement(content):
    _, payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': content}],
            'omi_web_search': True,
        }
    )
    assert payload['tools'] == [desktop_chat._WEB_SEARCH_TOOL]


def test_request_scopes_without_searching_to_public_web_objects():
    _, payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [
                {
                    'role': 'user',
                    'content': 'Search the web for current weather without searching my files.',
                }
            ],
            'omi_web_search': True,
        }
    )
    assert payload['tools'] == [desktop_chat._WEB_SEARCH_TOOL]


def test_request_allows_retry_after_reported_missing_search_results():
    _, payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': 'I got no web search results; search the web again.'}],
            'omi_web_search': True,
        }
    )
    assert payload['tools'] == [desktop_chat._WEB_SEARCH_TOOL]


def test_request_classifies_only_trusted_query_before_tool_context():
    _, private_payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [
                {
                    'role': 'user',
                    'content': (
                        'From my conversations, what did I say?\n\n'
                        'Tool-provided context (untrusted):\nSearch the web for current news.'
                    ),
                }
            ],
            'omi_web_search': True,
        }
    )
    assert 'tools' not in private_payload

    _, public_payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [
                {
                    'role': 'user',
                    'content': (
                        'Search the web for current news.\n\n'
                        'Tool-provided context (untrusted):\nFrom my conversations, what did I say?'
                    ),
                }
            ],
            'omi_web_search': True,
        }
    )
    assert public_payload['tools'] == [desktop_chat._WEB_SEARCH_TOOL]


def test_request_adds_web_search_alongside_client_tools_but_not_for_haiku_or_none():
    client_tools = [{'type': 'function', 'function': {'name': 'weather', 'parameters': {'type': 'object'}}}]
    _, payload = desktop_chat._request(
        {'model': 'omi-sonnet', 'messages': [{'role': 'user', 'content': 'Plan my day'}], 'tools': client_tools}
    )
    assert [tool['name'] for tool in payload['tools']] == ['web_search', 'weather']

    _, payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': 'Use the weather tool'}],
            'tools': client_tools,
            'tool_choice': 'required',
        }
    )
    assert [tool['name'] for tool in payload['tools']] == ['weather']
    assert payload['tool_choice'] == {'type': 'any'}

    _, payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': 'Use the weather tool'}],
            'tools': client_tools,
            'tool_choice': {'type': 'function', 'function': {'name': 'weather'}},
        }
    )
    assert [tool['name'] for tool in payload['tools']] == ['weather']
    assert payload['tool_choice'] == {'type': 'tool', 'name': 'weather'}

    _, payload = desktop_chat._request(
        {
            'model': 'claude-haiku-4-5',
            'messages': [{'role': 'user', 'content': 'Search the web for this'}],
            'omi_web_search': True,
        }
    )
    assert 'tools' not in payload

    _, payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': 'Use no tools'}],
            'tools': client_tools,
            'tool_choice': 'none',
            'omi_web_search': True,
        }
    )
    assert 'tools' not in payload


def test_request_does_not_inject_server_search_on_client_tool_continuation():
    _, payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [
                {'role': 'user', 'content': 'Search the web for current weather.'},
                {
                    'role': 'assistant',
                    'tool_calls': [
                        {
                            'id': 'call_1',
                            'type': 'function',
                            'function': {'name': 'weather', 'arguments': '{}'},
                        }
                    ],
                },
                {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'sunny'},
            ],
            'tools': [{'type': 'function', 'function': {'name': 'weather'}}],
            'omi_web_search': True,
        }
    )
    assert [tool['name'] for tool in payload['tools']] == ['weather']


def test_request_binds_public_web_privacy_policy_to_anthropic_system():
    _, payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [
                {'role': 'system', 'content': 'Use the supplied kernel context.'},
                {'role': 'user', 'content': 'What is the current weather in New York?'},
            ],
            'omi_web_search': True,
        }
    )
    assert payload['system'] == ('Use the supplied kernel context.\n\n' + desktop_chat._PUBLIC_WEB_ROUTING_INSTRUCTION)


def test_request_recognizes_pi_public_web_routing_policy():
    _, payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [
                {
                    'role': 'user',
                    'content': f'{desktop_chat._PUBLIC_WEB_ROUTING_INSTRUCTION}\n\nWhat is new today?',
                }
            ],
        }
    )
    assert payload['tools'] == [desktop_chat._WEB_SEARCH_TOOL]


def test_request_reports_web_search_capability_fallback(monkeypatch):
    fallbacks = []
    monkeypatch.setattr(desktop_chat, 'record_fallback', lambda **fields: fallbacks.append(fields))
    desktop_chat._request(
        {
            'model': 'claude-haiku-4-5',
            'messages': [{'role': 'user', 'content': 'What happened today?'}],
            'omi_web_search': True,
        }
    )
    assert fallbacks == [
        {
            'component': 'other',
            'from_mode': 'anthropic_web_search',
            'to_mode': 'model_knowledge',
            'reason': 'capability_mismatch',
            'outcome': 'degraded',
        }
    ]

    fallbacks.clear()
    desktop_chat._request(
        {
            'model': 'claude-haiku-4-5',
            'messages': [{'role': 'user', 'content': 'From my conversations, what did I say?'}],
            'omi_web_search': True,
        }
    )
    assert fallbacks == []


@pytest.mark.asyncio
async def test_record_usage_charges_web_search_requests(monkeypatch):
    calls = []

    async def run_blocking(_, function, *args):
        calls.append((function, args))

    monkeypatch.setattr(desktop_chat, 'run_blocking', run_blocking)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _: None)
    await desktop_chat._record_usage(
        'user',
        {
            'input_tokens': 3,
            'output_tokens': 4,
            'server_tool_use': {'web_search_requests': 3},
        },
    )
    assert calls[0][1][-1] == 0.03


@pytest.mark.asyncio
async def test_record_usage_skips_byok_requests(monkeypatch):
    calls = []

    async def run_blocking(_, function, *args):
        calls.append((function, args))

    monkeypatch.setattr(desktop_chat, 'run_blocking', run_blocking)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _: 'anthropic-key')
    await desktop_chat._record_usage('user', {'input_tokens': 3, 'web_search_requests': 1})
    assert calls == []


def test_response_preserves_openai_tool_and_cache_usage():
    message = SimpleNamespace(
        id='msg_1',
        content=[SimpleNamespace(type='tool_use', id='call_1', name='weather', input={'city': 'NYC'})],
        stop_reason='tool_use',
        usage=SimpleNamespace(
            input_tokens=3, cache_creation_input_tokens=2, cache_read_input_tokens=5, output_tokens=7
        ),
    )
    response = desktop_chat._message_response(message, 'omi-sonnet')
    assert response['choices'][0]['finish_reason'] == 'tool_calls'
    assert json.loads(response['choices'][0]['message']['tool_calls'][0]['function']['arguments']) == {'city': 'NYC'}
    assert response['usage'] == {
        'prompt_tokens': 10,
        'completion_tokens': 7,
        'total_tokens': 17,
        'prompt_tokens_details': {'cached_tokens': 5},
    }


@pytest.mark.asyncio
async def test_stream_emits_openai_terminal_event(monkeypatch):
    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get_final_message(self):
            return SimpleNamespace(
                content=[SimpleNamespace(type='text', text='hello')],
                stop_reason='end_turn',
                usage=SimpleNamespace(
                    input_tokens=1, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=1
                ),
            )

        def __aiter__(self):
            async def events():
                yield SimpleNamespace(
                    type='content_block_delta', delta=SimpleNamespace(type='text_delta', text='hello')
                )
                yield SimpleNamespace(
                    type='message_delta',
                    delta=SimpleNamespace(stop_reason='end_turn'),
                    usage=SimpleNamespace(
                        input_tokens=1, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=1
                    ),
                )

            return events()

    monkeypatch.setattr(
        desktop_chat, 'anthropic_client', SimpleNamespace(messages=SimpleNamespace(stream=lambda **_: Stream()))
    )

    async def record_usage(*_):
        return None

    monkeypatch.setattr(desktop_chat, '_record_usage', record_usage)
    events = [
        event
        async for event in desktop_chat._stream(
            {'model': 'claude-sonnet-4-6', 'max_tokens': 1, 'messages': []}, 'omi-sonnet', 'user'
        )
    ]
    assert json.loads(events[1][6:])['choices'][0]['delta'] == {'content': 'hello'}
    assert events[-1] == 'data: [DONE]\n\n'


@pytest.mark.asyncio
async def test_stream_does_not_forward_server_tool_input_deltas(monkeypatch):
    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def __aiter__(self):
            async def events():
                yield SimpleNamespace(
                    type='content_block_start',
                    index=0,
                    content_block=SimpleNamespace(type='server_tool_use', id='search_1', name='web_search'),
                )
                yield SimpleNamespace(
                    type='content_block_delta',
                    index=0,
                    delta=SimpleNamespace(type='input_json_delta', partial_json='{"query":"news"}'),
                )
                yield SimpleNamespace(
                    type='content_block_start',
                    index=1,
                    content_block=SimpleNamespace(type='tool_use', id='call_1', name='weather'),
                )
                yield SimpleNamespace(
                    type='content_block_delta',
                    index=1,
                    delta=SimpleNamespace(type='input_json_delta', partial_json='{"city":"NYC"}'),
                )
                yield SimpleNamespace(
                    type='content_block_start',
                    index=2,
                    content_block=SimpleNamespace(type='web_search_tool_result'),
                )
                yield SimpleNamespace(
                    type='content_block_start',
                    index=3,
                    content_block=SimpleNamespace(type='tool_use', id='call_2', name='calendar'),
                )
                yield SimpleNamespace(
                    type='content_block_delta',
                    index=3,
                    delta=SimpleNamespace(type='input_json_delta', partial_json='{"day":"today"}'),
                )
                yield SimpleNamespace(
                    type='message_delta',
                    delta=SimpleNamespace(stop_reason='tool_use'),
                    usage=SimpleNamespace(
                        input_tokens=1, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=1
                    ),
                )

            return events()

        async def get_final_message(self):
            return SimpleNamespace(
                content=[],
                stop_reason='tool_use',
                usage=SimpleNamespace(
                    input_tokens=1, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=1
                ),
            )

    monkeypatch.setattr(
        desktop_chat, 'anthropic_client', SimpleNamespace(messages=SimpleNamespace(stream=lambda **_: Stream()))
    )

    async def record_usage(*_):
        return None

    monkeypatch.setattr(desktop_chat, '_record_usage', record_usage)
    events = [
        event
        async for event in desktop_chat._stream(
            {'model': 'claude-sonnet-4-6', 'max_tokens': 1, 'messages': []}, 'omi-sonnet', 'user'
        )
    ]
    payloads = [json.loads(event[6:]) for event in events if event.startswith('data: {')]
    tool_calls = [
        call
        for payload in payloads
        if payload.get('choices')
        for call in payload['choices'][0].get('delta', {}).get('tool_calls', [])
    ]
    assert [call['index'] for call in tool_calls] == [0, 0, 1, 1]
    assert all(call.get('id') != 'search_1' for call in tool_calls)


@pytest.mark.asyncio
async def test_pause_turn_continuation_replays_anthropic_content_and_totals_usage(monkeypatch):
    calls = []
    first = SimpleNamespace(
        content=[SimpleNamespace(type='server_tool_use', id='search_1', name='web_search', input={'query': 'news'})],
        stop_reason='pause_turn',
        usage=SimpleNamespace(
            input_tokens=3, cache_creation_input_tokens=1, cache_read_input_tokens=2, output_tokens=4
        ),
    )
    final = SimpleNamespace(
        content=[SimpleNamespace(type='text', text='Here is the result.')],
        stop_reason='end_turn',
        usage=SimpleNamespace(
            input_tokens=5, cache_creation_input_tokens=0, cache_read_input_tokens=1, output_tokens=6
        ),
    )

    async def create(**payload):
        calls.append(payload)
        return first if len(calls) == 1 else final

    monkeypatch.setattr(desktop_chat, 'anthropic_client', SimpleNamespace(messages=SimpleNamespace(create=create)))
    message, usage, content = await desktop_chat._create_with_pause_turn_continuations(
        {'model': 'claude-sonnet-4-6', 'max_tokens': 100, 'messages': [{'role': 'user', 'content': 'Search this'}]}
    )

    assert message is final
    assert content[-1].text == 'Here is the result.'
    assert calls[1]['messages'][-1] == {
        'role': 'assistant',
        'content': [{'type': 'server_tool_use', 'id': 'search_1', 'name': 'web_search', 'input': {'query': 'news'}}],
    }
    assert usage == {
        'input_tokens': 8,
        'output_tokens': 10,
        'cache_creation_input_tokens': 1,
        'cache_read_input_tokens': 3,
    }


@pytest.mark.asyncio
async def test_stream_pause_turn_emits_only_continuation_content(monkeypatch):
    first = SimpleNamespace(
        content=[SimpleNamespace(type='server_tool_use', id='search_1', name='web_search', input={'query': 'news'})],
        stop_reason='pause_turn',
        usage=SimpleNamespace(
            input_tokens=3, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=2
        ),
    )
    final = SimpleNamespace(
        content=[SimpleNamespace(type='text', text='Grounded answer.')],
        stop_reason='end_turn',
        usage=SimpleNamespace(
            input_tokens=4, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=5
        ),
    )

    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def __aiter__(self):
            async def events():
                yield SimpleNamespace(
                    type='message_delta', delta=SimpleNamespace(stop_reason='pause_turn'), usage=first.usage
                )

            return events()

        async def get_final_message(self):
            return first

    async def create(**_):
        return final

    monkeypatch.setattr(
        desktop_chat,
        'anthropic_client',
        SimpleNamespace(messages=SimpleNamespace(stream=lambda **_: Stream(), create=create)),
    )
    recorded = []

    async def record_usage(_, usage):
        recorded.append(usage)

    monkeypatch.setattr(desktop_chat, '_record_usage', record_usage)
    events = [
        event
        async for event in desktop_chat._stream(
            {'model': 'claude-sonnet-4-6', 'max_tokens': 1, 'messages': []}, 'omi-sonnet', 'user'
        )
    ]
    payloads = [json.loads(event[6:]) for event in events if event.startswith('data: {')]
    text_chunks = [
        payload
        for payload in payloads
        if payload.get('choices') and payload['choices'][0].get('delta', {}).get('content')
    ]
    assert [chunk['choices'][0]['delta']['content'] for chunk in text_chunks] == ['Grounded answer.']
    assert recorded[0]['output_tokens'] == 7
    assert events[-1] == 'data: [DONE]\n\n'


@pytest.mark.asyncio
async def test_pause_turn_limit_preserves_accumulated_usage(monkeypatch):
    calls = []
    usage = SimpleNamespace(
        input_tokens=1,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
        output_tokens=2,
        server_tool_use=SimpleNamespace(web_search_requests=1),
    )
    message = SimpleNamespace(
        content=[SimpleNamespace(type='server_tool_use', id='search_1', name='web_search', input={'query': 'news'})],
        stop_reason='pause_turn',
        usage=usage,
    )

    async def create(**_payload):
        calls.append(True)
        return message

    monkeypatch.setattr(desktop_chat, 'anthropic_client', SimpleNamespace(messages=SimpleNamespace(create=create)))
    with pytest.raises(desktop_chat._PauseTurnContinuationLimitError) as error:
        await desktop_chat._create_with_pause_turn_continuations(
            {'model': 'claude-sonnet-4-6', 'max_tokens': 100, 'messages': []}
        )

    assert len(calls) == 4
    assert error.value.usage == {
        'input_tokens': 4,
        'output_tokens': 8,
        'cache_read_input_tokens': 0,
        'cache_creation_input_tokens': 0,
        'web_search_requests': 4,
    }


@pytest.mark.asyncio
async def test_stream_records_usage_when_pause_turn_limit_is_exhausted(monkeypatch):
    first = SimpleNamespace(
        content=[SimpleNamespace(type='server_tool_use', id='search_1', name='web_search', input={'query': 'news'})],
        stop_reason='pause_turn',
        usage=SimpleNamespace(
            input_tokens=3, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=2
        ),
    )

    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def __aiter__(self):
            async def events():
                yield SimpleNamespace(
                    type='message_delta', delta=SimpleNamespace(stop_reason='pause_turn'), usage=first.usage
                )

            return events()

        async def get_final_message(self):
            return first

    monkeypatch.setattr(
        desktop_chat,
        'anthropic_client',
        SimpleNamespace(messages=SimpleNamespace(stream=lambda **_: Stream())),
    )
    usage = {'input_tokens': 6, 'output_tokens': 4, 'web_search_requests': 3}

    async def raise_limit(*_args, **_kwargs):
        raise desktop_chat._PauseTurnContinuationLimitError(usage, first, first.content)

    monkeypatch.setattr(desktop_chat, '_continue_pause_turn', raise_limit)
    recorded = []

    async def record_usage(uid, value):
        recorded.append((uid, value))

    monkeypatch.setattr(desktop_chat, '_record_usage', record_usage)
    events = [
        event
        async for event in desktop_chat._stream(
            {'model': 'claude-sonnet-4-6', 'max_tokens': 1, 'messages': []}, 'omi-sonnet', 'user'
        )
    ]
    assert recorded == [('user', usage)]
    assert any('Upstream provider error' in event for event in events)


@pytest.mark.asyncio
async def test_stream_schedules_terminal_usage_when_cancelled_after_message_delta(monkeypatch):
    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def __aiter__(self):
            async def events():
                yield SimpleNamespace(
                    type='message_start',
                    message=SimpleNamespace(
                        usage=SimpleNamespace(
                            input_tokens=3,
                            cache_creation_input_tokens=1,
                            cache_read_input_tokens=2,
                            output_tokens=0,
                        )
                    ),
                )
                yield SimpleNamespace(
                    type='message_delta',
                    delta=SimpleNamespace(stop_reason='end_turn'),
                    usage=SimpleNamespace(
                        input_tokens=0,
                        cache_creation_input_tokens=0,
                        cache_read_input_tokens=0,
                        output_tokens=4,
                    ),
                )

            return events()

        async def get_final_message(self):
            raise asyncio.CancelledError

    monkeypatch.setattr(
        desktop_chat,
        'anthropic_client',
        SimpleNamespace(messages=SimpleNamespace(stream=lambda **_: Stream())),
    )
    recorded = []

    async def record_usage(uid, usage):
        recorded.append((uid, usage))

    monkeypatch.setattr(desktop_chat, '_record_usage', record_usage)
    with pytest.raises(asyncio.CancelledError):
        _ = [
            event
            async for event in desktop_chat._stream(
                {'model': 'claude-sonnet-4-6', 'max_tokens': 1, 'messages': []}, 'omi-sonnet', 'user'
            )
        ]
    await asyncio.sleep(0)
    assert recorded == [
        (
            'user',
            {
                'input_tokens': 3,
                'output_tokens': 4,
                'cache_read_input_tokens': 2,
                'cache_creation_input_tokens': 1,
            },
        )
    ]


@pytest.mark.asyncio
async def test_chat_completions_routes_public_web_search_to_direct_anthropic(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(desktop_chat, '_record_usage', lambda *_args, **_kwargs: _done())

    class Messages:
        async def create(self, **payload):
            assert payload['tools'] == [desktop_chat._WEB_SEARCH_TOOL]
            return SimpleNamespace(
                id='msg_web',
                content=[SimpleNamespace(type='text', text='grounded')],
                stop_reason='end_turn',
                usage=SimpleNamespace(
                    input_tokens=1, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=1
                ),
            )

    monkeypatch.setattr(
        desktop_chat,
        'get_direct_anthropic_client',
        lambda **_: SimpleNamespace(messages=Messages()),
    )

    class GatewayClient:
        async def post(self, *args, **kwargs):
            raise AssertionError('public web search must use direct Anthropic')

    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_client', lambda: GatewayClient())
    response = await desktop_chat.chat_completions(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': 'Search the web for current news.'}],
            'omi_web_search': True,
        },
        uid='user-1',
        x_app_platform=None,
        x_omi_chat_contract_version=None,
        x_omi_request_id=None,
    )
    assert b'grounded' in response.body


@pytest.mark.asyncio
async def test_chat_completions_routes_pi_public_web_policy_to_direct_anthropic(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(desktop_chat, '_record_usage', lambda *_args, **_kwargs: _done())

    class Messages:
        async def create(self, **payload):
            assert payload['tools'] == [desktop_chat._WEB_SEARCH_TOOL]
            return SimpleNamespace(
                id='msg_policy_web',
                content=[SimpleNamespace(type='text', text='grounded')],
                stop_reason='end_turn',
                usage=SimpleNamespace(
                    input_tokens=1, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=1
                ),
            )

    monkeypatch.setattr(
        desktop_chat,
        'get_direct_anthropic_client',
        lambda **_: SimpleNamespace(messages=Messages()),
    )

    class GatewayClient:
        async def post(self, *args, **kwargs):
            raise AssertionError('Pi public web policy must use direct Anthropic')

    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_client', lambda: GatewayClient())
    response = await desktop_chat.chat_completions(
        {
            'model': 'omi-sonnet',
            'messages': [
                {
                    'role': 'user',
                    'content': f'{desktop_chat._PUBLIC_WEB_ROUTING_INSTRUCTION}\n\nWhat is new today?',
                }
            ],
        },
        uid='user-1',
        x_app_platform=None,
        x_omi_chat_contract_version=None,
        x_omi_request_id=None,
    )
    assert b'grounded' in response.body


@pytest.mark.asyncio
async def test_chat_completions_records_usage_when_pause_turn_limit_is_exhausted(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: False)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(desktop_chat, '_record_chat_quota_question', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'get_direct_anthropic_client', lambda **_: object())
    usage = {'input_tokens': 6, 'output_tokens': 4, 'web_search_requests': 3}
    error = desktop_chat._PauseTurnContinuationLimitError(usage, SimpleNamespace(), [])

    async def raise_limit(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(desktop_chat, '_create_with_pause_turn_continuations', raise_limit)
    recorded = []

    async def record_usage(uid, value):
        recorded.append((uid, value))

    monkeypatch.setattr(desktop_chat, '_record_usage', record_usage)
    with pytest.raises(desktop_chat.HTTPException) as raised:
        await desktop_chat.chat_completions(
            {
                'model': 'omi-sonnet',
                'messages': [{'role': 'user', 'content': 'Search the web for current news.'}],
                'omi_web_search': True,
            },
            uid='user-1',
            x_app_platform=None,
            x_omi_chat_contract_version=None,
            x_omi_request_id=None,
        )

    assert raised.value.status_code == 502
    assert recorded == [('user-1', usage)]


@pytest.mark.asyncio
async def test_chat_completions_gateway_mode_uses_luna_auto_lane(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setattr(
        desktop_chat,
        'get_byok_key',
        lambda provider: 'sk-openai' if provider == 'openai' else None,
    )
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_base_url', lambda: 'http://gateway.test')
    recorded = []

    async def record_usage(uid, usage):
        recorded.append((uid, usage))

    monkeypatch.setattr(desktop_chat, '_record_usage', record_usage)

    class GatewayClient:
        def __init__(self):
            self.calls = []

        async def post(self, url, *, headers, json):
            self.calls.append({'url': url, 'headers': headers, 'json': json})
            assert headers.get('X-Omi-User-Uid') == 'user-1'
            assert headers.get('X-Omi-LLM-Feature') == 'chat_agent'
            return httpx.Response(
                200,
                json={
                    'id': 'chat-1',
                    'choices': [{'message': {'content': 'hello'}}],
                    'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5},
                },
                request=httpx.Request('POST', url),
            )

    client = GatewayClient()
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_client', lambda: client)

    response = await desktop_chat.chat_completions(
        {'messages': [{'role': 'user', 'content': 'hello'}]},
        uid='user-1',
        x_app_platform=None,
        x_omi_chat_contract_version=None,
        x_omi_request_id=None,
    )

    assert b'"id":"chat-1"' in response.body
    assert client.calls[0]['url'] == 'http://gateway.test/v1/chat/completions'
    assert client.calls[0]['headers']['X-Omi-Request-ID']
    assert client.calls[0]['json']['model'] == 'omi:auto:chat-agent'
    assert recorded and recorded[0][0] == 'user-1'
    assert recorded[0][1].input_tokens == 3
    assert recorded[0][1].output_tokens == 2


@pytest.mark.asyncio
async def test_gateway_rejection_does_not_record_quota_question(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _provider: None)
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_base_url', lambda: 'http://gateway.test')
    monkeypatch.setattr(desktop_chat.gateway_circuit, 'reset', lambda: None)
    quota_calls = []

    async def record_quota(*args, **kwargs):
        quota_calls.append((args, kwargs))

    monkeypatch.setattr(desktop_chat, '_record_chat_quota_question', record_quota)

    class GatewayClient:
        async def post(self, url, *, headers, json):
            return httpx.Response(
                400,
                json={'error': {'message': 'invalid request'}},
                request=httpx.Request('POST', url),
            )

    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_client', lambda: GatewayClient())

    with pytest.raises(desktop_chat.HTTPException) as error:
        await desktop_chat.chat_completions(
            {'messages': [{'role': 'user', 'content': 'hello'}]},
            uid='user-1',
            x_app_platform=None,
            x_omi_chat_contract_version=None,
            x_omi_request_id='request-1',
        )

    assert error.value.status_code == 502
    assert quota_calls == []


def _wire_direct_lane(monkeypatch, quota_calls):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: False)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _provider: None)

    async def record_quota(*args, **kwargs):
        quota_calls.append((args, kwargs))

    monkeypatch.setattr(desktop_chat, '_record_chat_quota_question', record_quota)

    async def record_usage(*_args, **_kwargs):
        return None

    monkeypatch.setattr(desktop_chat, '_record_usage', record_usage)
    monkeypatch.setattr(desktop_chat, '_record_usage_resilient', record_usage)


async def _drain(response):
    return ''.join([chunk async for chunk in response.body_iterator])


@pytest.mark.asyncio
async def test_direct_stream_rejection_does_not_record_quota_question(monkeypatch):
    quota_calls = []
    _wire_direct_lane(monkeypatch, quota_calls)

    class Stream:
        async def __aenter__(self):
            raise RuntimeError('upstream rejected the request')

        async def __aexit__(self, *_):
            return None

    monkeypatch.setattr(
        desktop_chat,
        'get_direct_anthropic_client',
        lambda **_: SimpleNamespace(messages=SimpleNamespace(stream=lambda **_kwargs: Stream())),
    )

    response = await desktop_chat.chat_completions(
        {'model': 'omi-sonnet', 'stream': True, 'messages': [{'role': 'user', 'content': 'hello'}]},
        uid='user-1',
        x_app_platform='windows',
        x_omi_chat_contract_version=None,
        x_omi_request_id='request-1',
    )
    body = await _drain(response)

    assert 'Upstream provider error' in body
    assert quota_calls == []


@pytest.mark.asyncio
async def test_direct_stream_records_one_quota_question_when_upstream_accepts(monkeypatch):
    quota_calls = []
    _wire_direct_lane(monkeypatch, quota_calls)

    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get_final_message(self):
            return SimpleNamespace(
                content=[SimpleNamespace(type='text', text='hi')], stop_reason='end_turn', usage=None
            )

        def __aiter__(self):
            async def events():
                yield SimpleNamespace(type='content_block_delta', delta=SimpleNamespace(type='text_delta', text='hi'))

            return events()

    monkeypatch.setattr(
        desktop_chat,
        'get_direct_anthropic_client',
        lambda **_: SimpleNamespace(messages=SimpleNamespace(stream=lambda **_kwargs: Stream())),
    )

    response = await desktop_chat.chat_completions(
        {'model': 'omi-sonnet', 'stream': True, 'messages': [{'role': 'user', 'content': 'hello'}]},
        uid='user-1',
        x_app_platform='windows',
        x_omi_chat_contract_version=None,
        x_omi_request_id='request-1',
    )
    body = await _drain(response)

    assert 'hi' in body
    assert [call[0] for call in quota_calls] == [('user-1', 'request-1', 'windows')]


@pytest.mark.asyncio
async def test_direct_json_upstream_error_does_not_record_quota_question(monkeypatch):
    quota_calls = []
    _wire_direct_lane(monkeypatch, quota_calls)
    monkeypatch.setattr(desktop_chat, 'get_direct_anthropic_client', lambda **_: object())

    async def raise_upstream(*_args, **_kwargs):
        raise RuntimeError('upstream rejected the request')

    monkeypatch.setattr(desktop_chat, '_create_with_pause_turn_continuations', raise_upstream)

    with pytest.raises(desktop_chat.HTTPException) as error:
        await desktop_chat.chat_completions(
            {'model': 'omi-sonnet', 'messages': [{'role': 'user', 'content': 'hello'}]},
            uid='user-1',
            x_app_platform='windows',
            x_omi_chat_contract_version=None,
            x_omi_request_id='request-1',
        )

    assert error.value.status_code == 502
    assert quota_calls == []


@pytest.mark.asyncio
async def test_chat_completions_rejects_unknown_explicit_model_before_gateway(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _provider: None)

    with pytest.raises(desktop_chat.HTTPException) as error:
        await desktop_chat.chat_completions(
            {'model': 'client-model', 'messages': [{'role': 'user', 'content': 'hello'}]},
            uid='user-1',
            x_app_platform=None,
            x_omi_chat_contract_version=None,
            x_omi_request_id=None,
        )

    assert error.value.status_code == 400
    assert error.value.detail == 'unsupported model'


@pytest.mark.asyncio
async def test_chat_completions_rejects_explicit_null_model_before_gateway(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _provider: None)

    with pytest.raises(desktop_chat.HTTPException) as error:
        await desktop_chat.chat_completions(
            {'model': None, 'messages': [{'role': 'user', 'content': 'hello'}]},
            uid='user-1',
            x_app_platform=None,
            x_omi_chat_contract_version=None,
            x_omi_request_id=None,
        )

    assert error.value.status_code == 400
    assert error.value.detail == 'unsupported model'


def test_gateway_body_preserves_validated_image_url():
    png = 'iVBORw0KGgo='
    body = desktop_chat._gateway_body(
        {
            'model': 'client-model',
            'messages': [
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': 'look'},
                        {'type': 'image_url', 'image_url': {'url': f'data:image/png;base64,{png}'}},
                    ],
                }
            ],
        }
    )
    assert body['model'] == 'omi:auto:chat-agent'
    assert body['messages'][0]['content'][1]['type'] == 'image_url'


def test_gateway_body_preserves_https_image_url():
    body = desktop_chat._gateway_body(
        {
            'model': 'client-model',
            'messages': [
                {
                    'role': 'user',
                    'content': [{'type': 'image_url', 'image_url': {'url': 'https://example.com/image.png'}}],
                }
            ],
        }
    )
    assert body['messages'][0]['content'][0]['image_url']['url'] == 'https://example.com/image.png'


def test_gateway_body_rejects_unsupported_image_url_instead_of_dropping_it():
    with pytest.raises(ValueError, match='data URL or an HTTPS URL'):
        desktop_chat._gateway_body(
            {
                'model': 'client-model',
                'messages': [
                    {
                        'role': 'user',
                        'content': [{'type': 'image_url', 'image_url': {'url': 'file:///tmp/image.png'}}],
                    }
                ],
            }
        )


def test_specialist_haiku_requests_bypass_managed_chat_agent():
    assert not desktop_chat._uses_managed_chat_agent({'model': 'claude-haiku-4-5-20251001'})
    assert not desktop_chat._uses_managed_chat_agent({'model': 'omi-opus'})
    assert not desktop_chat._uses_managed_chat_agent({'model': 'claude-opus-4-6'})
    assert desktop_chat._uses_managed_chat_agent({'model': 'claude-sonnet-4-6'})
    assert desktop_chat._uses_managed_chat_agent({})
    assert not desktop_chat._uses_managed_chat_agent({'model': 'client-model'})


def test_gateway_body_normalizes_openai_tool_history_content():
    body = desktop_chat._gateway_body(
        {
            'model': 'client-model',
            'messages': [
                {
                    'role': 'assistant',
                    'tool_calls': [
                        {
                            'id': 'call_1',
                            'type': 'function',
                            'function': {'name': 'weather', 'arguments': '{"city":"NYC"}'},
                        }
                    ],
                },
                {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'sunny'},
                {'role': 'assistant', 'content': None, 'tool_calls': []},
            ],
        }
    )
    assert body['messages'][0]['content'] == ''
    assert body['messages'][0]['tool_calls'][0]['id'] == 'call_1'
    assert body['messages'][1]['content'] == 'sunny'
    assert body['messages'][2]['content'] == ''


def test_openai_usage_as_anthropic_does_not_double_count_cached_tokens():
    usage = desktop_chat._openai_usage_as_anthropic(
        {
            'prompt_tokens': 100,
            'completion_tokens': 10,
            'total_tokens': 110,
            'prompt_tokens_details': {'cached_tokens': 40},
        }
    )
    assert usage.input_tokens == 60
    assert usage.output_tokens == 10
    assert usage.cache_read_input_tokens == 40
    assert usage.input_tokens + usage.cache_read_input_tokens == 100


@pytest.mark.asyncio
async def test_stream_gateway_emits_sse_error_on_http_failure(monkeypatch):
    class StreamResponse:
        status_code = 503

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def aiter_bytes(self):
            if False:
                yield b''

    class GatewayClient:
        def stream(self, *_args, **_kwargs):
            return StreamResponse()

    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_client', lambda: GatewayClient())
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_base_url', lambda: 'http://gateway.test')
    monkeypatch.setattr(desktop_chat, 'llm_gateway_headers', lambda **_kwargs: {})
    monkeypatch.setattr(desktop_chat.gateway_circuit, 'reset', lambda: None)

    events = [chunk async for chunk in desktop_chat._stream_gateway({'model': 'x', 'messages': []}, 'user-1')]
    assert b'Upstream provider error' in events[0]
    assert events[-1] == b'data: [DONE]\n\n'


@pytest.mark.asyncio
async def test_stream_gateway_records_usage_from_sse(monkeypatch):
    class StreamResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def aiter_bytes(self):
            yield b'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"hi"},"finish_reason":null}]}\n\n'
            yield (
                b'data: {"id":"chatcmpl-1","choices":[],'
                b'"usage":{"prompt_tokens":9,"completion_tokens":2,"total_tokens":11,'
                b'"prompt_tokens_details":{"cached_tokens":3}}}\n\n'
            )
            yield b'data: [DONE]\n\n'

    class GatewayClient:
        def stream(self, *_args, **_kwargs):
            return StreamResponse()

    recorded = []

    async def record_usage(uid, usage):
        recorded.append((uid, usage))

    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_client', lambda: GatewayClient())
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_base_url', lambda: 'http://gateway.test')
    monkeypatch.setattr(desktop_chat, 'llm_gateway_headers', lambda **_kwargs: {})
    monkeypatch.setattr(desktop_chat.gateway_circuit, 'reset', lambda: None)
    monkeypatch.setattr(desktop_chat, '_record_chat_quota_question', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, '_record_usage', record_usage)

    events = [chunk async for chunk in desktop_chat._stream_gateway({'model': 'x', 'messages': []}, 'user-1')]
    assert any(b'"content":"hi"' in chunk for chunk in events)
    assert recorded and recorded[0][0] == 'user-1'
    assert recorded[0][1].input_tokens == 6
    assert recorded[0][1].cache_read_input_tokens == 3
    assert recorded[0][1].output_tokens == 2


@pytest.mark.asyncio
async def test_chat_completions_gateway_mode_disabled_for_byok(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda provider: 'sk-test' if provider == 'anthropic' else None)
    monkeypatch.setattr(desktop_chat, '_record_usage', lambda *_args, **_kwargs: _done())
    fallbacks = []
    monkeypatch.setattr(desktop_chat, 'record_fallback', lambda **fields: fallbacks.append(fields))

    class Messages:
        async def create(self, **payload):
            assert payload['model'] == 'claude-sonnet-4-6'
            return SimpleNamespace(
                id='msg_byok',
                content=[SimpleNamespace(type='text', text='legacy')],
                stop_reason='end_turn',
                usage=SimpleNamespace(
                    input_tokens=1, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=1
                ),
            )

    gateway_calls = []

    class GatewayClient:
        async def post(self, *args, **kwargs):
            gateway_calls.append((args, kwargs))
            raise AssertionError('BYOK must not use managed gateway lane')

    monkeypatch.setattr(
        desktop_chat,
        'get_direct_anthropic_client',
        lambda **_: SimpleNamespace(messages=Messages()),
    )
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_client', lambda: GatewayClient())

    response = await desktop_chat.chat_completions(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': 'hello'}],
            'max_tokens': 16,
        },
        uid='user-1',
        x_app_platform=None,
        x_omi_chat_contract_version=None,
        x_omi_request_id=None,
    )

    assert gateway_calls == []
    assert b'"content":"legacy"' in response.body
    assert fallbacks == [
        {
            'component': 'llm_gateway',
            'from_mode': 'managed_gateway',
            'to_mode': 'anthropic_byok',
            'reason': 'byok',
            'outcome': 'recovered',
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('requested_model', 'translated_model'),
    [
        ('claude-haiku-4-5-20251001', 'claude-haiku-4-5'),
        ('omi-opus', 'claude-opus-4-6'),
    ],
)
async def test_chat_completions_specialist_models_bypass_managed_gateway(
    monkeypatch, requested_model, translated_model
):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(desktop_chat, '_record_usage', lambda *_args, **_kwargs: _done())

    class Messages:
        async def create(self, **payload):
            assert payload['model'] == translated_model
            return SimpleNamespace(
                id='msg_haiku',
                content=[SimpleNamespace(type='text', text='specialist')],
                stop_reason='end_turn',
                usage=SimpleNamespace(
                    input_tokens=1, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=1
                ),
            )

    monkeypatch.setattr(
        desktop_chat,
        'get_direct_anthropic_client',
        lambda **_: SimpleNamespace(messages=Messages()),
    )

    class GatewayClient:
        async def post(self, *args, **kwargs):
            raise AssertionError('specialist Haiku requests must not use managed gateway lane')

    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_client', lambda: GatewayClient())

    response = await desktop_chat.chat_completions(
        {
            'model': requested_model,
            'messages': [{'role': 'user', 'content': 'extract this'}],
            'max_tokens': 16,
        },
        uid='user-1',
        x_app_platform=None,
        x_omi_chat_contract_version=None,
        x_omi_request_id=None,
    )

    assert b'"content":"specialist"' in response.body


@pytest.mark.asyncio
async def test_chat_completions_gateway_config_error_is_http_503(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)

    def raise_config_error():
        raise RuntimeError('OMI_LLM_GATEWAY_URL required')

    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', raise_config_error)

    with pytest.raises(desktop_chat.HTTPException) as error:
        await desktop_chat.chat_completions(
            {'model': 'client-model', 'messages': [{'role': 'user', 'content': 'hello'}]},
            uid='user-1',
            x_app_platform=None,
            x_omi_chat_contract_version=None,
            x_omi_request_id=None,
        )
    assert error.value.status_code == 503


async def _done():
    return None


@pytest.mark.asyncio
async def test_server_metering_fails_closed_and_byok_bypasses(monkeypatch):
    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_chat, 'run_blocking', run_blocking)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(desktop_chat.redis_db, 'check_rate_limit', lambda *_: (_ for _ in ()).throw(RuntimeError()))

    with pytest.raises(desktop_chat.HTTPException) as error:
        await desktop_chat._meter_server_request('user')
    assert error.value.status_code == 503

    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _: 'key')
    await desktop_chat._meter_server_request('user')


@pytest.mark.asyncio
async def test_server_metering_rejects_exhausted_user(monkeypatch):
    async def run_blocking(_, function, *args):
        return function(*args)

    monkeypatch.setattr(desktop_chat, 'run_blocking', run_blocking)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(desktop_chat.redis_db, 'check_rate_limit', lambda *_: (False, 0, 37))

    with pytest.raises(desktop_chat.HTTPException) as error:
        await desktop_chat._meter_server_request('user')
    assert error.value.status_code == 429
    assert error.value.headers == {'Retry-After': '37'}
