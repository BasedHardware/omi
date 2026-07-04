"""Shared helpers for parsing Google Calendar API event payloads."""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, cast


def parse_event_times(event: Dict[str, Any]) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Parse start and end times from a Google Calendar event dict.

    Handles both dateTime (specific time) and date (all-day) formats.
    Returns (None, None) if parsing fails.
    """
    start_raw: object = event.get('start', {})
    end_raw: object = event.get('end', {})
    start: Dict[str, Any] = cast(Dict[str, Any], start_raw) if isinstance(start_raw, dict) else {}
    end: Dict[str, Any] = cast(Dict[str, Any], end_raw) if isinstance(end_raw, dict) else {}
    try:
        if 'dateTime' in start:
            start_dt = datetime.fromisoformat(str(start['dateTime']).replace('Z', '+00:00'))
        elif 'date' in start:
            start_dt = datetime.fromisoformat(str(start['date']) + 'T00:00:00+00:00')
        else:
            return None, None

        if 'dateTime' in end:
            end_dt = datetime.fromisoformat(str(end['dateTime']).replace('Z', '+00:00'))
        elif 'date' in end:
            # Google Calendar end.date is exclusive (the day after the event ends)
            end_dt = datetime.fromisoformat(str(end['date']) + 'T00:00:00+00:00') - timedelta(seconds=1)
        else:
            return None, None

        return start_dt, end_dt
    except (ValueError, KeyError):
        return None, None


def extract_attendees(event: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    """Extract attendee display names and emails from a Google Calendar event dict.

    Skips the calendar owner's own entry (self=True).
    Returns (display_names, emails).
    """
    names: List[str] = []
    emails: List[str] = []
    attendees_raw: object = event.get('attendees', [])
    raw_list: List[Any] = cast(List[Any], attendees_raw) if isinstance(attendees_raw, list) else []
    attendees: List[Dict[str, Any]] = [a for a in raw_list if isinstance(a, dict)]
    for attendee in attendees:
        if attendee.get('self', False):
            continue
        email = attendee.get('email', '')
        name = attendee.get('displayName') or email
        if name:
            names.append(str(name))
        if email:
            emails.append(str(email))
    return names, emails
