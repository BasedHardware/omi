import asyncio
import types
import sys
from unittest.mock import Mock
import pytest
from fastapi import HTTPException

# Stub firebase_admin if not already present in the environment
if "firebase_admin" not in sys.modules:
    fb = types.ModuleType("firebase_admin")
    fb_auth = types.ModuleType("firebase_admin.auth")
    fb.auth = fb_auth
    sys.modules["firebase_admin"] = fb
    sys.modules["firebase_admin.auth"] = fb_auth

try:
    from routers.auth import (
        _bounded_provider_error,
        _OAUTH_ERROR_CODES,
        auth_callback_google,
        auth_callback_apple_post,
    )
except ImportError:
    from backend.routers.auth import (
        _bounded_provider_error,
        _OAUTH_ERROR_CODES,
        auth_callback_google,
        auth_callback_apple_post,
    )


def test_bounded_provider_error_valid_known_codes():
    for code in [
        "access_denied",
        "invalid_request",
        "unauthorized_client",
        "server_error",
    ]:
        assert _bounded_provider_error(code) == code
        assert _bounded_provider_error(f"  {code.upper()}  ") == code


def test_bounded_provider_error_malicious_input_sanitized():
    malicious_inputs = [
        "<script>alert(1)</script>",
        "' OR 1=1 --",
        "error\r\nInjected-Header: true",
        "unknown_error_code_with_arbitrary_details_12345",
        "A" * 500,
    ]
    for bad_input in malicious_inputs:
        result = _bounded_provider_error(bad_input)
        assert result == "provider_error_other"
        assert "<" not in result
        assert "'" not in result
        assert "\n" not in result


def test_bounded_provider_error_bounded_length():
    long_string = "a" * 1000
    res = _bounded_provider_error(long_string)
    assert len(res) <= 64


def test_auth_callback_google_error_sanitization():
    async def _test():
        mock_request = Mock()
        # Malicious XSS error parameter
        with pytest.raises(HTTPException) as exc_info:
            await auth_callback_google(
                request=mock_request,
                state="test_state_123",
                error="<script>alert('xss')</script>",
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Auth error: provider_error_other"
        assert "<script>" not in exc_info.value.detail

        # Standard known error code
        with pytest.raises(HTTPException) as exc_info_known:
            await auth_callback_google(
                request=mock_request,
                state="test_state_123",
                error="access_denied",
            )
        assert exc_info_known.value.status_code == 400
        assert exc_info_known.value.detail == "Auth error: access_denied"

    asyncio.run(_test())


def test_auth_callback_apple_post_error_sanitization():
    async def _test():
        mock_request = Mock()
        # Malicious injection error parameter
        with pytest.raises(HTTPException) as exc_info:
            await auth_callback_apple_post(
                request=mock_request,
                code="dummy_code",
                state="test_state_456",
                error="error_with_internal_details_leak_attempt",
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Auth error: provider_error_other"
        assert "leak" not in exc_info.value.detail

        # Standard known error code
        with pytest.raises(HTTPException) as exc_info_known:
            await auth_callback_apple_post(
                request=mock_request,
                code="dummy_code",
                state="test_state_456",
                error="invalid_request",
            )
        assert exc_info_known.value.status_code == 400
        assert exc_info_known.value.detail == "Auth error: invalid_request"

    asyncio.run(_test())
