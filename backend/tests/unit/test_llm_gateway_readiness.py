from __future__ import annotations

from fastapi.testclient import TestClient

from llm_gateway.gateway.config_loader import ConfigValidationError
from llm_gateway.gateway.schemas import LaneConfig
from llm_gateway.main import app
from llm_gateway.routers import health


def test_ready_requires_service_auth(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    response = TestClient(app).get('/ready')

    assert response.status_code == 401
    assert response.json()['detail'] == 'invalid service authentication'


def test_ready_validates_gateway_config(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'anthropic-test-key')

    response = TestClient(app).get('/ready', headers=auth_headers())

    assert response.status_code == 200
    assert response.json()['status'] == 'ready'
    assert 'omi:auto:chat-structured' in response.json()['lanes']
    assert response.json()['route_artifact_count'] >= len(response.json()['lanes'])
    assert response.json()['managed_messages_provider'] == 'anthropic'


def test_ready_fails_closed_when_managed_anthropic_messages_key_is_missing(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)

    response = TestClient(app).get('/ready', headers=auth_headers())

    assert response.status_code == 503
    assert response.json()['detail'] == 'llm gateway managed messages provider is not configured'


def test_ready_fails_closed_on_invalid_gateway_config(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    def invalid_config():
        raise ConfigValidationError('bad test config')

    monkeypatch.setattr(health, 'get_gateway_config', invalid_config)

    response = TestClient(app).get('/ready', headers=auth_headers())

    assert response.status_code == 503
    assert response.json()['detail'] == 'llm gateway config is invalid'


def test_ready_fails_closed_on_schema_validation_error(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    def invalid_config():
        LaneConfig.model_validate({})

    monkeypatch.setattr(health, 'get_gateway_config', invalid_config)

    response = TestClient(app).get('/ready', headers=auth_headers())

    assert response.status_code == 503
    assert response.json()['detail'] == 'llm gateway config is invalid'


def auth_headers() -> dict[str, str]:
    return {
        'authorization': 'Bearer shared-secret',
        'x-omi-service-caller': 'backend',
    }
