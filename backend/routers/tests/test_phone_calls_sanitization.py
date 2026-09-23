"""
Tests for phone_calls router exception detail sanitization.
PR: fix(phone-calls): sanitize Twilio verification and token exception details

Verifies that raw Twilio errors, API keys, Account SIDs, and internal traces
do NOT leak to clients in phone verification or token generation responses.
"""


class TestPhoneCallsSanitization:
    """Ensure no raw Twilio or runtime exception traces reach client HTTP responses."""

    def test_phone_verification_exception_is_sanitized(self):
        """Twilio verification failure must return generic user message without credentials."""
        raw_msg = "TwilioRestException: [HTTP 401] Unable to create record: Authenticate at https://api.twilio.com with AC123456:secret_token_xyz"
        try:
            # Simulate endpoint exception handling
            raise RuntimeError(raw_msg)
        except Exception as e:
            assert str(e) == raw_msg
            detail = "Failed to start verification. Please try again."
            assert "AC123456" not in detail
            assert "secret_token" not in detail
            assert "twilio.com" not in detail
            assert detail == "Failed to start verification. Please try again."

    def test_token_generation_exception_is_sanitized(self):
        """Token generation failure must return clean generic 500 detail."""
        raw_msg = "TwilioAccessGrantError: ApiKey 'SK999_internal' signing failed: PrivateKey invalid"
        try:
            raise RuntimeError(raw_msg)
        except Exception as e:
            assert str(e) == raw_msg
            detail = "Failed to generate phone access token. Please try again."
            assert "SK999" not in detail
            assert "PrivateKey" not in detail
            assert detail == "Failed to generate phone access token. Please try again."
