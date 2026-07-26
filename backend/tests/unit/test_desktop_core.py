import hashlib
import hmac
import json

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


def test_apple_domain_and_sentry_installation_are_public(monkeypatch):
    monkeypatch.setenv("SENTRY_WEBHOOK_SECRET", "secret")
    client = make_client()

    assert client.get("/.well-known/apple-developer-domain-association.txt").text == ""
    assert client.post("/v1/webhooks/sentry", headers={"sentry-hook-resource": "installation"}).json() == {
        "status": "ok"
    }


def test_sentry_webhook_fails_closed_and_creates_feedback_item(monkeypatch):
    monkeypatch.setenv("SENTRY_WEBHOOK_SECRET", "secret")
    monkeypatch.setenv("SENTRY_ADMIN_UID", "admin")
    created = []
    monkeypatch.setattr(desktop_core.action_items_db, "get_action_items", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        desktop_core.action_items_db,
        "create_action_item",
        lambda uid, data, key: created.append((uid, data, key)),
    )
    client = make_client()
    payload = {"action": "created", "data": {"issue": {"id": "42", "shortId": "O-42", "issueCategory": "feedback"}}}

    assert client.post("/v1/webhooks/sentry", json=payload).status_code == 401
    content = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(b"secret", content, hashlib.sha256).hexdigest()
    body = client.post(
        "/v1/webhooks/sentry",
        content=content,
        headers={"content-type": "application/json", "sentry-hook-signature": signature},
    )

    assert body.status_code == 200
    assert body.json() == {"status": "created"}
    assert created[0][0] == "admin"
    assert created[0][1]["metadata"]["sentry_issue_id"] == "42"


def test_sentry_poll_classifies_auth_failure(monkeypatch):
    class Response:
        is_success = False
        status_code = 403

    class Client:
        async def get(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setenv("SENTRY_ADMIN_UID", "admin")
    monkeypatch.setenv("SENTRY_AUTH_TOKEN", "token")
    monkeypatch.setattr(desktop_core, "get_webhook_client", Client)

    response = make_client().post("/v1/webhooks/sentry/poll")

    assert response.status_code == 200
    assert response.json() == {
        "status": "skipped",
        "reason": "sentry_auth_error",
        "sentry_status": 403,
        "created": 0,
        "skipped": 0,
        "total_fetched": 0,
    }
