from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from llm_gateway.gateway.auth import ServiceAuthDependency, ServiceCaller, require_service_auth
from llm_gateway.main import app as gateway_app


def _protected_app() -> FastAPI:
    app = FastAPI()

    @app.get('/protected')
    def protected(caller: ServiceAuthDependency):
        return caller.model_dump(mode='json')

    return app


def test_health_remains_unauthenticated_when_service_token_is_missing(monkeypatch):
    monkeypatch.delenv('LLM_GATEWAY_SERVICE_TOKEN', raising=False)

    response = TestClient(gateway_app).get('/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'healthy'}


def test_missing_service_token_config_fails_closed(monkeypatch):
    monkeypatch.delenv('LLM_GATEWAY_SERVICE_TOKEN', raising=False)

    response = TestClient(_protected_app()).get('/protected')

    assert response.status_code == 503
    assert response.json()['detail'] == 'llm gateway service auth is not configured'


def test_missing_auth_header_is_rejected(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    response = TestClient(_protected_app()).get('/protected', headers={'x-omi-service-caller': 'backend'})

    assert response.status_code == 401


def test_wrong_token_is_rejected(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    response = TestClient(_protected_app()).get(
        '/protected',
        headers={
            'authorization': 'Bearer wrong-secret',
            'x-omi-service-caller': 'backend',
        },
    )

    assert response.status_code == 401


def test_unknown_caller_is_rejected(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    response = TestClient(_protected_app()).get(
        '/protected',
        headers={
            'authorization': 'Bearer shared-secret',
            'x-omi-service-caller': 'desktop',
        },
    )

    assert response.status_code == 403


def test_backend_and_pusher_callers_succeed_by_default(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    client = TestClient(_protected_app())

    for caller in ('backend', 'pusher'):
        response = client.get(
            '/protected',
            headers={
                'authorization': 'Bearer shared-secret',
                'x-omi-service-caller': caller,
                'x-omi-user-uid': 'user-123',
                'x-omi-tenant-id': 'tenant-abc',
            },
        )

        assert response.status_code == 200
        assert response.json() == {
            'name': caller,
            'user_uid': 'user-123',
            'tenant_id': 'tenant-abc',
        }


def test_auth_dependency_returns_service_caller_model():
    assert require_service_auth
    caller = ServiceCaller(name='Backend', user_uid=' user-123 ', tenant_id=' tenant-abc ')

    assert caller.name == 'backend'
    assert caller.user_uid == 'user-123'
    assert caller.tenant_id == 'tenant-abc'
