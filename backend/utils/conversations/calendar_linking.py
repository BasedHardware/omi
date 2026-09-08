"""
Calendar event linking for conversations.

Detects and links conversations to Google Calendar events when they overlap in time.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import database.users as users_db
from models.conversation import CalendarEventLink
from utils.conversations.calendar_utils import extract_attendees, parse_event_times
from utils.retrieval.tools.calendar_tools import (
    get_google_calendar_events,
    get_google_calendar_event,
    update_google_calendar_event,
)
from utils.retrieval.tools.google_utils import refresh_google_token
from utils.executors import run_blocking, db_executor
from utils.integration_telemetry import (
    GOOGLE_CALENDAR,
    IntegrationTelemetryContext,
    emit_sync_attempted,
    emit_sync_failed,
    emit_sync_succeeded,
)
from utils.share_links import build_share_url

logger = logging.getLogger(__name__)

# Minimum overlap duration in seconds to consider a match (10 seconds)
MIN_OVERLAP_SECONDS = 10

# Minimum overlap percentage of event duration to consider a match (50%)
MIN_OVERLAP_PERCENTAGE = 0.50

# Capture-gap ceiling: events longer than this (all-day blocks, travel days)
# are never reported as "not captured" — nobody records a 9h block end to end.
MAX_CAPTURE_GAP_EVENT_SECONDS = 8 * 60 * 60


def _as_utc(value) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def event_attendance_excluded(event: Dict[str, Any]) -> bool:
    """True when the event is cancelled, or the authorized user declined it.

    Google Calendar keeps cancelled instances and events the user answered "No"
    to in the primary feed; neither proves the user was in a meeting, so neither
    may keep a discarded conversation or surface as a capture gap.
    """
    if str(event.get('status', '')).strip().lower() == 'cancelled':
        return True
    attendees_raw = event.get('attendees')
    if not isinstance(attendees_raw, list):
        return False
    for attendee in attendees_raw:
        if not isinstance(attendee, dict):
            continue
        if attendee.get('self') and str(attendee.get('responseStatus', '')).strip().lower() == 'declined':
            return True
    return False


def select_overlapping_calendar_event(
    events: List[Dict[str, Any]],
    conversation_start: datetime,
    conversation_end: datetime,
    *,
    require_accepted: bool = False,
) -> Optional[Dict[str, Any]]:
    """Pick the Google Calendar event that best overlaps the conversation window.

    Pure on the raw Google event payloads so the matching rules are testable
    without a live provider. An overlap must be at least ``MIN_OVERLAP_SECONDS``
    long and cover ``MIN_OVERLAP_PERCENTAGE`` of either the event or the
    conversation — the OR is deliberate: a short recording wholly inside a long
    meeting matches through conversation coverage. With ``require_accepted`` the
    same rules apply but cancelled events and events the user declined are
    skipped (the discard-override path); the auto-link path keeps its current
    behavior of matching any overlapping event.
    """
    best_match: Optional[Dict[str, Any]] = None
    best_overlap_seconds = 0

    conversation_duration = (conversation_end - conversation_start).total_seconds()

    for event in events:
        if require_accepted and event_attendance_excluded(event):
            continue

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

    return best_match


def select_capture_gaps(
    events: List[Dict[str, Any]],
    conversations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Confirmed, timed calendar events with no overlapping kept conversation.

    The capture-gap surface (SCA-381): honesty about what was booked but never
    recorded, without minting conversation documents. An event qualifies when it
    is confirmed (not cancelled, not tentative, not declined by the user), has
    timed bounds no longer than ``MAX_CAPTURE_GAP_EVENT_SECONDS`` (all-day
    blocks parse to midnight bounds and exceed the ceiling), and no
    non-discarded conversation overlaps it by at least ``MIN_OVERLAP_SECONDS``
    — the same floor the linker applies, so a sub-10s blip is not "capture".
    """
    conversation_windows: List[tuple[datetime, datetime]] = []
    for conversation in conversations:
        if conversation.get('discarded'):
            continue
        start = _as_utc(conversation.get('started_at'))
        end = _as_utc(conversation.get('finished_at'))
        if start is None or end is None or end <= start:
            continue
        conversation_windows.append((start, end))

    rows: List[Dict[str, Any]] = []
    for event in events:
        if event_attendance_excluded(event):
            continue
        if str(event.get('status', 'confirmed')).strip().lower() != 'confirmed':
            continue
        event_start, event_end = parse_event_times(event)
        if event_start is None or event_end is None:
            continue
        event_duration = (event_end - event_start).total_seconds()
        if event_duration <= 0 or event_duration > MAX_CAPTURE_GAP_EVENT_SECONDS:
            continue
        covered = any(
            (min(event_end, window_end) - max(event_start, window_start)).total_seconds() >= MIN_OVERLAP_SECONDS
            for window_start, window_end in conversation_windows
        )
        if covered:
            continue
        rows.append(
            {
                'event_id': str(event.get('id', '')),
                'title': str(event.get('summary', 'Untitled Event')),
                'start_time': event_start,
                'end_time': event_end,
                'status': str(event.get('status', 'confirmed')),
                'coverage': 'not_captured',
            }
        )
    return rows


