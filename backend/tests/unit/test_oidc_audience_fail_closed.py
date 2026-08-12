"""OIDC audience validation is required (fail-closed): without OIDC_AUDIENCE the adapter must
reject rather than accept any issuer-signed token, closing cross-client token confusion
(cubic review PR 10887, backend/utils/auth/adapters/oidc.py)."""

import pytest

from utils.auth.adapters.oidc import OIDCAuthProvider
from utils.auth import errors


def test_verify_token_fails_closed_without_oidc_audience(monkeypatch):
    monkeypatch.delenv('OIDC_AUDIENCE', raising=False)
    # Rejected before any JWKS fetch — the missing audience is a fail-closed config error.
    with pytest.raises(errors.AuthError):
        OIDCAuthProvider().verify_token('any.jwt.token')


def test_verify_token_blank_audience_is_treated_as_unset(monkeypatch):
    monkeypatch.setenv('OIDC_AUDIENCE', '   ')
    with pytest.raises(errors.AuthError):
        OIDCAuthProvider().verify_token('any.jwt.token')
