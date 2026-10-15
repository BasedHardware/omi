"""Unit tests for conversations router calendar event linking exception sanitization.

Verifies that internal Google Calendar provider errors and retry exceptions
in link_calendar_event are masked and not leaked in HTTP 500 response bodies (CWE-209).
"""

from unittest.mock import AsyncMock
from fastapi import HTTPException
import pytest

from routers import conversations as conv_routes


@pytest.mark.asyncio
async def test_link_calendar_event_masks_provider_error(monkeypatch):
    """Ensure link_calendar_event raises generic 500 without leaking raw provider error."""
    monkeypatch.setattr(
        conv_routes, "_get_valid_conversation_by_id", lambda uid, conversation_id, **kw: {"id": conversation_id}
    )
    fake_integration = {"connected": True, "access_token": "valid_token"}
    monkeypatch.setattr(conv_routes.users_db, "get_integration", lambda uid, name: fake_integration)
    monkeypatch.setattr(
        conv_routes,
        "get_google_calendar_event",
        AsyncMock(
            side_effect=RuntimeError("Google Calendar API socket connection reset by peer on internal.gcp:8443")
        ),
    )

    req = conv_routes.LinkCalendarEventRequest(event_id="evt_test_123")
    with pytest.raises(HTTPException) as exc_info:
        await conv_routes.link_calendar_event(
            conversation_id="conv_123",
            request=req,
            uid="user_test_456",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to fetch calendar event from provider."
    assert "internal.gcp" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_link_calendar_event_masks_retry_error(monkeypatch):
    """Ensure link_calendar_event masks retry failure after token refresh."""
    monkeypatch.setattr(
        conv_routes, "_get_valid_conversation_by_id", lambda uid, conversation_id, **kw: {"id": conversation_id}
    )
    fake_integration = {"connected": True, "access_token": "expired_token"}
    monkeypatch.setattr(conv_routes.users_db, "get_integration", lambda uid, name: fake_integration)
    monkeypatch.setattr(conv_routes, "refresh_google_token", AsyncMock(return_value="new_token"))

    first_attempt = True

    async def mock_fetch_event(token, event_id):
        nonlocal first_attempt
        if first_attempt:
            first_attempt = False
            raise RuntimeError("Authentication failed: error 401 invalid_token")
        raise RuntimeError("Internal DB transaction timeout during oauth exchange in auth.googleapis.internal")

    monkeypatch.setattr(conv_routes, "get_google_calendar_event", mock_fetch_event)

    req = conv_routes.LinkCalendarEventRequest(event_id="evt_test_123")
    with pytest.raises(HTTPException) as exc_info:
        await conv_routes.link_calendar_event(
            conversation_id="conv_123",
            request=req,
            uid="user_test_456",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to fetch calendar event after token refresh."
    assert "auth.googleapis.internal" not in exc_info.value.detail

