"""Finding #3: the external-app OAuth authorize/token flow is Firebase-only and must be gated off on
non-Firebase auth backends instead of failing confusingly.

``/v1/oauth/authorize`` renders a hardwired FirebaseUI consent page (loads the Firebase JS SDK from the
gstatic CDN, mints a Firebase ID token client-side) and ``/v1/oauth/token`` verifies *that* token. Under
``AUTH_BACKEND=oidc`` there is no Firebase project and the selected OIDC provider would reject the
Firebase token against its issuer — surfacing as a misleading 401 (or a broken page that can't load the
CDN). On-prem OIDC brokers third-party apps at the provider (Auth-Code+PKCE), not through this page
(ADR-0034 §3), so the flow is gated with a clear 501 when the backend isn't Firebase.

Reuses the ``_loaded_oauth_router`` stubbing harness so the firebase/database/app fakes live in one place.
``auth_backend_name()`` reads ``AUTH_BACKEND`` at call time, so ``monkeypatch.setenv`` selects the backend
without reloading the module.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from tests.unit.test_oauth_token_async_boundaries import _loaded_oauth_router
from utils.auth import reset_auth_provider_for_tests


def test_authorize_gated_501_on_oidc_backend(monkeypatch):
    monkeypatch.setenv("AUTH_BACKEND", "oidc")
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):
        app = FastAPI()
        app.include_router(oauth.router)
        client = TestClient(app)
        resp = client.get("/v1/oauth/authorize", params={"app_id": "app-1"})
        assert resp.status_code == 501
        assert "Firebase auth backend" in resp.json()["detail"]


def test_token_gated_501_on_oidc_backend(monkeypatch):
    monkeypatch.setenv("AUTH_BACKEND", "oidc")
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(
                oauth.oauth_token(
                    firebase_id_token="firebase-token",
                    app_id="app-1",
                    state="opaque",
                    csrf_token="matching-csrf-token",
                    oauth_csrf_cookie="matching-csrf-token",
                )
            )
        assert exc.value.status_code == 501


def test_authorize_allowed_on_firebase_backend(monkeypatch):
    """The default Firebase backend keeps working — the gate must not regress the first-class path."""
    monkeypatch.setenv("AUTH_BACKEND", "firebase")
    reset_auth_provider_for_tests()
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):
        app = FastAPI()
        app.include_router(oauth.router)
        client = TestClient(app)
        resp = client.get("/v1/oauth/authorize", params={"app_id": "app-1"})
        assert resp.status_code == 200


def test_token_allowed_on_firebase_backend(monkeypatch):
    monkeypatch.setenv("AUTH_BACKEND", "firebase")
    reset_auth_provider_for_tests()
    with _loaded_oauth_router() as (oauth, _firebase_auth, _apps_db):
        result = asyncio.run(
            oauth.oauth_token(
                firebase_id_token="firebase-token",
                app_id="app-1",
                state="opaque",
                csrf_token="matching-csrf-token",
                oauth_csrf_cookie="matching-csrf-token",
            )
        )
        assert result["uid"] == "user-1"


def test_auth_backend_name_coerces_unknown_value_to_firebase(monkeypatch):
    """A typo in AUTH_BACKEND must coerce to the firebase default (logged), never raise — a mis-set
    gate must not take authentication down, and the gate must agree with get_auth_provider."""
    from utils.auth import factory as auth_factory

    monkeypatch.setenv("AUTH_BACKEND", "bogus-typo")
    assert auth_factory.auth_backend_name() == "firebase"


def test_auth_backend_name_blank_defaults_to_firebase(monkeypatch):
    from utils.auth import factory as auth_factory

    monkeypatch.setenv("AUTH_BACKEND", "   ")
    assert auth_factory.auth_backend_name() == "firebase"
