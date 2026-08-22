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
    # The resource half now also has to be declared under a non-firebase backend, or the whole document
    # 501s rather than advertise upstream's endpoint (BACKLOG L48). This test is about the OTHER half, so
    # it declares it and keeps asserting exactly what it always did.
    monkeypatch.setenv("MCP_RESOURCE_URL", "https://omi.example/v1/mcp/sse")
    meta = oauth_protected_resource_metadata()
    assert meta["authorization_servers"] == ["https://idp.example/realms/omi"]


def test_protected_resource_uses_builtin_on_firebase(monkeypatch):
    monkeypatch.setenv("AUTH_BACKEND", "firebase")
    meta = oauth_protected_resource_metadata()
    assert meta["authorization_servers"] == [MCP_AUTHORIZATION_SERVER_URL]


def test_protected_resource_fails_when_oidc_issuer_missing(monkeypatch):
    # Under AUTH_BACKEND=oidc with OIDC_ISSUER unset, discovery must FAIL, not fall back to the Firebase-only
    # server (a dead endpoint) (cubic PR 10887 mcp_sse.py:743).
    monkeypatch.setenv("AUTH_BACKEND", "oidc")
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    with pytest.raises(HTTPException) as exc:
        oauth_protected_resource_metadata()
    assert exc.value.status_code == 501


def test_protected_resource_get_route_serves_rfc9728_metadata_not_bare_list(monkeypatch):
    # cubic PR 10887 mcp_sse.py:735: a prior refactor moved the GET decorators onto the
    # _protected_resource_authorization_servers helper (bare list), so GET /.well-known/oauth-protected-resource
    # returned ["https://issuer"] instead of the RFC 9728 object -> MCP OAuth discovery broke. The earlier
    # test called the FUNCTION, not the ROUTE, so it missed it. Assert the route table binds the path to
    # oauth_protected_resource_metadata AND that it yields the full RFC 9728 dict.
    from routers.mcp_sse import router

    endpoints = {
        r.path: r.endpoint
        for r in router.routes
        if getattr(r, "path", None) == "/.well-known/oauth-protected-resource" and "GET" in getattr(r, "methods", set())
    }
    assert endpoints.get("/.well-known/oauth-protected-resource") is oauth_protected_resource_metadata

    monkeypatch.setenv("AUTH_BACKEND", "firebase")
    body = oauth_protected_resource_metadata()
    assert isinstance(body, dict)  # NOT a bare list
    assert set(body) >= {"resource", "authorization_servers", "scopes_supported", "bearer_methods_supported"}
    assert isinstance(body["authorization_servers"], list)


def test_protected_resource_head_matches_get_availability_under_misconfig(monkeypatch):
    # HEAD probe must see the SAME availability as GET: 501 when OIDC discovery is misconfigured, not a
    # blanket 200 (cubic PR 10887 mcp_sse.py:745).
    from routers.mcp_sse import oauth_protected_resource_metadata_head

    monkeypatch.setenv("AUTH_BACKEND", "oidc")
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    # Same note as above: the resource half is declared so this test still isolates the ISSUER
    # misconfiguration it was written for (BACKLOG L48).
    monkeypatch.setenv("MCP_RESOURCE_URL", "https://omi.example/v1/mcp/sse")
    with pytest.raises(HTTPException) as exc:
        oauth_protected_resource_metadata_head()
    assert exc.value.status_code == 501
    # And when correctly configured, HEAD is 200 (same availability GET advertises).
    monkeypatch.setenv("OIDC_ISSUER", "https://idp.example/realms/omi")
    assert oauth_protected_resource_metadata_head().status_code == 200


def test_mcp_sse_info_omits_builtin_oauth_under_oidc(monkeypatch):
    # /v1/mcp/sse/info must not advertise the built-in oauth2 (authorize/token 501 under OIDC); only api_key
    # (cubic PR 10887 mcp_sse.py:1889).
    from types import SimpleNamespace
    from routers.mcp_sse import mcp_sse_info

    req = SimpleNamespace(base_url="https://api.example/")
    monkeypatch.setenv("AUTH_BACKEND", "oidc")
    info = mcp_sse_info(req)
    assert info["authentication"]["methods"] == ["api_key"]
    assert "oauth2" not in info["authentication"]

    monkeypatch.setenv("AUTH_BACKEND", "firebase")
    info_fb = mcp_sse_info(req)
    assert "oauth2" in info_fb["authentication"]
