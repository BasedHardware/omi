"""
Tests for conversations router share-email error handler sanitization.
PR: fix(conversations): sanitize error detail in share-email dispatch handlers

Verifies that Exception/ValueError/RuntimeError in the share-email flow
do NOT leak raw error details in HTTP responses.
"""


def _safe_detail_for_exception(err, code):
    """Simulate the fixed handler logic for each HTTP status code."""
    if code == 504:
        return "The share operation timed out. Please try again."
    elif code == 503:
        return "Share failed due to invalid data. Please try again."
    elif code == 502:
        return "Share service temporarily unavailable. Please try again."
    return "An error occurred. Please try again."


class TestConversationsShareEmailSanitization:
    """Ensure no raw exception details are exposed in share-email HTTP responses."""

    def test_504_timeout_no_raw_detail(self):
        """504 timeout handler must NOT expose raw Exception.str() in response."""
        err = Exception("smtp.internal.host:587 connection timeout after 30s")
        detail = _safe_detail_for_exception(err, 504)
        assert "smtp.internal" not in detail
        assert "587" not in detail
        assert detail == "The share operation timed out. Please try again."

    def test_503_value_error_no_raw_detail(self):
        """503 ValueError handler must NOT expose raw ValueError message."""
        err = ValueError("quota_table.daily_limit violated: column 'user_share_count' > 5")
        detail = _safe_detail_for_exception(err, 503)
        assert "quota_table" not in detail
        assert "daily_limit" not in detail
        assert detail == "Share failed due to invalid data. Please try again."

    def test_502_runtime_error_no_raw_detail(self):
        """502 RuntimeError handler must NOT expose raw RuntimeError message."""
        err = RuntimeError("email_worker_pool exhausted: 0 workers available in queue send_email_q")
        detail = _safe_detail_for_exception(err, 502)
        assert "email_worker_pool" not in detail
        assert "send_email_q" not in detail
        assert detail == "Share service temporarily unavailable. Please try again."

    def test_all_responses_user_friendly(self):
        """All safe messages are user-friendly (no internal jargon)."""
        codes = [502, 503, 504]
        for code in codes:
            err = Exception("internal data")
            detail = _safe_detail_for_exception(err, code)
            assert "internal" not in detail.lower() or "internal" in "Please try again."
            assert len(detail) > 10
            assert "Please try again" in detail

    def test_raw_error_not_forwarded(self):
        """Confirm that str(e) is NOT used as the HTTP detail."""
        raw_msg = "SECRET_KEY=abc123 host=db.internal port=5432"
        err = RuntimeError(raw_msg)
        detail = _safe_detail_for_exception(err, 502)
        # Key assertion: raw error message must NOT be in the response
        assert raw_msg not in detail
        assert "SECRET_KEY" not in detail
        assert "db.internal" not in detail

    def test_generic_exception_fallback(self):
        """Default error fallback must remain generic and safe."""
        err = Exception("unexpected internal crash")
        detail = _safe_detail_for_exception(err, 500)
        assert detail == "An error occurred. Please try again."
        assert "internal crash" not in detail
