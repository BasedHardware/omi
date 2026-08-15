"""The MCP /authorize consent flow is Firebase-only (loads the Firebase JS SDK, posts a
firebase_id_token) and must be gated off under non-Firebase backends, exactly like /v1/oauth/authorize
(cubic review PR 10887, review 4939247683). Under AUTH_BACKEND=oidc it must fail 501, not dead-end the
MCP OIDC flow on a page that can't work.

``auth_backend_name()`` reads AUTH_BACKEND at call time, so monkeypatch.setenv selects the backend.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from routers.mcp_sse import (
    MCP_AUTHORIZATION_SERVER_URL,
    _guard_firebase_authorize_backend,
    oauth_authorization_server_metadata,
    oauth_protected_resource_metadata,
)


def test_authorize_gated_501_on_oidc_backend(monkeypatch):
    monkeypatch.setenv("AUTH_BACKEND", "oidc")
    with pytest.raises(HTTPException) as exc:
        _guard_firebase_authorize_backend()
    assert exc.value.status_code == 501


def test_authorize_allowed_on_firebase_backend(monkeypatch):
    monkeypatch.setenv("AUTH_BACKEND", "firebase")
    _guard_firebase_authorize_backend()  # must not raise


def test_authorization_server_metadata_404_on_oidc(monkeypatch):
    # Discovery must be consistent with the /authorize guard: the built-in OAuth server is Firebase-only,
    # so under OIDC the well-known AS metadata 404s instead of advertising an authorization_endpoint that
    # then 501s (cubic PR 10887 mcp_sse.py:1584).
    monkeypatch.setenv("AUTH_BACKEND", "oidc")
    with pytest.raises(HTTPException) as exc:
        oauth_authorization_server_metadata()
    assert exc.value.status_code == 404


def test_protected_resource_points_at_oidc_issuer_on_oidc(monkeypatch):
    # Under OIDC the protected-resource metadata advertises the real IdP issuer, so a compliant MCP client
    # discovers the working authorization server, not the dead built-in one.
    monkeypatch.setenv("AUTH_BACKEND", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", "https://idp.example/realms/omi")
    meta = oauth_protected_resource_metadata()
    assert meta["authorization_servers"] == ["https://idp.example/realms/omi"]


def test_protected_resource_uses_builtin_on_firebase(monkeypatch):
    monkeypatch.setenv("AUTH_BACKEND", "firebase")
    meta = oauth_protected_resource_metadata()
    assert meta["authorization_servers"] == [MCP_AUTHORIZATION_SERVER_URL]
