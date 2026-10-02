"""The moved-order behavior, wire thinking and per-origin overflow contract."""

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from config.vertex_reservations import State

from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.providers import VertexGeminiProvider
from llm_gateway.gateway.schemas import ProviderRef
from utils.llm import vertex_pt_routing as ptr
from utils.llm import vertex_direct_attempt as direct
from utils.llm.desktop_gemini_gateway import gemini_body_to_openai_chat
from routers import desktop_proxy as proxy


async def _token():
    return 'synthetic-token'


def _response():
    return {
        'candidates': [{'content': {'parts': [{'text': 'ok'}]}, 'finishReason': 'STOP'}],
        'usageMetadata': {'trafficType': 'PROVISIONED_THROUGHPUT'},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize('location', ['us', 'us-central1', 'global'])
async def test_target_probes_declared_order_location_then_promotes_without_a_deploy(monkeypatch, location):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv(ptr.PT_TARGET_LOCATION_ENV, location)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=_response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=_token)
        monkeypatch.setattr(
            provider._reservations, 'refresh', AsyncMock(return_value={ptr.PT_MODEL_TARGET: State.ACTIVE})
        )
        credentials = build_omi_managed_credential_context(ServiceCaller(name='backend'))
        await provider.create_chat_completion(
            {'messages': [{'role': 'user', 'content': 'test'}]},
            provider_ref=ProviderRef(provider='gemini', model=ptr.PT_MODEL_TARGET),
            credentials=credentials,
            timeout_ms=1000,
        )
        assert provider._reservation_active(ptr.PT_MODEL_TARGET)
        assert ptr.PT_MODEL_TARGET in provider._protected_models()
        await provider.create_chat_completion(
            {'messages': [{'role': 'user', 'content': 'test'}]},
            provider_ref=ProviderRef(provider='gemini', model=ptr.PT_MODEL_CURRENT),
            credentials=credentials,
            timeout_ms=1000,
        )
    assert f'/locations/{location}/' in str(seen[0].url)
    assert seen[0].headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated'
    assert json.loads(seen[0].content)['generationConfig']['thinkingConfig'] == {'thinkingLevel': 'low'}
    assert ptr.PT_MODEL_CURRENT in str(seen[1].url) and '/locations/us-central1/' in str(seen[1].url)
    assert seen[1].headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated'  # target success alone cannot revoke old capacity


def test_old_client_list_price_is_never_promoted_and_overflow_is_capped():
    for ready in [False, True]:
        pt = ptr.PT_MODEL_TARGET if ready else ptr.PT_MODEL_CURRENT
        assert ptr.desktop_serving_model(ptr.PT_MODEL_CURRENT) == ptr.PT_MODEL_CURRENT
        assert ptr.desktop_serving_model('gemini-2.5-pro') == 'gemini-3.1-flash-lite'
        for origin in [ptr.PT_MODEL_CURRENT, ptr.PT_MODEL_TARGET, 'gemini-2.5-flash-lite']:
            for candidate in ptr.resolve_overflow_ladder(pt_model=pt, origin_model=origin):
                assert candidate != pt and ptr.model_within_origin_price(candidate, origin)
    assert ptr.PT_MODEL_TARGET not in ptr.resolve_fallback_chain(
        model=ptr.PT_MODEL_CURRENT, pt_model=ptr.PT_MODEL_CURRENT, override=ptr.PT_MODEL_TARGET
    )


def test_thinking_level_survives_bff_then_adapts_on_fallback():
    body = {
        'contents': [{'parts': [{'text': 'test'}]}],
        'generationConfig': {'thinkingConfig': {'thinkingLevel': 'low'}},
    }
    request = gemini_body_to_openai_chat(body, lane_id='omi:auto:desktop-vertex-flash-38', stream=False)
    assert request['google'] == {'thinking_config': {'thinking_level': 'low'}}
    target = ptr.model_payload(body, ptr.PT_MODEL_TARGET)
    fallback = ptr.model_payload(body, 'gemini-2.5-flash-lite')
    assert target['generationConfig']['thinkingConfig'] == {'thinkingLevel': 'low'}
    assert fallback['generationConfig']['thinkingConfig'] == {'thinkingBudget': 1024}
    assert body['generationConfig']['thinkingConfig'] == {'thinkingLevel': 'low'}


