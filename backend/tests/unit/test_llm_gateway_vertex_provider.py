from __future__ import annotations

import json
import time

import httpx
import pytest
from pydantic import BaseModel

from llm_gateway.gateway import providers as provider_module
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_byok_credential_context, build_omi_managed_credential_context
from llm_gateway.gateway.providers import (
    ProviderFailure,
    VertexAccessTokenSupplier,
    VertexGeminiProvider,
)
from llm_gateway.gateway.vertex_wire import _json_schema_to_vertex_response_schema, _vertex_request
from llm_gateway.gateway.schemas import FailureClass, ProviderRef
from llm_gateway.routers import dependencies
from utils.executors import critical_executor


def _omi_credentials():
    return build_omi_managed_credential_context(ServiceCaller(name='backend'))


async def _access_token() -> str:
    return 'vertex-access-token'


@pytest.mark.asyncio
async def test_vertex_provider_uses_native_generate_content_and_normalizes_response(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    monkeypatch.setenv('GCP_LOCATION', 'us-central1')
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(
            200,
            json={
                'responseId': 'vertex-response-id',
                'modelVersion': 'gemini-2.5-flash-001',
                'trafficType': 'ON_DEMAND',
                'candidates': [
                    {
                        'content': {'parts': [{'text': 'A concise title'}]},
                        'finishReason': 'MAX_TOKENS',
                    }
                ],
                'usageMetadata': {
                    'promptTokenCount': 100,
                    'cachedContentTokenCount': 25,
                    'candidatesTokenCount': 20,
                    'thoughtsTokenCount': 5,
                    'totalTokenCount': 125,
                },
            },
        )

    provider = VertexGeminiProvider(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        access_token_supplier=_access_token,
    )
    response = await provider.create_chat_completion(
        {
            'model': 'gemini-2.5-flash-lite',
            'messages': [
                {'role': 'system', 'content': 'Give concise titles.'},
                {'role': 'user', 'content': 'Planning the project'},
                {'role': 'assistant', 'content': 'Project plan'},
                {'role': 'user', 'content': 'Another title'},
            ],
            'temperature': 0.2,
            'top_p': 0.9,
            'stop': 'END',
            'max_completion_tokens': 128,
            'reasoning_effort': 'none',
            'response_format': {
                'type': 'json_schema',
                'json_schema': {
                    'name': 'title',
                    'schema': {'type': 'object', 'properties': {'title': {'type': 'string'}}},
                },
            },
        },
        provider_ref=ProviderRef(provider='gemini', model='gemini-2.5-flash-lite'),
        credentials=_omi_credentials(),
        timeout_ms=8000,
    )

    request = seen_requests[0]
    assert request.url == (
        'https://us-central1-aiplatform.googleapis.com/v1/projects/test-project/locations/us-central1/'
        'publishers/google/models/gemini-2.5-flash-lite:generateContent'
    )
    assert request.headers['authorization'] == 'Bearer vertex-access-token'
    assert 'generativelanguage.googleapis.com' not in str(request.url)
    payload = json.loads(request.content)
    assert payload['systemInstruction'] == {'parts': [{'text': 'Give concise titles.'}]}
    assert payload['contents'] == [
        {'role': 'user', 'parts': [{'text': 'Planning the project'}]},
        {'role': 'model', 'parts': [{'text': 'Project plan'}]},
        {'role': 'user', 'parts': [{'text': 'Another title'}]},
    ]
    assert payload['generationConfig'] == {
        'temperature': 0.2,
        'topP': 0.9,
        'stopSequences': ['END'],
        'maxOutputTokens': 128,
        'thinkingConfig': {'thinkingBudget': 0},
        'responseMimeType': 'application/json',
        'responseSchema': {'type': 'object', 'properties': {'title': {'type': 'string'}}},
    }
    assert response['model'] == 'gemini-2.5-flash-lite'
    assert response['choices'][0]['message']['content'] == 'A concise title'
    assert response['choices'][0]['finish_reason'] == 'length'
    assert response['usage']['prompt_tokens_details']['cached_tokens'] == 25
    assert response['usage']['completion_tokens_details']['reasoning_tokens'] == 5
    assert response.accounting.actual_model_version == 'gemini-2.5-flash-001'
    assert response.accounting.usage is not None
    assert response.accounting.usage.cached_input_tokens == 25


@pytest.mark.asyncio
async def test_vertex_provider_translates_native_sse_to_openai_sse(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params == httpx.QueryParams({'alt': 'sse'})
        return httpx.Response(
            200,
            content=(
                b'data: {"responseId":"first","candidates":[{"content":{"parts":[{"text":"hello"}]}}]}\n\n'
                b'data: {"responseId":"first","candidates":[{"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":10,"cachedContentTokenCount":4,"candidatesTokenCount":2,"totalTokenCount":12}}\n\n'
            ),
            headers={'content-type': 'text/event-stream'},
        )

    provider = VertexGeminiProvider(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        access_token_supplier=_access_token,
    )
    chunks = [
        chunk
        async for chunk in provider.stream_chat_completion(
            {'model': 'gemini-2.5-flash-lite', 'messages': [{'role': 'user', 'content': 'hello'}], 'stream': True},
            provider_ref=ProviderRef(provider='gemini', model='gemini-2.5-flash-lite'),
            credentials=_omi_credentials(),
            timeout_ms=8000,
        )
    ]

    streamed = b''.join(chunks)
    assert b'"delta":{"content":"hello"}' in streamed
    assert b'"finish_reason":"stop"' in streamed
    assert b'"usage":{"prompt_tokens":10' in streamed
    assert streamed.endswith(b'data: [DONE]\n\n')


@pytest.mark.asyncio
async def test_vertex_provider_rejects_gemini_byok_before_making_request(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    provider = VertexGeminiProvider(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: pytest.fail('unexpected request'))),
        access_token_supplier=_access_token,
    )

    with pytest.raises(ProviderFailure) as exc_info:
        await provider.create_chat_completion(
            {'model': 'gemini-2.5-flash-lite', 'messages': [{'role': 'user', 'content': 'hello'}]},
            provider_ref=ProviderRef(provider='gemini', model='gemini-2.5-flash-lite'),
            credentials=build_byok_credential_context(ServiceCaller(name='backend'), {'gemini': 'byok-key'}),
            timeout_ms=8000,
        )

    assert exc_info.value.failure_class == FailureClass.BYOK_UNSUPPORTED_PROVIDER


@pytest.mark.asyncio
async def test_vertex_provider_maps_auth_errors_without_provider_body_leak(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    raw_body = 'provider response includes sensitive input'
    provider = VertexGeminiProvider(
        http_client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(401, text=raw_body))
        ),
        access_token_supplier=_access_token,
    )

    with pytest.raises(ProviderFailure) as exc_info:
        await provider.create_chat_completion(
            {'model': 'gemini-2.5-flash-lite', 'messages': [{'role': 'user', 'content': 'secret'}]},
            provider_ref=ProviderRef(provider='gemini', model='gemini-2.5-flash-lite'),
            credentials=_omi_credentials(),
            timeout_ms=8000,
        )

    assert exc_info.value.failure_class == FailureClass.INVALID_CONFIG
    assert raw_body not in str(exc_info.value)


