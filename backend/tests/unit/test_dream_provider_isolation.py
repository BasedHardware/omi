"""Dream HTTP targets cannot inherit desktop PT routing or recovery policy."""

import json
from dataclasses import replace
from unittest.mock import AsyncMock

import httpx
import pytest
from config.vertex_reservations import State

from llm_gateway.gateway import executor, providers
from llm_gateway.gateway.accounting import AttemptTrace
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.dream_lanes import DREAM_LANES
from llm_gateway.gateway.errors import GatewayError
from llm_gateway.gateway.executor import ProviderRegistry, execute_chat_completion, provider_request_for
from llm_gateway.gateway.providers import FakeChatCompletionProvider, ProviderFailure, VertexGeminiProvider
from llm_gateway.gateway.resolver import resolve_chat_completion_route
from llm_gateway.gateway.schemas import FailureClass, ProviderRef, RolloutStage
from llm_gateway.routers import openai_compatible as router
from utils.llm import vertex_pt_routing as ptr


@pytest.fixture
def setup_dream(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv('DREAM_ON_DEMAND_ENABLED', 'true')
    monkeypatch.setenv(ptr.PT_MODEL_OVERRIDE_ENV, 'gemini-2.5-flash')
    monkeypatch.setenv(ptr.MULTI_REGION_LOCATION_ENV, 'eu')
    monkeypatch.setenv(ptr.REGIONAL_LOCATION_ENV, 'europe-west1')
    monkeypatch.setenv(ptr.OVERFLOW_ENABLED_ENV, 'true')
    for name in (
        'reserved_generation_model',
        'model_payload',
        'reservation_endpoint',
        'vertex_endpoint',
        'overflow_origin_from_request',
    ):
        monkeypatch.setattr(ptr, name, lambda *a, **k: pytest.fail('Dream entered desktop routing/shaping'))
    monkeypatch.setattr(executor, 'select_lkg_route_for_failure', lambda *a, **k: pytest.fail('Dream attempted LKG'))


def resolved(lane, mode, **extra):
    return resolve_chat_completion_route(
        load_gateway_config(),
        {
            'model': lane,
            'messages': [{'role': 'user', 'content': 'invented request'}],
            'google': {'dream_capacity_mode': mode, 'dream_owner_allowlisted': True, 'dream_reserved_only': True},
            **extra,
        },
    )


async def access_token():
    return 'synthetic-token'


def credentials():
    return build_omi_managed_credential_context(ServiceCaller(name='backend', user_uid='synthetic-owner'))


@pytest.fixture
def force_explicit_dream_cache(setup_dream):
    """Exercise stale-handle guards without changing Gemini's implicit lane policy."""

    def force(request):
        policy = request['_gateway_cache_policy']
        assert policy['lane'] in DREAM_LANES
        assert policy['mode'] == 'implicit'
        policy['mode'] = 'explicit'
        return request

    return force


@pytest.mark.asyncio
@pytest.mark.parametrize('lane', sorted(DREAM_LANES))
@pytest.mark.parametrize('mode', ['reserved', 'on_demand'])
@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('outcome', ['success', '429', 'timeout', '503'])
async def test_exactly_one_38_us_http_attempt_under_25_operator_pin(
    setup_dream, monkeypatch, lane, mode, stream, outcome
):
    calls = []

    def handler(request):
        calls.append(request)
        if outcome == 'timeout':
            raise httpx.ReadTimeout('synthetic timeout', request=request)
        if outcome != 'success':
            return httpx.Response(int(outcome), json={'error': {'message': 'synthetic failure'}})
        payload = {
            'trafficType': 'PROVISIONED_THROUGHPUT' if mode == 'reserved' else 'ON_DEMAND',
            'candidates': [{'content': {'parts': [{'text': 'invented answer'}]}, 'finishReason': 'STOP'}],
            'usageMetadata': {'promptTokenCount': 20, 'candidatesTokenCount': 3},
        }
        return (
            httpx.Response(200, content=f'data: {json.dumps(payload)}\n\n'.encode())
            if stream
            else httpx.Response(200, json=payload)
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=access_token)
        # The moved order blocks all interactive Flash, but must still serve
        # exactly one admitted Dream attempt in either supported capacity mode.
        provider._reservation_states = {ptr.PT_MODEL_CURRENT: State.INACTIVE, ptr.PT_MODEL_TARGET: State.ACTIVE}
        monkeypatch.setattr(provider._reservations, 'record', AsyncMock())

        class SecondaryProvider(FakeChatCompletionProvider):
            async def stream_chat_completion(self, *args, **kwargs):
                pytest.fail('Dream attempted a secondary stream provider')
                yield b''

        secondary = SecondaryProvider()
        route = resolved(lane, mode)
        # Defense in depth against a future config regression. Neither retry nor
        # provider fallback may be purchased, even if an invalid artifact reaches execution.
        route = replace(
            route,
            active_route=route.active_route.model_copy(
                update={
                    'retry': route.active_route.retry.model_copy(update={'max_attempts': 3}),
                    'fallbacks': [ProviderRef(provider='openai', model='gpt-6-luna')],
                    'fallback_policy': route.active_route.fallback_policy.model_copy(
                        update={'fallback_on': list(FailureClass)}
                    ),
                }
            ),
        )
        trace = AttemptTrace()

        async def run():
            if stream:
                prepared = await router._prepared_streaming_iterator(
                    route,
                    credentials(),
                    ProviderRegistry({'gemini': provider, 'openai': secondary}),
                    route.active_route,
                    attempt_trace=trace,
                )
                return [prepared.first_chunk, *[chunk async for chunk in prepared.stream]]
            return await execute_chat_completion(
                route, credentials(), ProviderRegistry({'gemini': provider, 'openai': secondary}), attempt_trace=trace
            )

        if outcome == 'success':
            await run()
        else:
            with pytest.raises((GatewayError, ProviderFailure)):
                await run()
        assert len(calls) == 1
        assert secondary.calls == []
        expected_method = 'streamGenerateContent' if stream else 'generateContent'
        assert (
            str(calls[0].url).split('?')[0]
            == f'https://aiplatform.googleapis.com/v1/projects/synthetic-project/locations/us/publishers/google/models/gemini-3.8-flash:{expected_method}'
        )
        assert calls[0].headers[ptr.REQUEST_TYPE_HEADER] == ('dedicated' if mode == 'reserved' else 'shared')
        if not stream:
            assert len(trace.attempts) == 1
            assert trace.attempts[0].configured_model == 'gemini-3.8-flash'


@pytest.mark.asyncio
@pytest.mark.parametrize('lane', sorted(DREAM_LANES))
async def test_no_retry_without_attempt_trace(setup_dream, monkeypatch, lane):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=access_token)
        monkeypatch.setattr(provider._reservations, 'record', AsyncMock())
        route = resolved(lane, 'reserved')
        route = replace(
            route,
            active_route=route.active_route.model_copy(
                update={'retry': route.active_route.retry.model_copy(update={'max_attempts': 3})}
            ),
        )
        with pytest.raises(GatewayError):
            await execute_chat_completion(route, credentials(), ProviderRegistry({'gemini': provider}))
        assert len(calls) == 1