def test_bounded_gate_metadata_and_direct_model_adaptation():
    assert direct.gate_fields({'x-omi-screen-task-gate': 'PRIVATE', 'x-omi-screen-task-audit': 'true'}) == {
        'gate_outcome': 'none',
        'audit_sample': False,
    }
    assert direct.gate_fields({'x-omi-screen-task-gate': 'rejected', 'x-omi-screen-task-audit': 'true'}) == {
        'gate_outcome': 'rejected',
        'audit_sample': True,
    }
    original = b'{"contents": [], "generationConfig": {"thinkingConfig": {"thinkingLevel": "low"}}}'
    wire = json.loads(
        direct.request_body(
            original, 'https://us-central1-aiplatform.googleapis.com/models/gemini-2.5-flash-lite:generateContent'
        )
    )
    assert wire['generationConfig']['thinkingConfig'] == {'thinkingBudget': 1024}


@pytest.mark.asyncio
@pytest.mark.parametrize('location', ['us', 'us-central1', 'global'])
async def test_direct_kill_switch_uses_same_declared_location_and_old_client_capacity(monkeypatch, location):

    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv(ptr.PT_TARGET_LOCATION_ENV, location)
    monkeypatch.setattr(proxy._vertex_tokens, 'get_access_token', _token)
    proxy._reservation_snapshot.set({ptr.PT_MODEL_TARGET: State.ACTIVE})
    monkeypatch.setattr(proxy, 'get_byok_key', lambda name: None)
    route = await proxy._upstream(
        f'models/{ptr.PT_MODEL_TARGET}:generateContent', ptr.PT_MODEL_TARGET, 'generateContent', {}
    )
    assert f'/locations/{location}/' in route.url
    assert route.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated'
    assert proxy._recovery_plan(
        ptr.PT_MODEL_TARGET, 429, 'No provisioned throughput order configured', capacity='dedicated'
    )[0] == (ptr.PT_MODEL_TARGET, 'shared')
    proxy._reservation_snapshot.set({proxy.VERTEX_PT_TARGET_MODEL: State.ACTIVE, proxy.VERTEX_PT_MODEL: State.INACTIVE})
    old = await proxy._upstream(
        f'models/{ptr.PT_MODEL_CURRENT}:generateContent', ptr.PT_MODEL_CURRENT, 'generateContent', {}
    )
    assert '/locations/us-central1/' in old.url
    assert old.headers[ptr.REQUEST_TYPE_HEADER] == 'shared'
    assert all(
        ptr.model_within_origin_price(model, ptr.PT_MODEL_TARGET)
        for model, _ in proxy._overflow_plan(ptr.PT_MODEL_TARGET)
    )


