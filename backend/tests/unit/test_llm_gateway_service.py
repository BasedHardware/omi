import pytest
from fastapi.testclient import TestClient

from llm_gateway import main
from llm_gateway.main import app


def test_llm_gateway_app_imports_and_health_is_public():
    client = TestClient(app)

    response = client.get('/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'healthy'}


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
