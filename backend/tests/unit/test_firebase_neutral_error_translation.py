"""The Firebase auth adapter must not leak backend-specific exceptions through the neutral auth port:
every SDK/transport call is wrapped into the ``errors`` taxonomy, like ``verify_token`` (cubic review
PR 10887, backend/utils/auth/adapters/firebase.py:74 + :119)."""

import httpx
import pytest

from utils.auth import errors
from utils.auth.adapters.firebase import FirebaseAuthProvider


class _RaisingAuth:
    def __init__(self, exc: Exception):
        self._exc = exc

    def get_user(self, uid):
        raise self._exc

    def update_user(self, uid, **kw):
        raise self._exc

    def delete_user(self, uid):
        raise self._exc

    def create_custom_token(self, uid):
        raise self._exc


def test_profile_delete_and_custom_token_ops_translate_sdk_exceptions(monkeypatch):
    # A raw firebase_admin.auth exception (UserNotFoundError, a generic FirebaseError, ...) must surface
    # as a neutral errors.AuthError, not the backend class — otherwise callers on the neutral port catch
    # nothing portable (the same op raises OIDC/neutral errors on the oidc backend).
    monkeypatch.setattr("utils.auth.adapters.firebase._auth", lambda: _RaisingAuth(RuntimeError("sdk boom")))
    p = FirebaseAuthProvider()
    for call in (
        lambda: p.get_user_profile("u1"),
        lambda: p.update_user_profile("u1", display_name="x"),
        lambda: p.delete_user("u1"),
        lambda: p.mint_custom_token("u1"),
    ):
        with pytest.raises(errors.AuthError):
            call()


def test_exchange_idp_translates_httpx_transport_error(monkeypatch):
    # A httpx transport failure (connect/timeout/DNS) reaching the Identity Toolkit must become a neutral
    # AuthError, not a raw httpx exception that 500s the sign-in route.
    monkeypatch.setenv("FIREBASE_API_KEY", "test-key")

    def boom(*a, **k):
        raise httpx.ConnectError("cannot connect")

    monkeypatch.setattr(httpx, "post", boom)
    with pytest.raises(errors.AuthError):
        FirebaseAuthProvider().exchange_idp_credential("google", id_token="tok")
