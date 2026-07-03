from __future__ import annotations

import httpx
import pytest

from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_byok_credential_context, build_omi_managed_credential_context
from llm_gateway.gateway.providers import (
    MAX_RESPONSE_BYTES_ENV_VAR,
    OpenAICompatibleChatCompletionProvider,
    ProviderFailure,
)
from llm_gateway.gateway.schemas import FailureClass, ProviderRef


@pytest.mark.asyncio
async def test_openai_compatible_provider_posts_chat_completion(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    seen_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(
            200,
            json={
                'id': 'chatcmpl_test',
                'object': 'chat.completion',
                'model': 'gpt-4.1-mini',
                'choices': [{'message': {'role': 'assistant', 'content': '{}'}}],
            },
        )

    provider = OpenAICompatibleChatCompletionProvider(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    response = await provider.create_chat_completion(
        {'model': 'gpt-4.1-mini', 'messages': [], 'stream': False},
        provider_ref=ProviderRef(provider='openai', model='gpt-4.1-mini'),
        credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
        timeout_ms=8000,
    )

    assert response['id'] == 'chatcmpl_test'
    assert seen_requests[0].url == 'https://api.openai.com/v1/chat/completions'
    assert seen_requests[0].headers['authorization'] == 'Bearer test-key'


@pytest.mark.asyncio
async def test_openai_compatible_provider_streams_chat_completion_bytes(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    seen_requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\ndata: [DONE]\n\n',
            headers={'content-type': 'text/event-stream'},
        )

    provider = OpenAICompatibleChatCompletionProvider(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    chunks = [
        chunk
        async for chunk in provider.stream_chat_completion(
            {'model': 'gpt-4.1-mini', 'messages': [], 'stream': True},
            provider_ref=ProviderRef(provider='openai', model='gpt-4.1-mini'),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=8000,
        )
    ]

    assert b''.join(chunks).startswith(b'data:')
    assert seen_requests[0].url == 'https://api.openai.com/v1/chat/completions'
    assert seen_requests[0].headers['authorization'] == 'Bearer test-key'


@pytest.mark.asyncio
async def test_openai_compatible_provider_closes_owned_http_client():
    provider = OpenAICompatibleChatCompletionProvider()

    await provider.aclose()

    assert provider._http_client.is_closed


@pytest.mark.asyncio
async def test_openai_compatible_provider_fails_closed_without_api_key(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    provider = OpenAICompatibleChatCompletionProvider(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))),
    )

    with pytest.raises(ProviderFailure) as exc_info:
        await provider.create_chat_completion(
            {'model': 'gpt-4.1-mini', 'messages': [], 'stream': False},
            provider_ref=ProviderRef(provider='openai', model='gpt-4.1-mini'),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=8000,
        )

    assert exc_info.value.failure_class == FailureClass.INVALID_CONFIG


@pytest.mark.asyncio
async def test_openai_compatible_provider_maps_timeout(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout('test timeout')

    provider = OpenAICompatibleChatCompletionProvider(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ProviderFailure) as exc_info:
        await provider.create_chat_completion(
            {'model': 'gpt-4.1-mini', 'messages': [], 'stream': False},
            provider_ref=ProviderRef(provider='openai', model='gpt-4.1-mini'),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=8000,
        )

    assert exc_info.value.failure_class == FailureClass.TIMEOUT_BEFORE_OUTPUT


@pytest.mark.asyncio
async def test_openai_compatible_provider_maps_transport_error(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('test connect error')

    provider = OpenAICompatibleChatCompletionProvider(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ProviderFailure) as exc_info:
        await provider.create_chat_completion(
            {'model': 'gpt-4.1-mini', 'messages': [], 'stream': False},
            provider_ref=ProviderRef(provider='openai', model='gpt-4.1-mini'),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=8000,
        )

    assert exc_info.value.failure_class == FailureClass.PROVIDER_5XX_OMI_PAID


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('status_code', 'failure_class'),
    [
        (400, FailureClass.CAPABILITY_MISMATCH),
        (401, FailureClass.INVALID_CONFIG),
        (403, FailureClass.INVALID_CONFIG),
        (408, FailureClass.TIMEOUT_BEFORE_OUTPUT),
        (429, FailureClass.PROVIDER_429_OMI_PAID),
        (500, FailureClass.PROVIDER_5XX_OMI_PAID),
    ],
)
async def test_openai_compatible_provider_maps_status_without_leaking_body(monkeypatch, status_code, failure_class):
    raw_body = 'raw provider error with sensitive prompt'
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    provider = OpenAICompatibleChatCompletionProvider(
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(status_code, text=raw_body))
        ),
    )

    with pytest.raises(ProviderFailure) as exc_info:
        await provider.create_chat_completion(
            {'model': 'gpt-4.1-mini', 'messages': [{'role': 'user', 'content': 'secret'}], 'stream': False},
            provider_ref=ProviderRef(provider='openai', model='gpt-4.1-mini'),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=8000,
        )

    assert exc_info.value.failure_class == failure_class
    assert raw_body not in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'response',
    [
        httpx.Response(200, text='not json'),
        httpx.Response(200, json=[]),
        httpx.Response(200, json={'object': 'not.chat.completion', 'id': 'x', 'model': 'm', 'choices': []}),
        httpx.Response(200, json={'object': 'chat.completion', 'id': 'x', 'model': 'm', 'choices': []}),
        httpx.Response(200, json={'object': 'chat.completion', 'id': 'x', 'model': 'm', 'choices': [{}]}),
    ],
)
async def test_openai_compatible_provider_rejects_malformed_success_response(monkeypatch, response):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    provider = OpenAICompatibleChatCompletionProvider(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: response)),
    )

    with pytest.raises(ProviderFailure) as exc_info:
        await provider.create_chat_completion(
            {'model': 'gpt-4.1-mini', 'messages': [], 'stream': False},
            provider_ref=ProviderRef(provider='openai', model='gpt-4.1-mini'),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=8000,
        )

    assert exc_info.value.failure_class == FailureClass.PROVIDER_5XX_OMI_PAID


@pytest.mark.asyncio
async def test_openai_compatible_provider_rejects_oversized_response(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setenv(MAX_RESPONSE_BYTES_ENV_VAR, '8')
    provider = OpenAICompatibleChatCompletionProvider(
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'{"too":"large"}'))
        ),
    )

    with pytest.raises(ProviderFailure) as exc_info:
        await provider.create_chat_completion(
            {'model': 'gpt-4.1-mini', 'messages': [], 'stream': False},
            provider_ref=ProviderRef(provider='openai', model='gpt-4.1-mini'),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=8000,
        )

    assert exc_info.value.failure_class == FailureClass.PROVIDER_5XX_OMI_PAID


@pytest.mark.asyncio
async def test_openai_compatible_provider_keeps_byok_failure_visible(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    provider = OpenAICompatibleChatCompletionProvider(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))),
    )

    with pytest.raises(ProviderFailure) as exc_info:
        await provider.create_chat_completion(
            {'model': 'gpt-4.1-mini', 'messages': [], 'stream': False},
            provider_ref=ProviderRef(provider='openai', model='gpt-4.1-mini'),
            credentials=build_byok_credential_context(ServiceCaller(name='backend'), {'openai': 'sk-test'}),
            timeout_ms=8000,
        )

    assert exc_info.value.failure_class == FailureClass.BYOK_UNSUPPORTED_PROVIDER