# Captured from a real dedicated gemini-3.8-flash request on locations/us,
# 2026-10-02, while no target order exists. This is a Google error, not user data.
ABSENT_TARGET_ORDER_RESPONSE = {
    'error': {
        'code': 429,
        'message': (
            'Too many requests. Exceeded the provisioned throughput. Please refer to '
            'https://cloud.google.com/vertex-ai/generative-ai/docs/error-code-429 for more details.'
        ),
        'status': 'RESOURCE_EXHAUSTED',
    }
}


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('status', [200, 201])
@pytest.mark.parametrize('traffic', ['missing', 'PROVISIONED_THROUGHPUT', 'ON_DEMAND', None])
async def test_only_successful_dedicated_target_response_with_valid_traffic_promotes(
    monkeypatch, stream, status, traffic
):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    seen = []

    def handler(request):
        seen.append(request)
        result = _response()
        result.pop('usageMetadata', None)
        if traffic != 'missing':
            result['usageMetadata'] = {'trafficType': traffic}
        if stream:
            # A final ON_DEMAND/null block must override earlier PT metadata.
            earlier = {'usageMetadata': {'trafficType': 'PROVISIONED_THROUGHPUT'}}
            return httpx.Response(
                status, text='data: ' + json.dumps(earlier) + '\n\n' + 'data: ' + json.dumps(result) + '\n\n'
            )
        return httpx.Response(status, json=result)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=_token)
        monkeypatch.setattr(provider, '_attempt_plan', lambda *a, **k: [(ptr.PT_MODEL_TARGET, 'dedicated')])
        kwargs = dict(
            provider_ref=ProviderRef(provider='gemini', model=ptr.PT_MODEL_TARGET),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=1000,
        )
        request = {'messages': [{'role': 'user', 'content': 'test'}]}
        if stream:
            assert [chunk async for chunk in provider.stream_chat_completion(request, **kwargs)]
        else:
            await provider.create_chat_completion(request, **kwargs)
        assert provider._reservation_active(ptr.PT_MODEL_TARGET) == (
            traffic == 'PROVISIONED_THROUGHPUT' or (stream and traffic == 'missing')
        )
    assert len(seen) == 1 and seen[0].headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated'


@pytest.mark.asyncio
async def test_inactive_override_never_probes_with_customer_content_in_either_path(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv('OMI_VERTEX_RESERVATION_STATES', json.dumps({ptr.PT_MODEL_TARGET: 'inactive'}))
    monkeypatch.setattr(proxy._vertex_tokens, 'get_access_token', _token)
    monkeypatch.setattr(proxy, 'get_byok_key', lambda name: None)
    proxy._reservation_snapshot.set({})
    route = await proxy._upstream(
        f'models/{ptr.PT_MODEL_TARGET}:generateContent', ptr.PT_MODEL_TARGET, 'generateContent', {}
    )
    assert route.headers[ptr.REQUEST_TYPE_HEADER] == 'shared'
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=_response()))
    ) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=_token)
        assert provider._attempt_plan(ptr.PT_MODEL_TARGET) == [(ptr.PT_MODEL_TARGET, 'shared')]
        await provider.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
async def test_slow_reservation_io_keeps_short_request_budget_for_inference(monkeypatch, stream):
    from unittest.mock import AsyncMock

    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    seen = []

    def handler(request):
        seen.append(request)
        payload = _response()
        return (
            httpx.Response(200, text='data: ' + json.dumps(payload) + '\n\n')
            if stream
            else httpx.Response(200, json=payload)
        )

    async def stalled(*args, **kwargs):
        await asyncio.Event().wait()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=_token)
        monkeypatch.setattr(provider._reservations, 'transact', stalled)
        kwargs = dict(
            provider_ref=ProviderRef(provider='gemini', model=ptr.PT_MODEL_CURRENT),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=100,
        )
        async with asyncio.timeout(0.2):
            if stream:
                chunks = [
                    chunk
                    async for chunk in provider.stream_chat_completion(
                        {'messages': [{'role': 'user', 'content': 'synthetic'}]}, **kwargs
                    )
                ]
                assert chunks
            else:
                await provider.create_chat_completion(
                    {'messages': [{'role': 'user', 'content': 'synthetic'}]}, **kwargs
                )
        assert len(seen) == 1
        close = AsyncMock()
        monkeypatch.setattr(provider._reservations, 'aclose', close)
        await provider.aclose()
        close.assert_awaited_once()


@pytest.fixture(autouse=True)
def held_discovery_leases_for_request_matrix(monkeypatch):
    """Keep synthetic discovery separate from customer-attempt/accounting fixtures."""
    from utils.llm import vertex_reservation_state

    monkeypatch.setattr(vertex_reservation_state, 'discovery_models', lambda _: frozenset())
