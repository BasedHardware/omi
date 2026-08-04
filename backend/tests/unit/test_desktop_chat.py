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
    monkeypatch.setattr(desktop_chat, 'should_route_features_through_gateway', lambda: True)
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


@pytest.mark.asyncio
async def test_chat_completions_rejects_unknown_explicit_model_before_gateway(monkeypatch):
    monkeypatch.setattr(desktop_chat, 'llm_stub_enabled', lambda: False)
    monkeypatch.setattr(desktop_chat, 'enforce_chat_quota', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(desktop_chat, '_meter_server_request', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'run_blocking', lambda *_args, **_kwargs: _done())
    monkeypatch.setattr(desktop_chat, 'should_route_features_through_gateway', lambda: True)
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
    monkeypatch.setattr(desktop_chat, 'should_route_features_through_gateway', lambda: True)
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
    monkeypatch.setattr(desktop_chat, 'should_route_features_through_gateway', lambda: True)
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
    monkeypatch.setattr(desktop_chat, 'should_route_features_through_gateway', lambda: True)
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

    monkeypatch.setattr(desktop_chat, 'should_route_features_through_gateway', raise_config_error)

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
