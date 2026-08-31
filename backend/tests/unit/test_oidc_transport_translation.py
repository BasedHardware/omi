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


# --- verify_token's own catch-all: a bug must not read as "refresh your token" (BACKLOG L13) ---


def _verify_env(monkeypatch):
    monkeypatch.setenv("OIDC_ISSUER", "http://keycloak:8080/realms/omi")
    monkeypatch.setenv("OIDC_JWKS_URL", "http://keycloak:8080/realms/omi/protocol/openid-connect/certs")
    monkeypatch.setenv("OIDC_AUDIENCE", "omi-backend")


def test_a_transport_failure_fetching_the_jwks_is_the_transient_class(monkeypatch):
    """What the broad catch was FOR, and it keeps working: no keys right now, ask again later."""
    import utils.auth.adapters.oidc as oidc_mod

    _verify_env(monkeypatch)

    def unreachable(*_a, **_k):
        raise OSError('connection refused')

    monkeypatch.setattr(oidc_mod, '_get_jwks_client', unreachable)

    with pytest.raises(errors.JWKSUnavailable):
        OIDCAuthProvider().verify_token('tok')


def test_a_programming_error_is_NOT_told_to_refresh(monkeypatch):
    """`except Exception -> JWKSUnavailable` mapped a TypeError to the retryable class, and the WS mapper
    turns that into close code 4001 "Token refresh required" — so a deterministic bug told the client to
    refresh, forever, while HTTP hid it behind the same 401 (BACKLOG L13).

    The Firebase adapter already fixed exactly this: an unknown failure becomes a plain AuthError, not a
    retryable one, with the reasoning written in `_translate`. This is that shape, on the OIDC side.
    """
    import utils.auth.adapters.oidc as oidc_mod

    from utils.other.endpoints import map_ws_auth_close

    _verify_env(monkeypatch)

    def bug(*_a, **_k):
        raise TypeError("unsupported operand type(s) — a real bug, not a network problem")

    monkeypatch.setattr(oidc_mod, '_get_jwks_client', bug)

    with pytest.raises(errors.AuthError) as raised:
        OIDCAuthProvider().verify_token('tok')

    assert not isinstance(raised.value, errors.JWKSUnavailable), 'a bug is not "keys unavailable"'
    assert not isinstance(raised.value, errors.ExpiredToken)
    assert not isinstance(raised.value, errors.InvalidToken), 'nor is it a bad token from the client'

    code, _reason = map_ws_auth_close(raised.value)
    assert code == 1008, 'the client must be told the request is invalid, not to refresh its token'


def test_an_unexpected_error_keeps_its_message(monkeypatch):
    """The operator needs the original text to recognise a bug; swallowing it would trade one silence for
    another."""
    import utils.auth.adapters.oidc as oidc_mod

    _verify_env(monkeypatch)
    monkeypatch.setattr(
        oidc_mod, '_get_jwks_client', lambda *_a, **_k: (_ for _ in ()).throw(AttributeError('no attribute zap'))
    )

    with pytest.raises(errors.AuthError, match='no attribute zap'):
        OIDCAuthProvider().verify_token('tok')
