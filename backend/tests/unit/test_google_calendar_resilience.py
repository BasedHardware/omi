"""Unit tests for Google Calendar token refresh and null summary resilience.

Verifies:
1. Google Calendar event summaries that are None, missing, or whitespace-only
   cleanly fallback to 'Untitled Event' without raising Pydantic validation errors (HTTP 500)
   or storing literal 'None' strings.
2. Missing access tokens when refresh_token exists automatically trigger token refresh
   instead of failing with HTTP 400.
3. Auth errors (GoogleAPIError 401, httpx 401, invalid_grant, authentication failed)
   trigger refresh_google_token and transparent retry.
4. Retry failures or fatal provider errors raise sanitized HTTP 500 without leaking credentials.
5. Calendar capture gaps and conversation link builders handle null event summaries defensively.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import httpx
import pytest
from fastapi import HTTPException

from routers.google_calendar import (
    _event_to_response,
    _get_google_calendar_token,
    _is_google_auth_error,
    _normalize_event_title,
    get_calendar_capture_gaps,
    list_google_calendar_events,
)
import routers.google_calendar as gc_routes
from utils.conversations.calendar_linking import select_capture_gaps
from utils.retrieval.tools.google_utils import GoogleAPIError

# ---------------------------------------------------------------------------
# Unit tests: _normalize_event_title
# ---------------------------------------------------------------------------


def test_normalize_event_title_handles_none_and_blanks():
    assert _normalize_event_title(None) == 'Untitled Event'
    assert _normalize_event_title('') == 'Untitled Event'
    assert _normalize_event_title('   ') == 'Untitled Event'
    assert _normalize_event_title('\t\n') == 'Untitled Event'
    assert _normalize_event_title(12345) == 'Untitled Event'


def test_normalize_event_title_preserves_and_trims_valid_titles():
    assert _normalize_event_title('Sprint Planning') == 'Sprint Planning'
    assert _normalize_event_title('  Sprint Planning  ') == 'Sprint Planning'


# ---------------------------------------------------------------------------
# Unit tests: _event_to_response
# ---------------------------------------------------------------------------


def test_event_to_response_null_summary_yields_untitled_event():
    event = {
        'id': 'evt-null-summary',
        'summary': None,
        'start': {'dateTime': '2026-10-01T10:00:00Z'},
        'end': {'dateTime': '2026-10-01T11:00:00Z'},
    }
    response = _event_to_response(event)
    assert response is not None
    assert response.title == 'Untitled Event'
    assert response.event_id == 'evt-null-summary'


def test_event_to_response_missing_summary_yields_untitled_event():
    event = {
        'id': 'evt-no-summary',
        'start': {'dateTime': '2026-10-01T10:00:00Z'},
        'end': {'dateTime': '2026-10-01T11:00:00Z'},
    }
    response = _event_to_response(event)
    assert response is not None
    assert response.title == 'Untitled Event'


def test_event_to_response_whitespace_summary_yields_untitled_event():
    event = {
        'id': 'evt-space-summary',
        'summary': '   ',
        'start': {'dateTime': '2026-10-01T10:00:00Z'},
        'end': {'dateTime': '2026-10-01T11:00:00Z'},
    }
    response = _event_to_response(event)
    assert response is not None
    assert response.title == 'Untitled Event'


def test_event_to_response_invalid_times_returns_none():
    event = {
        'id': 'evt-invalid',
        'summary': 'Broken event',
        'start': {},
        'end': {},
    }
    assert _event_to_response(event) is None


# ---------------------------------------------------------------------------
# Unit tests: _is_google_auth_error
# ---------------------------------------------------------------------------


def test_is_google_auth_error_recognizes_auth_failures():
    # GoogleAPIError 401
    assert _is_google_auth_error(GoogleAPIError(401, 'Unauthorized')) is True

    # GoogleAPIError invalid_grant
    assert _is_google_auth_error(GoogleAPIError(400, 'invalid_grant: Bad Request')) is True

    # httpx.HTTPStatusError 401
    req = httpx.Request('GET', 'https://www.googleapis.com/calendar/v3/calendars/primary/events')
    resp_401 = httpx.Response(401, request=req)
    assert _is_google_auth_error(httpx.HTTPStatusError('401 Unauthorized', request=req, response=resp_401)) is True

    # Substring matches in general Exceptions
    assert _is_google_auth_error(RuntimeError("Client error '401 Unauthorized' for url")) is True
    assert _is_google_auth_error(RuntimeError("authentication failed")) is True
    assert _is_google_auth_error(RuntimeError("invalid_grant token expired")) is True
    assert _is_google_auth_error(RuntimeError("token expired")) is True


def test_is_google_auth_error_rejects_non_auth_errors():
    assert _is_google_auth_error(GoogleAPIError(500, 'Internal Server Error')) is False
    assert _is_google_auth_error(GoogleAPIError(403, 'Forbidden quota exceeded')) is False

    req = httpx.Request('GET', 'https://www.googleapis.com/calendar/v3/calendars/primary/events')
    resp_500 = httpx.Response(500, request=req)
    assert _is_google_auth_error(httpx.HTTPStatusError('500 Server Error', request=req, response=resp_500)) is False

    assert _is_google_auth_error(RuntimeError("Connection timeout")) is False
    assert _is_google_auth_error(RuntimeError("DNS resolution failed")) is False


# ---------------------------------------------------------------------------
# Unit tests: _get_google_calendar_token fallback
# ---------------------------------------------------------------------------


def test_get_google_calendar_token_not_connected(monkeypatch):
    monkeypatch.setattr(gc_routes.users_db, 'get_integration', lambda uid, key: None)
    with pytest.raises(HTTPException) as exc_info:
        _get_google_calendar_token('test-uid')
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Google Calendar not connected"


def test_get_google_calendar_token_missing_token_without_refresh(monkeypatch):
    monkeypatch.setattr(
        gc_routes.users_db,
        'get_integration',
        lambda uid, key: {'connected': True, 'access_token': None, 'refresh_token': None},
    )
    with pytest.raises(HTTPException) as exc_info:
        _get_google_calendar_token('test-uid')
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "No access token found"


def test_get_google_calendar_token_missing_access_token_with_refresh_fallback(monkeypatch):
    integration = {'connected': True, 'access_token': None, 'refresh_token': 'valid-refresh-token'}
    monkeypatch.setattr(gc_routes.users_db, 'get_integration', lambda uid, key: integration)
    token, result_integration = _get_google_calendar_token('test-uid')
    assert token == ''
    assert result_integration == integration


def test_get_google_calendar_token_returns_existing_token(monkeypatch):
    integration = {'connected': True, 'access_token': 'existing-token', 'refresh_token': 'valid-refresh-token'}
    monkeypatch.setattr(gc_routes.users_db, 'get_integration', lambda uid, key: integration)
    token, result_integration = _get_google_calendar_token('test-uid')
    assert token == 'existing-token'
    assert result_integration == integration


# ---------------------------------------------------------------------------
# Route tests: list_google_calendar_events resilience
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_events_automatic_refresh_when_access_token_is_empty(monkeypatch):
    """When access_token is empty but refresh_token exists, refresh_google_token is called immediately."""
    integration = {'connected': True, 'access_token': None, 'refresh_token': 'valid-refresh-token'}
    monkeypatch.setattr(gc_routes, "run_blocking", AsyncMock(return_value=('', integration)))
    monkeypatch.setattr(gc_routes, "refresh_google_token", AsyncMock(return_value="new-access-token"))

    mock_get_events = AsyncMock(
        return_value=[
            {
                'id': 'event-101',
                'summary': None,
                'start': {'dateTime': '2026-10-01T14:00:00Z'},
                'end': {'dateTime': '2026-10-01T15:00:00Z'},
            }
        ]
    )
    monkeypatch.setattr(gc_routes, "get_google_calendar_events", mock_get_events)

    events = await gc_routes.list_google_calendar_events(
        time_min=datetime(2026, 10, 1, tzinfo=timezone.utc),
        time_max=datetime(2026, 10, 2, tzinfo=timezone.utc),
        uid="user-123",
    )

    gc_routes.refresh_google_token.assert_awaited_once_with("user-123", integration)
    mock_get_events.assert_awaited_once()
    assert len(events) == 1
    assert events[0].event_id == 'event-101'
    assert events[0].title == 'Untitled Event'


@pytest.mark.asyncio
async def test_list_events_empty_token_refresh_failed_raises_401(monkeypatch):
    """When access_token is empty and refresh fails, raises 401."""
    integration = {'connected': True, 'access_token': None, 'refresh_token': 'expired-refresh-token'}
    monkeypatch.setattr(gc_routes, "run_blocking", AsyncMock(return_value=('', integration)))
    monkeypatch.setattr(gc_routes, "refresh_google_token", AsyncMock(return_value=None))

    with pytest.raises(HTTPException) as exc_info:
        await gc_routes.list_google_calendar_events(
            time_min=datetime(2026, 10, 1, tzinfo=timezone.utc),
            time_max=datetime(2026, 10, 2, tzinfo=timezone.utc),
            uid="user-123",
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Google Calendar authentication expired. Please reconnect."


@pytest.mark.asyncio
async def test_list_events_auth_error_triggers_refresh_and_retry(monkeypatch):
    """When get_google_calendar_events raises GoogleAPIError(401), it refreshes token and retries successfully."""
    integration = {'connected': True, 'access_token': 'expired-access-token', 'refresh_token': 'valid-refresh-token'}
    monkeypatch.setattr(gc_routes, "run_blocking", AsyncMock(return_value=('expired-access-token', integration)))
    monkeypatch.setattr(gc_routes, "refresh_google_token", AsyncMock(return_value="refreshed-token"))

    first_call = True

    async def mock_get_events(access_token, **kwargs):
        nonlocal first_call
        if first_call:
            first_call = False
            assert access_token == 'expired-access-token'
            raise GoogleAPIError(401, "Invalid Credentials")
        assert access_token == 'refreshed-token'
        return [
            {
                'id': 'event-retry',
                'summary': 'Recovered Meeting',
                'start': {'dateTime': '2026-10-01T16:00:00Z'},
                'end': {'dateTime': '2026-10-01T17:00:00Z'},
            }
        ]

    monkeypatch.setattr(gc_routes, "get_google_calendar_events", mock_get_events)

    events = await gc_routes.list_google_calendar_events(
        time_min=datetime(2026, 10, 1, tzinfo=timezone.utc),
        time_max=datetime(2026, 10, 2, tzinfo=timezone.utc),
        uid="user-123",
    )

    assert len(events) == 1
    assert events[0].title == 'Recovered Meeting'
    gc_routes.refresh_google_token.assert_awaited_once_with("user-123", integration)


# ---------------------------------------------------------------------------
# Route tests: get_calendar_capture_gaps resilience
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_capture_gaps_automatic_refresh_and_null_summary(monkeypatch):
    """When access_token is empty, refreshes token, fetches events, and safely parses null summary in gaps."""
    integration = {'connected': True, 'access_token': None, 'refresh_token': 'valid-refresh-token'}

    async def mock_run_blocking(_executor, fn, *args, **kwargs):
        if fn == gc_routes._get_google_calendar_token:
            return ('', integration)
        if fn == gc_routes.conversations_db.get_conversations:
            return []  # No conversations, so event is a capture gap
        return fn(*args, **kwargs)

    monkeypatch.setattr(gc_routes, "run_blocking", mock_run_blocking)
    monkeypatch.setattr(gc_routes, "refresh_google_token", AsyncMock(return_value="new-access-token"))

    mock_events = [
        {
            'id': 'gap-null-summary',
            'summary': None,
            'status': 'confirmed',
            'start': {'dateTime': '2026-10-01T10:00:00Z'},
            'end': {'dateTime': '2026-10-01T11:00:00Z'},
        }
    ]
    monkeypatch.setattr(gc_routes, "get_google_calendar_events", AsyncMock(return_value=mock_events))

    gaps = await gc_routes.get_calendar_capture_gaps(
        start=datetime(2026, 10, 1, tzinfo=timezone.utc),
        end=datetime(2026, 10, 2, tzinfo=timezone.utc),
        uid="user-123",
    )

    assert len(gaps) == 1
    assert gaps[0].event_id == 'gap-null-summary'
    assert gaps[0].title == 'Untitled Event'
    assert gaps[0].title != 'None'


@pytest.mark.asyncio
async def test_capture_gaps_auth_error_triggers_refresh(monkeypatch):
    """When get_google_calendar_events raises auth error during capture gaps, refreshes and retries."""
    integration = {'connected': True, 'access_token': 'stale-token', 'refresh_token': 'valid-refresh-token'}

    async def mock_run_blocking(_executor, fn, *args, **kwargs):
        if fn == gc_routes._get_google_calendar_token:
            return ('stale-token', integration)
        if fn == gc_routes.conversations_db.get_conversations:
            return []
        return fn(*args, **kwargs)

    monkeypatch.setattr(gc_routes, "run_blocking", mock_run_blocking)
    monkeypatch.setattr(gc_routes, "refresh_google_token", AsyncMock(return_value="refreshed-token"))

    first_call = True

    async def mock_get_events(access_token, **kwargs):
        nonlocal first_call
        if first_call:
            first_call = False
            raise GoogleAPIError(401, "Token expired")
        return [
            {
                'id': 'gap-recovered',
                'summary': 'Strategy Session',
                'status': 'confirmed',
                'start': {'dateTime': '2026-10-01T10:00:00Z'},
                'end': {'dateTime': '2026-10-01T11:00:00Z'},
            }
        ]

    monkeypatch.setattr(gc_routes, "get_google_calendar_events", mock_get_events)

    gaps = await gc_routes.get_calendar_capture_gaps(
        start=datetime(2026, 10, 1, tzinfo=timezone.utc),
        end=datetime(2026, 10, 2, tzinfo=timezone.utc),
        uid="user-123",
    )

    assert len(gaps) == 1
    assert gaps[0].title == 'Strategy Session'


# ---------------------------------------------------------------------------
# Unit tests: select_capture_gaps null summary resilience
# ---------------------------------------------------------------------------


def test_select_capture_gaps_null_and_blank_summary_yields_untitled_event():
    events = [
        {
            'id': 'gap-1',
            'summary': None,
            'status': 'confirmed',
            'start': {'dateTime': '2026-10-01T10:00:00Z'},
            'end': {'dateTime': '2026-10-01T11:00:00Z'},
        },
        {
            'id': 'gap-2',
            'summary': '   ',
            'status': 'confirmed',
            'start': {'dateTime': '2026-10-01T12:00:00Z'},
            'end': {'dateTime': '2026-10-01T13:00:00Z'},
        },
    ]
    rows = select_capture_gaps(events, [])
    assert len(rows) == 2
    assert rows[0]['title'] == 'Untitled Event'
    assert rows[0]['title'] != 'None'
    assert rows[1]['title'] == 'Untitled Event'
