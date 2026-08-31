"""OIDC verify_token: signing-algorithm allowlist (OIDC_SIGNING_ALGS) and correct error class for a
missing issuer (cubic review PR 10887, oidc.py:82 + :84). Real signatures + a mocked JWKS so jwt.decode
actually runs the algorithm check."""

from __future__ import annotations

import time
from functools import lru_cache
from types import SimpleNamespace

import jwt as jwt_mod
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from utils.auth import errors
from utils.auth.adapters import oidc as oidc_mod
from utils.auth.adapters.oidc import OIDCAuthProvider, _signing_algs

_ISSUER = "http://keycloak:8080/realms/omi"


# Generate the keys lazily (cached) so the RSA-2048 keygen cost is not paid at import/collection and
# dumped onto the first test's measured phase (backend/tests/README.md fast-unit budget) — cubic PR 10887.
@lru_cache(maxsize=1)
def _rsa():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@lru_cache(maxsize=1)
def _ec():
    return ec.generate_private_key(ec.SECP256R1())


def _claims(**over) -> dict:
    c = {"sub": "u1", "aud": "omi-backend", "iss": _ISSUER, "exp": int(time.time()) + 300}
    c.update(over)
    return c


def _mock_jwks(monkeypatch, public_key) -> None:
    monkeypatch.setattr(
        oidc_mod,
        "_get_jwks_client",
        lambda: SimpleNamespace(get_signing_key_from_jwt=lambda bearer: SimpleNamespace(key=public_key)),
    )


def test_signing_algs_default_and_override(monkeypatch):
    monkeypatch.delenv("OIDC_SIGNING_ALGS", raising=False)
    assert _signing_algs() == ["RS256"]
    monkeypatch.setenv("OIDC_SIGNING_ALGS", "ES256, PS256 ,")
    assert _signing_algs() == ["ES256", "PS256"]


def test_es256_token_accepted_when_configured(monkeypatch):
    monkeypatch.setenv("OIDC_AUDIENCE", "omi-backend")
    monkeypatch.setenv("OIDC_ISSUER", _ISSUER)
    monkeypatch.setenv("OIDC_SIGNING_ALGS", "ES256")
    _mock_jwks(monkeypatch, _ec().public_key())
    token = jwt_mod.encode(_claims(), _ec(), algorithm="ES256")
    assert OIDCAuthProvider().verify_token(token).uid == "u1"


def test_es256_token_rejected_under_default_rs256_only(monkeypatch):
    monkeypatch.setenv("OIDC_AUDIENCE", "omi-backend")
    monkeypatch.setenv("OIDC_ISSUER", _ISSUER)
    monkeypatch.delenv("OIDC_SIGNING_ALGS", raising=False)  # default RS256
    _mock_jwks(monkeypatch, _ec().public_key())
    token = jwt_mod.encode(_claims(), _ec(), algorithm="ES256")
    with pytest.raises(errors.InvalidToken):
        OIDCAuthProvider().verify_token(token)


@pytest.mark.slow  # first RSA-2048 keygen (~100-300ms) is charged to this test's measured phase, over the
# fast-unit 0.12s CPU budget even with the @lru_cache (which only helps AFTER the first call) — cubic 10887.
def test_missing_issuer_is_permanent_autherror_not_transient_jwks(monkeypatch):
    # A config error (OIDC_ISSUER unset) surfaces from _issuer() INSIDE the decode try; it must propagate
    # as a permanent AuthError, not be reclassified as JWKSUnavailable (transient/retryable).
    monkeypatch.setenv("OIDC_AUDIENCE", "omi-backend")
    monkeypatch.delenv("OIDC_ISSUER", raising=False)
    oidc_mod.reset_jwks_cache_for_tests()
    token = jwt_mod.encode(_claims(), _rsa(), algorithm="RS256")
    with pytest.raises(errors.AuthError) as ei:
        OIDCAuthProvider().verify_token(token)
    assert not isinstance(ei.value, errors.JWKSUnavailable)  # not the transient class
    assert "OIDC_ISSUER" in str(ei.value)
