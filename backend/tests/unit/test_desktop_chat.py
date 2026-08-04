import json
from types import SimpleNamespace

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
            'messages': [{'role': 'user', 'content': "Don't use web search; answer from memory."}],
            'omi_web_search': True,
        }
    )
    assert 'tools' not in payload


def test_request_adds_web_search_alongside_client_tools_but_not_for_haiku_or_none():
    client_tools = [{'type': 'function', 'function': {'name': 'weather', 'parameters': {'type': 'object'}}}]
    _, payload = desktop_chat._request(
        {'model': 'omi-sonnet', 'messages': [{'role': 'user', 'content': 'Plan my day'}], 'tools': client_tools}
    )
    assert [tool['name'] for tool in payload['tools']] == ['web_search', 'weather']

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
        }
    )
    assert 'tools' not in payload


def test_response_preserves_openai_tool_and_cache_usage():
    message = SimpleNamespace(
        id='msg_1',
        content=[SimpleNamespace(type='tool_use', id='call_1', name='weather', input={'city': 'NYC'})],
        stop_reason='tool_use',
        usage=SimpleNamespace(
            input_tokens=3,
            cache_creation_input_tokens=2,
            cache_read_input_tokens=5,
            output_tokens=7,
            server_tool_use=SimpleNamespace(web_search_requests=2),
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
        'web_search_requests': 2,
    }


def test_request_reports_web_search_capability_fallback(monkeypatch):
    fallbacks = []
    monkeypatch.setattr(desktop_chat, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))
    desktop_chat._request(
        {
            'model': 'claude-haiku-4-5',
            'messages': [{'role': 'user', 'content': 'What happened in the news?'}],
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
async def test_stream_emits_openai_terminal_event(monkeypatch):
    class Stream:
        async def get_final_message(self):
            return SimpleNamespace(
                content=[SimpleNamespace(type='text', text='hello')],
                stop_reason='end_turn',
                usage=SimpleNamespace(
                    input_tokens=1, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=1
                ),
            )

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

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
                    type='message_delta',
                    delta=SimpleNamespace(stop_reason='pause_turn'),
                    usage=first.usage,
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
