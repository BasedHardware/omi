"""Dispatch contract: company-paid Gemini is dedicated-only; overflow is Luna."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
import yaml

from config.vertex_reservations import State
from llm_gateway.gateway.accounting import AttemptTrace
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.config_loader import DEFAULT_CONFIG_DIR, ConfigValidationError, load_gateway_config
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.errors import GatewayProviderFailureError
from llm_gateway.gateway.executor import ProviderRegistry, execute_chat_completion
from llm_gateway.gateway.providers import OpenAICompatibleChatCompletionProvider, VertexGeminiProvider
from llm_gateway.gateway.resolver import resolve_chat_completion_route
from llm_gateway.routers.openai_compatible import _prepared_streaming_iterator
from utils.llm import vertex_pt_routing as ptr


def success():
    return {
        'object': 'chat.completion',
        'id': 'synthetic',
        'model': 'gpt-6-luna',
        'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'ok'}, 'finish_reason': 'stop'}],
        'usage': {'prompt_tokens': 2, 'completion_tokens': 1, 'total_tokens': 3},
    }


@pytest.mark.parametrize('anchor', list(ptr.DESKTOP_TEXT_LANES))
@pytest.mark.parametrize('state', [State.INACTIVE, State.UNKNOWN, State.ACTIVE])
@pytest.mark.parametrize('streaming', [False, True])
@pytest.mark.asyncio
async def test_paid_dispatch_never_reaches_shared_gemini(monkeypatch, anchor, state, streaming):
    monkeypatch.delenv('OMI_VERTEX_PT_MODEL', raising=False)
    monkeypatch.delenv('OMI_VERTEX_RESERVATION_STATES', raising=False)
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.host == 'us-central1-aiplatform.googleapis.com':
            assert request.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated'
            assert ptr.PT_MODEL_CURRENT + ':' in request.url.path
            return httpx.Response(429, json={'error': {'message': 'Provisioned throughput exhausted'}})
        assert request.url.path == '/v1/chat/completions'
        body = json.loads(request.content)
        assert body['model'] == 'gpt-6-luna'
        assert not {'google', 'reserved_capacity_only', 'pt_overflow_origin', 'top_p', 'stop'} & body.keys()
        if streaming:
            return httpx.Response(
                200,
                content=b'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
                headers={'content-type': 'text/event-stream'},
            )
        return httpx.Response(200, json=success())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vertex = VertexGeminiProvider(http_client=client, access_token_supplier=AsyncMock(return_value='synthetic'))
        monkeypatch.setattr(vertex._reservations, 'refresh', AsyncMock(return_value={ptr.PT_MODEL_CURRENT: state}))
        registry = ProviderRegistry(
            {'gemini': vertex, 'openai': OpenAICompatibleChatCompletionProvider(http_client=client)}
        )
        request = {'model': ptr.desktop_text_lane_id(anchor), 'messages': [{'role': 'user', 'content': 'synthetic'}]}
        resolved = resolve_chat_completion_route(load_gateway_config(), request)
        credentials = build_omi_managed_credential_context(ServiceCaller(name='backend'))
        if streaming:
            prepared = await _prepared_streaming_iterator(
                resolved, credentials, registry, resolved.active_route, attempt_trace=AttemptTrace()
            )
            assert prepared.provider == 'openai' and prepared.model == 'gpt-6-luna'
            output = (prepared.first_chunk or b'') + b''.join([chunk async for chunk in prepared.stream])
            assert b'ok' in output
        else:
            result = await execute_chat_completion(resolved, credentials, registry)
            assert result.selected_provider == 'openai' and result.selected_model == 'gpt-6-luna'
            assert result.response['choices'][0]['message']['content'] == 'ok'
            assert result.provider_accounting.usage.total_tokens == 3
        assert len(seen) == (2 if state == State.ACTIVE else 1)


@pytest.mark.parametrize('status,message', [(429, 'Ordinary project rate limit'), (400, 'Invalid tool')])
@pytest.mark.asyncio
async def test_generic_rejection_does_not_trigger_capacity_fallback(monkeypatch, status, message):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv('OMI_VERTEX_RESERVATION_STATES', '{"gemini-2.5-flash":"active","gemini-3.8-flash":"inactive"}')
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(status, json={'error': {'message': message}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        vertex = VertexGeminiProvider(http_client=client, access_token_supplier=AsyncMock(return_value='synthetic'))
        resolved = resolve_chat_completion_route(
            load_gateway_config(),
            {
                'model': ptr.desktop_text_lane_id(ptr.PT_MODEL_CURRENT),
                'messages': [{'role': 'user', 'content': 'synthetic'}],
            },
        )
        with pytest.raises(Exception) as error:
            await execute_chat_completion(
                resolved,
                build_omi_managed_credential_context(ServiceCaller(name='backend')),
                ProviderRegistry({'gemini': vertex}),
            )
        assert error.value.failure_class.value in {'provider_429_omi_paid', 'provider_invalid_request'}
        assert len(seen) == 1


@pytest.mark.parametrize('mutation', ['shared_primary', 'shared_fallback', 'openrouter_gemini', 'missing_luna'])
def test_config_load_rejects_paygo_gemini(tmp_path, mutation):
    for name in ['lanes.yaml', 'route_artifacts.yaml', 'feature_bundles.yaml', 'generated_route_overrides.yaml']:
        (tmp_path / name).write_bytes((DEFAULT_CONFIG_DIR / name).read_bytes())
    path = tmp_path / 'route_artifacts.yaml'
    contents = yaml.safe_load(path.read_text())
    route = contents['route_artifacts'][0]
    route.pop('artifact_digest', None)
    if mutation == 'shared_primary':
        route['primary'] = {'provider': 'gemini', 'model': ptr.PT_MODEL_CURRENT}
    elif mutation == 'shared_fallback':
        route['fallbacks'] = [{'provider': 'gemini', 'model': 'gemini-2.5-flash-lite'}]
    elif mutation == 'openrouter_gemini':
        route['primary'] = {'provider': 'openrouter', 'model': 'google/gemini-2.5-flash'}
    else:
        route['primary'] = {'provider': 'gemini', 'model': ptr.PT_MODEL_CURRENT}
        route['provider_options'] = {ptr.RESERVED_CAPACITY_OPTION: True}
        route['fallbacks'] = []
    path.write_text(yaml.safe_dump(contents))
    with pytest.raises(ConfigValidationError, match='company-paid Gemini|requires Luna'):
        load_gateway_config(tmp_path)


@pytest.mark.parametrize('anchor', list(ptr.DESKTOP_TEXT_LANES))
def test_all_desktop_aliases_follow_the_moved_order(anchor):
    assert (
        ptr.reserved_generation_model(anchor, {ptr.PT_MODEL_CURRENT: State.INACTIVE, ptr.PT_MODEL_TARGET: State.ACTIVE})
        == ptr.PT_MODEL_TARGET
    )
    assert ptr.reserved_generation_model(anchor, {}) is None
    assert (
        ptr.reserved_generation_model(anchor, {ptr.PT_MODEL_CURRENT: State.ACTIVE, ptr.PT_MODEL_TARGET: State.ACTIVE})
        is None
    )
