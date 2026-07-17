"""Unit tests for GET /v1/auth/me.

routers.identity imports cleanly, so the handler is tested directly (patch.object on the
get_user_from_uid seam), plus a TestClient case that verifies the response_model pins the
returned fields. No sys.modules mutation.
"""

import os

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key-not-real")

from unittest.mock import patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routers import identity as identity_router
from utils.other import endpoints as auth


def _user(**overrides):
    base = {
        "uid": "u1",
        "email": "a@b.com",
        "email_verified": True,
        "phone_number": None,
        "display_name": "Zed",
        "photo_url": None,
        "disabled": False,
    }
    base.update(overrides)
    return base


def test_returns_identity():
    user = _user()
    with patch.object(identity_router, "get_user_from_uid", return_value=user):
        resp = identity_router.get_my_identity(uid="u1")
    assert resp == user


def test_404_when_no_firebase_user():
    with patch.object(identity_router, "get_user_from_uid", return_value=None):
        with pytest.raises(HTTPException) as exc:
            identity_router.get_my_identity(uid="nope")
    assert exc.value.status_code == 404


def test_response_model_filters_extra_fields():
    app = FastAPI()
    app.include_router(identity_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: "u1"
    client = TestClient(app)
    # The helper returns an extra field; response_model must strip it from the API response.
    # Allow the rate limiter so this exercises the response shape, not the limit path.
    with patch.object(auth, "check_rate_limit", return_value=(True, 300, 0)), patch.object(
        identity_router, "get_user_from_uid", return_value=_user(secret_field="LEAK")
    ):
        r = client.get("/v1/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert "secret_field" not in body
    # Phone number and account-state flags are intentionally outside the exposed identity set.
    assert "phone_number" not in body
    assert "disabled" not in body
    assert body["uid"] == "u1"
    assert body["email"] == "a@b.com"
    assert body["email_verified"] is True


def test_rate_limited_request_returns_429_without_firebase_lookup():
    """/v1/auth/me is per-UID rate limited ("auth:me") because get_user_from_uid is a
    Firebase Admin lookup against an external, quota-metered service.

    Before the limit was wired the route reached the handler unconditionally; a denied
    rate-limit decision must now short-circuit with 429 before the external lookup runs.
    Patching the shared check_rate_limit to deny (shadow mode off) exercises enforcement.
    """
    app = FastAPI()
    app.include_router(identity_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: "u1"
    client = TestClient(app)
    with patch.object(auth, "check_rate_limit", return_value=(False, 0, 42)), patch.object(
        auth, "RATE_LIMIT_SHADOW", False
    ), patch.object(identity_router, "get_user_from_uid") as mock_get_user:
        r = client.get("/v1/auth/me")
    assert r.status_code == 429
    # The expensive Firebase Admin call must not run once the caller is over the limit.
    mock_get_user.assert_not_called()
