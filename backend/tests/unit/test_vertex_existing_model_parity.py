"""Wire/error expectations captured from origin/main (afa78002), without live calls.

Each request advances a deterministic clock by 300ms during the state read,
then pins the full inference deadline and retry budget,
including origin/main's acceptance of a valid body on a 3xx response.
All generation aliases now use the active dedicated reservation; embeddings retain shared capacity.
"""

import json

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
        ('gemini-2.5-flash-lite', 'gemini-2.5-flash', 'us-central1', 'dedicated'),
        ('gemini-2.5-pro', 'gemini-2.5-flash', 'us-central1', 'dedicated'),
        ('gemini-3.8-flash', 'gemini-2.5-flash', 'us-central1', 'dedicated'),
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

    expected = [(served, location, capacity, 60.0)]
    if status == 429 and 'provisioned' in message.lower():
        failure = FailureClass.RESERVED_CAPACITY_UNAVAILABLE
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
            assert raised.value.retry_after_seconds == (
                7 if status == 429 and failure != FailureClass.RESERVED_CAPACITY_UNAVAILABLE else None
            )
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
@pytest.mark.parametrize('status', [200, 302, 400, 401, 429, 500])
@pytest.mark.parametrize('token_delay_seconds', [0.0, 0.25])
async def test_embedding_embed_content_keeps_main_wire_deadline_errors_and_missing_usage(
    monkeypatch, status, token_delay_seconds
):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'synthetic-project')
    monkeypatch.setenv(ptr.REGIONAL_LOCATION_ENV, 'us-central1')
    monkeypatch.setenv('LLM_GATEWAY_EXPOSE_PROVIDER_ERROR_DETAILS', 'false')
    monkeypatch.delenv(ptr.PT_MODEL_OVERRIDE_ENV, raising=False)
    seen = []
    now = [100.0]

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
        now[0] += token_delay_seconds
        return 'synthetic-token'

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = VertexGeminiProvider(http_client=client, access_token_supplier=token, now=lambda: now[0])
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
        assert provider._reservation_states.get(ptr.PT_MODEL_TARGET) != State.ACTIVE
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
    # A single predict preserves its exact wire timeout after authentication.
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


@pytest.fixture(autouse=True)
def active_reserved_order(monkeypatch):
    monkeypatch.setenv('OMI_VERTEX_RESERVATION_STATES', '{"gemini-2.5-flash":"active","gemini-3.8-flash":"inactive"}')
