"""Neutral auth errors (ADR-0034).

The port raises these regardless of backend so callers never catch a Firebase ``InvalidIdTokenError``
or a PyJWT ``ExpiredSignatureError``. Adapters translate their backend's failure into these; the WS
close-code mapping (4001 refresh / 4004 relogin) and the HTTP 401s branch on THESE, not on SDK classes.
"""

from __future__ import annotations


class AuthError(RuntimeError):
    """Base class for auth failures surfaced through the port."""


class InvalidToken(AuthError):
    """The bearer token is malformed, has a bad signature, or fails audience/issuer checks."""


class ExpiredToken(AuthError):
    """The token was well-formed but has expired (client should refresh)."""


class RevokedToken(AuthError):
    """The token was explicitly revoked (client should re-login)."""


class JWKSUnavailable(AuthError):
    """The signing keys could not be fetched (transient; a retry may succeed)."""


class Unsupported(AuthError):
    """The verb is not supported by the configured backend (e.g. mint_custom_token on OIDC)."""


__all__ = ["AuthError", "InvalidToken", "ExpiredToken", "RevokedToken", "JWKSUnavailable", "Unsupported"]
