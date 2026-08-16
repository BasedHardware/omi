from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from llm_gateway.gateway import auth
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


def test_auth_rejection_uses_bounded_reason_without_caller_or_token_labels(monkeypatch):
    recorded: list[str] = []
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    monkeypatch.setattr(auth, 'observe_auth_rejection', lambda reason: recorded.append(reason))

    response = TestClient(_protected_app()).get(
        '/protected',
        headers={
            'authorization': 'Bearer attacker-controlled-value',
            'x-omi-service-caller': 'attacker-controlled-caller',
        },
    )

    assert response.status_code == 401
    assert recorded == ['invalid_token']


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


def test_malformed_caller_is_rejected_without_500(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    response = TestClient(_protected_app()).get(
        '/protected',
        headers={
            'authorization': 'Bearer shared-secret',
            'x-omi-service-caller': 'not valid',
        },
    )

    assert response.status_code == 403
    assert response.json()['detail'] == 'invalid service caller'


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


def test_authenticated_usage_feature_is_available_but_not_response_serialized(monkeypatch):
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')
    request = TestClient(_protected_app()).get(
        '/protected',
        headers={
            'authorization': 'Bearer shared-secret',
            'x-omi-service-caller': 'backend',
            'x-omi-llm-feature': 'conversation_processing',
        },
    )

    assert request.status_code == 200
    assert 'usage_feature' not in request.json()
    caller = ServiceCaller(name='backend', usage_feature=' conversation_processing ')
    assert caller.usage_feature == 'conversation_processing'


def test_primary_service_token_env_var_is_accepted(monkeypatch):
    """Gateway must accept OMI_LLM_GATEWAY_SERVICE_TOKEN (the client's primary var)."""
    monkeypatch.setenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', 'primary-token')
    monkeypatch.delenv('LLM_GATEWAY_SERVICE_TOKEN', raising=False)

    response = TestClient(_protected_app()).get(
        '/protected',
        headers={'authorization': 'Bearer primary-token', 'x-omi-service-caller': 'backend'},
    )

    assert response.status_code == 200


def test_primary_service_token_takes_precedence_over_legacy(monkeypatch):
    """When both vars are set, the OMI_ prefixed one must win (matching the client)."""
    monkeypatch.setenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', 'primary-token')
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'legacy-token')

    client = TestClient(_protected_app())
    primary = client.get(
        '/protected',
        headers={'authorization': 'Bearer primary-token', 'x-omi-service-caller': 'backend'},
    )
    legacy = client.get(
        '/protected',
        headers={'authorization': 'Bearer legacy-token', 'x-omi-service-caller': 'backend'},
    )

    assert primary.status_code == 200
    # Legacy token is rejected because the gateway resolves to the primary value.
    assert legacy.status_code == 401


def test_legacy_service_token_still_accepted_when_primary_absent(monkeypatch):
    """Bare LLM_GATEWAY_SERVICE_TOKEN still works for backward compatibility."""
    monkeypatch.delenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', raising=False)
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'legacy-token')

    response = TestClient(_protected_app()).get(
        '/protected',
        headers={'authorization': 'Bearer legacy-token', 'x-omi-service-caller': 'backend'},
    )

    assert response.status_code == 200


def test_both_service_token_vars_blank_fails_closed(monkeypatch):
    """Blank values in both vars must fail closed (503)."""
    monkeypatch.setenv('OMI_LLM_GATEWAY_SERVICE_TOKEN', '   ')
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', '')

    response = TestClient(_protected_app()).get(
        '/protected',
        headers={'authorization': 'Bearer anything', 'x-omi-service-caller': 'backend'},
    )

    assert response.status_code == 503
