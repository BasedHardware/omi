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
from utils.conversations.calendar_utils import extract_attendees, parse_event_times
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


def _get_google_calendar_token(uid: str) -> tuple[str, dict]:
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


def _event_to_response(event: dict) -> Optional[GoogleCalendarEvent]:
    """Convert a raw Google Calendar event to our response model."""
    start_time, end_time = parse_event_times(event)
    if start_time is None or end_time is None:
        return None

    attendee_names, attendee_emails = extract_attendees(event)

    return GoogleCalendarEvent(
        event_id=event.get('id', ''),
        title=event.get('summary', 'Untitled Event'),
        attendees=attendee_names,
        attendee_emails=attendee_emails,
        start_time=start_time,
        end_time=end_time,
        html_link=event.get('htmlLink'),
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
    max_results: int = Query(20, ge=1, le=100, description="Maximum number of events to return"),
    uid: str = Depends(auth.get_current_user_uid),
):
    """List Google Calendar events within a time range.

    Used by the event picker UI when manually linking a conversation to a calendar event.
    """
    access_token, integration = _get_google_calendar_token(uid)

    if time_min and time_min.tzinfo is None:
        time_min = time_min.replace(tzinfo=timezone.utc)
    if time_max and time_max.tzinfo is None:
        time_max = time_max.replace(tzinfo=timezone.utc)

    try:
        events = await get_google_calendar_events(
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

    return [converted for event in events if (converted := _event_to_response(event))]
