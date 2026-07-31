"""Dual-backend contract test for the neutral auth port (WP3, ADR-0034/0004).

The SAME verification assertions run against the in-memory fake (always, hermetic) and the OIDC
adapter against a real provider (Keycloak) — the proof that ``utils.auth`` abstracts the backend: a
bearer token is validated to the same neutral Principal whichever ``AUTH_BACKEND`` is configured.

Firebase has no easy offline token-minting story, so the fake encodes the reference semantics and the
OIDC adapter (the on-prem target) is the real backend under test; ``firebase`` runs only when a
firebase emulator is wired (skipped otherwise). Live services (each skipped when its env is absent):
  * ``OIDC_ISSUER`` (+ ``OIDC_TEST_TOKEN_URL``/``OIDC_TEST_CLIENT_ID``/``OIDC_TEST_USERNAME``/
    ``OIDC_TEST_PASSWORD``) — a Keycloak realm with a direct-access-grants client + a user.
  * ``FIREBASE_AUTH_EMULATOR_HOST`` — a firebase auth emulator (optional).
The fake needs nothing and always runs. Not hermetic (oidc/firebase need live services); not run by
``backend/test.sh``.
"""

from __future__ import annotations

import os

import pytest

from utils.auth.errors import InvalidToken, Unsupported


def _mint_oidc_token() -> str:
    import httpx

    resp = httpx.post(
        os.environ["OIDC_TEST_TOKEN_URL"],
        data={
            "grant_type": "password",
            "client_id": os.environ["OIDC_TEST_CLIENT_ID"],
            "username": os.environ["OIDC_TEST_USERNAME"],
            "password": os.environ["OIDC_TEST_PASSWORD"],
        },
    )
    assert resp.status_code == 200, f"token mint failed: {resp.status_code} {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(params=["fake", "oidc", "firebase"])
def provider_token(request):
    """Yield ``(provider, valid_token, expected, backend)`` for each configured backend."""
    backend = request.param

    if backend == "fake":
        from tests.auth_fakes import FakeAuthProvider
        from utils.auth.ports import Principal, UserProfile

        provider = FakeAuthProvider().register("tok-abc", Principal(uid="u1", email="a@b.c", provider="test"))
        provider.register_profile(UserProfile(uid="u1", email="a@b.c", display_name="Ada"))
        return provider, "tok-abc", {"uid": "u1", "email": "a@b.c"}, backend

    if backend == "oidc":
        if not os.environ.get("OIDC_ISSUER") or not os.environ.get("OIDC_TEST_TOKEN_URL"):
            pytest.skip("OIDC_ISSUER / OIDC_TEST_* not set")
        import jwt as _jwt

        from utils.auth.adapters import oidc as oidc_mod

        token = _mint_oidc_token()
        claims = _jwt.decode(token, options={"verify_signature": False})  # expected values only
        oidc_mod.reset_jwks_cache_for_tests()
        return oidc_mod.OIDCAuthProvider(), token, {"uid": claims["sub"], "email": claims.get("email")}, backend

    if not os.environ.get("FIREBASE_AUTH_EMULATOR_HOST"):
        pytest.skip("FIREBASE_AUTH_EMULATOR_HOST not set")
    pytest.skip("firebase emulator token-minting not wired in this harness")


# --- the common verification contract -----------------------------------------


def test_verify_token_returns_principal(provider_token):
    provider, token, expected, _backend = provider_token
    principal = provider.verify_token(token)
    assert principal.uid == expected["uid"]
    if expected.get("email") is not None:
        assert principal.email == expected["email"]
    assert principal.is_anonymous is False  # neither the fake principal nor an OIDC user is anonymous


def test_verify_invalid_token_raises(provider_token):
    provider, _token, _expected, _backend = provider_token
    with pytest.raises(InvalidToken):
        provider.verify_token("not-a-valid-token")


def test_firebase_only_verbs_unsupported_on_oidc(provider_token):
    provider, _token, _expected, backend = provider_token
    if backend != "oidc":
        pytest.skip("Firebase-only verbs are supported on fake/firebase; OIDC must reject them")
    with pytest.raises(Unsupported):
        provider.mint_custom_token("u1")
    with pytest.raises(Unsupported):
        provider.exchange_idp_credential("google", "id-token")