@pytest.mark.asyncio
async def test_vertex_provider_maps_access_token_supplier_errors_to_configuration_failure(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')

    async def unavailable_access_token() -> str:
        raise RuntimeError('credential diagnostic containing sensitive details')

    provider = VertexGeminiProvider(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: pytest.fail('unexpected request'))),
        access_token_supplier=unavailable_access_token,
    )

    with pytest.raises(ProviderFailure) as exc_info:
        await provider.create_chat_completion(
            {'model': 'gemini-2.5-flash-lite', 'messages': [{'role': 'user', 'content': 'hello'}]},
            provider_ref=ProviderRef(provider='gemini', model='gemini-2.5-flash-lite'),
            credentials=_omi_credentials(),
            timeout_ms=8000,
        )

    assert exc_info.value.failure_class == FailureClass.INVALID_CONFIG
    assert 'sensitive details' not in str(exc_info.value)


@pytest.mark.asyncio
async def test_vertex_provider_rejects_openai_parameters_it_cannot_preserve(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    provider = VertexGeminiProvider(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request: pytest.fail('unexpected request'))),
        access_token_supplier=_access_token,
    )

    with pytest.raises(ProviderFailure) as exc_info:
        await provider.create_chat_completion(
            {
                'model': 'gemini-2.5-flash-lite',
                'messages': [{'role': 'user', 'content': 'hello'}],
                'presence_penalty': 1,
            },
            provider_ref=ProviderRef(provider='gemini', model='gemini-2.5-flash-lite'),
            credentials=_omi_credentials(),
            timeout_ms=8000,
        )

    assert exc_info.value.failure_class == FailureClass.CAPABILITY_MISMATCH


