"""The moved-order behavior, wire thinking and per-origin overflow contract."""

import asyncio
import json

import httpx
import pytest

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
    return {'candidates': [{'content': {'parts': [{'text': 'ok'}]}, 'finishReason': 'STOP'}]}


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
        credentials = build_omi_managed_credential_context(ServiceCaller(name='backend'))
        await provider.create_chat_completion(
            {'messages': [{'role': 'user', 'content': 'test'}]},
            provider_ref=ProviderRef(provider='gemini', model=ptr.PT_MODEL_TARGET),
            credentials=credentials,
            timeout_ms=1000,
        )
        assert provider._pt_target_ready
        assert provider._provisioned_model() == ptr.PT_MODEL_TARGET
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
    assert seen[1].headers[ptr.REQUEST_TYPE_HEADER] == 'shared'


@pytest.mark.asyncio
async def test_absent_order_retries_same_target_on_us_paygo_without_touching_current_order(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    seen = []

    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(429, json={'error': {'message': 'No provisioned throughput order configured'}})
        return httpx.Response(200, json=_response())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=_token)
        await provider.create_chat_completion(
            {'messages': [{'role': 'user', 'content': 'test'}]},
            provider_ref=ProviderRef(provider='gemini', model=ptr.PT_MODEL_TARGET),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=1000,
        )
        assert not provider._pt_target_ready
        assert provider._attempt_plan(ptr.PT_MODEL_CURRENT) == [(ptr.PT_MODEL_CURRENT, 'dedicated')]
    assert [r.headers[ptr.REQUEST_TYPE_HEADER] for r in seen] == ['dedicated', 'shared']
    assert all('/locations/us/' in str(r.url) for r in seen)


def test_old_client_list_price_is_never_promoted_and_overflow_is_capped():
    for ready in [False, True]:
        pt = ptr.resolve_pt_model(target_dedicated_ready=ready)
        assert ptr.desktop_serving_model(ptr.PT_MODEL_CURRENT, target_dedicated_ready=ready) == ptr.PT_MODEL_CURRENT
        assert ptr.desktop_serving_model('gemini-2.5-pro', target_dedicated_ready=ready) == 'gemini-3.1-flash-lite'
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
@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('failure', [401, 403, 404, 429, 500, 'timeout', 'connection', 'malformed'])
async def test_any_dedicated_probe_failure_retries_shared_and_never_promotes(monkeypatch, failure, stream):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    seen = []

    def handler(request):
        seen.append(request)
        if request.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated':
            if failure == 'timeout':
                raise httpx.ReadTimeout('probe timed out', request=request)
            if failure == 'connection':
                raise httpx.ConnectError('probe disconnected', request=request)
            if failure == 'malformed':
                return httpx.Response(200, text='data: {invalid\n\n' if stream else '{invalid')
            return httpx.Response(failure, json={'error': {'message': 'unclassified failure'}})
        return (
            httpx.Response(200, text='data: ' + json.dumps(_response()) + '\n\n')
            if stream
            else httpx.Response(200, json=_response())
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=_token)
        kwargs = dict(
            provider_ref=ProviderRef(provider='gemini', model=ptr.PT_MODEL_TARGET),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=1000,
        )
        request = {'messages': [{'role': 'user', 'content': 'test'}]}
        if stream:
            assert [chunk async for chunk in provider.stream_chat_completion(request, **kwargs)]
        else:
            assert (await provider.create_chat_completion(request, **kwargs)).response['choices'][0]['message'][
                'content'
            ] == 'ok'
        assert not provider._pt_target_ready
        assert provider._provisioned_model() == ptr.PT_MODEL_CURRENT
        assert ptr.PT_MODEL_TARGET not in provider._model_unavailable_at
    assert [r.headers[ptr.REQUEST_TYPE_HEADER] for r in seen] == ['dedicated', 'shared']


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
async def test_probe_deadline_cancels_stalled_body_and_leaves_shared_request_budget(monkeypatch, stream):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    seen = []
    cancelled = []

    class StalledProbe(httpx.AsyncByteStream):
        async def __aiter__(self):
            try:
                if stream:
                    response = {'candidates': [{'content': {'parts': [{'text': 'dedicated-partial'}]}}]}
                    yield ('data: ' + json.dumps(response) + '\n\n').encode()
                await asyncio.Future()  # Deliberately unresponsive upstream; production timeout must cancel it.
            except asyncio.CancelledError:
                cancelled.append(True)
                raise

    def handler(request):
        seen.append(request)
        if request.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated':
            return httpx.Response(200, stream=StalledProbe())
        return (
            httpx.Response(200, text='data: ' + json.dumps(_response()) + '\n\n')
            if stream
            else httpx.Response(200, json=_response())
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=_token)
        kwargs = dict(
            provider_ref=ProviderRef(provider='gemini', model=ptr.PT_MODEL_TARGET),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=200,
        )
        request = {'messages': [{'role': 'user', 'content': 'test'}]}
        # This outer assertion bounds the whole user request, not only httpx's declared timeout.
        async with asyncio.timeout(0.2):
            if stream:
                chunks = [chunk async for chunk in provider.stream_chat_completion(request, **kwargs)]
                assert b'dedicated-partial' not in b''.join(chunks)
            else:
                assert (await provider.create_chat_completion(request, **kwargs)).response['choices'][0]['message'][
                    'content'
                ] == 'ok'
        assert cancelled == [True] and not provider._pt_target_ready
    assert [r.headers[ptr.REQUEST_TYPE_HEADER] for r in seen] == ['dedicated', 'shared']
    assert 0 < seen[0].extensions['timeout']['read'] <= 0.05
    assert 0 < seen[1].extensions['timeout']['read'] <= 0.16
    assert VertexGeminiProvider._pt_probe_timeout_ms(75000) == 1000


