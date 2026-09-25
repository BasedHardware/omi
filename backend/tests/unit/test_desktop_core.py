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
    monkeypatch.setenv("OMI_DESKTOP_BACKEND_RELEASE_SHA", "a" * 40)
    monkeypatch.setenv("OMI_DESKTOP_BACKEND_RELEASE_CHANNEL", "development")

    client = make_client()
    expected = {
        "status": "healthy",
        "service": "omi-desktop-backend",
        "version": "0.1.0",
        "release_tag": "v1.2.3",
        "release_sha": "abc123",
        "release_channel": "stable",
        "backend_release_sha": "a" * 40,
        "backend_release_channel": "development",
        "chat_contract_version": "1",
        "runtime_implementation": "python",
    }

    assert client.get("/").json() == expected
    assert client.get("/health").json() == expected


def test_health_uses_shared_backend_release_sha_when_desktop_sha_is_absent(monkeypatch):
    monkeypatch.delenv("OMI_DESKTOP_BACKEND_RELEASE_SHA", raising=False)
    monkeypatch.setenv("OMI_BACKEND_RELEASE_SHA", "b" * 40)

    response = make_client().get("/health").json()

    assert response["backend_release_sha"] == "b" * 40


def test_health_reports_null_backend_release_sha_when_unset(monkeypatch):
    monkeypatch.delenv("OMI_DESKTOP_BACKEND_RELEASE_SHA", raising=False)
    monkeypatch.delenv("OMI_BACKEND_RELEASE_SHA", raising=False)

    response = make_client().get("/health").json()

    assert response["backend_release_sha"] is None
    assert response["status"] == "healthy"


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


def test_apple_domain_association_is_public():
    client = make_client()

    assert client.get("/.well-known/apple-developer-domain-association.txt").text == ""
