from __future__ import annotations

import json

import httpx
import pytest

from llm_gateway.gateway import providers as provider_module
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_byok_credential_context, build_omi_managed_credential_context
from llm_gateway.gateway.providers import (
    ProviderFailure,
    VertexAccessTokenSupplier,
    VertexGeminiProvider,
    _vertex_request,
)
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
