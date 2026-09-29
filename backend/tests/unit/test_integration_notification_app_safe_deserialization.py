"""Hermetic unit tests for safe App deserialization in integration and notification endpoints.

Verifies that malformed app documents return 404 (App not found) instead of crashing with HTTP 500 ValidationError.
"""

import os
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from routers import integration as integration_router
from routers import notifications as notifications_router


def test_integration_notification_malformed_app_raises_404(monkeypatch):
    monkeypatch.setattr(integration_router, "verify_api_key", lambda app_id, key: True)
    # Corrupt app doc: missing required fields
    monkeypatch.setattr(
        integration_router.apps_utils,
        "get_available_app_by_id",
        lambda app_id, uid: {"id": "bad_app"},
    )

    mock_request = MagicMock()
    with pytest.raises(HTTPException) as exc_info:
        integration_router.send_notification_via_integration(
            request=mock_request,
            app_id="bad_app",
            message="Test alert",
            uid="user_123",
            authorization="Bearer test-key",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "App not found"


def test_notifications_endpoint_malformed_app_raises_404(monkeypatch):
    monkeypatch.setattr(notifications_router, "verify_api_key", lambda app_id, key: True)
    monkeypatch.setattr(
        notifications_router,
        "get_available_app_by_id",
        lambda aid, uid: {"id": "bad_app"},
    )

    mock_request = MagicMock()
    data = {"aid": "bad_app", "uid": "user_123", "message": "Test alert"}

    with pytest.raises(HTTPException) as exc_info:
        notifications_router.send_app_notification_to_user(
            request=mock_request,
            data=data,
            authorization="Bearer test-key",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "App not found"
