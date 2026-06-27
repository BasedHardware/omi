from __future__ import annotations

from fastapi.testclient import TestClient

from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import FakeChatCompletionProvider
from llm_gateway.main import app
from llm_gateway.routers import openai_compatible

LANE_ID = 'omi:auto:chat-structured'


def test_chat_completions_requires_service_auth(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    response = TestClient(app).post('/v1/chat/completions', json=valid_request())

    assert response.status_code == 401
    assert response.json()['detail'] == 'invalid service authentication'


def test_chat_completions_success_uses_lane_model_and_hides_route_metadata(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    provider = FakeChatCompletionProvider()
    app.dependency_overrides[openai_compatible.get_provider_registry] = lambda: ProviderRegistry({'openai': provider})
    try:
        response = TestClient(app).post(
            '/v1/chat/completions',
            json=valid_request(),
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
    assert provider.calls[0].model == 'gpt-4.1-mini'
    assert provider.calls[0].request['model'] == 'gpt-4.1-mini'


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
    assert response.json()['error']['param'] == 'stream'


def test_chat_completions_fails_closed_when_provider_registry_is_not_wired(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    response = TestClient(app).post('/v1/chat/completions', json=valid_request(), headers=auth_headers())

    assert response.status_code == 503
    assert response.json()['error']['code'] == 'invalid_route_config'


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
