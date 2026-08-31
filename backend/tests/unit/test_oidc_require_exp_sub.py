"""OIDC verify_token must REQUIRE exp + sub (cubic review PR 10887, review 4939247683).

PyJWT verifies `exp` only when it is PRESENT, so a token minted without `exp` would otherwise be
accepted as a never-expiring identity. And `sub` is the uid (read after decode) — a token without it
must fail closed as InvalidToken here, not raise KeyError -> 500 downstream. Uses a real RS256 signature
+ a mocked JWKS so `jwt.decode` (and its `require`) actually runs.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import jwt as jwt_mod
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from utils.auth import errors
from utils.auth.adapters import oidc as oidc_mod
from utils.auth.adapters.oidc import OIDCAuthProvider

_ISSUER = "http://keycloak:8080/realms/omi"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _sign(claims: dict) -> str:
    return jwt_mod.encode(claims, _KEY, algorithm="RS256")


def _provider(monkeypatch) -> OIDCAuthProvider:
    monkeypatch.setenv("OIDC_AUDIENCE", "omi-backend")
    monkeypatch.setenv("OIDC_ISSUER", _ISSUER)
    pub = _KEY.public_key()
    monkeypatch.setattr(
        oidc_mod,
        "_get_jwks_client",
        lambda: SimpleNamespace(get_signing_key_from_jwt=lambda bearer: SimpleNamespace(key=pub)),
    )
    return OIDCAuthProvider()


def _claims(**over) -> dict:
    c = {"sub": "u1", "aud": "omi-backend", "iss": _ISSUER, "exp": int(time.time()) + 300}
    c.update(over)
    return c


def test_valid_token_with_exp_and_sub_passes(monkeypatch):
    principal = _provider(monkeypatch).verify_token(_sign(_claims()))
    assert principal.uid == "u1"


def test_token_without_exp_is_rejected(monkeypatch):
    provider = _provider(monkeypatch)
    claims = _claims()
    del claims["exp"]
    with pytest.raises(errors.InvalidToken):  # never-expiring token must fail closed
        provider.verify_token(_sign(claims))


def test_token_without_sub_is_rejected_as_invalid_not_500(monkeypatch):
    provider = _provider(monkeypatch)
    claims = _claims()
    del claims["sub"]
    with pytest.raises(errors.InvalidToken):  # not a KeyError/500
        provider.verify_token(_sign(claims))


def test_expired_token_still_maps_to_expired(monkeypatch):
    provider = _provider(monkeypatch)
    with pytest.raises(errors.ExpiredToken):
        provider.verify_token(_sign(_claims(exp=int(time.time()) - 10)))
