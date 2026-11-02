"""Model-facing rendering of Google Calendar events for the chat calendar tools.

Kept apart from calendar_tools.py (API access and tool entry points) so event text
formatting, untrusted-content fencing and all-day date handling live in one place.
"""

import logging
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from utils.model_text import DisplayClock, format_date, format_span, truncation_note, untrusted_block

logger = logging.getLogger(__name__)


def all_day_date(value: Any, clock: DisplayClock) -> Optional[Tuple[date, str]]:
    """Interpret a Calendar all-day date in the user's calendar zone, not UTC midnight."""
    try:
        day = date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    local_midnight = datetime.combine(day, time.min).replace(tzinfo=clock.tz)
    return day, format_date(local_midnight, clock)


def render_calendar_event(event: Dict[str, Any], index: int, clock: DisplayClock) -> str:
    """Format one event, fencing text supplied by event owners and attendees."""
    summary = event.get('summary') or 'No title'
    result = f"{index}. Title: {untrusted_block('calendar title', str(summary))}\n"

    start = event.get('start', {})
    end = event.get('end', {})
    if 'dateTime' in start:
        try:
            start_dt = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end['dateTime'].replace('Z', '+00:00'))
            result += f"   When: {format_span(start_dt, end_dt, clock)}\n"
        except (ValueError, TypeError, KeyError):
            result += "   When: unknown time (event timestamp could not be parsed)\n"
    elif 'date' in start:
        start_day = all_day_date(start.get('date'), clock)
        end_day = all_day_date(end.get('date'), clock) if 'date' in end else None
        if start_day is None:
            result += "   When: all day; date unavailable\n"
        elif end_day is None:
            result += f"   When: all day, {start_day[1]}\n"
        else:
            inclusive_end = end_day[0] - timedelta(days=1)
            inclusive_end_label = all_day_date(
                inclusive_end.isoformat(),  # not-model-facing: local date parsing helper input
                clock,
            )
            if inclusive_end_label and inclusive_end > start_day[0]:
                result += f"   When: all day, {start_day[1]} – {inclusive_end_label[1]}\n"
            else:
                result += f"   When: all day, {start_day[1]}\n"

    location = event.get('location')
    if location:
        result += f"   Location: {untrusted_block('calendar location', str(location))}\n"

    attendees = event.get('attendees')
    if isinstance(attendees, list) and attendees:
        attendee_text: List[str] = []
        for attendee in attendees:
            if isinstance(attendee, dict):
                display_name = attendee.get('displayName')
                email = attendee.get('email')
                label = (
                    ' <'.join([str(display_name), str(email)]) + '>'
                    if display_name and email
                    else str(display_name or email or '')
                )
            else:
                label = str(attendee)
            if label:
                attendee_text.append(label)
        if attendee_text:
            result += f"   Attendees ({len(attendee_text)}): {untrusted_block('calendar attendees', ', '.join(attendee_text))}\n"

    description = event.get('description', '')
    if description:
        description = str(description)
        was_cut = len(description) > 100
        desc_preview = description[:100] + ('...' if was_cut else '')
        result += f"   Description: {untrusted_block('calendar description', desc_preview)}\n"
        if was_cut:
            result += (
                "   "
                + truncation_note(
                    shown=100,
                    total=len(description),
                    unit="description characters",
                    how_to_get_more="Ask for the event description to be retrieved in full.",
                )
                + "\n"
            )

    return result + "\n"
