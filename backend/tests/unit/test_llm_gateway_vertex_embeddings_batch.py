"""Exercise the real Vertex adapter against gemini-embedding-001's wire limit."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import ProviderFailure, VertexGeminiProvider
from llm_gateway.gateway.schemas import FailureClass, ProviderRef
from llm_gateway.main import app
from llm_gateway.routers import dependencies, embeddings
from utils.llm import desktop_gemini_gateway as dgg


async def _access_token() -> str:
    return 'test-token'


@pytest.mark.asyncio
@pytest.mark.parametrize('inputs', ['text', ['text']])
async def test_single_input_keeps_exact_wire_timeout_after_token_acquisition(monkeypatch, inputs):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    now = [100.0]
    seen = []

    async def token():
        now[0] += 0.3
        return 'test-token'

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={'predictions': [{'embeddings': {'values': [0.1]}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await VertexGeminiProvider(
            http_client=client, access_token_supplier=token, now=lambda: now[0]
        ).create_embedding(
            {'input': inputs},
            provider_ref=ProviderRef(provider='gemini', model='gemini-embedding-001'),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=60_000,
        )
    assert len(seen) == 1
    assert seen[0].extensions['timeout'] == dict(connect=60.0, read=60.0, write=60.0, pool=60.0)
    assert result.response['data'] == [{'object': 'embedding', 'embedding': [0.1], 'index': 0}]
    assert result.accounting.usage is None


@pytest.mark.asyncio
@pytest.mark.parametrize('count', [2, 100])
async def test_batch_obeys_vertex_single_input_limit_and_preserves_mapping(monkeypatch, count):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    seen = []

    def handler(request):
        payload = json.loads(request.content)
        seen.append(payload)
        # Model-specific limit, not the generic 250-text embeddings quota.
        if len(payload['instances']) != 1:
            return httpx.Response(400, json={'error': {'message': 'only one input text is supported'}})
        instance = payload['instances'][0]
        assert instance['task_type'] == 'RETRIEVAL_DOCUMENT'
        assert instance['title'] == 'document'
        return httpx.Response(200, json={'predictions': [{'embeddings': {'values': [int(instance['content'])]}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=_access_token)
        result = await provider.create_embedding(
            {'input': [str(i) for i in range(count)], 'task_type': 'RETRIEVAL_DOCUMENT', 'title': 'document'},
            provider_ref=ProviderRef(provider='gemini', model='gemini-embedding-001'),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=30_000,
        )

    assert len(seen) == count
    assert [item['index'] for item in result.response['data']] == list(range(count))
    assert [item['embedding'] for item in result.response['data']] == [[float(i)] for i in range(count)]
    assert result.accounting.usage is None


@pytest.mark.asyncio
async def test_full_desktop_batch_avoids_aggregate_response_byte_cap(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    monkeypatch.delenv('OPENAI_MAX_RESPONSE_BYTES', raising=False)
    vector = [0.012345678901234567] * 3072
    prediction = json.dumps({'embeddings': {'values': vector}}).encode()
    # 100 default-dimensional embeddings exceed the old 2 MiB reader cap even
    # when the upstream returns HTTP 200. A permissive upstream fixture isolates
    # this local provider_5xx mechanism from Vertex's separate one-input limit.
    old_batch_body = b'{"predictions":[' + b','.join([prediction] * 100) + b']}'
    assert len(old_batch_body) > 2 * 1024 * 1024
    seen = []

    def handler(request):
        instances = json.loads(request.content)['instances']
        seen.append(len(instances))
        body = b'{"predictions":[' + b','.join([prediction] * len(instances)) + b']}'
        return httpx.Response(200, content=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await VertexGeminiProvider(http_client=client, access_token_supplier=_access_token).create_embedding(
            {'input': ['text'] * 100},
            provider_ref=ProviderRef(provider='gemini', model='gemini-embedding-001'),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=30_000,
        )
    assert seen == [1] * 100
    assert len(result.response['data']) == 100
    assert all(item['embedding'] == vector for item in result.response['data'])


@pytest.mark.parametrize(
    'status,expected_class',
    [(400, 'provider_invalid_request'), (429, 'provider_429_omi_paid'), (503, 'provider_5xx_omi_paid')],
)
def test_upstream_status_reaches_terminal_log_without_provider_body(monkeypatch, caplog, status, expected_class):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    monkeypatch.setattr(embeddings, 'schedule_attempt_trace', lambda *args: None)
    secret = 'private-user-text-and-provider-body'
    provider = VertexGeminiProvider(
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(status, text=secret))
        ),
        access_token_supplier=_access_token,
    )
    app.dependency_overrides[dependencies.get_provider_registry] = lambda: ProviderRegistry({'gemini': provider})
    try:
        response = TestClient(app).post(
            '/v1/embeddings',
            json={'model': 'omi:auto:gemini-embeddings', 'input': secret},
            headers={'x-omi-service-caller': 'backend', 'authorization': 'Bearer shared-secret'},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == (400 if status == 400 else 502)
    assert response.json()['error']['failure_class'] == expected_class
    logs = [record.message for record in caplog.records if 'llm_gateway_terminal' in record.message]
    assert len(logs) == 1
    assert f'upstream_http_status={status}' in logs[0]
    assert secret not in caplog.text


@pytest.mark.asyncio
async def test_batch_has_bounded_fanout_and_restores_out_of_order_results(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    started = asyncio.Event()
    release = asyncio.Event()
    calls = []
    finished = []
    active = 0
    peak = 0

    async def handler(request):
        nonlocal active, peak
        index = int(json.loads(request.content)['instances'][0]['content'])
        calls.append(index)
        active += 1
        peak = max(peak, active)
        try:
            if len(calls) == 8:
                started.set()
            # The first item completes after the others, not in input order.
            if index == 0:
                await release.wait()
            else:
                await started.wait()
            finished.append(index)
            if len(finished) == 19:
                release.set()
            return httpx.Response(200, json={'predictions': [{'embeddings': {'values': [index]}}]})
        finally:
            active -= 1

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await asyncio.wait_for(
            VertexGeminiProvider(http_client=client, access_token_supplier=_access_token).create_embedding(
                {'input': [str(i) for i in range(20)]},
                provider_ref=ProviderRef(provider='gemini', model='gemini-embedding-001'),
                credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
                timeout_ms=1000,
            ),
            timeout=2,
        )
    assert peak == 8
    assert active == 0
    assert finished[-1] == 0
    assert [item['embedding'] for item in result.response['data']] == [[float(i)] for i in range(20)]


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['http', 'deadline', 'cancel'])
async def test_batch_drains_workers_on_failure_deadline_or_caller_cancel(monkeypatch, failure):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    started = asyncio.Event()
    blocked = asyncio.Event()
    calls = []
    active = 0

    async def handler(request):
        nonlocal active
        index = int(json.loads(request.content)['instances'][0]['content'])
        calls.append(index)
        active += 1
        try:
            if len(calls) == 8:
                started.set()
            await started.wait()
            if failure == 'http' and index == 7:
                return httpx.Response(503)
            await blocked.wait()
        finally:
            active -= 1

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=_access_token)
        task = asyncio.create_task(
            provider.create_embedding(
                {'input': [str(i) for i in range(100)]},
                provider_ref=ProviderRef(provider='gemini', model='gemini-embedding-001'),
                credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
                timeout_ms=30 if failure == 'deadline' else 1000,
            )
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        if failure == 'cancel':
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            with pytest.raises(ProviderFailure) as error:
                await task
            expected = (
                FailureClass.TIMEOUT_BEFORE_OUTPUT if failure == 'deadline' else FailureClass.PROVIDER_5XX_OMI_PAID
            )
            assert error.value.failure_class == expected
            assert error.value.upstream_http_status == (503 if failure == 'http' else None)
    assert active == 0
    assert len(calls) == 8  # No queued work started after a terminal failure.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'response',
    [
        b'not-json',
        b'{"predictions":[]}',
        b'{"predictions":[{"embeddings":{"values":[]}}]}',
        b'{"predictions":[{"embeddings":{"values":["bad"]}}]}',
    ],
)
async def test_malformed_success_is_typed_and_retains_http_200(monkeypatch, response):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=response))
    ) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=_access_token)
        with pytest.raises(ProviderFailure) as error:
            await provider.create_embedding(
                {'input': ['text']},
                provider_ref=ProviderRef(provider='gemini', model='gemini-embedding-001'),
                credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
                timeout_ms=1000,
            )
    assert error.value.failure_class == FailureClass.PROVIDER_5XX_OMI_PAID
    assert error.value.upstream_http_status == 200


@pytest.mark.asyncio
async def test_desktop_mixed_metadata_batch_through_real_gateway_route_and_vertex_adapter(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    monkeypatch.setattr(embeddings, 'schedule_attempt_trace', lambda *args: None)
    seen = []

    def handler(request):
        instances = json.loads(request.content)['instances']
        assert len(instances) == 1
        seen.extend(instances)
        return httpx.Response(200, json={'predictions': [{'embeddings': {'values': [int(instances[0]['content'])]}}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as upstream:
        provider = VertexGeminiProvider(http_client=upstream, access_token_supplier=_access_token)
        app.dependency_overrides[dependencies.get_provider_registry] = lambda: ProviderRegistry({'gemini': provider})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://gateway.test') as gateway:

            async def post(url, *, headers, payload):
                return await gateway.post('/v1/embeddings', json=payload, headers=headers)

            monkeypatch.setattr(dgg, '_gateway_post', post)
            monkeypatch.setattr(
                dgg,
                '_desktop_gateway_headers',
                lambda **kwargs: {
                    'x-omi-service-caller': 'backend',
                    'authorization': 'Bearer shared-secret',
                    'x-omi-request-id': kwargs['request_id'],
                },
            )
            try:
                result = await dgg.gateway_desktop_batch_embed_contents(
                    json.dumps(
                        {
                            'requests': [
                                {
                                    'content': {'parts': [{'text': str(i)}]},
                                    'taskType': 'RETRIEVAL_DOCUMENT',
                                    'title': f'doc-{i % 2}',
                                }
                                for i in range(6)
                            ]
                        }
                    ).encode(),
                    uid='test-uid',
                    request_id='936c2c10-c509-41f1-95cf-2162710d5ac8',
                    product_lane='desktop-screen-activity',
                    client_platform='macos',
                )
            finally:
                app.dependency_overrides.clear()

    assert result.embeddings == [[float(i)] for i in range(6)]
    assert len(seen) == 6
    assert all(item['title'] == f"doc-{int(item['content']) % 2}" for item in seen)
