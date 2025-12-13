"""
Calendar event linking for conversations.

This module provides functionality to detect and link conversations
to Google Calendar events when they overlap in time.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import database.users as users_db
from models.conversation import CalendarEventLink
from utils.retrieval.tools.calendar_tools import get_google_calendar_events
from utils.retrieval.tools.google_utils import refresh_google_token

# Minimum overlap duration in seconds to consider a match (5 minutes)
MIN_OVERLAP_SECONDS = 5 * 60

# Minimum overlap percentage of event duration to consider a match (50%)
MIN_OVERLAP_PERCENTAGE = 0.50


def get_overlapping_calendar_event(
    uid: str,
    conversation_start: datetime,
    conversation_end: datetime,
) -> Optional[CalendarEventLink]:
    """
    Find a Google Calendar event that overlaps with the conversation timeframe.

    Args:
        uid: User ID
        conversation_start: When the conversation started
        conversation_end: When the conversation ended

    Returns:
        CalendarEventLink if a matching event is found, None otherwise
    """
    # Check if user has Google Calendar connected
    integration = users_db.get_integration(uid, 'google_calendar')
    if not integration or not integration.get('connected'):
        return None

    access_token = integration.get('access_token')
    if not access_token:
        return None

    # Ensure datetimes are timezone-aware (UTC)
    if conversation_start.tzinfo is None:
        conversation_start = conversation_start.replace(tzinfo=timezone.utc)
    if conversation_end.tzinfo is None:
        conversation_end = conversation_end.replace(tzinfo=timezone.utc)

    # Expand search window slightly to catch events that might start/end near conversation
    search_start = conversation_start - timedelta(minutes=30)
    search_end = conversation_end + timedelta(minutes=30)

    try:
        events = get_google_calendar_events(
            access_token=access_token,
            time_min=search_start,
            time_max=search_end,
            max_results=20,
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
                        time_min=search_start,
                        time_max=search_end,
                        max_results=20,
                    )
                except Exception:
                    return None
            else:
                return None
        else:
            return None

    if not events:
        return None

    # Find the event with the most overlap
    best_match = None
    best_overlap_seconds = 0
    best_overlap_percentage = 0

    for event in events:
        event_start, event_end = _parse_event_times(event)
        if event_start is None or event_end is None:
            continue

        # Calculate overlap
        overlap_start = max(event_start, conversation_start)
        overlap_end = min(event_end, conversation_end)
        overlap_duration = (overlap_end - overlap_start).total_seconds()

        # Calculate event duration and overlap percentage
        event_duration = (event_end - event_start).total_seconds()
        overlap_percentage = overlap_duration / event_duration if event_duration > 0 else 0

        # Check if overlap meets criteria:
        # 1. At least 5 minutes overlap, OR
        # 2. At least 50% of the event duration (for shorter events)
        meets_time_criteria = overlap_duration >= MIN_OVERLAP_SECONDS
        meets_percentage_criteria = overlap_percentage >= MIN_OVERLAP_PERCENTAGE and overlap_duration > 0

        if (meets_time_criteria or meets_percentage_criteria) and overlap_duration > best_overlap_seconds:
            best_overlap_seconds = overlap_duration
            best_overlap_percentage = overlap_percentage
            best_match = event

    if best_match is None:
        return None

    # Extract event details
    event_start, event_end = _parse_event_times(best_match)
    attendee_names, attendee_emails = _extract_attendees(best_match)

    event_title = best_match.get('summary', 'Untitled Event')
    event_id = best_match.get('id', '')
    html_link = best_match.get('htmlLink')

    return CalendarEventLink(
        event_id=event_id,
        title=event_title,
        attendees=attendee_names,
        attendee_emails=attendee_emails,
        start_time=event_start,
        end_time=event_end,
        html_link=html_link,
    )


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
