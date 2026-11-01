import json

import httpx
import pytest

from llm_gateway.gateway.cache_policy import apply_lane_cache_policy
from llm_gateway.gateway.vertex_cache import CacheReceipt, VertexContentCache, validated_stream
from llm_gateway.gateway.vertex_wire import _vertex_request
from llm_gateway.gateway.provider_types import _VertexHttpError

ENDPOINT = 'https://us-aiplatform.googleapis.com/v1/projects/synthetic-project/locations/us/publishers/google/models/gemini-3.8-flash:generateContent'
NAME = 'projects/synthetic-project/locations/us/cachedContents/invented-cache'


@pytest.mark.asyncio
async def test_retiring_stream_buffer_is_bounded_and_closes_without_output():
    from llm_gateway.gateway.provider_types import ProviderFailure

    closed = []

    async def source():
        try:
            yield b'ab'
            yield b'cd'
        finally:
            closed.append(True)

    output = []
    with pytest.raises(ProviderFailure):
        async for chunk in validated_stream(source(), enabled=True, max_bytes=3):
            output.append(chunk)
    assert output == [] and closed == [True]


@pytest.mark.asyncio
@pytest.mark.parametrize('limit_kind', ['small', 'invalid_config'])
async def test_unbuffered_stream_preserves_first_chunk_and_bytes_without_limit_read(limit_kind):
    stages = []

    async def source():
        stages.append('first')
        yield b'ab'
        stages.append('second')
        yield b'cd'

    limit = 1 if limit_kind == 'small' else lambda: pytest.fail('unbuffered stream must not read a new byte cap')
    stream = validated_stream(source(), enabled=False, max_bytes=limit)
    assert await anext(stream) == b'ab'
    assert stages == ['first']
    assert [part async for part in stream] == [b'cd']


def request(lane='omi:auto:dream-reasoning', *, force_explicit=False):
    result = {
        '_dream_capacity_mode': 'reserved',
        'messages': [
            {'role': 'system', 'content': 'contract'},
            {
                'role': 'user',
                'content': [
                    {
                        'type': 'text',
                        'text': 'synthetic stable context ' * 1100,
                        'prompt_cache_breakpoint': {'mode': 'explicit'},
                    }
                ],
            },
            {'role': 'user', 'content': 'invented continuation'},
        ],
        'tools': [
            {'type': 'function', 'function': {'name': 'invented', 'parameters': {'type': 'object', 'properties': {}}}}
        ],
    }
    apply_lane_cache_policy(result, lane=lane, provider='gemini', model='gemini-3.8-flash')
    if force_explicit:
        # Exercise the cache manager's explicit path independently of the
        # production Gemini lane policy, which now leaves caching implicit.
        result['_gateway_cache_policy']['mode'] = 'explicit'
    return result


@pytest.mark.asyncio
async def test_cache_wire_reuse_owner_isolation_expiry_and_refresh():
    calls = []
    clock = [100.0]

    def handle(req):
        calls.append(req)
        return httpx.Response(200, json={'name': NAME, 'usageMetadata': {'totalTokenCount': 6400}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        cache = VertexContentCache(client, now=lambda: clock[0])
        req = request(force_explicit=True)
        payload = _vertex_request(req)
        assert payload['contents'] == [
            {
                'role': 'user',
                'parts': [
                    {'text': 'synthetic stable context ' * 1100},
                    {'text': 'invented continuation'},
                ],
            }
        ]

        async def prepare(owner='synthetic-owner-a'):
            receipt = CacheReceipt()
            body, key = await cache.prepare(
                payload,
                request=req,
                owner=owner,
                endpoint=ENDPOINT,
                model='gemini-3.8-flash',
                headers={'Authorization': 'synthetic-token', 'X-Vertex-AI-LLM-Request-Type': 'dedicated'},
                receipt=receipt,
            )
            return body, key, receipt

        body, key, receipt = await prepare()
        assert body['cachedContent'] == NAME
        assert 'systemInstruction' not in body and 'tools' not in body
        assert body['contents'] == [{'role': 'user', 'parts': [{'text': 'invented continuation'}]}]
        assert receipt.write_tokens == 6400
        assert receipt.storage_token_seconds == 6400 * 1800
        assert 'X-Vertex-AI-LLM-Request-Type' not in calls[0].headers
        created = json.loads(calls[0].content)
        assert created['model'].endswith('/models/gemini-3.8-flash')
        assert created['systemInstruction'] == payload['systemInstruction']
        assert created['tools'] == payload['tools']
        assert created['contents'] == [{'role': 'user', 'parts': [{'text': 'synthetic stable context ' * 1100}]}]
        assert (await prepare())[2].write_tokens == 0
        assert len(calls) == 1
        assert (await prepare('synthetic-owner-b'))[1] != key
        assert len(calls) == 2
        clock[0] += 1000
        assert (await prepare())[2].storage_token_seconds == 6400 * 1000
        assert calls[-1].method == 'PATCH'
        clock[0] += 1900
        assert (await prepare())[2].write_tokens == 6400
        assert calls[-1].method == 'POST'


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'lane',
    [
        'omi:auto:dream-reasoning',
        'omi:auto:dream-verify',
        'omi:auto:desktop-vertex-flash',
    ],
)
async def test_configured_gemini_lanes_do_not_create_vertex_caches(lane):
    calls = []

    def handle(req):
        calls.append(req)
        raise AssertionError(f'unexpected Vertex cache request: {req.method} {req.url}')

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        cache = VertexContentCache(client)
        req = request(lane=lane)
        payload = _vertex_request(req)
        body, key = await cache.prepare(
            payload,
            request=req,
            owner='synthetic-owner',
            endpoint=ENDPOINT,
            model='gemini-3.8-flash',
            headers={},
            receipt=CacheReceipt(),
        )

    assert req['_gateway_cache_policy']['mode'] == 'implicit'
    assert body == payload and key is None
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [400, 403, 429, 500])
async def test_cache_errors_fall_through(status):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(status, json={}))) as client:
        cache = VertexContentCache(client)
        req = request(force_explicit=True)
        payload = _vertex_request(req)
        receipt = CacheReceipt()
        body, key = await cache.prepare(
            payload,
            request=req,
            owner='synthetic-owner',
            endpoint=ENDPOINT,
            model='gemini-3.8-flash',
            headers={},
            receipt=receipt,
        )
        assert body == payload and key is None and receipt.mode == 'implicit'


