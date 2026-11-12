"""
Google Calendar integration endpoints.

Provides endpoints for listing Google Calendar events for the event picker UI
and surfacing capture gaps (booked meetings with no recorded conversation).
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

import logging

logger = logging.getLogger(__name__)
import database.conversations as conversations_db
import database.users as users_db
from database import google_calendar_preferences
from utils.retrieval import google_calendar_selection, google_calendar_catalog_cache
from utils.retrieval.tools.google_utils import GoogleAPIError
from utils.conversations.calendar_linking import select_capture_gaps
from utils.conversations.calendar_utils import extract_attendees, parse_event_times
from utils.integration_telemetry import (
    GOOGLE_CALENDAR,
    IntegrationTelemetryContext,
    emit_sync_attempted,
    emit_sync_failed,
    emit_sync_succeeded,
)
from utils.executors import db_executor, run_blocking
from utils.other import endpoints as auth
from utils.retrieval.tools.calendar_tools import get_google_calendar_events
from utils.retrieval.tools.google_utils import refresh_google_token

router = APIRouter()


class ReadableCalendar(BaseModel):
    id: str
    name: str
    primary: bool
    available: bool


class CalendarSelection(BaseModel):
    account_id: str
    calendars: List[ReadableCalendar]
    selected_ids: List[str]
    write_calendar_id: str = 'primary'


class CalendarSelectionUpdate(BaseModel):
    account_id: str = Field(min_length=1, max_length=1024)
    selected_ids: List[Annotated[str, Field(min_length=1, max_length=1024)]] = Field(
        min_length=1, max_length=google_calendar_selection.MAX_SELECTED
    )


async def _selection_catalog(uid: str) -> dict[str, Any]:
    # Explicit refresh/save always revalidates live provider access. Hot event
    # reads use the short-lived metadata cache instead.
    google_calendar_catalog_cache.invalidate(uid)
    try:
        async with asyncio.timeout(20):
            return await _selection_catalog_with_refresh(uid)
    except TimeoutError:
        raise HTTPException(504, 'Calendar list timed out. Please try again.') from None


async def _selection_catalog_with_refresh(uid: str) -> dict[str, Any]:
    token, integration = await run_blocking(db_executor, _get_google_calendar_token, uid)
    try:
        return await google_calendar_selection.catalog(uid, token)
    except GoogleAPIError as error:
        if error.is_auth_error:
            token = await refresh_google_token(uid, integration)
            if token:
                try:
                    return await google_calendar_selection.catalog(uid, token)
                except Exception:
                    raise HTTPException(502, 'Calendar list unavailable. Please try again.') from None
            raise HTTPException(401, 'Google Calendar authentication expired. Please reconnect.') from None
        if error.is_permission_error:
            raise HTTPException(403, 'Google Calendar list access denied. Please reconnect.') from None
        raise HTTPException(502, 'Calendar list unavailable. Please try again.') from None
    except Exception:
        raise HTTPException(502, 'Calendar list unavailable. Please try again.') from None


@router.get('/v1/calendar/google/calendars', response_model=CalendarSelection, tags=['google_calendar'])
async def list_readable_google_calendars(
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'calendar:catalog', fail_closed=True)),
):
    return await _selection_catalog(uid)


@router.put('/v1/calendar/google/calendars', response_model=CalendarSelection, tags=['google_calendar'])
async def save_google_calendar_selection(
    request: CalendarSelectionUpdate,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, 'calendar:catalog', fail_closed=True)),
):
    current = await _selection_catalog(uid)
    if request.account_id != current['account_id']:
        raise HTTPException(409, 'Google account changed. Reload the calendar list before saving.')
    readable = {row['id'] for row in current['calendars'] if row['available']}
    ids = list(dict.fromkeys(request.selected_ids))
    retained = set(current['selected_ids'])
    if any(value not in readable and value not in retained for value in ids):
        raise HTTPException(409, 'A selected calendar is unavailable. Reload and choose readable calendars.')
    # Store canonical primary identity so a differently named Google account
    # never inherits this selection. Disconnect does not erase preferences.
    await run_blocking(db_executor, google_calendar_preferences.save_selection, uid, request.account_id, ids)
    google_calendar_catalog_cache.invalidate(uid)
    return {**current, 'selected_ids': ids}


class GoogleCalendarEvent(BaseModel):
    """Response model for a Google Calendar event."""

    event_id: str = Field(description="Google Calendar event ID")
    title: str = Field(description="Event title/summary")
    attendees: List[str] = Field(default=[], description="List of attendee display names")
    attendee_emails: List[str] = Field(default=[], description="List of attendee email addresses")
    start_time: datetime = Field(description="Event start time")
    end_time: datetime = Field(description="Event end time")
    html_link: Optional[str] = Field(default=None, description="Link to open event in Google Calendar")
    location: str = Field(default='', description="Event location")
    description: str = Field(default='', description="Event description, truncated for transport")
    all_day: bool = Field(default=False, description="True when the event has a date but no time")


class CalendarCaptureGap(BaseModel):
    """An accepted calendar event with no overlapping kept conversation."""

    event_id: str = Field(description="Google Calendar event ID")
    title: str = Field(description="Event title/summary")
    start_time: datetime = Field(description="Event start time")
    end_time: datetime = Field(description="Event end time")
    status: str = Field(default="confirmed", description="Calendar event status")
    coverage: str = Field(default="not_captured", description="Capture coverage verdict")


# The capture-gap window is bounded so one request cannot page a user's whole
# calendar history and decrypt an unbounded conversation range.
CAPTURE_GAPS_MAX_WINDOW = timedelta(days=31)
CAPTURE_GAPS_MAX_EVENTS = 250
CAPTURE_GAPS_MAX_CONVERSATIONS = 500
# A conversation started before the window can still cover an event inside it
# (an 8h event at the window edge); one day of pad is the honest bracket.
CAPTURE_GAPS_CONVERSATION_PAD = timedelta(hours=24)


def _get_google_calendar_token(uid: str) -> tuple[str, Dict[str, Any]]:
    """Get and validate Google Calendar access token for a user.

    Returns (access_token, integration_dict).
    Raises HTTPException if not connected or token missing.
    """
    integration = users_db.get_integration(uid, 'google_calendar')
    if not integration or not integration.get('connected'):
        raise HTTPException(status_code=400, detail="Google Calendar not connected")
    access_token = integration.get('access_token')
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token found")
    return access_token, integration


def _event_to_response(event: Dict[str, Any]) -> Optional[GoogleCalendarEvent]:
    """Convert a raw Google Calendar event to our response model."""
    start_time, end_time = parse_event_times(event)
    if start_time is None or end_time is None:
        return None

    attendee_names, attendee_emails = extract_attendees(event)

    start_raw = event.get('start') or {}
    all_day = isinstance(start_raw, dict) and 'date' in start_raw and 'dateTime' not in start_raw

    return GoogleCalendarEvent(
        event_id=event.get('id', ''),
        title=event.get('summary', 'Untitled Event'),
        attendees=attendee_names,
        attendee_emails=attendee_emails,
        start_time=start_time,
        end_time=end_time,
        html_link=event.get('htmlLink'),
        location=(event.get('location') or '')[:200],
        description=(event.get('description') or '')[:300],
        all_day=all_day,
    )


@router.get(
    "/v1/calendar/google/events",
    response_model=List[GoogleCalendarEvent],
    tags=['google_calendar'],
)
async def list_google_calendar_events(
    time_min: Optional[datetime] = Query(None, description="Minimum time for events (ISO format)"),
    time_max: Optional[datetime] = Query(None, description="Maximum time for events (ISO format)"),
    q: Optional[str] = Query(None, description="Search query to filter events"),
    # Ceiling raised from 100 for the desktop connector import, which reads a
    # year of history in one pass; Google's own list cap is 2500.
    max_results: int = Query(20, ge=1, le=500, description="Maximum number of events to return"),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
    x_app_version: Optional[str] = Header(None, alias='X-App-Version'),
    x_app_build: Optional[str] = Header(None, alias='X-App-Build'),
    uid: str = Depends(auth.get_current_user_uid),
):
    """List Google Calendar events within a time range.

    Used by the event picker UI when manually linking a conversation to a calendar event.
    """
    access_token, integration = await run_blocking(db_executor, _get_google_calendar_token, uid)
    telemetry_context = IntegrationTelemetryContext(
        integration_name=GOOGLE_CALENDAR,
        operation='fetch_events',
        uid=uid,
        app_platform=x_app_platform,
        app_version=x_app_version,
        app_build=x_app_build,
    )
    emit_sync_attempted(telemetry_context)

    if time_min and time_min.tzinfo is None:
        time_min = time_min.replace(tzinfo=timezone.utc)
    if time_max and time_max.tzinfo is None:
        time_max = time_max.replace(tzinfo=timezone.utc)

    try:
        events = await get_google_calendar_events(
            uid=uid,
            access_token=access_token,
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
            search_query=q,
        )
    except Exception as e:
        error_msg = str(e)
        if "error 401" in error_msg.lower() or "authentication failed" in error_msg.lower():
            new_token = await refresh_google_token(uid, integration)
            if new_token:
                try:
                    events = await get_google_calendar_events(
                        uid=uid,
                        access_token=new_token,
                        time_min=time_min,
                        time_max=time_max,
                        max_results=max_results,
                        search_query=q,
                    )
                except Exception as retry_error:
                    emit_sync_failed(telemetry_context, retry_error)
                    logger.error(f"Failed after token refresh: {retry_error}")
                    raise HTTPException(status_code=500, detail="Failed to fetch calendar events after token refresh.")
            else:
                emit_sync_failed(telemetry_context, e)
                raise HTTPException(status_code=401, detail="Google Calendar authentication expired. Please reconnect.")
        else:
            emit_sync_failed(telemetry_context, e)
            logger.error(f"Failed to fetch calendar events: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch calendar events from provider.")

    converted_events = [converted for event in events if (converted := _event_to_response(event))]
    emit_sync_succeeded(telemetry_context, item_count=len(converted_events))
    return converted_events


@router.get(
    "/v1/calendar/capture-gaps",
    response_model=List[CalendarCaptureGap],
    tags=['google_calendar'],
)
async def get_calendar_capture_gaps(
    start: datetime = Query(..., description="Window start (ISO format, inclusive)"),
    end: datetime = Query(..., description="Window end (ISO format, inclusive)"),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Accepted calendar events in [start, end] with no overlapping non-discarded conversation.

    The honesty surface for the Conversations list (SCA-381): what was booked
    but never recorded. Read-only against Google Calendar; it never creates or
    mutates conversations. Declined, cancelled, tentative, and all-day / >8h
    blocks are excluded by ``select_capture_gaps``.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if end <= start:
        raise HTTPException(status_code=400, detail="end must be after start")
    if end - start > CAPTURE_GAPS_MAX_WINDOW:
        raise HTTPException(status_code=400, detail=f"window too large (max {CAPTURE_GAPS_MAX_WINDOW.days} days)")

    access_token, integration = await run_blocking(db_executor, _get_google_calendar_token, uid)
    telemetry_context = IntegrationTelemetryContext(
        integration_name=GOOGLE_CALENDAR,
        operation='fetch_events_for_capture_gaps',
        uid=uid,
    )
    emit_sync_attempted(telemetry_context)
    try:
        events = await get_google_calendar_events(
            uid=uid,
            access_token=access_token,
            time_min=start,
            time_max=end,
            max_results=CAPTURE_GAPS_MAX_EVENTS,
        )
    except Exception as e:
        error_msg = str(e)
        if "error 401" in error_msg.lower() or "authentication failed" in error_msg.lower():
            new_token = await refresh_google_token(uid, integration)
            if new_token:
                try:
                    events = await get_google_calendar_events(
                        uid=uid,
                        access_token=new_token,
                        time_min=start,
                        time_max=end,
                        max_results=CAPTURE_GAPS_MAX_EVENTS,
                    )
                except Exception as retry_error:
                    emit_sync_failed(telemetry_context, retry_error)
                    logger.error(f"Failed after token refresh: {retry_error}")
                    raise HTTPException(status_code=500, detail="Failed to fetch calendar events after token refresh.")
            else:
                emit_sync_failed(telemetry_context, e)
                raise HTTPException(status_code=401, detail="Google Calendar authentication expired. Please reconnect.")
        else:
            emit_sync_failed(telemetry_context, e)
            logger.error(f"Failed to fetch calendar events: {e}")
            raise HTTPException(status_code=500, detail="Failed to fetch calendar events from provider.")

    # include_discarded=True keeps this a single-field Firestore range read
    # (no composite index); `select_capture_gaps` applies the discarded filter.
    conversations = await run_blocking(
        db_executor,
        conversations_db.get_conversations,
        uid,
        limit=CAPTURE_GAPS_MAX_CONVERSATIONS,
        include_discarded=True,
        start_date=start - CAPTURE_GAPS_CONVERSATION_PAD,
        end_date=end,
        date_field='started_at',
    )

    gaps = [CalendarCaptureGap(**row) for row in select_capture_gaps(events, conversations or [])]
    emit_sync_succeeded(telemetry_context, item_count=len(gaps))
    return gaps
