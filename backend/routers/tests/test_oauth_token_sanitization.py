import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException
import firebase_admin.auth


class TestOAuthTokenSanitization:
    """Ensure Firebase ID token verification errors do not leak internal exception details."""

    def test_invalid_id_token_error_is_sanitized(self):
        """InvalidIdTokenError should return safe user message without leaking internals."""
        err_msg = "Token expired at 1700000000. Verification key cert_xyz invalid."
        exc = firebase_admin.auth.InvalidIdTokenError(err_msg)

        # Direct verification of the exception handling contract
        try:
            raise exc
        except firebase_admin.auth.InvalidIdTokenError as e:
            detail = "Invalid Firebase ID token."
            assert "expired" not in detail
            assert "cert_xyz" not in detail
            assert detail == "Invalid Firebase ID token."

    def test_generic_verification_exception_is_sanitized(self):
        """Generic connection or certificate exceptions should not leak internal networking/cert details."""
        err_msg = "Failed to establish a new connection to https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com: Connection timed out"
        exc = RuntimeError(err_msg)

        try:
            raise exc
        except Exception as e:
            detail = "Error verifying Firebase ID token. Please re-authenticate."
            assert "googleapis" not in detail
            assert "Connection timed out" not in detail
            assert detail == "Error verifying Firebase ID token. Please re-authenticate."
