"""OIDC introspection + admin-API calls must translate httpx transport failures and non-JSON bodies into
the neutral errors taxonomy — they sit outside verify_token's translation block, so a raw httpx/JSON
exception would otherwise escape the auth port (cubic review PR 10887, oidc.py:150/186)."""

import httpx
import pytest

from utils.auth import errors
from utils.auth.adapters.oidc import OIDCAuthProvider


def _admin_env(monkeypatch):
    monkeypatch.setenv("OIDC_ISSUER", "http://keycloak:8080/realms/omi")
    monkeypatch.setenv("OIDC_ADMIN_API_URL", "http://keycloak:8080/admin/realms/omi")
    monkeypatch.setenv("OIDC_ADMIN_TOKEN_URL", "http://keycloak:8080/realms/omi/protocol/openid-connect/token")
    monkeypatch.setenv("OIDC_ADMIN_CLIENT_ID", "omi-backend-admin")
    monkeypatch.setenv("OIDC_ADMIN_CLIENT_SECRET", "s")


def test_introspection_transport_failure_is_neutral(monkeypatch):
    _admin_env(monkeypatch)
    monkeypatch.setattr(httpx, "post", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("down")))
    with pytest.raises(errors.AuthError):  # JWKSUnavailable is an AuthError subclass
        OIDCAuthProvider()._introspect_active("tok")


def test_admin_token_transport_failure_is_neutral(monkeypatch):
    _admin_env(monkeypatch)

    def boom(*a, **k):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(errors.AuthError):
        OIDCAuthProvider()._admin_token()


def test_get_user_profile_non_json_body_is_neutral(monkeypatch):
    _admin_env(monkeypatch)

    class _Resp:
        status_code = 200

        def json(self):
            raise ValueError("not json")

    # admin token ok, but the user GET returns a 200 non-JSON body
    monkeypatch.setattr(OIDCAuthProvider, "_admin_token", lambda self: "t")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp())
    with pytest.raises(errors.AuthError):
        OIDCAuthProvider().get_user_profile("u1")
