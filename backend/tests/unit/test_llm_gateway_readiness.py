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

    response = TestClient(app).get('/ready', headers=auth_headers())

    assert response.status_code == 200
    assert response.json()['status'] == 'ready'
    # R0: 16 lanes total (1 existing + 15 new). See .aidlc/spec.md lane table.
    assert response.json()['lanes'] == sorted(
        [
            'omi:auto:chat-structured',
            'omi:auto:chat-extraction',
            'omi:auto:daily-summary',
            'omi:auto:memories-extraction',
            'omi:auto:memory-graph',
            'omi:auto:conv-action-items',
            'omi:auto:conv-structure',
            'omi:auto:general-assistant',
            'omi:auto:reasoning',
            'omi:auto:stt-realtime',
            'omi:auto:transcription',
            'omi:auto:screenshot-understanding',
            'omi:auto:screenshot-embedding',
            'omi:auto:realtime-ptt',
            'omi:auto:persona-chat',
            'omi:auto:notification-classifier',
        ]
    )
    # R0: 17 artifacts total (2 existing chat-structured + 15 new).
    assert response.json()['route_artifact_count'] == 17


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
