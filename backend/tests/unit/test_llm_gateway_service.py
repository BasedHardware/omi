import uuid

import pytest
from fastapi.testclient import TestClient

from llm_gateway import main
from llm_gateway.main import app
from llm_gateway.routers import dependencies


def test_llm_gateway_app_imports_and_health_is_public():
    client = TestClient(app)

    response = client.get('/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'healthy'}
    assert str(uuid.UUID(response.headers['x-omi-request-id'])) == response.headers['x-omi-request-id']


def test_request_correlation_preserves_canonical_uuid_and_replaces_untrusted_value():
    client = TestClient(app)
    request_id = str(uuid.uuid4())

    preserved = client.get('/health', headers={'x-omi-request-id': request_id})
    replaced = client.get('/health', headers={'x-omi-request-id': 'not-a-safe-correlation-id'})

    assert preserved.headers['x-omi-request-id'] == request_id
    assert replaced.headers['x-omi-request-id'] != 'not-a-safe-correlation-id'
    assert str(uuid.UUID(replaced.headers['x-omi-request-id'])) == replaced.headers['x-omi-request-id']


def test_unexpected_500_keeps_request_correlation_without_exposing_exception(monkeypatch):
    request_id = '61fce54a-9f3f-4223-a2ac-eaa23435a6d9'
    monkeypatch.setenv('LLM_GATEWAY_SERVICE_TOKEN', 'shared-secret')

    def fail_config_load():
        raise RuntimeError('secret detail must not be returned')

    app.dependency_overrides[dependencies.get_gateway_config] = fail_config_load
    try:
        response = TestClient(app, raise_server_exceptions=False).post(
            '/v1/chat/completions',
            json={'model': 'omi:auto:chat-structured', 'messages': []},
            headers={
                'authorization': 'Bearer shared-secret',
                'x-omi-service-caller': 'backend',
                'x-omi-request-id': request_id,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert response.headers['x-omi-request-id'] == request_id
    assert response.json() == {'detail': 'internal server error'}


@pytest.mark.asyncio
async def test_lifespan_runs_registry_cleanup_when_image_cleanup_fails(monkeypatch):
    calls = []

    async def fail_image_cleanup():
        calls.append('image')
        raise RuntimeError('image cleanup failed')

    async def close_registry():
        calls.append('registry')

    monkeypatch.setattr(main.openai_compatible, 'close_image_generation_client', fail_image_cleanup)
    monkeypatch.setattr(main, 'close_provider_registry', close_registry)

    async with main.lifespan(app):
        pass

    assert calls == ['image', 'registry']
