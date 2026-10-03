"""Wire/error expectations captured from origin/main (afa78002), without live calls.

Each request advances a deterministic clock by 300ms during the state read,
then pins the full inference deadline and retry budget,
including origin/main's acceptance of a valid body on a 3xx response.
The 3.8 first-request shared route is an intentional departure from that baseline.
"""

import asyncio
import json
import time

import httpx
import pytest
from config.vertex_reservations import State

from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.providers import ProviderFailure, VertexGeminiProvider
from llm_gateway.gateway.schemas import FailureClass, ProviderRef
from utils.llm import vertex_pt_routing as ptr
from utils.llm.desktop_gemini_gateway import gemini_body_to_openai_chat
from llm_gateway.gateway.vertex_wire import _vertex_request


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize(
    'anchor,served,location,capacity',
    [
        ('gemini-2.5-flash', 'gemini-2.5-flash', 'us-central1', 'dedicated'),
        ('gemini-2.5-flash-lite', 'gemini-2.5-flash-lite', 'us-central1', 'shared'),
        ('gemini-2.5-pro', 'gemini-3.1-flash-lite', 'us', 'shared'),
        ('gemini-3.8-flash', 'gemini-3.8-flash', 'us', 'shared'),
    ],
)
@pytest.mark.parametrize(
    'status,message,failure',
    [
        (200, '', None),
        (302, '', None),
        (400, 'invalid request', FailureClass.PROVIDER_INVALID_REQUEST),
        (401, 'invalid credentials', FailureClass.INVALID_CONFIG),
        (429, 'Provisioned Throughput dedicated capacity exhausted', FailureClass.PROVIDER_429_OMI_PAID),
        (429, 'generic quota exceeded', FailureClass.PROVIDER_429_OMI_PAID),
    ],
)
async def test_existing_models_keep_main_attempts_deadlines_headers_and_errors(
    monkeypatch, stream, anchor, served, location, capacity, status, message, failure
):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv(ptr.REGIONAL_LOCATION_ENV, 'us-central1')
    monkeypatch.setenv(ptr.MULTI_REGION_LOCATION_ENV, 'us')
    monkeypatch.setenv('OMI_VERTEX_PT_TARGET_LOCATION', 'us')
    monkeypatch.setenv('LLM_GATEWAY_EXPOSE_PROVIDER_ERROR_DETAILS', 'false')
    for name in [ptr.PT_MODEL_OVERRIDE_ENV, ptr.OVERFLOW_MODEL_OVERRIDE_ENV, ptr.OVERFLOW_ENABLED_ENV]:
        monkeypatch.delenv(name, raising=False)
    now = [100.0]
    seen = []

    class Body(httpx.AsyncByteStream):
        def __init__(self, payload, check_availability):
            self.payload = payload
            self.check_availability = check_availability

        async def __aiter__(self):
            if self.check_availability:
                # Streams clear expired reachability at headers; non-streaming
                # requests do so only after successfully parsing the whole body.
                assert (served in provider._model_unavailable_at) == (not stream)
            yield self.payload

    def handler(request):
        seen.append(request)
        now[0] += 0.25
        code = status if len(seen) == 1 else 200
        result = {'candidates': [{'content': {'parts': [{'text': 'ok'}]}, 'finishReason': 'STOP'}]}
        payload = json.dumps({'error': {'message': message}} if code >= 400 else result)
        if stream and code < 400:
            payload = 'data: ' + payload + '\n\n'
        return httpx.Response(
            code, stream=Body(payload.encode(), len(seen) == 1 and code < 400), headers={'retry-after': '7'}
        )

    async def token():
        return 'synthetic-token'

    overflow = status == 429 and capacity == 'dedicated' and message.startswith('Provisioned')
    expected = [(served, location, capacity, 60.0)]
    if overflow:
        expected.append(('gemini-3.1-flash-lite', 'us', 'shared', 59.75))
        failure = None
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=token, now=lambda: now[0])

        async def slow_state_read(*args, **kwargs):
            now[0] += 0.3
            return {ptr.PT_MODEL_CURRENT: State.ACTIVE}

        monkeypatch.setattr(provider._reservations, 'refresh', slow_state_read)
        provider._model_unavailable_at[served] = -1000.0  # Expired observation; model is eligible again.
        kwargs = dict(
            provider_ref=ProviderRef(provider='gemini', model=anchor),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=60000,
        )

        async def call():
            request = {
                'messages': [{'role': 'user', 'content': 'synthetic parity input'}],
                'max_tokens': 64,
                'google': {'thinking_config': {'thinking_budget': 0}},
            }
            if stream:
                chunks = [chunk async for chunk in provider.stream_chat_completion(request, **kwargs)]
                assert b'"ok"' in b''.join(chunks) and chunks[-1] == b'data: [DONE]\n\n'
            else:
                assert (await provider.create_chat_completion(request, **kwargs)).response['choices'][0]['message'][
                    'content'
                ] == 'ok'

        if failure:
            with pytest.raises(ProviderFailure) as raised:
                await call()
            assert raised.value.failure_class == failure
            assert str(raised.value) == 'provider request failed'
            assert raised.value.retry_after_seconds == (7 if status == 429 else None)
        else:
            await call()
    assert len(seen) == len(expected)
    method = 'streamGenerateContent' if stream else 'generateContent'
    for request, (model, region, request_type, timeout) in zip(seen, expected):
        host = 'aiplatform.googleapis.com' if region == 'us' else region + '-aiplatform.googleapis.com'
        assert str(request.url).split('?')[0] == (
            f'https://{host}/v1/projects/synthetic-project/locations/{region}/publishers/google/models/{model}:{method}'
        )
        assert request.url.query == (b'alt=sse' if stream else b'')
        assert request.headers['authorization'] == 'Bearer synthetic-token'
        assert request.headers['content-type'] == 'application/json'
        assert request.headers[ptr.REQUEST_TYPE_HEADER] == request_type
        assert request.extensions['timeout'] == dict(connect=timeout, read=timeout, write=timeout, pool=timeout)
        # Literal origin/main wire body, including the Pro remap and overflow.
        # Do not derive this expectation using the helper under test.
        assert json.loads(request.content) == {
            'contents': [{'role': 'user', 'parts': [{'text': 'synthetic parity input'}]}],
            'generationConfig': {
                'maxOutputTokens': 64,
                'thinkingConfig': ({'thinkingLevel': 'low'} if model == 'gemini-3.8-flash' else {'thinkingBudget': 0}),
            },
        }


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize('ready', [False, True])
async def test_non_target_traffic_leaves_cross_request_target_promotion_state_untouched(monkeypatch, stream, ready):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.delenv(ptr.PT_MODEL_OVERRIDE_ENV, raising=False)
    seen = []
    status = 200

    def handler(request):
        seen.append(request)
        body = (
            {'candidates': [{'content': {'parts': [{'text': 'ok'}]}, 'finishReason': 'STOP'}]}
            if status == 200
            else {'error': {'message': 'synthetic unclassified error'}}
        )
        content = json.dumps(body)
        if stream and status == 200:
            content = 'data: ' + content + '\n\n'
        return httpx.Response(status, content=content)

    async def token():
        return 'synthetic-token'

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=token, now=lambda: 100.0)
        provider._reservation_states = {ptr.PT_MODEL_TARGET: State.ACTIVE} if ready else {}
        provider._reservations._positive = {m: time.monotonic() for m in provider._reservation_states}
        for anchor, status in [
            ('gemini-2.5-flash', 200),
            ('gemini-2.5-flash', 401),
            ('gemini-2.5-flash', 500),
            ('gemini-2.5-flash', 429),
            ('gemini-2.5-flash-lite', 200),
            ('gemini-2.5-pro', 200),
        ]:
            kwargs = dict(
                provider_ref=ProviderRef(provider='gemini', model=anchor),
                credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
                timeout_ms=60000,
            )
            request = {'messages': [{'role': 'user', 'content': 'synthetic parity input'}]}

            async def call():
                if stream:
                    return [chunk async for chunk in provider.stream_chat_completion(request, **kwargs)]
                return await provider.create_chat_completion(request, **kwargs)

            if status >= 400:
                with pytest.raises(ProviderFailure):
                    await call()
            else:
                await call()
            assert provider._reservation_active(ptr.PT_MODEL_TARGET) is ready
        assert len(seen) == 6
        assert all(ptr.PT_MODEL_TARGET not in str(request.url) for request in seen)
        assert [request.headers[ptr.REQUEST_TYPE_HEADER] for request in seen[:4]] == [
            'dedicated'  # observing the successor alone cannot deactivate the old order
        ] * 4


