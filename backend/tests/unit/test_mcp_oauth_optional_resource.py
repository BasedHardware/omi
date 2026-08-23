"""Regression tests: the MCP OAuth shim must accept requests without ``resource``.

RFC 8707 resource indicators are OPTIONAL for OAuth clients, and real connector
clients that talk to a single MCP resource server omit the parameter entirely —
claude.ai's custom-connector flow sends /authorize with only response_type,
client_id, redirect_uri, state, scope and PKCE, no ``resource``. The shim used
to declare ``resource`` as a required query/form/body field, so the very first
step of the claude.ai Connect flow died with a FastAPI 422
(``{"type": "missing", "loc": ["query", "resource"]}``) before OAuth logic ran.

External contract: https://datatracker.ietf.org/doc/html/rfc8707#section-2
("the resource parameter ... MAY be used") — at the authorization step an
omitted indicator binds the grant to the canonical MCP_RESOURCE_URL (the
audience the protected-resource metadata advertises); at the token endpoint an
omitted indicator keeps the audience already stored on the code / refresh-token
document (stored-audience matching lives in database.mcp_oauth and is covered
by test_mcp_oauth.py). Explicit values — an empty string included — are
validated exactly as before.

These tests exercise the real router through FastAPI's TestClient (conftest
sets the fake env vars needed for import).
"""

import base64
import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

CODE_VERIFIER = "regression-test-code-verifier-0123456789abcdefghijklmn"
CODE_CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(CODE_VERIFIER.encode("ascii")).digest()).decode("ascii").rstrip("=")
)
REDIRECT_URI = "https://claude.ai/api/mcp/auth_callback"
CLIENT_ID = "omi-claude-prod"


@pytest.fixture()
def mcp_sse():
    from routers import mcp_sse as module

    return module


@pytest.fixture()
def client(mcp_sse):
    app = FastAPI()
    app.include_router(mcp_sse.router)
    return TestClient(app)


@pytest.fixture()
def claude_client(mcp_sse, monkeypatch):
    registered = {
        "id": CLIENT_ID,
        "name": "Claude",
        "registration_mode": "claude_env",
        "allowed_redirect_uris": [REDIRECT_URI],
        "allowed_redirect_uri_prefixes": [],
        "allowed_resources": [mcp_sse.MCP_RESOURCE_URL],
        "allowed_scopes": list(mcp_sse.mcp_oauth_db.SUPPORTED_SCOPES),
        "token_endpoint_auth_method": "none",
        "client_secret_hash": "",
        "disabled_at": None,
    }
    monkeypatch.setattr(
        mcp_sse.mcp_oauth_db, "get_client", lambda client_id: registered if client_id == CLIENT_ID else None
    )
    return registered


def _authorize_params(**overrides):
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "state": "opaque-state",
        "code_challenge": CODE_CHALLENGE,
        "code_challenge_method": "S256",
    }
    params.update(overrides)
    return params


def test_authorize_get_without_resource_defaults_to_canonical_resource(client, mcp_sse, claude_client):
    """The claude.ai request shape (no resource) must render consent, not 422."""
    response = client.get("/authorize", params=_authorize_params())
    assert response.status_code == 200
    # The consent page round-trips oauth_params into the POST form, so the
    # defaulted canonical resource must be embedded for the consent step.
    assert mcp_sse.MCP_RESOURCE_URL in response.text


def test_authorize_get_with_explicit_resource_still_works(client, claude_client, mcp_sse):
    response = client.get("/authorize", params=_authorize_params(resource=mcp_sse.MCP_RESOURCE_URL))
    assert response.status_code == 200


def test_authorize_get_still_rejects_a_wrong_explicit_resource(client, claude_client):
    """Defaulting must not loosen validation of explicitly supplied values."""
    response = client.get("/authorize", params=_authorize_params(resource="https://evil.example/v1/mcp/sse"))
    body = response.json()
    assert body["error"] == "invalid_request"
    assert "resource" in body["error_description"].lower()


def test_authorize_get_still_rejects_an_empty_explicit_resource(client, claude_client):
    """Present-but-empty is an invalid explicit value, not an omission to default."""
    response = client.get("/authorize", params=_authorize_params(resource=""))
    body = response.json()
    assert body["error"] == "invalid_request"
    assert "resource" in body["error_description"].lower()


def test_consent_post_without_resource_grants_against_canonical_resource(client, mcp_sse, claude_client, monkeypatch):
    captured = {}

    def fake_verify_id_token(token):
        assert token == "firebase-token"
        return {"uid": "user-1"}

    def fake_create_grant(uid, client_id, redirect_uri, resource, scopes, code_challenge):
        captured["resource"] = resource
        return {"id": "grant-1"}, "auth-code-1"

    monkeypatch.setattr(mcp_sse.firebase_admin.auth, "verify_id_token", fake_verify_id_token)
    monkeypatch.setattr(mcp_sse.mcp_oauth_db, "create_grant_and_authorization_code_if_allowed", fake_create_grant)

    form = _authorize_params()
    form["firebase_id_token"] = "firebase-token"
    response = client.post("/authorize", data=form)
    assert response.status_code == 200
    assert captured["resource"] == mcp_sse.MCP_RESOURCE_URL
    assert "code=auth-code-1" in response.json()["redirect_uri"]


def test_token_code_exchange_without_resource_defers_to_stored_audience(client, mcp_sse, claude_client, monkeypatch):
    """An omitted resource must reach the exchange as None (RFC 8707: keep the
    audience stored on the code), not be rewritten to the server-canonical URL."""
    captured = {"resource": "sentinel-not-called"}

    def fake_exchange(code, client_id, redirect_uri, resource, code_verifier):
        captured["resource"] = resource
        return {
            "access_token": "at-1",
            "refresh_token": "rt-1",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "memories:read",
        }

    monkeypatch.setattr(mcp_sse.mcp_oauth_db, "verify_client_auth", lambda registered, secret: True)
    monkeypatch.setattr(mcp_sse.mcp_oauth_db, "exchange_authorization_code_for_tokens", fake_exchange)

    response = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": "auth-code-1",
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
        },
    )
    assert response.status_code == 200
    assert captured["resource"] is None
    assert response.json()["access_token"] == "at-1"


def test_token_refresh_without_resource_defers_to_stored_audience(client, mcp_sse, claude_client, monkeypatch):
    captured = {"resource": "sentinel-not-called"}

    def fake_rotate(refresh_token, client_id, resource, scope):
        captured["resource"] = resource
        return {
            "access_token": "at-2",
            "refresh_token": "rt-2",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "memories:read",
        }

    monkeypatch.setattr(mcp_sse.mcp_oauth_db, "verify_client_auth", lambda registered, secret: True)
    monkeypatch.setattr(mcp_sse.mcp_oauth_db, "rotate_refresh_token", fake_rotate)

    response = client.post(
        "/token",
        data={"grant_type": "refresh_token", "client_id": CLIENT_ID, "refresh_token": "rt-1"},
    )
    assert response.status_code == 200
    assert captured["resource"] is None


def test_token_still_rejects_a_wrong_explicit_resource(client, mcp_sse, claude_client, monkeypatch):
    """Explicit values keep failing validate_resource with invalid_target."""
    monkeypatch.setattr(mcp_sse.mcp_oauth_db, "verify_client_auth", lambda registered, secret: True)

    response = client.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": "auth-code-1",
            "redirect_uri": REDIRECT_URI,
            "code_verifier": CODE_VERIFIER,
            "resource": "https://evil.example/v1/mcp/sse",
        },
    )
    assert response.json()["error"] == "invalid_target"
