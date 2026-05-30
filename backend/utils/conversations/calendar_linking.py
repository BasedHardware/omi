"""
Calendar event linking for conversations.

Detects and links conversations to Google Calendar events when they overlap in time.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import database.users as users_db
from models.conversation import CalendarEventLink
from utils.conversations.calendar_utils import extract_attendees, parse_event_times
from utils.retrieval.tools.calendar_tools import (
    get_google_calendar_events,
    get_google_calendar_event,
    update_google_calendar_event,
)
from utils.retrieval.tools.google_utils import refresh_google_token

logger = logging.getLogger(__name__)

# Minimum overlap duration in seconds to consider a match (10 seconds)
MIN_OVERLAP_SECONDS = 10

# Minimum overlap percentage of event duration to consider a match (50%)
MIN_OVERLAP_PERCENTAGE = 0.50


async def get_overlapping_calendar_event(
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
        events = await get_google_calendar_events(
            access_token=access_token,
            time_min=search_start,
            time_max=search_end,
            max_results=20,
        )
    except Exception as e:
        error_msg = str(e)
        if "error 401" in error_msg.lower() or "authentication failed" in error_msg.lower():
            new_token = await refresh_google_token(uid, integration)
            if new_token:
                try:
                    events = await get_google_calendar_events(
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

    conversation_duration = (conversation_end - conversation_start).total_seconds()

    for event in events:
        event_start, event_end = parse_event_times(event)
        if event_start is None or event_end is None:
            continue

        overlap_start = max(event_start, conversation_start)
        overlap_end = min(event_end, conversation_end)
        overlap_duration = (overlap_end - overlap_start).total_seconds()

        if overlap_duration <= 0:
            continue

        event_duration = (event_end - event_start).total_seconds()
        overlap_pct_of_event = overlap_duration / event_duration if event_duration > 0 else 0
        overlap_pct_of_conversation = overlap_duration / conversation_duration if conversation_duration > 0 else 0

        # Must meet the absolute time threshold AND cover a meaningful portion
        # of either the event or the conversation — prevents a short recording
        # from spuriously linking to a multi-hour all-day block.
        meets_time_criteria = overlap_duration >= MIN_OVERLAP_SECONDS
        meets_percentage_criteria = (
            overlap_pct_of_event >= MIN_OVERLAP_PERCENTAGE or overlap_pct_of_conversation >= MIN_OVERLAP_PERCENTAGE
        )

        if meets_time_criteria and meets_percentage_criteria and overlap_duration > best_overlap_seconds:
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


async def write_conversation_link_to_calendar_event(
    uid: str,
    event_id: str,
    conversation_id: str,
) -> None:
    """
    Write the conversation link into the Google Calendar event description.

    Appends https://h.omi.me/conversations/<conversation_id> to the event description.
    Silently no-ops on any error — linking the conversation to the event is the primary
    action; failing to write the description link should not block the caller.
    """
    integration = users_db.get_integration(uid, 'google_calendar')
    if not integration or not integration.get('connected'):
        return

    access_token = integration.get('access_token')
    if not access_token:
        return

    conversation_link = f"https://h.omi.me/conversations/{conversation_id}"

    async def _write(token: str) -> None:
        existing = await get_google_calendar_event(token, event_id)
        current_description = existing.get('description', '') or ''
        if conversation_link in current_description:
            return
        new_description = f"{current_description}\n\n{conversation_link}" if current_description else conversation_link
        await update_google_calendar_event(access_token=token, event_id=event_id, description=new_description)

    try:
        await _write(access_token)
    except Exception as e:
        error_msg = str(e)
        if "error 401" in error_msg.lower() or "authentication failed" in error_msg.lower():
            new_token = await refresh_google_token(uid, integration)
            if new_token:
                try:
                    await _write(new_token)
                except Exception as retry_error:
                    logger.warning(
                        f"write_conversation_link_to_calendar_event failed after token refresh: {retry_error}"
                    )
        else:
            logger.warning(
                f"write_conversation_link_to_calendar_event failed for conversation {conversation_id}: {error_msg}"
            )
