from fastapi.testclient import TestClient

from llm_gateway.main import app


def test_llm_gateway_app_imports_and_health_is_public():
    client = TestClient(app)

    response = client.get('/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'healthy'}
