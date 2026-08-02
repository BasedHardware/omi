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
async def test_chat_completions_gateway_mode_uses_luna_auto_lane(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_features_through_gateway', lambda: True)
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_base_url', lambda: 'http://gateway.test')
    monkeypatch.setattr(desktop_chat, 'llm_gateway_headers', lambda **_kwargs: {'x-omi-service-caller': 'backend'})

    class GatewayClient:
        def __init__(self):
            self.calls = []

        async def post(self, url, *, headers, json):
            self.calls.append({'url': url, 'headers': headers, 'json': json})
            return httpx.Response(
                200,
                json={'id': 'chat-1', 'choices': [{'message': {'content': 'hello'}}]},
                request=httpx.Request('POST', url),
            )

    client = GatewayClient()
    monkeypatch.setattr(desktop_chat, 'get_llm_gateway_client', lambda: client)

    response = await desktop_chat.chat_completions(
        {'model': 'client-model', 'messages': [{'role': 'user', 'content': 'hello'}]},
        uid='user-1',
        x_app_platform=None,
        x_omi_chat_contract_version=None,
        x_omi_request_id=None,
    )

    assert response.body == b'{"id":"chat-1","choices":[{"message":{"content":"hello"}}]}'
    assert client.calls[0]['url'] == 'http://gateway.test/v1/chat/completions'
    assert client.calls[0]['json']['model'] == 'omi:auto:chat-agent'


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