@pytest.mark.asyncio
async def test_expired_handle_recreated_once_then_uncached():
    creates = []

    def handle(req):
        creates.append(req)
        return httpx.Response(200, json={'name': NAME, 'usageMetadata': {'totalTokenCount': 6400}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        cache = VertexContentCache(client)
        req = request(force_explicit=True)
        payload = _vertex_request(req)
        sent = []

        async def send(body):
            sent.append(body)
            if 'cachedContent' in body:
                raise _VertexHttpError(404, b'')
            return {'synthetic': True}

        receipt = CacheReceipt()
        assert await cache.generate(
            send,
            payload,
            request=req,
            owner='synthetic-owner',
            endpoint=ENDPOINT,
            model='gemini-3.8-flash',
            headers={},
            receipt=receipt,
            allow_recreate=True,
        ) == {'synthetic': True}
        assert len(creates) == 2 and len(sent) == 3
        assert sent[-1] == payload
        assert receipt.mode == 'implicit' and receipt.write_tokens == 12800


@pytest.mark.asyncio
async def test_short_or_ownerless_prefix_never_persists():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: pytest.fail('unexpected cache I/O'))
    ) as client:
        cache = VertexContentCache(client)
        for req, owner in [
            (request(force_explicit=True), None),
            (
                {'messages': [{'role': 'system', 'content': 'short'}, {'role': 'user', 'content': 'tail'}]},
                'synthetic-owner',
            ),
        ]:
            apply_lane_cache_policy(req, lane='omi:auto:dream-verify', provider='gemini', model='gemini-3.8-flash')
            req['_gateway_cache_policy']['mode'] = 'explicit'
            payload = _vertex_request(req)
            assert (
                await cache.prepare(
                    payload,
                    request=req,
                    owner=owner,
                    endpoint=ENDPOINT,
                    model='gemini-3.8-flash',
                    headers={},
                    receipt=CacheReceipt(),
                )
            )[0] == payload


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'lane',
    [
        'omi:auto:dream-reasoning',
        'omi:auto:dream-verify',
    ],
)
@pytest.mark.parametrize('capacity', ['dedicated', 'shared'])
@pytest.mark.parametrize('streaming', [False, True])
async def test_provider_boundary_skips_explicit_cache_for_gemini_lanes(monkeypatch, lane, capacity, streaming):
    from llm_gateway.gateway.auth import ServiceCaller
    from llm_gateway.gateway.credentials import build_omi_managed_credential_context
    from llm_gateway.gateway.providers import VertexGeminiProvider
    from llm_gateway.gateway.schemas import ProviderRef
    from llm_gateway.gateway.accounting import openai_usage_from_sse_payload, CacheStatus
    from llm_gateway.gateway.sse import SSEEventDecoder

    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv('DREAM_ON_DEMAND_ENABLED', 'true')
    seen = []

    def handle(req):
        seen.append(req)
        if req.url.path.endswith('/cachedContents'):
            return httpx.Response(
                200,
                json={
                    'name': req.url.path.removeprefix('/v1/') + '/invented-cache',
                    'usageMetadata': {'totalTokenCount': 6400},
                },
            )
        payload = {
            'candidates': [{'content': {'parts': [{'text': 'invented answer'}]}, 'finishReason': 'STOP'}],
            'trafficType': 'ON_DEMAND' if capacity == 'shared' else 'PROVISIONED_THROUGHPUT',
            'usageMetadata': {'promptTokenCount': 6500, 'candidatesTokenCount': 4},
        }
        if streaming:
            return httpx.Response(200, content=f'data: {json.dumps(payload)}\n\n'.encode())
        return httpx.Response(200, json=payload)

    async def token():
        return 'synthetic-token'

    async def refresh(budget):
        pass

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=token)
        monkeypatch.setattr(provider, '_refresh_reservations', refresh)
        req = request(lane=lane)
        if capacity == 'shared':
            req.update(_dream_capacity_mode='on_demand', google={'dream_owner_allowlisted': True})
        kwargs = {
            'provider_ref': ProviderRef(provider='gemini', model='gemini-3.8-flash'),
            'credentials': build_omi_managed_credential_context(
                ServiceCaller(name='backend', user_uid='synthetic-owner', tenant_id='synthetic-tenant')
            ),
            'timeout_ms': 10000,
        }
        if streaming:
            decoder = SSEEventDecoder()
            events = []
            async for chunk in provider.stream_chat_completion(req, **kwargs):
                events.extend(decoder.feed(chunk))
            metadata = [openai_usage_from_sse_payload(json.loads(e.data)) for e in events if e.data != '[DONE]'][-1]
            assert metadata.cache_mode == 'implicit' and metadata.cache_write_tokens == 0
            assert metadata.usage.cache_status == CacheStatus.NOT_REPORTED
        else:
            response = await provider.create_chat_completion(req, **kwargs)
            assert response.accounting.cache_mode == 'implicit'
            assert response.accounting.cache_write_tokens == 0
            assert response.accounting.traffic_type == (
                'ON_DEMAND' if capacity == 'shared' else 'PROVISIONED_THROUGHPUT'
            )
        assert len(seen) == 1
        inference = seen[-1]
        assert inference.headers['X-Vertex-AI-LLM-Request-Type'] == capacity
        assert not any(req.url.path.endswith('/cachedContents') for req in seen)
        assert 'cachedContent' not in json.loads(inference.content)
        assert 'systemInstruction' in json.loads(inference.content)


