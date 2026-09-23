"""Unit tests for users router notification endpoint exception sanitization.

Verifies that ValueError raised by notification_db is masked and does not leak
internal database schema, column constraints, or enum values in HTTP 400 responses.
"""

from unittest.mock import MagicMock
from fastapi import HTTPException
import pytest

from routers import users as users_routes


def test_update_daily_summary_settings_masks_value_error_detail(monkeypatch):
    """Ensure update_daily_summary_settings raises sanitized 400 without internal schema details."""
    mock_db = MagicMock()
    mock_db.set_daily_summary_hour_local.side_effect = ValueError(
        "Column 'hour' must be in range [0, 23]; got -5 (check: notification_hour_range)"
    )
    monkeypatch.setattr(users_routes, 'notification_db', mock_db)

    req = users_routes.DailySummarySettingsUpdate(hour=12)
    with pytest.raises(HTTPException) as exc_info:
        users_routes.update_daily_summary_settings(req, uid="test-uid-123")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid hour value. Must be between 0 and 23."
    assert "Column" not in exc_info.value.detail
    assert "notification_hour_range" not in exc_info.value.detail


def test_update_mentor_notification_settings_masks_value_error_detail(monkeypatch):
    """Ensure update_mentor_notification_settings raises sanitized 400 without internal enum values."""
    mock_db = MagicMock()
    mock_db.set_mentor_notification_frequency.side_effect = ValueError(
        "mentor_frequency must be in range [0, 5]; received: 99 (constraint: chk_mentor_freq)"
    )
    monkeypatch.setattr(users_routes, 'notification_db', mock_db)

    req = users_routes.MentorNotificationSettingsUpdate(frequency=3)
    with pytest.raises(HTTPException) as exc_info:
        users_routes.update_mentor_notification_settings(req, uid="test-uid-123")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid notification frequency value."
    assert "chk_mentor_freq" not in exc_info.value.detail
    assert "constraint" not in exc_info.value.detail
