from __future__ import annotations

from fastapi.testclient import TestClient

from llm_gateway.gateway.config_loader import ConfigValidationError
from llm_gateway.main import app
from llm_gateway.routers import health


def test_ready_requires_service_auth(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    response = TestClient(app).get('/ready')

    assert response.status_code == 401
    assert response.json()['detail'] == 'invalid service authentication'


def test_ready_validates_gateway_config(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    response = TestClient(app).get('/ready', headers=auth_headers())

    assert response.status_code == 200
    assert response.json()['status'] == 'ready'
    assert response.json()['lanes'] == ['omi:auto:chat-structured']
    assert response.json()['route_artifact_count'] == 2


def test_ready_fails_closed_on_invalid_gateway_config(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    def invalid_config():
        raise ConfigValidationError('bad test config')

    monkeypatch.setattr(health, 'get_gateway_config', invalid_config)

    response = TestClient(app).get('/ready', headers=auth_headers())

    assert response.status_code == 503
    assert response.json()['detail'] == 'llm gateway config is invalid'


def auth_headers() -> dict[str, str]:
    return {
        'authorization': 'Bearer shared-secret',
        'x-omi-service-caller': 'backend',
    }