@pytest.mark.asyncio
async def test_vertex_access_token_refresh_runs_in_critical_executor(monkeypatch):
    calls: list[object] = []

    class Credentials:
        token = ''
        expiry = None

        def refresh(self, _request) -> None:
            self.token = 'adc-token'

    credentials = Credentials()

    async def fake_run_blocking(executor, function):
        calls.append(executor)
        return function()

    monkeypatch.setattr(provider_module, 'run_blocking', fake_run_blocking)
    supplier = VertexAccessTokenSupplier(
        credentials_factory=lambda **_kwargs: (credentials, 'test-project'),
        auth_request_factory=object,
    )

    assert await supplier.get_access_token() == 'adc-token'
    assert calls == [critical_executor]


def test_vertex_provider_does_not_bind_pt_clock_to_token_supplier():
    """PT probe TTL is monotonic; ADC expiry is wall-clock.

    Sharing the PT `now` with VertexAccessTokenSupplier makes
    `monotonic() < expiry.timestamp()` stay true forever, so tokens never
    refresh after the first fetch.
    """
    provider = VertexGeminiProvider(http_client=httpx.AsyncClient(), now=lambda: 0.0)
    supplier = provider._access_token_supplier.__self__
    assert isinstance(supplier, VertexAccessTokenSupplier)
    assert supplier._now is time.time


@pytest.mark.asyncio
async def test_gateway_registry_uses_native_vertex_for_gemini():
    dependencies.get_provider_registry.cache_clear()
    registry = dependencies.get_provider_registry()
    try:
        assert isinstance(registry.provider_for('gemini'), VertexGeminiProvider)
    finally:
        await registry.aclose()
        dependencies.get_provider_registry.cache_clear()


# ---------------------------------------------------------------------------
# Multimodal content
#
# These exist because the Vertex translator used to run every message through
# _text_content(), which keeps only `type == "text"` parts. An image attached to
# a Gemini request was therefore dropped without a word, and the model answered
# about content it had never been sent. utils/screen_frames/judge.py is a privacy
# gate that decides whether a screenshot may leave the machine; a confident
# verdict from a model that received no image is a fail-OPEN, because the judge's
# fail-closed handling only triggers on errors.
# ---------------------------------------------------------------------------

_PIXEL = "iVBORw0KGgoAAAANSUhEUg=="


def test_vertex_request_forwards_an_inline_image_instead_of_dropping_it():
    payload = _vertex_request(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "is this safe to store?"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_PIXEL}"}},
                    ],
                }
            ]
        },
    )

    parts = payload["contents"][0]["parts"]
    assert parts[0] == {"text": "is this safe to store?"}
    assert parts[1] == {"inlineData": {"mimeType": "image/jpeg", "data": _PIXEL}}


def test_vertex_request_refuses_a_remote_image_url_rather_than_answering_blind():
    # Vertex cannot fetch an arbitrary https image the way OpenAI can. Silently
    # dropping it would send the prompt alone.
    with pytest.raises(ProviderFailure) as exc:
        _vertex_request(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "image_url", "image_url": {"url": "https://example.com/a.jpg"}}],
                    }
                ]
            },
        )
    assert exc.value.failure_class is FailureClass.CAPABILITY_MISMATCH


def test_vertex_request_refuses_content_parts_it_cannot_represent():
    with pytest.raises(ProviderFailure) as exc:
        _vertex_request(
            {"messages": [{"role": "user", "content": [{"type": "input_audio", "input_audio": {}}]}]},
        )
    assert exc.value.failure_class is FailureClass.CAPABILITY_MISMATCH


def test_vertex_request_refuses_an_image_in_the_system_instruction():
    with pytest.raises(ProviderFailure) as exc:
        _vertex_request(
            {
                "messages": [
                    {
                        "role": "system",
                        "content": [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{_PIXEL}"}}],
                    },
                    {"role": "user", "content": "hi"},
                ]
            },
        )
    assert exc.value.failure_class is FailureClass.CAPABILITY_MISMATCH


def test_vertex_request_still_handles_plain_string_and_system_text():
    payload = _vertex_request(
        {
            "messages": [
                {"role": "system", "content": "be terse"},
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": [{"type": "text", "text": "hi"}]},
            ]
        },
    )
    assert payload["systemInstruction"]["parts"] == [{"text": "be terse"}]
    assert payload["contents"][0] == {"role": "user", "parts": [{"text": "hello"}]}
    assert payload["contents"][1] == {"role": "model", "parts": [{"text": "hi"}]}


def test_vertex_request_accepts_a_data_url_with_rfc2397_parameters():
    """`data:image/jpeg;charset=utf-8;base64,...` is a valid data URL and browsers
    emit them. Rejecting it would be the mirror of the bug this module fixed:
    refusing an image that can in fact be represented."""
    payload = _vertex_request(
        {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;charset=utf-8;base64,{_PIXEL}"}}
                    ],
                }
            ]
        }
    )
    assert payload["contents"][0]["parts"][0] == {"inlineData": {"mimeType": "image/png", "data": _PIXEL}}


