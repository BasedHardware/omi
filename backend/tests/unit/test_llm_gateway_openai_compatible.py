from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient
import httpx
import pytest
from starlette.requests import Request

from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.executor import ProviderRegistry, provider_request_for
from llm_gateway.gateway.providers import FakeChatCompletionProvider, ProviderFailure
from llm_gateway.gateway.resolver import resolve_chat_completion_route
from llm_gateway.gateway.schemas import FailureClass, ProviderRef, ProviderRejection
from llm_gateway.main import app
from llm_gateway.routers import dependencies, openai_compatible
from models.structured_extraction import ActionItemsExtraction, ConversationStructureExtraction
from utils.llm.gateway_client import _chat_structured_payload

LANE_ID = 'omi:auto:chat-structured'


@pytest.fixture
def gateway_client():
    # TestClient startup belongs to fixture setup, not the fast-unit call budget.
    with TestClient(app) as client:
        yield client


def test_chat_completions_requires_service_auth(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    response = TestClient(app).post('/v1/chat/completions', json=valid_request())

    assert response.status_code == 401
    assert response.json()['detail'] == 'invalid service authentication'


def test_chat_completions_invalid_json_records_pre_route_rejection(monkeypatch, gateway_client):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    recorded: list[dict] = []
    monkeypatch.setattr(
        openai_compatible,
        'observe_request_rejection',
        lambda **kwargs: recorded.append(kwargs),
    )

    response = gateway_client.post(
        '/v1/chat/completions',
        content='{',
        headers={**auth_headers(), 'content-type': 'application/json'},
    )

    assert response.status_code == 400
    assert len(recorded) == 1
    assert recorded[0]['api_surface'] == 'openai_chat_completions'
    assert recorded[0]['error_class'] == 'invalid_request'
    assert recorded[0]['request_id']


def test_chat_completions_success_uses_lane_model_and_hides_route_metadata(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    provider = FakeChatCompletionProvider()
    app.dependency_overrides[dependencies.get_provider_registry] = lambda: ProviderRegistry({'openai': provider})
    try:
        response = TestClient(app).post(
            '/v1/chat/completions',
            json=valid_request(temperature=0, max_completion_tokens=64, metadata={'omi_feature': 'smoke'}),
            headers=auth_headers(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body['object'] == 'chat.completion'
    assert body['model'] == LANE_ID
    assert 'selected_provider' not in body
    assert 'selected_route_artifact_id' not in body
    # The checked-in active route is in shadow rollout (percent 0), so live
    # traffic is served by the last-known-good route. The LKG primary uses the
    # gateway-only chat_extraction policy (gpt-5.4-nano), leaving the legacy
    # product route unchanged while shadow-only.
    assert provider.calls[0].model == 'gpt-5.4-nano'
    assert provider.calls[0].request['model'] == 'gpt-5.4-nano'
    assert provider.calls[0].request['temperature'] == 0
    assert provider.calls[0].request['max_completion_tokens'] == 64
    assert 'metadata' not in provider.calls[0].request


@pytest.mark.parametrize(
    ('failure_class', 'provider_rejection', 'expected_code'),
    [
        (
            FailureClass.CAPABILITY_MISMATCH,
            ProviderRejection.UNSUPPORTED_REASONING_EFFORT,
            'capability_not_supported',
        ),
        (
            FailureClass.PROVIDER_INVALID_REQUEST,
            ProviderRejection.CONTEXT_LENGTH_EXCEEDED,
            'provider_request_rejected',
        ),
    ],
)
def test_provider_rejection_preserves_exact_terminal_class_and_bounded_member(
    monkeypatch,
    failure_class,
    provider_rejection,
    expected_code,
):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    recorded: list[dict] = []
    provider = FakeChatCompletionProvider([ProviderFailure(failure_class, provider_rejection=provider_rejection)])
    monkeypatch.setattr(openai_compatible, 'observe_error', lambda *_args, **kwargs: recorded.append(kwargs))
    app.dependency_overrides[dependencies.get_provider_registry] = lambda: ProviderRegistry({'openai': provider})
    try:
        response = TestClient(app).post(
            '/v1/chat/completions',
            json=valid_request(),
            headers=auth_headers(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()['error']['code'] == expected_code
    assert len(recorded) == 1
    error = recorded[0]['error']
    assert error.failure_class == failure_class
    assert error.provider == 'openai'
    assert error.model == 'gpt-5.4-nano'
    assert error.provider_rejection == provider_rejection


def test_chat_completions_persists_cache_aware_attempt_with_authenticated_attribution(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    persisted = []

    def capture_persist(context, trace):
        persisted.append((context, trace))

    provider = FakeChatCompletionProvider(
        [
            {
                'id': 'chatcmpl-accounted',
                'object': 'chat.completion',
                'created': 1,
                'model': 'gpt-5.4-nano',
                'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': '{}'}, 'finish_reason': 'stop'}],
                'usage': {
                    'prompt_tokens': 100,
                    'completion_tokens': 20,
                    'prompt_tokens_details': {'cached_tokens': 40},
                },
            }
        ]
    )
    monkeypatch.setattr(openai_compatible, 'schedule_attempt_trace', capture_persist)
    app.dependency_overrides[dependencies.get_provider_registry] = lambda: ProviderRegistry({'openai': provider})
    try:
        response = TestClient(app).post(
            '/v1/chat/completions',
            json=valid_request(prompt_cache_key='conversation-123'),
            headers={**auth_headers(), 'x-omi-llm-feature': 'conversation_processing'},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(persisted) == 1
    context, trace = persisted[0]
    assert context.user_uid == 'user-123'
    assert context.feature == 'conversation_processing'
    assert trace.attempts[0].usage is not None
    assert trace.attempts[0].usage.cached_input_tokens == 40
    assert trace.attempts[0].usage.cache_status.value == 'partial_hit'


def test_gateway_provider_body_forwards_validated_gpt56_cache_fields_unchanged():
    request = valid_request(
        prompt_cache_key='omi-extract-actions-v1-b0',
        prompt_cache_options={'mode': 'explicit', 'ttl': '30m'},
        messages=[
            {
                'role': 'system',
                'content': [
                    {
                        'type': 'text',
                        'text': 'Stable instructions.',
                        'prompt_cache_breakpoint': {'mode': 'explicit'},
                    }
                ],
            },
            {'role': 'user', 'content': 'Dynamic content.'},
        ],
    )
    resolved = resolve_chat_completion_route(load_gateway_config(prod_mode=True), request)
    forwarded = provider_request_for(resolved, ProviderRef(provider='openai', model='gpt-5.6-luna'))

    assert forwarded['prompt_cache_key'] == 'omi-extract-actions-v1-b0'
    assert forwarded['prompt_cache_options'] == {'mode': 'explicit', 'ttl': '30m'}
    assert forwarded['messages'] == request['messages']


def test_gateway_provider_body_strips_gpt56_cache_fields_for_legacy_route():
    request = valid_request(
        prompt_cache_key='omi-extract-actions-v1-b0',
        prompt_cache_options={'mode': 'explicit', 'ttl': '30m'},
        messages=[
            {
                'role': 'system',
                'content': [
                    {
                        'type': 'text',
                        'text': 'Stable instructions.',
                        'prompt_cache_breakpoint': {'mode': 'explicit'},
                    }
                ],
            },
            {'role': 'user', 'content': 'Dynamic content.'},
        ],
    )
    resolved = resolve_chat_completion_route(load_gateway_config(prod_mode=True), request)
    forwarded = provider_request_for(resolved, ProviderRef(provider='openai', model='gpt-5.4-nano'))

    assert forwarded['prompt_cache_key'] == 'omi-extract-actions-v1-b0'
    assert 'prompt_cache_options' not in forwarded
    assert forwarded['messages'][0]['content'] == [{'type': 'text', 'text': 'Stable instructions.'}]


def test_metadata_feature_never_enters_the_accounting_context(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    persisted = []

    def capture_persist(context, trace):
        persisted.append((context, trace))

    monkeypatch.setattr(openai_compatible, 'schedule_attempt_trace', capture_persist)
    provider = FakeChatCompletionProvider()
    app.dependency_overrides[dependencies.get_provider_registry] = lambda: ProviderRegistry({'openai': provider})
    try:
        response = TestClient(app).post(
            '/v1/chat/completions',
            json=valid_request(metadata={'omi_feature': 'private user supplied metadata'}),
            headers=auth_headers(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert persisted[0][0].feature == LANE_ID


def test_chat_completions_uses_forwarded_byok_credentials(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    provider = FakeChatCompletionProvider()
    app.dependency_overrides[dependencies.get_provider_registry] = lambda: ProviderRegistry({'openai': provider})
    try:
        response = TestClient(app).post(
            '/v1/chat/completions',
            json=valid_request(),
            headers={
                **auth_headers(),
                'X-Omi-Byok-OpenAI-Key': 'sk-user-byok',
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert provider.calls[0].credential_mode == 'byok'


def test_image_generation_records_gateway_attempt(monkeypatch):
    class FakeImageClient:
        async def post(self, *_args, **_kwargs):
            return httpx.Response(200, json={'created': 1, 'data': [{'url': 'https://example.invalid/image'}]})

    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    monkeypatch.setenv('OPENAI_API_KEY', 'omi-openai-key')
    persisted = []

    def capture_persist(context, trace):
        persisted.append((context, trace))

    monkeypatch.setattr(openai_compatible, '_get_image_generation_client', lambda: FakeImageClient())
    monkeypatch.setattr(openai_compatible, 'schedule_attempt_trace', capture_persist)
    response = TestClient(app).post(
        '/v1/images/generations',
        json={'model': 'gpt-image-1', 'prompt': 'private prompt', 'size': '1024x1024', 'quality': 'high', 'n': 2},
        headers={**auth_headers(), 'x-omi-llm-feature': 'app_generator'},
    )

    assert response.status_code == 200
    assert len(persisted) == 1
    context, trace = persisted[0]
    assert context.api_surface == 'openai_images_generations'
    assert context.feature == 'app_generator'
    assert trace.attempts[0].usage is not None
    assert trace.attempts[0].usage.unit_type == 'images'
    assert trace.attempts[0].usage.image_count == 2


def test_image_generation_normalizes_auto_defaults_for_estimated_accounting(monkeypatch):
    class FakeImageClient:
        def __init__(self):
            self.calls = []

        async def post(self, *_args, **kwargs):
            self.calls.append(kwargs)
            return httpx.Response(200, json={'created': 1, 'data': [{'url': 'https://example.invalid/image'}]})

    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    monkeypatch.setenv('OPENAI_API_KEY', 'omi-openai-key')
    persisted = []
    client = FakeImageClient()
    monkeypatch.setattr(openai_compatible, '_get_image_generation_client', lambda: client)
    monkeypatch.setattr(
        openai_compatible, 'schedule_attempt_trace', lambda context, trace: persisted.append((context, trace))
    )

    response = TestClient(app).post(
        '/v1/images/generations',
        json={'model': 'gpt-image-1', 'prompt': 'private prompt'},
        headers=auth_headers(),
    )

    usage = persisted[0][1].attempts[0].usage
    assert response.status_code == 200
    assert client.calls[0]['json']['size'] == 'auto'
    assert client.calls[0]['json']['quality'] == 'auto'
    assert usage is not None
    assert usage.image_size == 'auto'
    assert usage.image_quality == 'auto'


def test_chat_completions_forwards_action_item_extraction_strict_schema(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    provider = FakeChatCompletionProvider()
    app.dependency_overrides[dependencies.get_provider_registry] = lambda: ProviderRegistry({'openai': provider})
    try:
        request = _chat_structured_payload(
            'Extract action items.',
            ActionItemsExtraction,
            feature='conversation_action_items.extract.shadow',
        )
        response = TestClient(app).post('/v1/chat/completions', json=request, headers=auth_headers())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    forwarded_schema = provider.calls[0].request['response_format']['json_schema']['schema']
    assert forwarded_schema['required'] == ['action_items']
    action_item_schema = forwarded_schema['$defs']['ExtractedActionItem']
    assert action_item_schema['additionalProperties'] is False
    assert action_item_schema['required'] == [
        'description',
        'due_at',
        'capture_kind',
        'capture_confidence',
        'ownership_confidence',
        'capture_owner',
        'concrete_deliverable',
        'candidate_action',
        'target_task_id',
    ]
    assert 'default' not in action_item_schema['properties']['due_at']


def test_chat_completions_forwards_conversation_structure_extraction_strict_schema(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    provider = FakeChatCompletionProvider()
    app.dependency_overrides[dependencies.get_provider_registry] = lambda: ProviderRegistry({'openai': provider})
    try:
        request = _chat_structured_payload(
            'Extract conversation structure.',
            ConversationStructureExtraction,
            feature='conversation_structure.extract.shadow',
        )
        response = TestClient(app).post('/v1/chat/completions', json=request, headers=auth_headers())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    forwarded_schema = provider.calls[0].request['response_format']['json_schema']['schema']
    assert forwarded_schema['required'] == ['title', 'overview', 'emoji', 'category']
    category_schema = forwarded_schema['properties']['category']
    assert category_schema['type'] == 'string'
    assert 'enum' in category_schema
    assert '$ref' not in category_schema
    assert category_schema['description'] == 'A category for this conversation'


def test_chat_completions_rejects_unknown_auto_lane(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    request = valid_request(model='omi:auto:unknown')

    response = TestClient(app).post('/v1/chat/completions', json=request, headers=auth_headers())

    assert response.status_code == 404
    assert response.json()['error']['code'] == 'model_not_found'


def test_chat_completions_rejects_bare_provider_model(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    request = valid_request(model='gpt-4o-mini')

    response = TestClient(app).post('/v1/chat/completions', json=request, headers=auth_headers())

    assert response.status_code == 400
    assert response.json()['error']['code'] == 'unsupported_model'


def test_chat_completions_rejects_unsupported_capability(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    request = valid_request(stream=True)

    response = TestClient(app).post('/v1/chat/completions', json=request, headers=auth_headers())

    assert response.status_code == 400
    assert response.json()['error']['code'] == 'capability_not_supported'
    assert response.json()['error']['type'] == 'invalid_request_error'
    assert response.json()['error']['param'] == 'stream'


def test_chat_completions_error_type_is_openai_category_not_code_duplicate(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    request = valid_request(unexpected_parameter=True)

    response = TestClient(app).post('/v1/chat/completions', json=request, headers=auth_headers())

    assert response.status_code == 400
    error = response.json()['error']
    assert error['type'] == 'invalid_request_error'
    assert error['code'] != error['type']


def test_chat_completions_rejects_unknown_request_parameter(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    request = valid_request(unexpected_parameter=True)

    response = TestClient(app).post('/v1/chat/completions', json=request, headers=auth_headers())

    assert response.status_code == 400
    assert response.json()['error']['code'] == 'invalid_request'
    assert response.json()['error']['param'] == 'unexpected_parameter'


def test_chat_completions_fails_closed_when_openai_key_is_not_configured(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)

    response = TestClient(app).post('/v1/chat/completions', json=valid_request(), headers=auth_headers())

    assert response.status_code == 503
    assert response.json()['error']['code'] == 'invalid_route_config'


def test_streaming_provider_setup_failure_returns_json_error_before_streaming(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    recorded: list[dict] = []
    monkeypatch.setattr(openai_compatible, 'observe_error', lambda *_args, **kwargs: recorded.append(kwargs))
    app.dependency_overrides[dependencies.get_gateway_config] = _streaming_enabled_gateway_config
    app.dependency_overrides[dependencies.get_provider_registry] = lambda: ProviderRegistry(
        {'openai': FailingStreamProvider()}
    )
    try:
        response = TestClient(app).post('/v1/chat/completions', json=valid_request(stream=True), headers=auth_headers())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.headers['content-type'].startswith('application/json')
    assert response.json()['error']['code'] == 'invalid_route_config'
    assert len(recorded) == 1
    assert recorded[0]['streaming'] is True
    assert recorded[0]['request_id']


class FailingStreamProvider(FakeChatCompletionProvider):
    async def stream_chat_completion(self, *_args, **_kwargs):
        raise ProviderFailure(FailureClass.INVALID_CONFIG)
        yield b''


class CancellingStreamProvider(FakeChatCompletionProvider):
    async def stream_chat_completion(self, *_args, **_kwargs):
        raise asyncio.CancelledError
        yield b''


@pytest.mark.asyncio
async def test_streaming_cancellation_before_output_records_cancelled(monkeypatch):
    recorded: list[dict] = []
    request_id = '2a055692-a190-407c-bb17-bf35ed955cca'
    monkeypatch.setattr(openai_compatible, 'observe_route_result', lambda *_args, **kwargs: recorded.append(kwargs))
    body = json.dumps(valid_request(stream=True)).encode()
    consumed = False

    async def receive():
        nonlocal consumed
        if consumed:
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        consumed = True
        return {'type': 'http.request', 'body': body, 'more_body': False}

    request = Request(
        {
            'type': 'http',
            'method': 'POST',
            'path': '/v1/chat/completions',
            'headers': [],
        },
        receive,
    )
    request.state.request_id = request_id

    with pytest.raises(asyncio.CancelledError):
        await openai_compatible.create_chat_completion(
            request,
            ServiceCaller(name='backend'),
            _streaming_enabled_gateway_config(),
            ProviderRegistry({'openai': CancellingStreamProvider()}),
        )

    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'cancelled'
    assert recorded[0]['error_class'] == 'client_cancelled'
    assert recorded[0]['phase'] == 'before_output'
    assert recorded[0]['streaming'] is True
    assert recorded[0]['request_id'] == request_id


class TerminalStreamProvider(FakeChatCompletionProvider):
    def __init__(self, chunks: list[bytes]):
        super().__init__()
        self.chunks = chunks
        self.stream_requests: list[dict] = []

    async def stream_chat_completion(self, request, *_args, **_kwargs):
        self.stream_requests.append(request)
        for chunk in self.chunks:
            yield chunk


def test_streaming_success_requires_done_marker_and_records_byok_source(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    recorded: list[dict] = []
    persisted = []
    request_id = 'f6720df5-245e-4fd7-b10b-ec869888e1de'
    provider = TerminalStreamProvider(
        [
            b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n',
            b'data: {"usage":{"prompt_tokens":10,"completion_tokens":4,"prompt_tokens_details":{"cached_tokens":0}}}\n\n',
            b'data: [DONE]\n\n',
        ]
    )
    monkeypatch.setattr(openai_compatible, 'observe_route_result', lambda *_args, **kwargs: recorded.append(kwargs))

    def capture_persist(context, trace):
        persisted.append((context, trace))

    monkeypatch.setattr(openai_compatible, 'schedule_attempt_trace', capture_persist)
    app.dependency_overrides[dependencies.get_gateway_config] = _streaming_enabled_gateway_config
    app.dependency_overrides[dependencies.get_provider_registry] = lambda: ProviderRegistry({'openai': provider})
    try:
        response = TestClient(app).post(
            '/v1/chat/completions',
            json=valid_request(stream=True),
            headers={
                **auth_headers(),
                'x-omi-request-id': request_id,
                'x-omi-byok-openai-key': 'sk-test-byok',
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers['x-omi-request-id'] == request_id
    assert response.content.endswith(b'data: [DONE]\n\n')
    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'success'
    assert recorded[0]['phase'] == 'terminal_marker'
    assert recorded[0]['credential_source'] == 'service_forwarded_byok'
    assert recorded[0]['streaming'] is True
    assert recorded[0]['ttfb_seconds'] is not None
    assert recorded[0]['budget_source'] == 'none'
    assert recorded[0]['output_budget'] == 'none'
    assert recorded[0]['completion_size'] == 'le_64'
    assert recorded[0]['finish_reason'] == 'unknown'
    assert len(persisted) == 1
    context, trace = persisted[0]
    assert context.payer == 'byok'
    assert trace.attempts[-1].usage is not None
    assert trace.attempts[-1].usage.cache_status.value == 'no_cache_read_observed'
    assert provider.stream_requests[0]['stream_options']['include_usage'] is True


def test_streaming_payload_text_cannot_fake_done_marker(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    recorded: list[dict] = []
    provider = TerminalStreamProvider([b'data: {"choices":[{"delta":{"content":"data: [DONE]"}}]}\n\n'])
    monkeypatch.setattr(openai_compatible, 'observe_route_result', lambda *_args, **kwargs: recorded.append(kwargs))
    app.dependency_overrides[dependencies.get_gateway_config] = _streaming_enabled_gateway_config
    app.dependency_overrides[dependencies.get_provider_registry] = lambda: ProviderRegistry({'openai': provider})
    try:
        response = TestClient(app).post(
            '/v1/chat/completions',
            json=valid_request(stream=True),
            headers=auth_headers(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'error'
    assert recorded[0]['error_class'] == 'eof_before_terminal_marker'


@pytest.mark.asyncio
async def test_streaming_midstream_provider_failure_records_error_exactly_once(monkeypatch):
    recorded: list[dict] = []
    monkeypatch.setattr(openai_compatible, 'observe_route_result', lambda *_args, **kwargs: recorded.append(kwargs))
    config = _streaming_enabled_gateway_config()
    resolved = resolve_chat_completion_route(config, valid_request(stream=True))
    route = openai_compatible.selected_serving_route(resolved)

    async def failing_stream():
        raise ProviderFailure(FailureClass.PROVIDER_5XX_OMI_PAID)
        yield b''

    prepared = openai_compatible._PreparedStream(
        first_chunk=b'data: {"choices":[]}\n\n',
        stream=failing_stream(),
        provider='openai',
        model='gpt-5.4-nano',
        fallback_used=False,
        fallback_reason=None,
    )
    stream = openai_compatible._stream_with_terminal_metrics(
        prepared,
        resolved_route=resolved,
        credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
        route=route,
        started_at=openai_compatible.time_request(),
        request_id='2cb4c714-f0f1-4d37-a1d4-fb28cb22c359',
    )

    assert await anext(stream) == b'data: {"choices":[]}\n\n'
    with pytest.raises(ProviderFailure):
        await anext(stream)

    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'error'
    assert recorded[0]['error_class'] == 'provider_5xx_omi_paid_midstream'


@pytest.mark.asyncio
async def test_streaming_consumer_abandonment_records_cancelled_exactly_once(monkeypatch):
    recorded: list[dict] = []
    monkeypatch.setattr(openai_compatible, 'observe_route_result', lambda *_args, **kwargs: recorded.append(kwargs))
    config = _streaming_enabled_gateway_config()
    resolved = resolve_chat_completion_route(config, valid_request(stream=True))
    route = openai_compatible.selected_serving_route(resolved)

    async def remaining_stream():
        yield b'data: {"choices":[]}\n\n'

    stream = openai_compatible._stream_with_terminal_metrics(
        openai_compatible._PreparedStream(
            first_chunk=b'data: {"choices":[]}\n\n',
            stream=remaining_stream(),
            provider='openai',
            model='gpt-5.4-nano',
            fallback_used=False,
            fallback_reason=None,
        ),
        resolved_route=resolved,
        credentials=build_omi_managed_credential_context(ServiceCaller(name='backend')),
        route=route,
        started_at=openai_compatible.time_request(),
        request_id='69fec0ac-5e33-44a3-a881-407989aa02ac',
    )

    _ = await anext(stream)
    await stream.aclose()

    assert len(recorded) == 1
    assert recorded[0]['outcome'] == 'cancelled'
    assert recorded[0]['error_class'] == 'consumer_abandoned_stream'


def _streaming_enabled_gateway_config():
    config = load_gateway_config(prod_mode=True)
    lane = config.lanes[LANE_ID]
    capabilities = lane.capabilities.model_copy(update={'streaming': True})
    lane = lane.model_copy(update={'capabilities': capabilities})
    route_artifacts = dict(config.route_artifacts)
    for route_id in (lane.active_route, lane.last_known_good):
        route_artifacts[route_id] = route_artifacts[route_id].model_copy(update={'capabilities': capabilities})
    lanes = dict(config.lanes)
    lanes[LANE_ID] = lane
    return config.model_copy(update={'lanes': lanes, 'route_artifacts': route_artifacts})


def auth_headers() -> dict[str, str]:
    return {
        'authorization': 'Bearer shared-secret',
        'x-omi-service-caller': 'backend',
        'x-omi-user-uid': 'user-123',
    }


def valid_request(**overrides):
    request = {
        'model': LANE_ID,
        'messages': [
            {'role': 'system', 'content': 'Return structured JSON.'},
            {'role': 'user', 'content': 'Extract the memory.'},
        ],
        'response_format': {
            'type': 'json_schema',
            'json_schema': {
                'name': 'memory_extraction',
                'strict': True,
                'schema': {
                    'type': 'object',
                    'properties': {'memory': {'type': 'string'}},
                    'required': ['memory'],
                    'additionalProperties': False,
                },
            },
        },
    }
    request.update(overrides)
    return request