@pytest.mark.asyncio
@pytest.mark.parametrize('status', [200, 302, 400, 401, 429, 500])
async def test_embedding_embed_content_keeps_main_wire_deadline_errors_and_missing_usage(monkeypatch, status):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv(ptr.REGIONAL_LOCATION_ENV, 'us-central1')
    monkeypatch.setenv('LLM_GATEWAY_EXPOSE_PROVIDER_ERROR_DETAILS', 'false')
    monkeypatch.delenv(ptr.PT_MODEL_OVERRIDE_ENV, raising=False)
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            status,
            json=(
                {'error': {'message': 'synthetic error'}}
                if status >= 400
                else {
                    'predictions': [{'embeddings': {'values': [0.1, 0.2]}}],
                    'metadata': {'billableCharacterCount': 22},
                }
            ),
            headers={'retry-after': '7'},
        )

    async def token():
        return 'synthetic-token'

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=token)
        kwargs = dict(
            provider_ref=ProviderRef(provider='gemini', model='gemini-embedding-001'),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=60000,
        )
        request = {'input': 'synthetic parity input', 'task_type': 'RETRIEVAL_QUERY'}
        if status >= 400:
            with pytest.raises(ProviderFailure) as raised:
                await provider.create_embedding(request, **kwargs)
            assert (
                raised.value.failure_class
                == {
                    400: FailureClass.PROVIDER_INVALID_REQUEST,
                    401: FailureClass.INVALID_CONFIG,
                    429: FailureClass.PROVIDER_429_OMI_PAID,
                    500: FailureClass.PROVIDER_5XX_OMI_PAID,
                }[status]
            )
            assert str(raised.value) == 'provider request failed'
            assert raised.value.retry_after_seconds == (7 if status == 429 else None)
        else:
            response = await provider.create_embedding(request, **kwargs)
            assert response.response == {
                'object': 'list',
                'data': [{'object': 'embedding', 'embedding': [0.1, 0.2], 'index': 0}],
                'model': 'gemini-embedding-001',
            }
            assert response.accounting.usage is None
        assert provider._reservation_active(ptr.PT_MODEL_TARGET) is False
    assert len(seen) == 1
    outgoing = seen[0]
    assert str(outgoing.url) == (
        'https://us-central1-aiplatform.googleapis.com/v1/projects/synthetic-project'
        '/locations/us-central1/publishers/google/models/gemini-embedding-001:predict'
    )
    assert outgoing.method == 'POST'
    assert outgoing.headers['authorization'] == 'Bearer synthetic-token'
    assert outgoing.headers['content-type'] == 'application/json'
    assert outgoing.headers[ptr.REQUEST_TYPE_HEADER] == 'shared'
    assert outgoing.extensions['timeout'] == dict(connect=60.0, read=60.0, write=60.0, pool=60.0)
    assert json.loads(outgoing.content) == {
        'instances': [{'content': 'synthetic parity input', 'task_type': 'RETRIEVAL_QUERY'}]
    }