@pytest.mark.parametrize('lane', sorted(DREAM_LANES))
def test_inactive_dream_never_selects_lkg(lane):
    route = resolved(lane, 'reserved')
    route = replace(
        route,
        active_route=route.active_route.model_copy(
            update={
                'rollout': route.active_route.rollout.model_copy(update={'stage': RolloutStage.DISABLED, 'percent': 0})
            }
        ),
    )
    with pytest.raises(GatewayError):
        executor.selected_serving_route(route)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['reserved', 'on_demand'])
@pytest.mark.parametrize('stream', [False, True])
async def test_implicit_dream_generation_does_not_create_cached_content(setup_dream, monkeypatch, mode, stream):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(404, json={'error': {'message': 'invented cache expired'}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=access_token)
        monkeypatch.setattr(provider._reservations, 'record', AsyncMock())
        route = resolved(
            'omi:auto:dream-reasoning',
            mode,
            messages=[
                {'role': 'system', 'content': 'invented static contract ' * 1000},
                {'role': 'user', 'content': 'invented continuation'},
            ],
        )
        request = provider_request_for(route, route.active_route.primary)
        assert request['_gateway_cache_policy']['mode'] == 'implicit'
        with pytest.raises(ProviderFailure):
            if stream:
                _ = [
                    chunk
                    async for chunk in provider.stream_chat_completion(
                        request, provider_ref=route.active_route.primary, credentials=credentials(), timeout_ms=10000
                    )
                ]
            else:
                await provider.create_chat_completion(
                    request, provider_ref=route.active_route.primary, credentials=credentials(), timeout_ms=10000
                )
        generations = [r for r in calls if '/models/' in r.url.path]
        assert len(generations) == 1
        assert not any(r.url.path.endswith('/cachedContents') for r in calls)
        assert 'cachedContent' not in json.loads(generations[0].content)
        assert provider._content_cache.entries == {}


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['reserved', 'on_demand'])
@pytest.mark.parametrize('stream', [False, True])
async def test_stale_cached_content_does_not_buy_second_dream_generation(
    setup_dream, force_explicit_dream_cache, monkeypatch, mode, stream
):
    calls = []
    cache_name = 'projects/synthetic-project/locations/us/cachedContents/invented-cache'

    def handler(request):
        calls.append(request)
        if request.url.path.endswith('/cachedContents'):
            return httpx.Response(200, json={'name': cache_name, 'usageMetadata': {'totalTokenCount': 6400}})
        return httpx.Response(404, json={'error': {'message': 'invented cache expired'}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=access_token)
        monkeypatch.setattr(provider._reservations, 'record', AsyncMock())
        route = resolved(
            'omi:auto:dream-reasoning',
            mode,
            messages=[
                {
                    'role': 'system',
                    'content': [
                        {
                            'type': 'text',
                            'text': 'invented static contract ' * 1000,
                            'prompt_cache_breakpoint': {'mode': 'explicit'},
                        }
                    ],
                },
                {'role': 'user', 'content': 'invented continuation'},
            ],
        )
        request = force_explicit_dream_cache(provider_request_for(route, route.active_route.primary))
        with pytest.raises(ProviderFailure):
            if stream:
                _ = [
                    chunk
                    async for chunk in provider.stream_chat_completion(
                        request, provider_ref=route.active_route.primary, credentials=credentials(), timeout_ms=10000
                    )
                ]
            else:
                await provider.create_chat_completion(
                    request, provider_ref=route.active_route.primary, credentials=credentials(), timeout_ms=10000
                )

        creates = [r for r in calls if r.url.path.endswith('/cachedContents')]
        generations = [r for r in calls if '/models/' in r.url.path]
        assert len(creates) == 1
        assert len(generations) == 1
        assert 'cachedContent' in json.loads(generations[0].content)
        assert provider._content_cache.entries == {}
