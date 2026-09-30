"""Unit tests for trends router resilience and error boundaries."""

from unittest.mock import MagicMock
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest

from routers import trends as trends_router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(trends_router.router)
    return TestClient(app, raise_server_exceptions=False)


def test_get_trends_success(client, monkeypatch):
    mock_data = [{"category": "company", "topics": [{"topic": "OpenAI", "memories_count": 5}]}]
    monkeypatch.setattr(trends_router.trends_db, "get_trends_data", lambda: mock_data)

    response = client.get("/v1/trends")

    assert response.status_code == 200
    assert response.json() == mock_data


def test_get_trends_db_failure_returns_500(client, monkeypatch):
    def _fail():
        raise RuntimeError("Firestore stream error")

    monkeypatch.setattr(trends_router.trends_db, "get_trends_data", _fail)

    response = client.get("/v1/trends")

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to retrieve trends data"
