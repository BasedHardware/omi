from fastapi import FastAPI
from fastapi.testclient import TestClient

from llm_gateway.routers.metrics import router

app = FastAPI()
app.include_router(router)

client = TestClient(app)


def test_metrics_no_secret_configured(monkeypatch):
    monkeypatch.delenv('METRICS_SECRET', raising=False)
    response = client.get('/metrics', headers={'Authorization': 'Bearer any'})
    assert response.status_code == 401


def test_metrics_no_credentials(monkeypatch):
    monkeypatch.setenv('METRICS_SECRET', 'secret123')
    response = client.get('/metrics')
    assert response.status_code == 401


def test_metrics_wrong_credentials(monkeypatch):
    monkeypatch.setenv('METRICS_SECRET', 'secret123')
    response = client.get('/metrics', headers={'Authorization': 'Bearer wrong'})
    assert response.status_code == 401


def test_metrics_correct_credentials(monkeypatch):
    monkeypatch.setenv('METRICS_SECRET', 'secret123')
    response = client.get('/metrics', headers={'Authorization': 'Bearer secret123'})
    assert response.status_code == 200
    assert "HELP" in response.text
