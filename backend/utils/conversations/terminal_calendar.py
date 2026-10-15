"""Conservative calendar protection for failed-finalization rule discards."""

from datetime import datetime, timedelta
from typing import Any, Mapping
import asyncio


def calendar_retains(uid: str, row: Mapping[str, Any]) -> bool | None:
    # Local imports keep transaction-only harnesses and normal keep terminals cheap.
    from database import calendar_meetings, users
    from utils.conversations.calendar_linking import get_google_calendar_events, select_overlapping_calendar_event
    from utils.conversations.meeting_context import MEETING_SEARCH_TOLERANCE_MINUTES, select_overlapping_meeting

    if (
        row.get('calendar_event')
        or row.get('calendar_meeting_context')
        or (row.get('external_data') or {}).get('calendar_meeting_context')
    ):
        return True
    start, end = row.get('started_at'), row.get('finished_at')
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        # No trustworthy window means the terminal cannot disprove overlap.
        return None
    tolerance = timedelta(minutes=MEETING_SEARCH_TOLERANCE_MINUTES)
    meetings = calendar_meetings.get_meetings_in_time_range(uid, start - tolerance, end + tolerance)
    if select_overlapping_meeting(meetings, started_at=start, finished_at=end) is not None:
        return True
    # The normal linker deliberately maps provider errors to None. A failed
    # terminal must distinguish unavailable evidence from confirmed no overlap.
    integration = users.get_integration(uid, 'google_calendar')
    if not integration or not integration.get('connected'):
        return False
    token = integration.get('access_token')
    if not token:
        return None
    events = asyncio.run(
        get_google_calendar_events(
            access_token=token,
            time_min=start - timedelta(minutes=30),
            time_max=end + timedelta(minutes=30),
            max_results=20,
        )
    )
    if select_overlapping_calendar_event(events, start, end, require_accepted=True) is not None:
        return True
    # A bounded result can omit an overlapping event; uncertainty keeps.
    return None if len(events) >= 20 else False
