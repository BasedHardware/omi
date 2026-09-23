"""Unit tests for oauth router Firebase ID token verification exception sanitization.

Verifies that InvalidIdTokenError and unexpected exceptions during token verification
in oauth_token do not leak internal verification details (cert fetch URLs, claim states,
certificate IDs) in HTTP 401 response bodies.
"""

from unittest.mock import AsyncMock
from fastapi import HTTPException
import firebase_admin.auth
import pytest

from routers import oauth as oauth_routes


@pytest.mark.asyncio
async def test_oauth_token_masks_invalid_id_token_error(monkeypatch):
    """Ensure InvalidIdTokenError details (timestamps, cert IDs) are not leaked in 401 response."""
    leak_text = "Firebase ID token has expired at timestamp 1700000000 (key_id=prod-cert-xyz-999)"

    async def mock_run_blocking(executor, func, *args, **kwargs):
        raise firebase_admin.auth.InvalidIdTokenError(leak_text)

    monkeypatch.setattr(oauth_routes, "run_blocking", mock_run_blocking)

    with pytest.raises(HTTPException) as exc_info:
        await oauth_routes.oauth_token(
            firebase_id_token="invalid.test.token",
            app_id="test-app-001",
            csrf_token="valid-csrf-token",
            oauth_csrf_cookie="valid-csrf-token",
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid Firebase ID token."
    assert "1700000000" not in exc_info.value.detail
    assert "prod-cert-xyz" not in exc_info.value.detail
    assert "key_id" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_oauth_token_masks_generic_verification_exception(monkeypatch):
    """Ensure generic verification failure details (internal connection strings) are masked in 401 response."""
    leak_text = "Failed to fetch public keys from https://www.googleapis.com/robot/v1/metadata/x509: [Errno 110] Connection timed out"

    async def mock_run_blocking(executor, func, *args, **kwargs):
        raise RuntimeError(leak_text)

    monkeypatch.setattr(oauth_routes, "run_blocking", mock_run_blocking)

    with pytest.raises(HTTPException) as exc_info:
        await oauth_routes.oauth_token(
            firebase_id_token="test.token",
            app_id="test-app-002",
            csrf_token="valid-csrf-token",
            oauth_csrf_cookie="valid-csrf-token",
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Error verifying Firebase ID token."
    assert "googleapis.com" not in exc_info.value.detail
    assert "Errno 110" not in exc_info.value.detail
    assert "Connection timed out" not in exc_info.value.detail
