"""Unit tests for google_calendar router exception sanitization.

Verifies that internal exceptions, Google Calendar API provider errors, and raw
connection details in list_google_calendar_events and get_calendar_capture_gaps
are masked and not leaked in HTTP 500 response bodies.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from fastapi import HTTPException
import pytest

from routers import google_calendar as gc_routes


@pytest.mark.asyncio
async def test_get_events_masks_provider_error_detail(monkeypatch):
    """Ensure list_google_calendar_events raises generic 500 without internal socket details."""
    monkeypatch.setattr(gc_routes, "run_blocking", AsyncMock(return_value=("fake-token", {})))
    monkeypatch.setattr(
        gc_routes,
        "get_google_calendar_events",
        AsyncMock(
            side_effect=RuntimeError(
                "HTTPSConnectionPool(host='www.googleapis.com'): Max retries exceeded with url /calendar/v3/calendars/primary/events?access_token=ya29.a0AfH6_SECRET"
            )
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await gc_routes.list_google_calendar_events(
            time_min=datetime(2026, 1, 1, tzinfo=timezone.utc),
            time_max=datetime(2026, 1, 2, tzinfo=timezone.utc),
            uid="test-user-123",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to fetch calendar events from provider."
    assert "googleapis.com" not in exc_info.value.detail
    assert "ya29" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_events_masks_retry_error_detail(monkeypatch):
    """Ensure retry failure after token refresh raises sanitized 500."""
    monkeypatch.setattr(gc_routes, "run_blocking", AsyncMock(return_value=("expired-token", {})))
    monkeypatch.setattr(gc_routes, "refresh_google_token", AsyncMock(return_value="new-token"))

    first_call = True

    async def mock_get_events(*args, **kwargs):
        nonlocal first_call
        if first_call:
            first_call = False
            raise RuntimeError("Authentication failed: error 401 invalid_token")
        raise RuntimeError("Internal Google SSL failure: certificate verify failed [Errno 1] on backend host")

    monkeypatch.setattr(gc_routes, "get_google_calendar_events", mock_get_events)

    with pytest.raises(HTTPException) as exc_info:
        await gc_routes.list_google_calendar_events(
            time_min=datetime(2026, 1, 1, tzinfo=timezone.utc),
            time_max=datetime(2026, 1, 2, tzinfo=timezone.utc),
            uid="test-user-123",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to fetch calendar events after token refresh."
    assert "certificate verify failed" not in exc_info.value.detail
    assert "Errno" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_capture_gaps_masks_provider_error_detail(monkeypatch):
    """Ensure get_calendar_capture_gaps raises generic 500 without internal provider error."""
    monkeypatch.setattr(gc_routes, "run_blocking", AsyncMock(return_value=("fake-token", {})))
    monkeypatch.setattr(
        gc_routes,
        "get_google_calendar_events",
        AsyncMock(side_effect=RuntimeError("Google DNS resolution failure for apis.google.internal:5000")),
    )

    with pytest.raises(HTTPException) as exc_info:
        await gc_routes.get_calendar_capture_gaps(
            start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end=datetime(2026, 1, 2, tzinfo=timezone.utc),
            uid="test-user-123",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to fetch calendar events from provider."
    assert "google.internal" not in exc_info.value.detail


@pytest.mark.asyncio
async def test_capture_gaps_masks_retry_error_detail(monkeypatch):
    """Ensure capture gaps retry failure after token refresh raises sanitized 500."""
    monkeypatch.setattr(gc_routes, "run_blocking", AsyncMock(return_value=("expired-token", {})))
    monkeypatch.setattr(gc_routes, "refresh_google_token", AsyncMock(return_value="new-token"))

    first_call = True

    async def mock_get_events(*args, **kwargs):
        nonlocal first_call
        if first_call:
            first_call = False
            raise RuntimeError("Authentication failed: error 401 token expired")
        raise RuntimeError("Google API Rate limit exceeded: quota project 918239123 exhausted")

    monkeypatch.setattr(gc_routes, "get_google_calendar_events", mock_get_events)

    with pytest.raises(HTTPException) as exc_info:
        await gc_routes.get_calendar_capture_gaps(
            start=datetime(2026, 1, 1, tzinfo=timezone.utc),
            end=datetime(2026, 1, 2, tzinfo=timezone.utc),
            uid="test-user-123",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to fetch calendar events after token refresh."
    assert "918239123" not in exc_info.value.detail
