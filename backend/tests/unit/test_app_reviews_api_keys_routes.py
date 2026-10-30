"""Router-level coverage for GET /v1/apps/{app_id}/reviews and GET /v1/apps/{app_id}/keys.

The deserializer tests in `test_app_reviews_api_keys_resilient_deserialization.py`
exercise `deserialize_many_safe` directly; these tests go through the FastAPI routes
so a regression in the router wiring (e.g. returning the raw cache/DB payload again)
would surface as the original HTTP 500 instead of passing silently.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.app import AppReview
from routers import apps as apps_router
from utils.other import endpoints as auth

UID = "uid-app-owner"
APP_ID = "app-123"

VALID_REVIEW = {
    "uid": "user_123",
    "rated_at": "2026-10-01T12:00:00+00:00",
    "score": 4.5,
    "review": "Great application!",
    "username": "Alice",
    "response": "Thank you!",
    "responded_at": "2026-10-01T13:00:00+00:00",
}


def _client(monkeypatch) -> TestClient:
    monkeypatch.setattr(auth, "_enforce_rate_limit", lambda *args, **kwargs: None)
    app = FastAPI()
    app.include_router(apps_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: UID
    # A malformed record that slipped through would surface as a 500, not a re-raise.
    return TestClient(app, raise_server_exceptions=False)


def test_reviews_route_skips_malformed_cached_reviews(monkeypatch):
    cached = {
        "user_123": VALID_REVIEW,
        "u2": {"uid": "u2", "score": "not-a-number", "review": "Broken score"},
        "u3": "not_a_dict",
        "u4": {"uid": "u4", "rated_at": "2026-10-02T09:00:00Z", "score": 5.0, "review": "Awesome"},
        "u5": {"uid": "u5", "rated_at": "2026-10-02T09:00:00Z", "score": 3.0, "review": ""},
    }
    monkeypatch.setattr(apps_router, "get_app_reviews", lambda app_id: cached)

    response = _client(monkeypatch).get(f"/v1/apps/{APP_ID}/reviews")

    assert response.status_code == 200
    assert [review["uid"] for review in response.json()] == ["user_123", "u4"]


def test_reviews_route_returns_empty_list_for_no_reviews(monkeypatch):
    monkeypatch.setattr(apps_router, "get_app_reviews", lambda app_id: {})

    response = _client(monkeypatch).get(f"/v1/apps/{APP_ID}/reviews")

    assert response.status_code == 200
    assert response.json() == []


def test_api_keys_route_skips_malformed_key_documents(monkeypatch):
    monkeypatch.setattr(apps_router, "get_available_app_by_id", lambda app_id, uid: {"id": app_id, "uid": UID})
    monkeypatch.setattr(
        apps_router,
        "list_api_keys_db",
        lambda app_id: [
            {"id": "k1", "label": "Valid Key", "created_at": datetime(2026, 10, 1, tzinfo=timezone.utc)},
            {"invalid": "missing id entirely"},
            {"id": "k2"},
        ],
    )

    response = _client(monkeypatch).get(f"/v1/apps/{APP_ID}/keys")

    assert response.status_code == 200
    body = response.json()
    assert [key["id"] for key in body] == ["k1", "k2"]
    assert body[1]["label"] == "API Key"


def test_api_keys_route_still_rejects_non_owner(monkeypatch):
    monkeypatch.setattr(
        apps_router, "get_available_app_by_id", lambda app_id, uid: {"id": app_id, "uid": "someone-else"}
    )
    monkeypatch.setattr(apps_router, "list_api_keys_db", lambda app_id: [{"id": "k1", "label": "Key"}])

    response = _client(monkeypatch).get(f"/v1/apps/{APP_ID}/keys")

    assert response.status_code == 403


def test_skipped_review_warning_does_not_log_user_content(caplog):
    sensitive = {"uid": "u9", "score": "not-a-number", "review": "PRIVATE-REVIEW-TEXT", "username": "PRIVATE-NAME"}

    with caplog.at_level(logging.WARNING):
        parsed = AppReview.deserialize_many_safe({"u9": sensitive})

    assert parsed == []
    assert "u9" in caplog.text
    assert "PRIVATE-REVIEW-TEXT" not in caplog.text
    assert "PRIVATE-NAME" not in caplog.text
