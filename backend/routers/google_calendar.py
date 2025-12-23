"""
Google Calendar integration endpoints.

Provides endpoints for listing Google Calendar events for the event picker UI.
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import database.users as users_db
from models.conversation import CalendarEventLink
from utils.other import endpoints as auth
from utils.retrieval.tools.calendar_tools import get_google_calendar_events
from utils.retrieval.tools.google_utils import refresh_google_token


router = APIRouter()


class GoogleCalendarEvent(BaseModel):
    """Response model for a Google Calendar event."""

    event_id: str = Field(description="Google Calendar event ID")
    title: str = Field(description="Event title/summary")
    attendees: List[str] = Field(default=[], description="List of attendee display names")
    attendee_emails: List[str] = Field(default=[], description="List of attendee email addresses")
    start_time: datetime = Field(description="Event start time")
    end_time: datetime = Field(description="Event end time")
    html_link: Optional[str] = Field(default=None, description="Link to open event in Google Calendar")


def _extract_attendees(event: dict) -> tuple[list[str], list[str]]:
    """
    Extract attendee names and emails from a Google Calendar event.

    Returns:
        Tuple of (display_names, emails)
    """
    names = []
    emails = []
    for attendee in event.get('attendees', []):
        # Skip the organizer's own entry
        if attendee.get('self', False):
            continue

        email = attendee.get('email', '')
        # Prefer display name for UI, fall back to email
        name = attendee.get('displayName') or email

        if name:
            names.append(name)
        if email:
            emails.append(email)

    return names, emails


def _parse_event_times(event: dict) -> tuple[Optional[datetime], Optional[datetime]]:
    """
    Parse start and end times from a Google Calendar event.

    Returns:
        Tuple of (start_time, end_time) as timezone-aware datetimes, or (None, None) if parsing fails
    """
    start = event.get('start', {})
    end = event.get('end', {})

    try:
        # Handle dateTime (specific time) vs date (all-day event)
        if 'dateTime' in start:
            start_dt = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
        elif 'date' in start:
            # All-day event - use start of day
            start_dt = datetime.fromisoformat(start['date'] + 'T00:00:00+00:00')
        else:
            return None, None

        if 'dateTime' in end:
            end_dt = datetime.fromisoformat(end['dateTime'].replace('Z', '+00:00'))
        elif 'date' in end:
            # All-day event - use end of day
            end_dt = datetime.fromisoformat(end['date'] + 'T23:59:59+00:00')
        else:
            return None, None

        return start_dt, end_dt
    except (ValueError, KeyError):
        return None, None


def _event_to_response(event: dict) -> Optional[GoogleCalendarEvent]:
    """Convert a raw Google Calendar event to our response model."""
    start_time, end_time = _parse_event_times(event)
    if start_time is None or end_time is None:
        return None

    attendee_names, attendee_emails = _extract_attendees(event)

    return GoogleCalendarEvent(
        event_id=event.get('id', ''),
        title=event.get('summary', 'Untitled Event'),
        attendees=attendee_names,
        attendee_emails=attendee_emails,
        start_time=start_time,
        end_time=end_time,
        html_link=event.get('htmlLink'),
    )


def _get_google_calendar_token(uid: str) -> str:
    """
    Get and validate Google Calendar access token for a user.
    Raises HTTPException if not connected or token invalid.
    """
    integration = users_db.get_integration(uid, 'google_calendar')
    if not integration or not integration.get('connected'):
        raise HTTPException(status_code=400, detail="Google Calendar not connected")

    access_token = integration.get('access_token')
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token found")

    return access_token


@router.get(
    "/v1/calendar/google/events",
    response_model=List[GoogleCalendarEvent],
    tags=['google_calendar'],
)
def list_google_calendar_events(
    time_min: Optional[datetime] = Query(None, description="Minimum time for events (ISO format)"),
    time_max: Optional[datetime] = Query(None, description="Maximum time for events (ISO format)"),
    q: Optional[str] = Query(None, description="Search query to filter events"),
    max_results: int = Query(20, ge=1, le=100, description="Maximum number of events to return"),
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    List Google Calendar events within a time range.

    Used by the event picker UI when manually linking a conversation to a calendar event.
    """
    integration = users_db.get_integration(uid, 'google_calendar')
    if not integration or not integration.get('connected'):
        raise HTTPException(status_code=400, detail="Google Calendar not connected")

    access_token = integration.get('access_token')
    if not access_token:
        raise HTTPException(status_code=400, detail="No access token found")

    # Ensure datetimes are timezone-aware
    if time_min and time_min.tzinfo is None:
        time_min = time_min.replace(tzinfo=timezone.utc)
    if time_max and time_max.tzinfo is None:
        time_max = time_max.replace(tzinfo=timezone.utc)

    try:
        events = get_google_calendar_events(
            access_token=access_token,
            time_min=time_min,
            time_max=time_max,
            max_results=max_results,
            search_query=q,
        )
    except Exception as e:
        error_msg = str(e)
        # Try to refresh token if authentication failed
        if "Authentication failed" in error_msg or "401" in error_msg:
            new_token = refresh_google_token(uid, integration)
            if new_token:
                try:
                    events = get_google_calendar_events(
                        access_token=new_token,
                        time_min=time_min,
                        time_max=time_max,
                        max_results=max_results,
                        search_query=q,
                    )
                except Exception as retry_error:
                    raise HTTPException(status_code=500, detail=f"Failed after token refresh: {str(retry_error)}")
            else:
                raise HTTPException(status_code=401, detail="Google Calendar authentication expired. Please reconnect.")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to fetch calendar events: {error_msg}")

    # Convert to response model
    result = []
    for event in events:
        converted = _event_to_response(event)
        if converted:
            result.append(converted)

    return result