async def get_overlapping_calendar_event(
    uid: str,
    conversation_start: datetime,
    conversation_end: datetime,
    *,
    require_accepted: bool = False,
) -> Optional[CalendarEventLink]:
    """
    Find a Google Calendar event that overlaps with the conversation timeframe.

    Args:
        uid: User ID
        conversation_start: When the conversation started
        conversation_end: When the conversation ended
        require_accepted: Skip cancelled events and events the user declined
            (used by the discard override; auto-link keeps matching any event)

    Returns:
        CalendarEventLink if a matching event is found, None otherwise
    (disconnected calendar, missing token, and provider errors all return None)
    """
    integration_raw = await run_blocking(db_executor, users_db.get_integration, uid, 'google_calendar')
    integration: Optional[Dict[str, Any]] = integration_raw
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
    telemetry_context = IntegrationTelemetryContext(
        integration_name=GOOGLE_CALENDAR,
        operation='fetch_events_for_auto_link',
        uid=uid,
    )
    emit_sync_attempted(telemetry_context)

    events: List[Dict[str, Any]] = []
    try:
        events = await get_google_calendar_events(
            access_token=str(access_token),
            time_min=search_start,
            time_max=search_end,
            max_results=20,
        )
    except Exception as e:
        error_msg = str(e)
        if "error 401" in error_msg.lower() or "authentication failed" in error_msg.lower():
            new_token: Optional[str] = await refresh_google_token(uid, integration)
            if new_token:
                try:
                    events = await get_google_calendar_events(
                        access_token=new_token,
                        time_min=search_start,
                        time_max=search_end,
                        max_results=20,
                    )
                except Exception as retry_error:
                    emit_sync_failed(telemetry_context, retry_error)
                    return None
            else:
                emit_sync_failed(telemetry_context, e)
                return None
        else:
            emit_sync_failed(telemetry_context, e)
            return None
    emit_sync_succeeded(telemetry_context, item_count=len(events))

    if not events:
        return None

    best_match = select_overlapping_calendar_event(
        events,
        conversation_start,
        conversation_end,
        require_accepted=require_accepted,
    )

    if best_match is None:
        return None

    event_start, event_end = parse_event_times(best_match)
    attendee_names, attendee_emails = extract_attendees(best_match)

    # best_match was selected only when parse_event_times returned valid datetimes
    # (the loop body continues on None), but re-parse for the model. Guard anyway.
    if event_start is None or event_end is None:
        return None

    return CalendarEventLink(
        event_id=str(best_match.get('id', '')),
        title=str(best_match.get('summary', 'Untitled Event')),
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

    Appends a share URL for the conversation to the event description.
    Silently no-ops on any error — linking the conversation to the event is the primary
    action; failing to write the description link should not block the caller.
    """
    integration_raw = await run_blocking(db_executor, users_db.get_integration, uid, 'google_calendar')
    integration: Optional[Dict[str, Any]] = integration_raw
    if not integration or not integration.get('connected'):
        return

    access_token = integration.get('access_token')
    if not access_token:
        return

    conversation_link = build_share_url(f'/conversations/{conversation_id}')
    telemetry_context = IntegrationTelemetryContext(
        integration_name=GOOGLE_CALENDAR,
        operation='write_conversation_link',
        uid=uid,
    )

    async def _write(token: str) -> None:
        existing = await get_google_calendar_event(token, event_id)
        current_description = str(existing.get('description', '') or '')
        if conversation_link in current_description:
            return
        new_description = f"{current_description}\n\n{conversation_link}" if current_description else conversation_link
        await update_google_calendar_event(access_token=token, event_id=event_id, description=new_description)

    try:
        emit_sync_attempted(telemetry_context)
        await _write(access_token)
        emit_sync_succeeded(telemetry_context, item_count=1)
    except Exception as e:
        error_msg = str(e)
        if "error 401" in error_msg.lower() or "authentication failed" in error_msg.lower():
            new_token: Optional[str] = await refresh_google_token(uid, integration)
            if new_token:
                try:
                    await _write(new_token)
                    emit_sync_succeeded(telemetry_context, item_count=1)
                except Exception as retry_error:
                    logger.warning(
                        f"write_conversation_link_to_calendar_event failed after token refresh: {retry_error}"
                    )
                    emit_sync_failed(telemetry_context, retry_error)
            else:
                emit_sync_failed(telemetry_context, e)
        else:
            logger.warning(
                f"write_conversation_link_to_calendar_event failed for conversation {conversation_id}: {error_msg}"
            )
            emit_sync_failed(telemetry_context, e)