def test_vertex_request_never_emits_a_message_with_zero_parts():
    """Vertex rejects a Content with an empty parts array, and the previous
    text-only implementation always produced [{'text': ''}] here. An assistant
    tool-call turn carries content=None, so this is reachable as soon as a
    multi-turn Gemini feature exists."""
    payload = _vertex_request({"messages": [{"role": "assistant", "content": None}, {"role": "user", "content": []}]})
    assert payload["contents"][0] == {"role": "model", "parts": [{"text": ""}]}
    assert payload["contents"][1] == {"role": "user", "parts": [{"text": ""}]}


def test_vertex_response_schema_inlines_nested_translation_json_schema():
    """Nested Pydantic json_schema must not be copied into Vertex responseSchema.

    Vertex responseSchema is an OpenAPI subset. JSON Schema $defs/$ref is the
    400 that made omi:auto:translation 100% InvalidArgument. Local models match
    GeminiTranslationBatch / GeminiTranslationItem so this stays a cheap unit
    test (importing translation providers pulls langchain into call-phase CPU).
    """

    class GeminiTranslationItem(BaseModel):
        text: str
        detected_language: str

    class GeminiTranslationBatch(BaseModel):
        translations: list[GeminiTranslationItem]

    schema = GeminiTranslationBatch.model_json_schema()
    assert '$defs' in schema
    assert schema['properties']['translations']['items'] == {'$ref': '#/$defs/GeminiTranslationItem'}

    converted = _json_schema_to_vertex_response_schema(schema)
    dumped = json.dumps(converted)
    assert '$ref' not in dumped
    assert '$defs' not in dumped
    assert converted['type'] == 'object'
    assert converted['properties']['translations']['items'] == {
        'properties': {
            'text': {'title': 'Text', 'type': 'string'},
            'detected_language': {'title': 'Detected Language', 'type': 'string'},
        },
        'required': ['text', 'detected_language'],
        'title': 'GeminiTranslationItem',
        'type': 'object',
    }

    payload = _vertex_request(
        {
            'messages': [{'role': 'user', 'content': 'translate'}],
            'response_format': {
                'type': 'json_schema',
                'json_schema': {'name': 'GeminiTranslationBatch', 'schema': schema},
            },
        }
    )
    response_schema = payload['generationConfig']['responseSchema']
    assert '$ref' not in json.dumps(response_schema)
    assert '$defs' not in json.dumps(response_schema)
    assert response_schema['properties']['translations']['items']['type'] == 'object'


def test_vertex_response_schema_inlines_openai_strict_nested_schema():
    schema = {
        '$defs': {
            'GeminiTranslationItem': {
                'properties': {
                    'text': {'title': 'Text', 'type': 'string'},
                    'detected_language': {'title': 'Detected Language', 'type': 'string'},
                },
                'required': ['text', 'detected_language'],
                'title': 'GeminiTranslationItem',
                'type': 'object',
                'additionalProperties': False,
            }
        },
        'properties': {
            'translations': {
                'items': {'$ref': '#/$defs/GeminiTranslationItem'},
                'title': 'Translations',
                'type': 'array',
            }
        },
        'required': ['translations'],
        'title': 'GeminiTranslationBatch',
        'type': 'object',
        'additionalProperties': False,
    }

    converted = _json_schema_to_vertex_response_schema(schema)
    dumped = json.dumps(converted)
    assert '$ref' not in dumped
    assert '$defs' not in dumped
    assert converted['additionalProperties'] is False
    assert converted['properties']['translations']['items']['additionalProperties'] is False
    assert converted['properties']['translations']['items']['required'] == ['text', 'detected_language']