@pytest.fixture(autouse=True)
def held_discovery_leases_for_request_matrix(monkeypatch):
    """Keep synthetic discovery separate from customer-attempt/accounting fixtures."""
    from utils.llm import vertex_reservation_state

    monkeypatch.setattr(vertex_reservation_state, 'discovery_models', lambda _: frozenset())


@pytest.mark.parametrize('thinking', [{'thinkingBudget': 0}, {'thinkingLevel': 'high'}])
def test_bff_to_vertex_wire_accepts_explicit_zero_budget_and_flash_lite_level(thinking):
    body = {
        'contents': [{'role': 'user', 'parts': [{'text': 'synthetic'}]}],
        'generationConfig': {'thinkingConfig': thinking},
    }
    translated = gemini_body_to_openai_chat(body, lane_id='omi:auto:desktop-vertex-flash-lite', stream=False)
    assert _vertex_request(translated)['generationConfig']['thinkingConfig'] == thinking


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
async def test_first_target_customer_request_is_shared_with_separate_synthetic_discovery(monkeypatch, stream):
    from utils.llm import vertex_reservation_state as state_module
    from config.vertex_reservations import RESERVATIONS

    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv('OMI_VERTEX_PT_TARGET_LOCATION', 'us')
    for key in ['REDIS_DB_HOST', 'OMI_VERTEX_PT_MODEL', 'OMI_VERTEX_RESERVATION_STATES']:
        monkeypatch.delenv(key, raising=False)
    # Undo this module's held-lease fixture: exercise actual scheduling and wire.
    monkeypatch.setattr(state_module, 'discovery_models', lambda _: frozenset(RESERVATIONS))
    seen = []

    def handler(request):
        seen.append(request)
        if request.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated':
            return httpx.Response(429, json={'error': {'message': 'Exceeded the provisioned throughput.'}})
        payload = {
            'candidates': [{'content': {'parts': [{'text': 'ok'}]}, 'finishReason': 'STOP'}],
            'usageMetadata': {'trafficType': 'ON_DEMAND'},
        }
        return httpx.Response(200, content=('data: ' + json.dumps(payload) + '\n\n') if stream else json.dumps(payload))

    async def token():
        return 'synthetic-token'

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=token)
        try:
            kwargs = dict(
                provider_ref=ProviderRef(provider='gemini', model='gemini-3.8-flash'),
                credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
                timeout_ms=60000,
            )
            request = {'messages': [{'role': 'user', 'content': 'synthetic customer fixture'}], 'max_tokens': 64}
            if stream:
                chunks = [chunk async for chunk in provider.stream_chat_completion(request, **kwargs)]
                assert chunks[-1] == b'data: [DONE]\n\n'
            else:
                result = await provider.create_chat_completion(request, **kwargs)
                assert result.response['choices'][0]['message']['content'] == 'ok'
            # The first refresh leases one model; the next refresh can lease the other.
            await asyncio.gather(*provider._reservations._probe_tasks)
            await provider._refresh_reservations(1.6)
            await asyncio.gather(*provider._reservations._probe_tasks)
            assert (await provider._reservations.refresh())['gemini-3.8-flash'] == State.UNKNOWN
        finally:
            await provider._reservations.aclose()
    customer = [r for r in seen if r.headers[ptr.REQUEST_TYPE_HEADER] == 'shared']
    probes = [r for r in seen if r.headers[ptr.REQUEST_TYPE_HEADER] == 'dedicated']
    assert len(customer) == 1
    assert '/locations/us/publishers/google/models/gemini-3.8-flash:' in customer[0].url.path
    assert json.loads(customer[0].content)['contents'][0]['parts'] == [{'text': 'synthetic customer fixture'}]
    assert {r.url.path.split('/models/')[1] for r in probes} == {
        'gemini-2.5-flash:generateContent',
        'gemini-3.8-flash:generateContent',
    }
    for probe in probes:
        body = json.loads(probe.content)
        assert body['contents'] == [{'role': 'user', 'parts': [{'text': 'Reply OK.'}]}]
        assert body['generationConfig']['maxOutputTokens'] == 16
        assert probe.extensions['timeout'] == dict(connect=30, read=30, write=30, pool=30)
