"""Today's calendar, as the reader will actually live it."""

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from models.paper import CalendarEntry, SourceHealth
from utils.conversations.calendar_utils import extract_attendees, parse_event_times
from utils.log_sanitizer import sanitize
from utils.retrieval.tools.calendar_tools import get_google_calendar_events

logger = logging.getLogger(__name__)

MAX_EVENTS = 20


async def fetch_today(
    integration: dict[str, Any] | None,
    access_token: str | None,
    day: date,
) -> tuple[list[CalendarEntry], SourceHealth]:
    """Events on ``day``.

    A day with no events is a real answer and reports ``ok`` — "calendar is
    clear" is information. Only a failed read is degraded.
    """
    if not integration or not access_token:
        return [], SourceHealth(source='calendar', ok=False, note='Google account not connected')

    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    try:
        raw = await get_google_calendar_events(
            access_token,
            time_min=start,
            time_max=end,
            max_results=MAX_EVENTS,
        )
    except Exception as e:  # noqa: BLE001 — a missing calendar costs one section.
        logger.warning('paper: calendar read failed: %s', sanitize(str(e)))
        return [], SourceHealth(source='calendar', ok=False, note=sanitize(str(e))[:200])

    entries: list[CalendarEntry] = []
    for event in raw or []:
        if str(event.get('status') or '') == 'cancelled':
            continue
        title = str(event.get('summary') or '').strip()
        if not title:
            continue
        started, ended = parse_event_times(event)
        names, _emails = extract_attendees(event)
        entries.append(
            CalendarEntry(
                title=title,
                start=started.isoformat() if started else '',
                end=ended.isoformat() if ended else '',
                attendees=names[:8],
                location=str(event.get('location') or '').strip(),
            )
        )

    return entries, SourceHealth(
        source='calendar',
        ok=True,
        fetched=len(raw or []),
        kept=len(entries),
        note='' if entries else 'no events scheduled',
    )
