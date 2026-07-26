import redis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import desktop_core
from utils.other.endpoints import get_current_user_uid


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(desktop_core.router)
    app.dependency_overrides[get_current_user_uid] = lambda: "user-1"
    return TestClient(app)


def test_health_and_root_preserve_release_identity(monkeypatch):
    monkeypatch.setenv("OMI_DESKTOP_RELEASE_TAG", "v1.2.3")
    monkeypatch.setenv("OMI_DESKTOP_RELEASE_SHA", "abc123")
    monkeypatch.setenv("OMI_DESKTOP_RELEASE_CHANNEL", "stable")

    client = make_client()
    expected = {
        "status": "healthy",
        "service": "omi-desktop-backend",
        "version": "0.1.0",
        "release_tag": "v1.2.3",
        "release_sha": "abc123",
        "release_channel": "stable",
    }

    assert client.get("/").json() == expected
    assert client.get("/health").json() == expected


def test_ready_requires_configured_redis(monkeypatch):
    monkeypatch.delenv("REDIS_DB_HOST", raising=False)

    response = make_client().get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "service": "omi-desktop-backend",
        "redis": {"status": "not_configured", "failure_class": "not_configured"},
    }


def test_ready_reports_redis_ping(monkeypatch):
    monkeypatch.setenv("REDIS_DB_HOST", "redis")
    monkeypatch.setattr(desktop_core.redis_db.r, "ping", lambda: True)

    response = make_client().get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "service": "omi-desktop-backend",
        "redis": {"status": "ready"},
    }


def test_ready_bounds_redis_auth_failure(monkeypatch):
    monkeypatch.setenv("REDIS_DB_HOST", "redis")

    def ping():
        raise redis.exceptions.AuthenticationError("credential detail")

    monkeypatch.setattr(desktop_core.redis_db.r, "ping", ping)

    response = make_client().get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "service": "omi-desktop-backend",
        "redis": {"status": "unavailable", "failure_class": "auth_config"},
    }


def test_api_keys_require_firebase_auth_and_omit_unset_values(monkeypatch):
    monkeypatch.setenv("FIREBASE_API_KEY", "firebase-key")
    monkeypatch.delenv("GOOGLE_CALENDAR_API_KEY", raising=False)
    monkeypatch.delenv("DESKTOP_LEGACY_ANTHROPIC_KEY", raising=False)

    app = FastAPI()
    app.include_router(desktop_core.router)
    client = TestClient(app)

    assert client.get("/v1/config/api-keys").status_code == 401

    app.dependency_overrides[get_current_user_uid] = lambda: "user-1"
    response = client.get("/v1/config/api-keys")

    assert response.status_code == 200
    assert response.json() == {"firebase_api_key": "firebase-key"}
