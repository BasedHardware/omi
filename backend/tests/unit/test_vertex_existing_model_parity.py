"""Wire/error expectations captured from origin/main (afa78002), without live calls.

Each request uses a deterministic clock to pin the full deadline and retry budget,
including origin/main's acceptance of a valid body on a 3xx response.
"""

import json

import httpx
import pytest

from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.providers import ProviderFailure, VertexGeminiProvider
from llm_gateway.gateway.schemas import FailureClass, ProviderRef
from utils.llm import vertex_pt_routing as ptr


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [False, True])
@pytest.mark.parametrize(
    'anchor,served,location,capacity',
    [
        ('gemini-2.5-flash', 'gemini-2.5-flash', 'us-central1', 'dedicated'),
        ('gemini-2.5-flash-lite', 'gemini-2.5-flash-lite', 'us-central1', 'shared'),
        ('gemini-2.5-pro', 'gemini-3.1-flash-lite', 'us', 'shared'),
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
        provider._model_unavailable_at[served] = -1000.0  # Expired observation; model is eligible again.
        kwargs = dict(
            provider_ref=ProviderRef(provider='gemini', model=anchor),
            credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
            timeout_ms=60000,
        )

        async def call():
            request = {'messages': [{'role': 'user', 'content': 'synthetic parity input'}]}
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
