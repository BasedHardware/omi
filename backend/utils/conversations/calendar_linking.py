"""
Calendar event linking for conversations.

Detects and links conversations to Google Calendar events when they overlap in time.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

import database.users as users_db
from models.conversation import CalendarEventLink
from utils.conversations.calendar_utils import extract_attendees, parse_event_times
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
    integration = users_db.get_integration(uid, 'google_calendar')
    if not integration or not integration.get('connected'):
        return None

    access_token = integration.get('access_token')
    if not access_token:
        return None

    if conversation_start.tzinfo is None:
        conversation_start = conversation_start.replace(tzinfo=timezone.utc)
    if conversation_end.tzinfo is None:
        conversation_end = conversation_end.replace(tzinfo=timezone.utc)

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

    best_match = None
    best_overlap_seconds = 0

    for event in events:
        event_start, event_end = parse_event_times(event)
        if event_start is None or event_end is None:
            continue

        overlap_start = max(event_start, conversation_start)
        overlap_end = min(event_end, conversation_end)
        overlap_duration = (overlap_end - overlap_start).total_seconds()

        event_duration = (event_end - event_start).total_seconds()
        overlap_percentage = overlap_duration / event_duration if event_duration > 0 else 0

        meets_time_criteria = overlap_duration >= MIN_OVERLAP_SECONDS
        meets_percentage_criteria = overlap_percentage >= MIN_OVERLAP_PERCENTAGE and overlap_duration > 0

        if (meets_time_criteria or meets_percentage_criteria) and overlap_duration > best_overlap_seconds:
            best_overlap_seconds = overlap_duration
            best_match = event

    if best_match is None:
        return None

    event_start, event_end = parse_event_times(best_match)
    attendee_names, attendee_emails = extract_attendees(best_match)

    return CalendarEventLink(
        event_id=best_match.get('id', ''),
        title=best_match.get('summary', 'Untitled Event'),
        attendees=attendee_names,
        attendee_emails=attendee_emails,
        start_time=event_start,
        end_time=event_end,
        html_link=best_match.get('htmlLink'),
    )
