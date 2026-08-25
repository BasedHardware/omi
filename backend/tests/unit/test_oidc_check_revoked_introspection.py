"""cubic review 4909186286: the OIDC adapter accepted ``check_revoked=True`` but ignored it — a
silent no-op, so a revoked-but-unexpired JWT would pass a caller that asked for revocation checking
(the anonymous migrate-owner proof, routers/apps.py). A stateless JWT stays signature/exp-valid after a
server-side logout, so the only way to reflect revocation is RFC 7662 token introspection.

These tests cover the verify_token branch (mocking the JWKS/decode so no real token is needed) and the
_introspect_active helper (mocking httpx.post). Hermetic — no live Keycloak.
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import jwt as jwt_mod
import pytest

from utils.auth import errors
from utils.auth.adapters import oidc as oidc_mod
from utils.auth.adapters.oidc import OIDCAuthProvider


def _make_decodable(monkeypatch, claims: dict):
    # verify_token requires OIDC_AUDIENCE (fail-closed) + OIDC_ISSUER; then it needs a signing key and a
    # decoded payload. Stub the JWKS client and jwt.decode so no real signed token is required.
    monkeypatch.setenv("OIDC_AUDIENCE", "omi-backend")
    monkeypatch.setenv("OIDC_ISSUER", "http://keycloak:8080/realms/omi")
    monkeypatch.setattr(
        oidc_mod,
        "_get_jwks_client",
        lambda: SimpleNamespace(get_signing_key_from_jwt=lambda bearer: SimpleNamespace(key="signing-key")),
    )
    monkeypatch.setattr(jwt_mod, "decode", lambda *a, **k: dict(claims))


def test_check_revoked_true_rejects_inactive_token(monkeypatch):
    _make_decodable(monkeypatch, {"sub": "u1"})
    provider = OIDCAuthProvider()
    monkeypatch.setattr(provider, "_introspect_active", lambda token: False)  # revoked/inactive
    with pytest.raises(errors.RevokedToken):
        provider.verify_token("tok", check_revoked=True)


def test_check_revoked_true_accepts_active_token(monkeypatch):
    _make_decodable(monkeypatch, {"sub": "u1", "email": "e@x.com", "iss": "http://keycloak:8080/realms/omi"})
    provider = OIDCAuthProvider()
    monkeypatch.setattr(provider, "_introspect_active", lambda token: True)
    principal = provider.verify_token("tok", check_revoked=True)
    assert principal.uid == "u1"


def test_check_revoked_false_does_not_introspect(monkeypatch):
    _make_decodable(monkeypatch, {"sub": "u1"})
    provider = OIDCAuthProvider()
    calls = {"n": 0}

    def spy(token):
        calls["n"] += 1
        return True

    monkeypatch.setattr(provider, "_introspect_active", spy)
    provider.verify_token("tok", check_revoked=False)
    assert calls["n"] == 0  # introspection only when revocation is requested


def test_introspect_active_parses_flag_and_posts_token(monkeypatch):
    monkeypatch.setenv("OIDC_ISSUER", "http://keycloak:8080/realms/omi")
    monkeypatch.setenv("OIDC_ADMIN_CLIENT_ID", "omi-backend-admin")
    monkeypatch.setenv("OIDC_ADMIN_CLIENT_SECRET", "secret")
    captured: dict = {}

    def fake_post(url, data=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        return SimpleNamespace(status_code=200, json=lambda: {"active": True})

    monkeypatch.setattr(httpx, "post", fake_post)
    provider = OIDCAuthProvider()
    assert provider._introspect_active("tok") is True
    assert captured["url"].endswith("/protocol/openid-connect/token/introspect")
    assert captured["data"]["token"] == "tok"


def test_introspect_inactive_flag(monkeypatch):
    monkeypatch.setenv("OIDC_ISSUER", "http://keycloak:8080/realms/omi")
    monkeypatch.setenv("OIDC_ADMIN_CLIENT_ID", "omi-backend-admin")
    monkeypatch.setenv("OIDC_ADMIN_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, data=None, timeout=None: SimpleNamespace(status_code=200, json=lambda: {"active": False}),
    )
    assert OIDCAuthProvider()._introspect_active("tok") is False


def test_introspect_non_boolean_active_is_fail_closed(monkeypatch):
    # A non-compliant IdP returning the STRING "false" for `active` must NOT be read as active — bool("false")
    # is truthy, so only the literal boolean True counts (cubic PR 10887 oidc.py:181).
    monkeypatch.setenv("OIDC_ISSUER", "http://keycloak:8080/realms/omi")
    monkeypatch.setenv("OIDC_ADMIN_CLIENT_ID", "omi-backend-admin")
    monkeypatch.setenv("OIDC_ADMIN_CLIENT_SECRET", "secret")
    for bogus in ("false", "true", 1, 0, "active"):
        monkeypatch.setattr(
            httpx,
            "post",
            lambda url, data=None, timeout=None, _v=bogus: SimpleNamespace(
                status_code=200, json=lambda: {"active": _v}
            ),
        )
        assert OIDCAuthProvider()._introspect_active("tok") is False, f"non-bool active {bogus!r} must be inactive"


def test_introspect_non_object_json_raises_autherror(monkeypatch):
    # Valid JSON that is not an object (a list here) must surface as a neutral AuthError, not leak an
    # AttributeError from the later `.get("active")` through the auth port (cubic PR 10887 oidc.py:68).
    monkeypatch.setenv("OIDC_ISSUER", "http://keycloak:8080/realms/omi")
    monkeypatch.setenv("OIDC_ADMIN_CLIENT_ID", "omi-backend-admin")
    monkeypatch.setenv("OIDC_ADMIN_CLIENT_SECRET", "secret")
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, data=None, timeout=None: SimpleNamespace(status_code=200, json=lambda: ["not", "an", "object"]),
    )
    with pytest.raises(errors.AuthError):
        OIDCAuthProvider()._introspect_active("tok")


def test_introspect_missing_credentials_fails_closed(monkeypatch):
    monkeypatch.setenv("OIDC_ISSUER", "http://keycloak:8080/realms/omi")
    monkeypatch.delenv("OIDC_ADMIN_CLIENT_ID", raising=False)
    monkeypatch.delenv("OIDC_ADMIN_CLIENT_SECRET", raising=False)
    with pytest.raises(errors.AuthError):
        OIDCAuthProvider()._introspect_active("tok")