def test_vertex_response_schema_leaves_flat_schemas_unchanged():
    schema = {'type': 'object', 'properties': {'title': {'type': 'string'}}}
    assert _json_schema_to_vertex_response_schema(schema) == schema


# --- Desktop company-paid PT policy (moved from the desktop proxy) ---------


def _pt_provider(handler, **kwargs) -> VertexGeminiProvider:
    return VertexGeminiProvider(
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        access_token_supplier=_access_token,
        **kwargs,
    )


def _ok_vertex_response() -> dict:
    return {
        'candidates': [{'content': {'parts': [{'text': 'ok'}]}, 'finishReason': 'STOP'}],
        'usageMetadata': {'promptTokenCount': 3, 'candidatesTokenCount': 2, 'totalTokenCount': 5},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'anchor,expected_model,expected_host,expected_capacity',
    [
        # The current PT reservation is gemini-2.5-flash in us-central1: the
        # flash anchor pins to it and asks for dedicated capacity.
        ('gemini-2.5-flash', 'gemini-2.5-flash', 'us-central1-aiplatform.googleapis.com', 'dedicated'),
        # Pro never runs on-demand: it pins to the migration target, which is
        # served multi-region and is shared until it holds the reservation.
        ('gemini-2.5-pro', 'gemini-3.1-flash-lite', 'aiplatform.googleapis.com', 'shared'),
        # Client-pinned flash-lite stays the cheap shared floor, regional host.
        ('gemini-2.5-flash-lite', 'gemini-2.5-flash-lite', 'us-central1-aiplatform.googleapis.com', 'shared'),
        # Direct pins of the migration target are shared until promotion.
        ('gemini-3.1-flash-lite', 'gemini-3.1-flash-lite', 'aiplatform.googleapis.com', 'shared'),
    ],
)
async def test_vertex_provider_pt_header_and_host_per_anchor(
    monkeypatch, anchor, expected_model, expected_host, expected_capacity
):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    monkeypatch.setenv('GCP_LOCATION', 'us-central1')
    monkeypatch.delenv('OMI_VERTEX_PT_MODEL', raising=False)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_ok_vertex_response())

    provider = _pt_provider(handler)
    await provider.create_chat_completion(
        {'model': anchor, 'messages': [{'role': 'user', 'content': 'hi'}]},
        provider_ref=ProviderRef(provider='gemini', model=anchor),
        credentials=_omi_credentials(),
        timeout_ms=30_000,
    )

    assert len(seen) == 1
    request = seen[0]
    assert request.url.host == expected_host
    assert f'models/{expected_model}:generateContent' in str(request.url.path)
    assert request.headers[provider_module.ptr.REQUEST_TYPE_HEADER] == expected_capacity


