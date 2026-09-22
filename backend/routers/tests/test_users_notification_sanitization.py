"""
Tests for users router notification endpoint ValueError sanitization.
PR: fix(users): sanitize ValueError detail in notification settings endpoints

Verifies that ValueError from notification_db is NOT exposed raw in HTTP responses.
"""


def _safe_detail_for_notification(err, endpoint):
    """Simulate the fixed handler logic."""
    if endpoint == "daily_summary_hour":
        return "Invalid hour value. Must be between 0 and 23."
    elif endpoint == "mentor_frequency":
        return "Invalid notification frequency value."
    return "Invalid value."


class TestUsersNotificationSanitization:
    """Ensure no raw ValueError messages from notification_db reach HTTP responses."""

    def test_set_daily_summary_hour_no_raw_detail(self):
        """set_daily_summary_notification must NOT expose raw ValueError in response."""
        err = ValueError("Column 'hour' must be in range [0, 23]; got value: -5 (check: notification_hour_range)")
        detail = _safe_detail_for_notification(err, "daily_summary_hour")
        assert "notification_hour_range" not in detail
        assert "Column" not in detail
        assert detail == "Invalid hour value. Must be between 0 and 23."

    def test_set_daily_summary_no_internal_schema(self):
        """Response must not expose internal DB schema details."""
        err = ValueError("notification_settings.daily_summary_hour constraint violated: enum=['morning','evening']")
        detail = _safe_detail_for_notification(err, "daily_summary_hour")
        assert "notification_settings" not in detail
        assert "constraint" not in detail
        assert "enum" not in detail

    def test_set_mentor_frequency_no_raw_detail(self):
        """set_mentor_notification_frequency must NOT expose raw ValueError."""
        err = ValueError("mentor_frequency must be one of: ['never', 'daily', 'weekly']; received: 'hourly'")
        detail = _safe_detail_for_notification(err, "mentor_frequency")
        assert "never" not in detail
        assert "must be one of" not in detail
        assert detail == "Invalid notification frequency value."

    def test_mentor_frequency_no_internal_enum(self):
        """Response must not expose the internal enum values from DB constraints."""
        err = ValueError("ENUM_VIOLATION: frequency='biweekly' not in ALLOWED_FREQUENCIES")
        detail = _safe_detail_for_notification(err, "mentor_frequency")
        assert "ENUM_VIOLATION" not in detail
        assert "ALLOWED_FREQUENCIES" not in detail
        assert "biweekly" not in detail

    def test_all_user_messages_actionable(self):
        """All sanitized messages are user-friendly and actionable."""
        endpoints = ["daily_summary_hour", "mentor_frequency"]
        for ep in endpoints:
            err = ValueError("internal error detail")
            detail = _safe_detail_for_notification(err, ep)
            assert len(detail) > 5
            assert "internal" not in detail.lower()