@pytest.mark.asyncio
@pytest.mark.parametrize('early_close', [False, True])
async def test_vertex_prepared_stream_may_resume_or_close_in_another_task(monkeypatch, early_close):
    import asyncio
    from llm_gateway.gateway.providers import VertexGeminiProvider
    from llm_gateway.gateway.auth import ServiceCaller
    from llm_gateway.gateway.credentials import build_omi_managed_credential_context
    from llm_gateway.gateway.schemas import ProviderRef
    from unittest.mock import AsyncMock
    from config.vertex_reservations import State

    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.delenv('OMI_VERTEX_PT_MODEL', raising=False)
    monkeypatch.delenv('OMI_VERTEX_RESERVATION_STATES', raising=False)

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"candidates":[{"content":{"parts":[{"text":"invented"}]}}]}\n\n'
            yield b'data: {"candidates":[{"finishReason":"STOP"}],"usageMetadata":{"trafficType":"PROVISIONED_THROUGHPUT"}}\n\n'

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, stream=Stream()))
    ) as client:
        provider = VertexGeminiProvider(
            http_client=client, access_token_supplier=AsyncMock(return_value='synthetic-token')
        )
        monkeypatch.setattr(
            provider._reservations, 'refresh', AsyncMock(return_value={'gemini-3.8-flash': State.ACTIVE})
        )
        monkeypatch.setattr(provider._reservations, 'record', AsyncMock())
        stream = provider.stream_chat_completion(
            {
                'messages': [{'role': 'user', 'content': 'invented'}],
                '_dream_capacity_mode': 'reserved',
                '_gateway_cache_policy': {'lane': 'omi:auto:dream-reasoning'},
            },
            provider_ref=ProviderRef(provider='gemini', model='gemini-3.8-flash'),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend', user_uid='synthetic-owner')),
            timeout_ms=10000,
        )

        async def first():
            result = await anext(stream)
            assert provider._cache_context.get() is None
            return result

        assert b'invented' in await asyncio.create_task(first())

        async def resume():
            if early_close:
                await stream.aclose()
            else:
                assert b'[DONE]' in b''.join([chunk async for chunk in stream])
            assert provider._cache_context.get() is None

        await asyncio.create_task(resume())
        assert provider._cache_context.get() is None
