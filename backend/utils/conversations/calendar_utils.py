"""Shared helpers for parsing Google Calendar API event payloads."""

from datetime import datetime, timedelta
from typing import Optional


def parse_event_times(event: dict) -> tuple[Optional[datetime], Optional[datetime]]:
    """Parse start and end times from a Google Calendar event dict.

    Handles both dateTime (specific time) and date (all-day) formats.
    Returns (None, None) if parsing fails.
    """
    start = event.get('start', {})
    end = event.get('end', {})
    try:
        if 'dateTime' in start:
            start_dt = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
        elif 'date' in start:
            start_dt = datetime.fromisoformat(start['date'] + 'T00:00:00+00:00')
        else:
            return None, None

        if 'dateTime' in end:
            end_dt = datetime.fromisoformat(end['dateTime'].replace('Z', '+00:00'))
        elif 'date' in end:
            # Google Calendar end.date is exclusive (the day after the event ends)
            end_dt = datetime.fromisoformat(end['date'] + 'T00:00:00+00:00') - timedelta(seconds=1)
        else:
            return None, None

        return start_dt, end_dt
    except (ValueError, KeyError):
        return None, None


def extract_attendees(event: dict) -> tuple[list[str], list[str]]:
    """Extract attendee display names and emails from a Google Calendar event dict.

    Skips the calendar owner's own entry (self=True).
    Returns (display_names, emails).
    """
    names = []
    emails = []
    for attendee in event.get('attendees', []):
        if attendee.get('self', False):
            continue
        email = attendee.get('email', '')
        name = attendee.get('displayName') or email
        if name:
            names.append(name)
        if email:
            emails.append(email)
    return names, emails
