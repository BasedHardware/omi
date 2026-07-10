from __future__ import annotations

from fastapi.testclient import TestClient

from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import FakeChatCompletionProvider, ProviderFailure
from llm_gateway.gateway.schemas import FailureClass
from llm_gateway.main import app
from llm_gateway.routers import dependencies
from models.structured_extraction import ActionItemsExtraction, ConversationStructureExtraction
from utils.llm.gateway_client import _chat_structured_payload

LANE_ID = 'omi:auto:chat-structured'


def test_chat_completions_requires_service_auth(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    response = TestClient(app).post('/v1/chat/completions', json=valid_request())

    assert response.status_code == 401
    assert response.json()['detail'] == 'invalid service authentication'


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
    # traffic is served by the last-known-good route. The LKG primary matches
    # the legacy `chat_extraction` model (gpt-4.1-mini) so enabling the pilot
    # is a no-user-visible behavior match while shadow-only.
    assert provider.calls[0].model == 'gpt-4.1-mini'
    assert provider.calls[0].request['model'] == 'gpt-4.1-mini'
    assert provider.calls[0].request['temperature'] == 0
    assert provider.calls[0].request['max_completion_tokens'] == 64
    assert 'metadata' not in provider.calls[0].request


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
    assert action_item_schema['required'] == ['description', 'due_at']
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


class FailingStreamProvider(FakeChatCompletionProvider):
    async def stream_chat_completion(self, *_args, **_kwargs):
        raise ProviderFailure(FailureClass.INVALID_CONFIG)
        yield b''


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
