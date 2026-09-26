import pytest
from backend.routers.auth import _bounded_provider_error, _OAUTH_ERROR_CODES


def test_bounded_provider_error_valid_known_codes():
    for code in ["access_denied", "invalid_request", "unauthorized_client", "server_error"]:
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