@pytest.mark.asyncio
async def test_vertex_provider_overflows_to_on_demand_when_dedicated_is_exhausted(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    monkeypatch.setenv('GCP_LOCATION', 'us-central1')
    monkeypatch.delenv('OMI_GEMINI_OVERFLOW_ENABLED', raising=False)
    monkeypatch.delenv('OMI_GEMINI_OVERFLOW_MODEL', raising=False)
    monkeypatch.delenv('OMI_VERTEX_PT_MODEL', raising=False)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(
                429,
                json={
                    'error': {
                        'message': 'Resource has been exhausted (e.g. check quota). provisioned throughput dedicated capacity is exhausted'
                    }
                },
            )
        return httpx.Response(200, json=_ok_vertex_response())

    provider = _pt_provider(handler)
    result = await provider.create_chat_completion(
        {'model': 'gemini-2.5-flash', 'messages': [{'role': 'user', 'content': 'hi'}]},
        provider_ref=ProviderRef(provider='gemini', model='gemini-2.5-flash'),
        credentials=_omi_credentials(),
        timeout_ms=60_000,
    )

    assert result.response['choices'][0]['message']['content'] == 'ok'
    # First attempt: the reservation, dedicated. Overflow: on-demand shared rungs.
    assert seen[0].headers[provider_module.ptr.REQUEST_TYPE_HEADER] == 'dedicated'
    assert 'gemini-2.5-flash:generateContent' in str(seen[0].url.path)
    later_capacities = [r.headers[provider_module.ptr.REQUEST_TYPE_HEADER] for r in seen[1:]]
    later_models = [str(r.url.path).split('/models/')[-1] for r in seen[1:]]
    assert 'dedicated' not in later_capacities
    assert later_models[0].startswith('gemini-3.1-flash-lite')


@pytest.mark.asyncio
async def test_vertex_provider_walks_fallback_chain_when_model_is_unavailable(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    monkeypatch.setenv('GCP_LOCATION', 'us-central1')
    monkeypatch.delenv('OMI_VERTEX_PT_MODEL', raising=False)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if 'gemini-3.1-flash-lite' in str(request.url.path):
            return httpx.Response(404, json={'error': {'message': 'Publisher model not found'}})
        return httpx.Response(200, json=_ok_vertex_response())

    provider = _pt_provider(handler)
    result = await provider.create_chat_completion(
        {'model': 'gemini-2.5-pro', 'messages': [{'role': 'user', 'content': 'hi'}]},
        provider_ref=ProviderRef(provider='gemini', model='gemini-2.5-pro'),
        credentials=_omi_credentials(),
        timeout_ms=60_000,
    )

    assert result.response['choices'][0]['message']['content'] == 'ok'
    # Pro pins to the target, which 404s: the declared chain serves flash-lite.
    assert 'gemini-3.1-flash-lite' in str(seen[0].url.path)
    assert 'gemini-2.5-flash-lite' in str(seen[-1].url.path)
    # The dead observation is latched: the next request skips straight to the rung.
    seen.clear()
    await provider.create_chat_completion(
        {'model': 'gemini-2.5-pro', 'messages': [{'role': 'user', 'content': 'hi'}]},
        provider_ref=ProviderRef(provider='gemini', model='gemini-2.5-pro'),
        credentials=_omi_credentials(),
        timeout_ms=60_000,
    )
    assert len(seen) == 1
    assert 'gemini-2.5-flash-lite' in str(seen[0].url.path)


@pytest.mark.asyncio
async def test_vertex_provider_embedding_uses_predict_and_translates_wire(monkeypatch):
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'test-project')
    monkeypatch.setenv('GCP_LOCATION', 'us-central1')
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                'predictions': [{'embeddings': {'values': [0.1, 0.2, 0.3]}}],
                'metadata': {'billTotalCount': '7'},
            },
        )

    provider = _pt_provider(handler)
    result = await provider.create_embedding(
        {'model': 'gemini-embedding-001', 'input': ['screen text'], 'task_type': 'RETRIEVAL_QUERY'},
        provider_ref=ProviderRef(provider='gemini', model='gemini-embedding-001'),
        credentials=_omi_credentials(),
        timeout_ms=30_000,
    )

    assert ':predict' in str(seen[0].url.path)
    body = json.loads(seen[0].content)
    assert body['instances'] == [{'content': 'screen text', 'task_type': 'RETRIEVAL_QUERY'}]
    assert seen[0].headers[provider_module.ptr.REQUEST_TYPE_HEADER] == 'shared'
    assert result.response['data'][0]['embedding'] == [0.1, 0.2, 0.3]
    # Vertex :predict reports billable characters, not tokens: usage stays
    # NOT_REPORTED instead of fabricating token counts.
    assert result.accounting.usage is None


def test_vertex_tools_and_tool_config_translate_to_gemini_native():
    payload = _vertex_request(
        {
            'messages': [
                {
                    'role': 'assistant',
                    'content': None,
                    'tool_calls': [
                        {
                            'id': 'call_take_photo_0',
                            'type': 'function',
                            'function': {'name': 'take_photo', 'arguments': '{"q": "the park"}'},
                        }
                    ],
                },
                {'role': 'tool', 'tool_call_id': 'call_take_photo_0', 'content': '{"status": "ok"}'},
            ],
            'tools': [
                {
                    'type': 'function',
                    'function': {'name': 'take_photo', 'description': 'Take a photo', 'parameters': {'type': 'object'}},
                }
            ],
            'tool_choice': 'required',
        }
    )
    assert payload['tools'] == [
        {
            'functionDeclarations': [
                {'name': 'take_photo', 'description': 'Take a photo', 'parameters': {'type': 'object'}}
            ]
        }
    ]
    assert payload['toolConfig'] == {'functionCallingConfig': {'mode': 'ANY'}}
    model_turn, tool_turn = payload['contents']
    assert model_turn['role'] == 'model'
    assert model_turn['parts'] == [{'functionCall': {'name': 'take_photo', 'args': {'q': 'the park'}}}]
    assert tool_turn['role'] == 'user'
    assert tool_turn['parts'] == [{'functionResponse': {'name': 'take_photo', 'response': {'status': 'ok'}}}]
