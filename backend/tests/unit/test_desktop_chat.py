import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from routers import desktop_chat
from utils.observability import journeys


def _authorized_request(body, *, web_search_allowed: bool = True):
    """Translate a body as an authorized principal, so these cases keep asserting
    the non-authorization conditions that gate server-side web search."""
    status = 'authorized' if web_search_allowed else 'denied'
    return desktop_chat._request(body, web_search_authorization=status)


def _fail_direct_anthropic(message: str):
    def _raise(**_kwargs):
        raise AssertionError(message)

    return _raise


def test_request_translates_openai_tool_history_and_alias():
    public_model, payload = _authorized_request(
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
    # Response identity is the SERVED model (OpenAI chat-completions convention:
    # response.model names the model that generated the response), never the
    # requested alias — clients attribute answers from it.
    assert public_model == 'claude-sonnet-4-6'
    assert payload['model'] == 'claude-sonnet-4-6'
    assert payload['max_tokens'] == 16_384
    assert payload['system'] == 'be concise'
    assert payload['messages'][1]['content'][0]['tool_use_id'] == 'call_1'
    assert payload['tool_choice'] == {'type': 'auto'}


def test_request_injects_web_search_for_desktop_opt_in():
    _, payload = _authorized_request(
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
    _, payload = _authorized_request(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': 'From my conversations, what did I say about the trip?'}],
            'omi_web_search': True,
        }
    )
    assert 'tools' not in payload

    _, payload = _authorized_request(
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

    _, payload = _authorized_request(
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

    _, payload = _authorized_request(
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

    _, payload = _authorized_request(
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
    _, payload = _authorized_request(
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
    _, payload = _authorized_request(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': content}],
            'omi_web_search': True,
        }
    )
    assert payload['tools'] == [desktop_chat._WEB_SEARCH_TOOL]


def test_request_scopes_without_searching_to_public_web_objects():
    _, payload = _authorized_request(
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
    _, payload = _authorized_request(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': 'I got no web search results; search the web again.'}],
            'omi_web_search': True,
        }
    )
    assert payload['tools'] == [desktop_chat._WEB_SEARCH_TOOL]


def test_request_classifies_only_trusted_query_before_tool_context():
    _, private_payload = _authorized_request(
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

    # A public-looking trusted query no longer earns server-side web search once
    # tool output is inlined behind the untrusted marker: that inlined text is the
    # private context the Anthropic-side query could carry out (issue #11412).
    _, public_payload = _authorized_request(
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
    assert 'tools' not in public_payload

    _, clean_payload = _authorized_request(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': 'Search the web for current news.'}],
            'omi_web_search': True,
        }
    )
    assert clean_payload['tools'] == [desktop_chat._WEB_SEARCH_TOOL]


def test_request_keeps_client_tools_without_web_search_and_skips_haiku_or_none():
    client_tools = [{'type': 'function', 'function': {'name': 'weather', 'parameters': {'type': 'object'}}}]
    _, payload = _authorized_request(
        {'model': 'omi-sonnet', 'messages': [{'role': 'user', 'content': 'Plan my day'}], 'tools': client_tools}
    )
    assert [tool['name'] for tool in payload['tools']] == ['weather']

    _, payload = _authorized_request(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': 'Use the weather tool'}],
            'tools': client_tools,
            'tool_choice': 'required',
        }
    )
    assert [tool['name'] for tool in payload['tools']] == ['weather']
    assert payload['tool_choice'] == {'type': 'any'}

    _, payload = _authorized_request(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': 'Use the weather tool'}],
            'tools': client_tools,
            'tool_choice': {'type': 'function', 'function': {'name': 'weather'}},
        }
    )
    assert [tool['name'] for tool in payload['tools']] == ['weather']
    assert payload['tool_choice'] == {'type': 'tool', 'name': 'weather'}

    _, payload = _authorized_request(
        {
            'model': 'claude-haiku-4-5',
            'messages': [{'role': 'user', 'content': 'Search the web for this'}],
            'omi_web_search': True,
        }
    )
    assert 'tools' not in payload

    _, payload = _authorized_request(
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
    _, payload = _authorized_request(
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
    _, payload = _authorized_request(
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
    _, payload = _authorized_request(
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
    _authorized_request(
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
    _authorized_request(
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
    exclusions = []

    async def run_blocking(_, function, *args):
        calls.append((function, args))
        function(*args)

    monkeypatch.setattr(desktop_chat, 'run_blocking', run_blocking)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _: 'anthropic-key')
    # The exclusion call site passes firestore_client=get_customer_firestore_client(),
    # which is evaluated before the stubbed recorder runs and builds a real client --
    # resolving GCP credentials and reaching the metadata server under the hermetic
    # network guard. Production must keep using the customer client (record_llm_cost_exclusion
    # falls back to the default `db`, not the customer client, when passed None), so stub
    # the factory here rather than dropping the argument.
    monkeypatch.setattr(desktop_chat, 'get_customer_firestore_client', lambda: object())
    monkeypatch.setattr(
        desktop_chat.llm_usage_db,
        'record_llm_cost_exclusion',
        lambda *args, **kwargs: exclusions.append((args, kwargs)),
    )
    await desktop_chat._record_usage('user', {'input_tokens': 3, 'web_search_requests': 1})
    assert len(calls) == 1
    assert exclusions[0][0] == ('user',)
    assert exclusions[0][1]['cost_exclusion'] == 'byok_provider_cost'


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
async def test_chat_completions_routes_public_web_search_to_managed_perplexity_lane(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_desktop_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(desktop_chat, '_record_usage', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_base_url', lambda: 'http://gateway.test')
    monkeypatch.setattr(
        desktop_chat,
        'get_direct_anthropic_client',
        _fail_direct_anthropic('public web search must not construct a direct Anthropic client'),
    )

    class GatewayClient:
        def __init__(self):
            self.calls = []

        async def post(self, url, *, headers, json):
            self.calls.append({'url': url, 'headers': headers, 'json': json})
            return httpx.Response(
                200,
                json={
                    'id': 'chat-web',
                    'choices': [{'message': {'content': 'grounded from https://example.com'}}],
                    'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5},
                },
                request=httpx.Request('POST', url),
            )

    client = GatewayClient()
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_client', lambda: client)
    response = await desktop_chat.chat_completions(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': 'Search the web for current news.'}],
            'omi_web_search': True,
            'tools': [{'type': 'function', 'function': {'name': 'weather', 'parameters': {'type': 'object'}}}],
        },
        uid='user-1',
        x_app_platform=None,
        x_omi_chat_contract_version=None,
        x_omi_request_id=None,
    )
    assert b'grounded from https://example.com' in response.body
    assert client.calls[0]['json']['model'] == 'omi:auto:web-search'
    assert 'tools' not in client.calls[0]['json']
    assert 'tool_choice' not in client.calls[0]['json']
    assert client.calls[0]['headers'].get('X-Omi-LLM-Feature') == 'web_search'
    assert desktop_chat._PUBLIC_WEB_ROUTING_INSTRUCTION in client.calls[0]['json']['messages'][0]['content']


@pytest.mark.asyncio
async def test_chat_completions_routes_pi_public_web_policy_to_managed_perplexity_lane(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_desktop_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(desktop_chat, '_record_usage', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_base_url', lambda: 'http://gateway.test')
    monkeypatch.setattr(
        desktop_chat,
        'get_direct_anthropic_client',
        _fail_direct_anthropic('Pi public web policy must not construct a direct Anthropic client'),
    )

    class GatewayClient:
        def __init__(self):
            self.calls = []

        async def post(self, url, *, headers, json):
            self.calls.append(json)
            return httpx.Response(
                200,
                json={
                    'id': 'chat-policy-web',
                    'choices': [{'message': {'content': 'grounded'}}],
                    'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5},
                },
                request=httpx.Request('POST', url),
            )

    client = GatewayClient()
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_client', lambda: client)
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
    assert client.calls[0]['model'] == 'omi:auto:web-search'
    assert client.calls[0]['messages'][0]['content'].startswith(desktop_chat._PUBLIC_WEB_ROUTING_INSTRUCTION)


@pytest.mark.asyncio
async def test_chat_completions_streams_public_web_search_through_managed_perplexity_lane(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_desktop_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(desktop_chat, '_record_usage', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_base_url', lambda: 'http://gateway.test')
    monkeypatch.setattr(
        desktop_chat,
        'get_direct_anthropic_client',
        _fail_direct_anthropic('streaming public web search must not construct a direct Anthropic client'),
    )

    class StreamResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def aiter_bytes(self):
            yield b'data: {"id":"chatcmpl-1","choices":[{"delta":{"content":"grounded"},"finish_reason":"stop"}]}\n\n'
            yield (
                b'data: {"id":"chatcmpl-1","choices":[],'
                b'"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5}}\n\n'
            )
            yield b'data: [DONE]\n\n'

    class GatewayClient:
        def __init__(self):
            self.calls = []

        def stream(self, method, url, **kwargs):
            self.calls.append({'method': method, 'url': url, **kwargs})
            return StreamResponse()

        async def post(self, *args, **kwargs):
            raise AssertionError('streaming public web search must use stream()')

    client = GatewayClient()
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_client', lambda: client)
    response = await desktop_chat.chat_completions(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': 'Search the web for current news.'}],
            'omi_web_search': True,
            'stream': True,
        },
        uid='user-1',
        x_app_platform=None,
        x_omi_chat_contract_version=None,
        x_omi_request_id=None,
    )
    body = await _drain(response)
    assert 'grounded' in body
    assert client.calls[0]['json']['model'] == 'omi:auto:web-search'
    assert 'tools' not in client.calls[0]['json']


@pytest.mark.asyncio
async def test_chat_completions_records_usage_when_pause_turn_limit_is_exhausted(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_desktop_chat_quota', lambda *_args, **_kwargs: None)
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
    monkeypatch.setattr(desktop_chat, 'enforce_desktop_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setenv('OMI_JIT_PROACTIVITY_BUDGET_CONTRACT', 'jit-cloud-qa-v1')
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
                headers={'x-omi-jit-gateway-receipt': 'trusted-receipt'},
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
        x_omi_jit_contract_version='jit-cloud-qa-v1',
        x_omi_jit_run_id='jit-relay-run-1',
        x_omi_jit_max_attempts='3',
        x_omi_jit_max_output_tokens='2048',
        x_omi_jit_max_input_tokens='32768',
        x_omi_jit_max_spend_micro_usd='50000',
    )

    assert b'"id":"chat-1"' in response.body
    assert client.calls[0]['url'] == 'http://gateway.test/v1/chat/completions'
    assert client.calls[0]['headers']['X-Omi-Request-ID']
    assert client.calls[0]['headers']['X-Omi-Jit-Contract-Version'] == 'jit-cloud-qa-v1'
    assert client.calls[0]['headers']['X-Omi-Jit-Run-Id'] == 'jit-relay-run-1'
    assert client.calls[0]['headers']['X-Omi-Jit-Max-Attempts'] == '3'
    assert client.calls[0]['headers']['X-Omi-Jit-Max-Output-Tokens'] == '2048'
    assert client.calls[0]['headers']['X-Omi-Jit-Max-Input-Tokens'] == '32768'
    assert client.calls[0]['headers']['X-Omi-Jit-Max-Spend-Micro-Usd'] == '50000'
    assert response.headers['X-Omi-Jit-Gateway-Receipt'] == 'trusted-receipt'
    assert client.calls[0]['json']['model'] == 'omi:auto:chat-agent'
    assert recorded and recorded[0][0] == 'user-1'
    assert recorded[0][1].input_tokens == 3
    assert recorded[0][1].output_tokens == 2


@pytest.mark.asyncio
async def test_gateway_rejection_does_not_record_quota_question(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_desktop_chat_quota', lambda *_args, **_kwargs: None)
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
    monkeypatch.setattr(desktop_chat, 'enforce_desktop_chat_quota', lambda *_args, **_kwargs: None)
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
    # The direct Anthropic path yields str chunks; the managed gateway path
    # proxies raw bytes via httpx aiter_bytes. Accept both.
    chunks = [chunk async for chunk in response.body_iterator]
    return ''.join(c.decode() if isinstance(c, (bytes, bytearray)) else c for c in chunks)


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
    monkeypatch.setattr(desktop_chat, 'enforce_desktop_chat_quota', lambda *_args, **_kwargs: None)
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
    monkeypatch.setattr(desktop_chat, 'enforce_desktop_chat_quota', lambda *_args, **_kwargs: None)
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


def test_legacy_haiku_aliases_use_structured_lane_not_chat_agent():
    assert desktop_chat._uses_managed_chat_agent({'model': 'claude-haiku-4-5-20251001'})
    assert desktop_chat._managed_lane_id({'model': 'claude-haiku-4-5-20251001'}) == 'omi:auto:chat-structured'
    assert desktop_chat._uses_managed_chat_agent({'model': 'omi-opus'})
    assert desktop_chat._uses_managed_chat_agent({'model': 'claude-opus-4-6'})
    assert desktop_chat._uses_managed_chat_agent({'model': 'claude-sonnet-4-6'})
    assert desktop_chat._uses_managed_chat_agent({'model': 'omi:auto:chat-agent'})
    assert desktop_chat._uses_managed_chat_agent({'model': 'omi-luna'})
    assert desktop_chat._uses_managed_chat_agent({'model': ''})
    assert desktop_chat._uses_managed_chat_agent({})
    assert not desktop_chat._uses_managed_chat_agent({'model': 'client-model'})


def test_structured_aliases_route_to_the_structured_lane_not_chat():
    for alias in (
        'omi-structured',
        'OMI-Structured',
        'omi:auto:chat-structured',
        'claude-haiku-4-5',
        'claude-haiku-4-5-20251001',
    ):
        assert desktop_chat._uses_managed_chat_agent({'model': alias})
        assert desktop_chat._managed_lane_id({'model': alias}) == 'omi:auto:chat-structured'

    # Conversational and omitted models keep the chat-agent lane.
    for alias in ('omi-luna', 'omi-auto', 'claude-sonnet-4-6', 'omi-opus', ''):
        assert desktop_chat._managed_lane_id({'model': alias}) == 'omi:auto:chat-agent'
    assert desktop_chat._managed_lane_id({}) == 'omi:auto:chat-agent'


def test_structured_lane_traffic_is_attributed_to_its_own_feature():
    """Structured-lane calls must not land in the ledger as chat-agent traffic."""
    assert desktop_chat._gateway_feature_for_lane('omi:auto:chat-structured') == 'chat_structured'
    assert desktop_chat._gateway_feature_for_lane('omi:auto:chat-agent') == 'chat_agent'
    assert desktop_chat._gateway_feature_for_lane('omi:auto:web-search') == 'web_search'
    assert desktop_chat._gateway_request_headers(
        'req-1', 'omi:auto:chat-structured'
    ) != desktop_chat._gateway_request_headers('req-1', 'omi:auto:chat-agent')
    assert desktop_chat._gateway_request_headers(
        'req-1', 'omi:auto:web-search'
    ) != desktop_chat._gateway_request_headers('req-1', 'omi:auto:chat-agent')


def test_gateway_body_stamps_the_selected_lane():
    request = {'model': 'omi-structured', 'messages': [{'role': 'user', 'content': 'plan this'}]}
    lane = desktop_chat._managed_lane_id(request)
    assert desktop_chat._gateway_body(request, lane)['model'] == 'omi:auto:chat-structured'
    # Default stays the chat lane for callers that do not pass one.
    assert desktop_chat._gateway_body(request)['model'] == 'omi:auto:chat-agent'


def test_gateway_body_strips_tools_on_the_web_search_lane():
    request = {
        'model': 'omi-sonnet',
        'messages': [{'role': 'system', 'content': 'be concise'}, {'role': 'user', 'content': 'news?'}],
        'tools': [{'type': 'function', 'function': {'name': 'weather', 'parameters': {'type': 'object'}}}],
        'tool_choice': 'auto',
        'omi_web_search': True,
    }
    body = desktop_chat._gateway_body(request, desktop_chat.WEB_SEARCH_AUTO_LANE_ID)
    assert body['model'] == 'omi:auto:web-search'
    assert 'tools' not in body
    assert 'tool_choice' not in body
    assert 'omi_web_search' not in body
    assert desktop_chat._PUBLIC_WEB_ROUTING_INSTRUCTION in body['messages'][0]['content']


def test_gateway_body_appends_web_search_retrieval_appendix_on_the_last_user_message():
    request = {
        'model': 'omi-sonnet',
        'messages': [
            {'role': 'system', 'content': 'be concise'},
            {'role': 'user', 'content': 'how long did Whisper Flow take to build v1?'},
            {'role': 'assistant', 'content': 'earlier turn'},
            {'role': 'user', 'content': 'news?'},
        ],
        'tools': [{'type': 'function', 'function': {'name': 'weather', 'parameters': {'type': 'object'}}}],
    }
    body = desktop_chat._gateway_body(request, desktop_chat.WEB_SEARCH_AUTO_LANE_ID)
    # The appendix lands on the last user message only, next to the policy
    # instruction the lane already injects elsewhere in the transcript.
    assert body['messages'][-1]['content'] == 'news?' + desktop_chat.WEB_SEARCH_RETRIEVAL_APPENDIX
    assert body['messages'][1]['content'] == 'how long did Whisper Flow take to build v1?'
    assert desktop_chat._PUBLIC_WEB_ROUTING_INSTRUCTION in body['messages'][0]['content']
    assert 'tools' not in body
    assert 'tool_choice' not in body
    # Idempotent: re-building the gateway body never stacks appendices.
    rebuilt = desktop_chat._gateway_body(
        {'model': 'omi-sonnet', 'messages': body['messages']}, desktop_chat.WEB_SEARCH_AUTO_LANE_ID
    )
    assert rebuilt['messages'][-1]['content'] == body['messages'][-1]['content']
    # Other lanes keep the client question untouched.
    chat_body = desktop_chat._gateway_body(request)
    assert chat_body['messages'][3]['content'] == 'news?'


def test_gateway_body_appends_web_search_appendix_as_a_text_block_for_multimodal_turns():
    request = {
        'model': 'omi-sonnet',
        'messages': [
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': 'what is in this screenshot?'},
                    {'type': 'image_url', 'image_url': {'url': 'https://example.com/a.png'}},
                ],
            }
        ],
    }
    body = desktop_chat._gateway_body(request, desktop_chat.WEB_SEARCH_AUTO_LANE_ID)
    blocks = body['messages'][-1]['content']
    assert blocks[0] == {'type': 'text', 'text': 'what is in this screenshot?'}
    assert blocks[-1] == {'type': 'text', 'text': desktop_chat.WEB_SEARCH_RETRIEVAL_APPENDIX}


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
    monkeypatch.setattr(desktop_chat, 'enforce_desktop_chat_quota', lambda *_args, **_kwargs: None)
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
async def test_chat_completions_jit_stays_on_gateway_when_anthropic_byok_exists(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_desktop_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setenv('OMI_JIT_PROACTIVITY_BUDGET_CONTRACT', 'jit-cloud-qa-v1')
    monkeypatch.setattr(
        desktop_chat, 'get_byok_key', lambda provider: 'sk-anthropic' if provider == 'anthropic' else None
    )
    monkeypatch.setattr(desktop_chat, '_record_usage', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(
        desktop_chat,
        'get_direct_anthropic_client',
        _fail_direct_anthropic('qualified JIT must not construct a direct Anthropic client'),
    )
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_base_url', lambda: 'http://gateway.test')

    class GatewayClient:
        def __init__(self):
            self.calls = []

        async def post(self, url, *, headers, json):
            self.calls.append((url, headers, json))
            return httpx.Response(
                200,
                json={'id': 'jit', 'choices': [{'message': {'content': 'gateway'}}], 'usage': {}},
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
        x_omi_jit_contract_version='jit-cloud-qa-v1',
        x_omi_jit_run_id='jit-byok-run',
        x_omi_jit_max_attempts='3',
        x_omi_jit_max_output_tokens='2048',
        x_omi_jit_max_input_tokens='32768',
        x_omi_jit_max_spend_micro_usd='50000',
    )

    assert response.body and b'gateway' in response.body
    assert len(client.calls) == 1
    assert client.calls[0][1]['X-Omi-Jit-Run-Id'] == 'jit-byok-run'


@pytest.mark.asyncio
async def test_chat_completions_jit_rejects_direct_mode(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: False)
    monkeypatch.setenv('OMI_JIT_PROACTIVITY_BUDGET_CONTRACT', 'jit-cloud-qa-v1')

    with pytest.raises(desktop_chat.HTTPException) as error:
        await desktop_chat.chat_completions(
            {'messages': [{'role': 'user', 'content': 'hello'}]},
            uid='user-1',
            x_app_platform=None,
            x_omi_chat_contract_version=None,
            x_omi_request_id=None,
            x_omi_jit_contract_version='jit-cloud-qa-v1',
            x_omi_jit_run_id='jit-direct-run',
            x_omi_jit_max_attempts='3',
            x_omi_jit_max_output_tokens='2048',
            x_omi_jit_max_input_tokens='32768',
            x_omi_jit_max_spend_micro_usd='50000',
        )

    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_chat_completions_legacy_haiku_alias_uses_structured_gateway(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_desktop_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(desktop_chat, '_record_usage', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_base_url', lambda: 'http://gateway.test')
    monkeypatch.setattr(
        desktop_chat,
        'get_direct_anthropic_client',
        _fail_direct_anthropic('legacy Haiku aliases must not construct a direct Anthropic client'),
    )

    class GatewayClient:
        def __init__(self):
            self.calls = []

        async def post(self, url, *, headers, json):
            self.calls.append(json)
            return httpx.Response(
                200,
                json={
                    'id': 'chat-haiku',
                    'choices': [{'message': {'content': 'structured'}}],
                    'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5},
                },
                request=httpx.Request('POST', url),
            )

    client = GatewayClient()
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_client', lambda: client)
    response = await desktop_chat.chat_completions(
        {
            'model': 'claude-haiku-4-5-20251001',
            'messages': [{'role': 'user', 'content': 'extract this'}],
            'max_tokens': 16,
            'omi_web_search': True,
        },
        uid='user-1',
        x_app_platform=None,
        x_omi_chat_contract_version=None,
        x_omi_request_id=None,
    )

    assert b'structured' in response.body
    assert client.calls[0]['model'] == 'omi:auto:chat-structured'


@pytest.mark.asyncio
async def test_chat_completions_routes_legacy_opus_alias_through_managed_gateway(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_desktop_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(desktop_chat, '_record_usage', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_base_url', lambda: 'http://gateway.test')
    monkeypatch.setattr(
        desktop_chat,
        'get_direct_anthropic_client',
        _fail_direct_anthropic('legacy opus aliases must not construct a direct Anthropic client'),
    )

    class GatewayClient:
        def __init__(self):
            self.calls = []

        async def post(self, url, *, headers, json):
            self.calls.append(json)
            return httpx.Response(
                200,
                json={
                    'id': 'chat-opus',
                    'choices': [{'message': {'content': 'managed'}}],
                    'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5},
                },
                request=httpx.Request('POST', url),
            )

    client = GatewayClient()
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_client', lambda: client)
    response = await desktop_chat.chat_completions(
        {
            'model': 'omi-opus',
            'messages': [{'role': 'user', 'content': 'hello'}],
            'max_tokens': 16,
        },
        uid='user-1',
        x_app_platform=None,
        x_omi_chat_contract_version=None,
        x_omi_request_id=None,
    )
    assert b'managed' in response.body
    assert client.calls[0]['model'] == 'omi:auto:chat-agent'


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


def test_request_does_not_let_client_tools_alone_enable_server_side_web_search():
    client_tools = [{'type': 'function', 'function': {'name': 'search_memories', 'parameters': {'type': 'object'}}}]
    _, payload = _authorized_request(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': 'What is the weather in New York today?'}],
            'tools': client_tools,
        }
    )
    assert [tool['name'] for tool in payload['tools']] == ['search_memories']
    assert desktop_chat._PUBLIC_WEB_ROUTING_INSTRUCTION not in str(payload.get('system', ''))


def test_request_withholds_web_search_from_an_unauthorized_principal(monkeypatch):
    fallbacks = []
    monkeypatch.setattr(desktop_chat, 'record_fallback', lambda **fields: fallbacks.append(fields))
    _, payload = _authorized_request(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': 'What is the weather in New York today?'}],
            'omi_web_search': True,
        },
        web_search_allowed=False,
    )
    assert 'tools' not in payload
    assert [fallback['reason'] for fallback in fallbacks] == ['not_authorized']


def test_request_withholds_web_search_when_private_tool_output_is_in_context(monkeypatch):
    fallbacks = []
    monkeypatch.setattr(desktop_chat, 'record_fallback', lambda **fields: fallbacks.append(fields))
    _, payload = _authorized_request(
        {
            'model': 'omi-sonnet',
            'messages': [
                {'role': 'user', 'content': 'What did I say about the acquisition?'},
                {
                    'role': 'assistant',
                    'tool_calls': [
                        {
                            'id': 'call_1',
                            'type': 'function',
                            'function': {'name': 'search_memories', 'arguments': '{}'},
                        }
                    ],
                },
                {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'secret: board deck passphrase'},
                {'role': 'assistant', 'content': 'You discussed the acquisition.'},
                {'role': 'user', 'content': 'Now search the web for the latest news.'},
            ],
            'omi_web_search': True,
        }
    )
    assert 'tools' not in payload
    assert [fallback['reason'] for fallback in fallbacks] == ['private_tool_output_in_context']


def test_request_allows_web_search_when_only_public_safe_tool_output_is_in_context():
    _, payload = _authorized_request(
        {
            'model': 'omi-sonnet',
            'messages': [
                {'role': 'user', 'content': 'Add a task'},
                {
                    'role': 'assistant',
                    'tool_calls': [
                        {
                            'id': 'call_1',
                            'type': 'function',
                            'function': {'name': 'create_action_item', 'arguments': '{}'},
                        }
                    ],
                },
                {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'created'},
                {'role': 'user', 'content': 'Now search the web for the latest news.'},
            ],
            'omi_web_search': True,
        }
    )
    assert [tool['name'] for tool in payload['tools']] == ['web_search']


def test_request_withholds_web_search_when_tool_output_is_inlined_in_the_user_turn():
    _, payload = _authorized_request(
        {
            'model': 'omi-sonnet',
            'messages': [
                {
                    'role': 'user',
                    'content': (
                        'Search the web for current news.'
                        f'{desktop_chat._UNTRUSTED_TOOL_CONTEXT_DELIMITER}'
                        'screen: recovery code 998811'
                    ),
                }
            ],
            'omi_web_search': True,
        }
    )
    assert 'tools' not in payload


def test_request_treats_unrecognized_tool_output_as_private():
    _, payload = _authorized_request(
        {
            'model': 'omi-sonnet',
            'messages': [
                {'role': 'user', 'content': 'Check my mail'},
                {
                    'role': 'assistant',
                    'tool_calls': [
                        {
                            'id': 'call_1',
                            'type': 'function',
                            'function': {'name': 'some_future_connector', 'arguments': '{}'},
                        }
                    ],
                },
                {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'inbox contents'},
                {'role': 'user', 'content': 'Now search the web.'},
            ],
            'omi_web_search': True,
        }
    )
    assert 'tools' not in payload


@pytest.mark.asyncio
async def test_chat_completions_keeps_private_tool_output_out_of_managed_web_search(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_desktop_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(desktop_chat, '_record_usage', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_base_url', lambda: 'http://gateway.test')
    monkeypatch.setattr(
        desktop_chat,
        'get_direct_anthropic_client',
        _fail_direct_anthropic('tainted web-search turns must stay on the managed gateway'),
    )

    class GatewayClient:
        def __init__(self):
            self.calls = []

        async def post(self, url, *, headers, json):
            self.calls.append(json)
            return httpx.Response(
                200,
                json={
                    'id': 'chat-private',
                    'choices': [{'message': {'content': 'answered'}}],
                    'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5},
                },
                request=httpx.Request('POST', url),
            )

    client = GatewayClient()
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_client', lambda: client)
    response = await desktop_chat.chat_completions(
        {
            'model': 'omi-sonnet',
            'messages': [
                {'role': 'user', 'content': 'What did I read on screen?'},
                {
                    'role': 'assistant',
                    'tool_calls': [
                        {
                            'id': 'call_1',
                            'type': 'function',
                            'function': {'name': 'search_screen_history', 'arguments': '{}'},
                        }
                    ],
                },
                {'role': 'tool', 'tool_call_id': 'call_1', 'content': 'recovery code 998811'},
                {'role': 'user', 'content': 'Search the web for current news.'},
            ],
            'omi_web_search': True,
        },
        uid='user-1',
        x_app_platform=None,
        x_omi_chat_contract_version=None,
        x_omi_request_id=None,
    )
    assert b'answered' in response.body
    assert client.calls[0]['model'] == 'omi:auto:chat-agent'


@pytest.mark.asyncio
async def test_chat_completions_withholds_managed_web_search_when_unauthorized(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_desktop_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_chat_agent_through_gateway', lambda: True)
    monkeypatch.setattr(desktop_chat, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(desktop_chat, '_record_usage', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_base_url', lambda: 'http://gateway.test')
    monkeypatch.setattr(
        desktop_chat,
        'get_direct_anthropic_client',
        _fail_direct_anthropic('unauthorized web-search turns must not construct a direct Anthropic client'),
    )

    async def denied(*_args, **_kwargs):
        return 'denied'

    monkeypatch.setattr(desktop_chat, '_web_search_authorized', denied)
    fallbacks = []
    monkeypatch.setattr(desktop_chat, 'record_fallback', lambda **fields: fallbacks.append(fields))

    class GatewayClient:
        def __init__(self):
            self.calls = []

        async def post(self, url, *, headers, json):
            self.calls.append(json)
            return httpx.Response(
                200,
                json={
                    'id': 'chat-denied',
                    'choices': [{'message': {'content': 'answered'}}],
                    'usage': {'prompt_tokens': 3, 'completion_tokens': 2, 'total_tokens': 5},
                },
                request=httpx.Request('POST', url),
            )

    client = GatewayClient()
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_client', lambda: client)
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
    assert b'answered' in response.body
    assert client.calls[0]['model'] == 'omi:auto:chat-agent'
    assert [fallback['reason'] for fallback in fallbacks] == ['not_authorized']


@pytest.mark.asyncio
async def test_web_search_authorized_allows_a_principal_that_predates_the_gate(monkeypatch):
    # Legacy principal: no user doc, therefore no stored web_search decision.
    monkeypatch.setattr(desktop_chat.users_db, 'get_assistant_settings', lambda uid: {})
    assert await desktop_chat._web_search_authorized('legacy-user') == 'authorized'

    monkeypatch.setattr(desktop_chat.users_db, 'get_assistant_settings', lambda uid: {'focus': {'enabled': True}})
    assert await desktop_chat._web_search_authorized('legacy-user') == 'authorized'


@pytest.mark.asyncio
async def test_web_search_authorized_denies_only_a_stored_decision(monkeypatch):
    monkeypatch.setattr(desktop_chat.users_db, 'get_assistant_settings', lambda uid: {'web_search': {'enabled': False}})
    assert await desktop_chat._web_search_authorized('opted-out') == 'denied'

    monkeypatch.setattr(desktop_chat.users_db, 'get_assistant_settings', lambda uid: {'web_search': {'enabled': True}})
    assert await desktop_chat._web_search_authorized('opted-in') == 'authorized'


@pytest.mark.asyncio
async def test_web_search_authorized_fails_closed_when_the_lookup_breaks(monkeypatch):
    fallbacks = []
    monkeypatch.setattr(desktop_chat, 'record_fallback', lambda **fields: fallbacks.append(fields))

    def _boom(uid):
        raise RuntimeError('firestore down')

    monkeypatch.setattr(desktop_chat.users_db, 'get_assistant_settings', _boom)
    assert await desktop_chat._web_search_authorized('user') == 'unavailable'
    assert [fallback['reason'] for fallback in fallbacks] == ['authorization_unavailable']


@pytest.mark.asyncio
async def test_authorization_lookup_failure_is_not_reported_as_an_explicit_denial(monkeypatch):
    """A Firestore/settings outage must not also emit ``not_authorized`` for the
    same request: lookup failures and per-user denials are mutually exclusive
    reasons so metrics can distinguish infra failure from explicit opt-out."""
    fallbacks = []
    monkeypatch.setattr(desktop_chat, 'record_fallback', lambda **fields: fallbacks.append(fields))

    def _boom(uid):
        raise RuntimeError('firestore down')

    monkeypatch.setattr(desktop_chat.users_db, 'get_assistant_settings', _boom)
    _, payload = desktop_chat._request(
        {
            'model': 'omi-sonnet',
            'messages': [{'role': 'user', 'content': 'What is the weather in New York today?'}],
            'omi_web_search': True,
        },
        web_search_authorization=await desktop_chat._web_search_authorized('user'),
    )
    assert 'tools' not in payload
    assert [fallback['reason'] for fallback in fallbacks] == ['authorization_unavailable']


def test_gateway_request_headers_forward_the_client_app_platform():
    """chat_agent gateway spend must carry the platform the request came from."""
    headers = desktop_chat._gateway_request_headers('request-1', desktop_chat.CHAT_AGENT_AUTO_LANE_ID, 'desktop')

    assert headers['X-Omi-App-Platform'] == 'desktop'
    assert headers['X-Omi-LLM-Feature'] == 'chat_agent'


def test_gateway_request_headers_omit_app_platform_when_client_sent_none():
    headers = desktop_chat._gateway_request_headers('request-1', desktop_chat.CHAT_AGENT_AUTO_LANE_ID, None)

    assert 'X-Omi-App-Platform' not in headers


def test_jit_qualification_headers_forward_only_versioned_bounded_contract(monkeypatch):
    monkeypatch.setenv('OMI_JIT_PROACTIVITY_BUDGET_CONTRACT', 'jit-cloud-qa-v1')
    headers = desktop_chat._jit_headers_for_forward('jit-cloud-qa-v1', 'a' * 64, '3', '2048', '32768', '50000')
    assert headers['X-Omi-Jit-Run-Id'] == 'a' * 64
    assert headers['X-Omi-Jit-Max-Attempts'] == '3'
    assert headers['X-Omi-Jit-Max-Output-Tokens'] == '2048'
    assert headers['X-Omi-Jit-Max-Input-Tokens'] == '32768'
    assert headers['X-Omi-Jit-Max-Spend-Micro-Usd'] == '50000'
    for values in (
        ('4', '2048', '32768', '50000'),
        ('3', '2049', '32768', '50000'),
        ('3', '2048', '32769', '50000'),
        ('3', '2048', '32768', '50001'),
    ):
        with pytest.raises(ValueError):
            desktop_chat._jit_headers_for_forward('jit-cloud-qa-v1', 'a' * 64, *values)
    monkeypatch.delenv('OMI_JIT_PROACTIVITY_BUDGET_CONTRACT')
    assert desktop_chat._jit_headers_for_forward(None, None, None, None, None, None) == {}


def _count_cache_control(value):
    """Count cache_control keys in a payload. Nested markers would split or
    duplicate the automatic breakpoint and silently miss the shared prefix."""
    count = 0
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == 'cache_control':
                count += 1
            count += _count_cache_control(nested)
    elif isinstance(value, list):
        for item in value:
            count += _count_cache_control(item)
    return count


def _stable_prefix(payload):
    """Byte-stable tools+system prefix. User turns sit after the automatic
    breakpoint's shared prefix and must not appear here."""
    return json.dumps(
        {'system': payload.get('system'), 'tools': payload.get('tools')},
        sort_keys=True,
        separators=(',', ':'),
    )


_STABLE_DESKTOP_SYSTEM = (
    'You are Omi, a desktop assistant.\n'
    '<sql_schema>\nCREATE TABLE memories (id TEXT, content TEXT);\n</sql_schema>\n'
    '<memories>\n1. User prefers vim.\n2. User is in Ho Chi Minh City.\n</memories>'
)
_STABLE_DESKTOP_TOOLS = [
    {'type': 'function', 'function': {'name': 'search_memories', 'parameters': {'type': 'object'}}},
    {'type': 'function', 'function': {'name': 'execute_sql', 'parameters': {'type': 'object'}}},
]


def test_request_attaches_one_top_level_cache_control_breakpoint():
    """Anthropic's direct API caches only at an explicit breakpoint. One
    top-level automatic marker covers tools + system + the growing transcript;
    a nested copy would consume a second slot and is not this change."""
    _, payload = _authorized_request(
        {
            'model': 'omi-sonnet',
            'messages': [
                {'role': 'system', 'content': _STABLE_DESKTOP_SYSTEM},
                {'role': 'user', 'content': 'hello'},
            ],
            'tools': _STABLE_DESKTOP_TOOLS,
        }
    )
    assert payload['cache_control'] == desktop_chat._PROMPT_CACHE_CONTROL
    assert payload['cache_control'] == {'type': 'ephemeral', 'ttl': '1h'}
    assert _count_cache_control(payload) == 1
    assert 'cache_control' not in json.dumps(payload.get('system'))
    assert 'cache_control' not in json.dumps(payload.get('tools'))
    assert 'cache_control' not in json.dumps(payload.get('messages'))


def test_request_cache_prefix_is_byte_stable_across_volatile_user_turns():
    """Cache hits require the tools+system prefix to be byte-identical across
    turns from the same client. Timestamps and the current user turn live in
    messages, after that prefix, so they cannot silently invalidate it."""
    tools = _STABLE_DESKTOP_TOOLS
    system = _STABLE_DESKTOP_SYSTEM
    _, first = _authorized_request(
        {
            'model': 'omi-sonnet',
            'messages': [
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': 'Current time: 2024-01-19 14:23:45.123456\nWhat did I work on?'},
            ],
            'tools': tools,
        }
    )
    _, second = _authorized_request(
        {
            'model': 'omi-sonnet',
            'messages': [
                {'role': 'system', 'content': system},
                {'role': 'user', 'content': 'Current time: 2024-01-19 14:23:45.123456\nWhat did I work on?'},
                {'role': 'assistant', 'content': 'You were on the desktop chat route.'},
                {'role': 'user', 'content': 'Current time: 2024-06-01 09:00:00.654321\nSummarize that.'},
            ],
            'tools': tools,
        }
    )
    assert _stable_prefix(first) == _stable_prefix(second)
    assert first['system'] == second['system'] == system
    assert first['tools'] == second['tools']
    assert first['cache_control'] == second['cache_control'] == desktop_chat._PROMPT_CACHE_CONTROL
    assert _count_cache_control(first) == _count_cache_control(second) == 1
    assert first['messages'] != second['messages']
    assert '2024-01-19 14:23:45.123456' not in _stable_prefix(first)
    assert '2024-06-01 09:00:00.654321' not in _stable_prefix(second)


def test_request_web_search_injection_keeps_a_constant_cached_prefix():
    """Server-side web search appends a constant routing instruction and tool.
    Two successive public-web turns from the same client must still share a
    byte-identical prefix; only the user turn may change."""
    _, first = _authorized_request(
        {
            'model': 'omi-sonnet',
            'messages': [
                {'role': 'system', 'content': _STABLE_DESKTOP_SYSTEM},
                {'role': 'user', 'content': 'Search the web for the weather in New York. asked at 2024-01-19 14:23:45'},
            ],
            'tools': _STABLE_DESKTOP_TOOLS,
            'omi_web_search': True,
        }
    )
    _, second = _authorized_request(
        {
            'model': 'omi-sonnet',
            'messages': [
                {'role': 'system', 'content': _STABLE_DESKTOP_SYSTEM},
                {'role': 'user', 'content': 'Search the web for the weather in London. asked at 2024-06-01 09:00:00'},
            ],
            'tools': _STABLE_DESKTOP_TOOLS,
            'omi_web_search': True,
        }
    )
    assert _stable_prefix(first) == _stable_prefix(second)
    assert first['cache_control'] == second['cache_control'] == desktop_chat._PROMPT_CACHE_CONTROL
    assert _count_cache_control(first) == 1
    assert first['system'] == _STABLE_DESKTOP_SYSTEM + '\n\n' + desktop_chat._PUBLIC_WEB_ROUTING_INSTRUCTION
    assert [tool['name'] for tool in first['tools']] == ['web_search', 'search_memories', 'execute_sql']
    assert '2024-01-19' not in _stable_prefix(first)
    assert '2024-06-01' not in _stable_prefix(second)


def test_gateway_forwardable_params_stay_within_the_gateway_allowlist():
    """The router must never forward a key the gateway will reject.

    The gateway validates the forwarded body against a strict allowlist and
    fails the whole request with HTTP 400 on the first unknown top-level key.
    Forwarding the client body verbatim therefore took managed desktop chat
    down for ~19 hours. Pin the router's projection against the gateway's own
    constants so the two cannot drift apart again.
    """
    from llm_gateway.gateway.validator import (
        CONTROL_PARAMS,
        FORWARDED_CHAT_COMPLETION_PARAMS,
        GATEWAY_LOCAL_PARAMS,
    )

    accepted = CONTROL_PARAMS | GATEWAY_LOCAL_PARAMS | FORWARDED_CHAT_COMPLETION_PARAMS
    unsupported = desktop_chat._GATEWAY_FORWARDABLE_PARAMS - accepted

    assert not unsupported, f'router forwards keys the gateway rejects: {sorted(unsupported)}'


def test_gateway_body_drops_client_params_the_gateway_would_reject():
    """A real pi-mono turn must survive gateway validation.

    The OpenAI JS SDK the local agent runs sets `store` on every request, and
    `reasoning_effort` whenever a thinking level is configured. Neither is in
    the gateway allowlist, and forwarding either one 400s the turn before a
    lane is resolved.
    """
    body = {
        'model': 'omi-sonnet',
        'messages': [{'role': 'user', 'content': 'hello'}],
        'store': False,
        'reasoning_effort': 'low',
        'parallel_tool_calls': True,
        'temperature': 0.5,
        'stream': True,
        'omi_web_search': True,
    }

    result = desktop_chat._gateway_body(body)

    assert 'store' not in result
    assert 'reasoning_effort' not in result
    assert 'parallel_tool_calls' not in result
    assert 'omi_web_search' not in result
    # Supported params still reach the gateway.
    assert result['temperature'] == 0.5
    assert result['stream'] is True
    assert result['model'] == desktop_chat.CHAT_AGENT_AUTO_LANE_ID
    assert result['messages'][0]['role'] == 'user'


def test_thinking_escalation_routes_managed_and_drops_tools():
    body = {
        'model': 'omi-luna-think',
        'messages': [{'role': 'user', 'content': 'hello'}],
        'reasoning_effort': 'high',
        'tools': [{'type': 'function', 'function': {'name': 'noop', 'parameters': {}}}],
        'stream': False,
    }

    assert desktop_chat._uses_managed_chat_agent(body) is True
    assert desktop_chat._managed_lane_id(body) == desktop_chat.CHAT_AGENT_AUTO_LANE_ID

    result = desktop_chat._gateway_body(body, desktop_chat._managed_lane_id(body))
    assert result['model'] == desktop_chat.CHAT_AGENT_AUTO_LANE_ID
    assert result['reasoning_effort'] == 'high'
    # OpenAI rejects function tools combined with a non-none effort on
    # gpt-5.6-luna, so the escalation lane never carries client tools.
    assert 'tools' not in result
    assert 'tool_choice' not in result


def test_thinking_escalation_maps_effort_levels_and_rejects_unknown():
    base = {
        'model': 'omi-luna-think',
        'messages': [{'role': 'user', 'content': 'hello'}],
    }

    # Missing effort defaults to the product `normal` level (Luna high).
    assert desktop_chat._gateway_body(dict(base))['reasoning_effort'] == 'high'
    assert desktop_chat._gateway_body({**base, 'reasoning_effort': 'high'})['reasoning_effort'] == 'high'
    assert desktop_chat._gateway_body({**base, 'reasoning_effort': 'xhigh'})['reasoning_effort'] == 'xhigh'

    for invalid in ('low', 'medium', 'max', 'ultra', 'none', 7):
        with pytest.raises(ValueError):
            desktop_chat._gateway_body({**base, 'reasoning_effort': invalid})


def test_thinking_escalation_forwards_image_url_parts_to_the_gateway():
    data_uri = 'data:image/jpeg;base64,' + 'A' * 16
    body = {
        'model': 'omi-luna-think',
        'reasoning_effort': 'xhigh',
        'messages': [
            {'role': 'system', 'content': 'speak only the conclusion'},
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': 'What is on my screen?'},
                    {'type': 'image_url', 'image_url': {'url': data_uri}},
                ],
            },
        ],
    }

    result = desktop_chat._gateway_body(body, desktop_chat._managed_lane_id(body))
    user = result['messages'][1]
    assert user['content'] == [
        {'type': 'text', 'text': 'What is on my screen?'},
        {'type': 'image_url', 'image_url': {'url': data_uri}},
    ]


def test_regular_chat_aliases_still_drop_client_reasoning_effort():
    """The generic projection must keep dropping SDK-set reasoning_effort.

    Only the validated thinking alias injects a server-authored effort; a
    regular pi-mono turn with an SDK-set effort still forwards none.
    """
    body = {
        'model': 'omi-sonnet',
        'messages': [{'role': 'user', 'content': 'hello'}],
        'reasoning_effort': 'low',
    }
    result = desktop_chat._gateway_body(body)
    assert 'reasoning_effort' not in result


def _capture_client_journeys(monkeypatch):
    accepted = []
    terminal = []
    monkeypatch.setattr(
        journeys,
        'record_client_journey_accepted',
        lambda journey, client_kind: accepted.append((journey, client_kind)),
    )
    monkeypatch.setattr(
        journeys,
        'record_client_journey_terminal',
        lambda journey, client_kind, outcome, _elapsed, *, issue_class=None: terminal.append(
            (journey, client_kind, outcome, issue_class)
        ),
    )
    return accepted, terminal


@pytest.mark.asyncio
async def test_desktop_chat_journey_requires_content_and_done_for_stream_success(monkeypatch):
    accepted, terminal = _capture_client_journeys(monkeypatch)
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
    assert 'hi' in await _drain(response)
    assert accepted == [('desktop_chat', 'desktop_windows')]
    assert terminal == [('desktop_chat', 'desktop_windows', 'success', None)]


@pytest.mark.asyncio
async def test_desktop_chat_journey_catches_in_band_502_before_later_done(monkeypatch):
    _accepted, terminal = _capture_client_journeys(monkeypatch)
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
        x_app_platform='macos',
        x_omi_chat_contract_version=None,
        x_omi_request_id='request-1',
    )
    body = await _drain(response)
    assert 'Upstream provider error' in body
    assert 'data: [DONE]' in body
    assert terminal == [('desktop_chat', 'desktop_macos', 'failure', 'provider_error')]


@pytest.mark.asyncio
async def test_desktop_chat_journey_records_direct_anthropic_json_success_and_failure(monkeypatch):
    _accepted, terminal = _capture_client_journeys(monkeypatch)
    quota_calls = []
    _wire_direct_lane(monkeypatch, quota_calls)
    monkeypatch.setattr(desktop_chat, 'get_direct_anthropic_client', lambda **_: object())

    async def answer(*_args, **_kwargs):
        message = SimpleNamespace(
            id='message-1',
            content=[SimpleNamespace(type='text', text='answer')],
            stop_reason='end_turn',
            usage=None,
        )
        return message, None, None

    monkeypatch.setattr(desktop_chat, '_create_with_pause_turn_continuations', answer)
    response = await desktop_chat.chat_completions(
        {'model': 'omi-sonnet', 'messages': [{'role': 'user', 'content': 'hello'}]},
        uid='user-1',
        x_app_platform='linux',
        x_omi_chat_contract_version=None,
        x_omi_request_id='request-2',
    )
    assert response.status_code == 200
    assert terminal[-1] == ('desktop_chat', 'desktop_linux', 'success', None)

    async def fail(*_args, **_kwargs):
        raise RuntimeError('provider failed')

    monkeypatch.setattr(desktop_chat, '_create_with_pause_turn_continuations', fail)
    with pytest.raises(desktop_chat.HTTPException):
        await desktop_chat.chat_completions(
            {'model': 'omi-sonnet', 'messages': [{'role': 'user', 'content': 'hello'}]},
            uid='user-1',
            x_app_platform='linux',
            x_omi_chat_contract_version=None,
            x_omi_request_id='request-3',
        )
    assert terminal[-1] == ('desktop_chat', 'desktop_linux', 'failure', 'provider_error')


@pytest.mark.asyncio
async def test_desktop_chat_metric_failure_does_not_break_stream(monkeypatch):
    quota_calls = []
    _wire_direct_lane(monkeypatch, quota_calls)
    monkeypatch.setattr(
        journeys.OMI_CLIENT_JOURNEY_TERMINAL_TOTAL,
        'labels',
        lambda **_: (_ for _ in ()).throw(RuntimeError('metrics unavailable')),
    )

    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def get_final_message(self):
            return SimpleNamespace(
                content=[SimpleNamespace(type='text', text='still delivered')], stop_reason='end_turn', usage=None
            )

        def __aiter__(self):
            async def events():
                yield SimpleNamespace(
                    type='content_block_delta', delta=SimpleNamespace(type='text_delta', text='still delivered')
                )

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
        x_omi_request_id='request-4',
    )
    assert 'still delivered' in await _drain(response)
