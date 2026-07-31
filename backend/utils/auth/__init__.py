"""Neutral auth port (ADR-0034/0004): Firebase | OIDC behind one contract."""

from utils.auth.errors import (
    AuthError,
    ExpiredToken,
    InvalidToken,
    JWKSUnavailable,
    RevokedToken,
    Unsupported,
)
from utils.auth.factory import get_auth_provider, reset_auth_provider_for_tests
from utils.auth.ports import AuthProvider, Principal, UserProfile

__all__ = [
    "AuthProvider",
    "Principal",
    "UserProfile",
    "AuthError",
    "InvalidToken",
    "ExpiredToken",
    "RevokedToken",
    "JWKSUnavailable",
    "Unsupported",
    "get_auth_provider",
    "reset_auth_provider_for_tests",
]