@pytest.mark.asyncio
async def test_streaming_absent_regional_order_retries_us_shared_then_next_probe_promotes(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv(ptr.PT_TARGET_LOCATION_ENV, 'us-central1')
    seen = []

    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(404, json={'error': {'message': 'Publisher Model was not found'}})
        return httpx.Response(
            200, text='data: ' + json.dumps(_response()) + '\n\n', headers={'content-type': 'text/event-stream'}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=_token)
        credentials = build_omi_managed_credential_context(ServiceCaller(name='backend'))
        request = {'messages': [{'role': 'user', 'content': 'test'}]}
        ref = ProviderRef(provider='gemini', model=ptr.PT_MODEL_TARGET)
        chunks = [
            chunk
            async for chunk in provider.stream_chat_completion(
                request, provider_ref=ref, credentials=credentials, timeout_ms=1000
            )
        ]
        assert chunks and not provider._pt_target_ready
        assert ptr.PT_MODEL_TARGET not in provider._model_unavailable_at
        provider._pt_target_probed_at = None
        chunks = [
            chunk
            async for chunk in provider.stream_chat_completion(
                request, provider_ref=ref, credentials=credentials, timeout_ms=1000
            )
        ]
        assert chunks and provider._pt_target_ready
    assert [r.headers[ptr.REQUEST_TYPE_HEADER] for r in seen] == ['dedicated', 'shared', 'dedicated']
    assert '/locations/us-central1/' in str(seen[0].url)
    assert '/locations/us/' in str(seen[1].url)


@pytest.mark.asyncio
@pytest.mark.parametrize('location', ['us', 'us-central1', 'global'])
async def test_direct_kill_switch_uses_same_declared_location_and_old_client_capacity(monkeypatch, location):

    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv(ptr.PT_TARGET_LOCATION_ENV, location)
    monkeypatch.setattr(proxy._vertex_tokens, 'get_access_token', _token)
    monkeypatch.setattr(proxy, '_pt_target_ready', False)
    monkeypatch.setattr(proxy, '_pt_target_probed_at', None)
    monkeypatch.setattr(proxy, 'get_byok_key', lambda name: None)
    route = await proxy._upstream(
        f'models/{ptr.PT_MODEL_TARGET}:generateContent', ptr.PT_MODEL_TARGET, 'generateContent', {}
    )
    assert f'/locations/{location}/' in route.url
    assert route.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated'
    assert proxy._recovery_plan(
        ptr.PT_MODEL_TARGET, 429, 'No provisioned throughput order configured', capacity='dedicated'
    )[0] == (ptr.PT_MODEL_TARGET, 'shared')
    proxy._record_pt_target_observation(True)
    old = await proxy._upstream(
        f'models/{ptr.PT_MODEL_CURRENT}:generateContent', ptr.PT_MODEL_CURRENT, 'generateContent', {}
    )
    assert '/locations/us-central1/' in old.url
    assert old.headers[ptr.REQUEST_TYPE_HEADER] == 'shared'
    assert all(
        ptr.model_within_origin_price(model, ptr.PT_MODEL_TARGET)
        for model, _ in proxy._overflow_plan(ptr.PT_MODEL_TARGET)
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('ready', [False, True])
@pytest.mark.parametrize('absent', [False, True])
async def test_target_absent_order_keeps_probe_ttl_but_full_order_promotes_and_spills_same_model(
    monkeypatch, stream, ready, absent
):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    seen = []
    now = [100.0]
    message = (
        'NO PROVISIONED THROUGHPUT ORDER CONFIGURED'
        if absent
        else 'Provisioned Throughput dedicated capacity exhausted'
    )

    def handler(request):
        seen.append(request)
        now[0] += 0.125
        if len(seen) == 1:
            return httpx.Response(429, json={'error': {'message': message}})
        return (
            httpx.Response(200, text='data: ' + json.dumps(_response()) + '\n\n')
            if stream
            else httpx.Response(200, json=_response())
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=_token, now=lambda: now[0])
        provider._pt_target_ready = ready
        kwargs = dict(
            provider_ref=ProviderRef(provider='gemini', model=ptr.PT_MODEL_TARGET),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=1000,
        )
        request = {'messages': [{'role': 'user', 'content': 'test'}]}
        if stream:
            assert [chunk async for chunk in provider.stream_chat_completion(request, **kwargs)]
        else:
            assert (await provider.create_chat_completion(request, **kwargs)).response['choices'][0]['message'][
                'content'
            ] == 'ok'
        assert provider._pt_target_ready == (not absent)
        assert [r.headers[ptr.REQUEST_TYPE_HEADER] for r in seen] == ['dedicated', 'shared']
        assert all(f'/models/{ptr.PT_MODEL_TARGET}:' in str(r.url) for r in seen)
        assert seen[0].extensions['timeout']['read'] == (1.0 if ready else 0.25)
        assert seen[1].extensions['timeout']['read'] == 0.875
        assert provider._attempt_plan(ptr.PT_MODEL_TARGET) == [
            (ptr.PT_MODEL_TARGET, 'shared' if absent else 'dedicated')
        ]
        assert provider._attempt_plan(ptr.PT_MODEL_CURRENT) == [
            (ptr.PT_MODEL_CURRENT, 'dedicated' if absent else 'shared')
        ]
        if absent:
            probe_at = provider._pt_target_probed_at
            assert probe_at is not None
            now[0] = probe_at + 599
            assert provider._attempt_plan(ptr.PT_MODEL_TARGET) == [(ptr.PT_MODEL_TARGET, 'shared')]
            now[0] = probe_at + 600
            assert provider._attempt_plan(ptr.PT_MODEL_TARGET) == [
                (ptr.PT_MODEL_TARGET, 'dedicated'),
                (ptr.PT_MODEL_TARGET, 'shared'),
            ]


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
async def test_only_target_probe_rejects_3xx_while_shared_target_accepts_its_body(monkeypatch, stream):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    seen = []

    def handler(request):
        seen.append(request)
        return (
            httpx.Response(302, text='data: ' + json.dumps(_response()) + '\n\n')
            if stream
            else httpx.Response(302, json=_response())
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=_token)
        kwargs = dict(
            provider_ref=ProviderRef(provider='gemini', model=ptr.PT_MODEL_TARGET),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=1000,
        )
        request = {'messages': [{'role': 'user', 'content': 'test'}]}
        if stream:
            assert [chunk async for chunk in provider.stream_chat_completion(request, **kwargs)]
        else:
            assert (await provider.create_chat_completion(request, **kwargs)).response['choices'][0]['message'][
                'content'
            ] == 'ok'
        assert not provider._pt_target_ready
    assert [r.headers[ptr.REQUEST_TYPE_HEADER] for r in seen] == ['dedicated', 'shared']
