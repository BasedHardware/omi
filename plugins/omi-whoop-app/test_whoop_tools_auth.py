import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from whoop_tools_auth import require_whoop_tools_auth


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("WHOOP_TOOLS_SECRET", raising=False)

    app = FastAPI()

    @app.post("/protected")
    def protected(_: None = Depends(require_whoop_tools_auth)):
        return {"ok": True}

    return TestClient(app)


def test_fails_closed_when_secret_is_unconfigured(client):
    response = client.post("/protected")

    assert response.status_code == 503
    assert response.json()["detail"] == "Whoop tools authentication is not configured"


def test_rejects_missing_credentials(client, monkeypatch):
    monkeypatch.setenv("WHOOP_TOOLS_SECRET", "real-secret")

    response = client.post("/protected")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "headers,params",
    [
        ({"Authorization": "Bearer wrong-secret"}, {}),
        ({"Authorization": "Basic real-secret"}, {}),
        ({"Authorization": "Bearer"}, {}),
        ({}, {"whoop_tools_token": "wrong-secret"}),
    ],
)
def test_rejects_invalid_credentials(client, monkeypatch, headers, params):
    monkeypatch.setenv("WHOOP_TOOLS_SECRET", "real-secret")

    response = client.post("/protected", headers=headers, params=params)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing Whoop tools credentials"


def test_accepts_valid_bearer_token(client, monkeypatch):
    monkeypatch.setenv("WHOOP_TOOLS_SECRET", "real-secret")

    response = client.post(
        "/protected",
        headers={"Authorization": "Bearer real-secret"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_accepts_valid_query_token(client, monkeypatch):
    monkeypatch.setenv("WHOOP_TOOLS_SECRET", "real-secret")

    response = client.post(
        "/protected",
        params={"whoop_tools_token": "real-secret"},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_bearer_token_takes_precedence_over_query_token(client, monkeypatch):
    monkeypatch.setenv("WHOOP_TOOLS_SECRET", "real-secret")

    response = client.post(
        "/protected",
        headers={"Authorization": "Bearer wrong-secret"},
        params={"whoop_tools_token": "real-secret"},
    )

    assert response.status_code == 401
