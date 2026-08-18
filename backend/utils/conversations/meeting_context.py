"""Bounded, read-only meeting context enrichment before note generation."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Iterable, Optional

from models.calendar_context import CalendarMeetingContext, MeetingParticipant
from models.conversation import CalendarEventLink

MAX_SCREEN_CONTEXT_ROWS = 80
MAX_SCREEN_CONTEXT_CHARACTERS = 12_000

_CONFERENCING_MARKERS = ('zoom', 'microsoft teams', 'webex', 'facetime', 'google meet', 'meet.google')
_OCR_UI_WORDS = {
    'audio',
    'camera',
    'chat',
    'leave',
    'meeting',
    'microphone',
    'more',
    'mute',
    'participants',
    'reactions',
    'record',
    'screen',
    'share',
    'stop video',
    'unmute',
}


def _is_conferencing_row(row: dict[str, Any]) -> bool:
    haystack = f'{row.get("appName", "")} {row.get("windowTitle", "")}'.casefold()
    return any(marker in haystack for marker in _CONFERENCING_MARKERS)


def _name_candidates(text: str) -> Iterable[str]:
    for raw_line in text.splitlines():
        line = re.sub(r'\s+', ' ', raw_line).strip(' •|\t')
        folded = line.casefold()
        if not line or len(line) > 60 or folded in _OCR_UI_WORDS or '@' in line or 'http' in folded:
            continue
        if any(word in folded for word in ('mute', 'video', 'meeting', 'screen', 'recording')):
            continue
        words = line.split()
        if not 1 <= len(words) <= 4:
            continue
        if all(re.fullmatch(r"[A-Za-z][A-Za-z.'’-]*", word) for word in words):
            yield line


def context_from_screen_activity(
    rows: list[dict[str, Any]],
    *,
    started_at: datetime,
    finished_at: datetime,
) -> Optional[CalendarMeetingContext]:
    """Extract conservative names/title from already-captured conferencing rows.

    This deliberately avoids another LLM call. OCR is used only as metadata;
    the transcript remains the authority for note claims.
    """
    selected: list[dict[str, Any]] = []
    used_characters = 0
    for row in rows[:MAX_SCREEN_CONTEXT_ROWS]:
        if not _is_conferencing_row(row):
            continue
        row_text = f'{row.get("windowTitle", "")}\n{row.get("ocrText", "")}'
        remaining = MAX_SCREEN_CONTEXT_CHARACTERS - used_characters
        if remaining <= 0:
            break
        selected.append({**row, 'ocrText': row_text[:remaining]})
        used_characters += min(len(row_text), remaining)
    if not selected:
        return None

    titles = [str(row.get('windowTitle') or '').strip() for row in selected if row.get('windowTitle')]
    title = next((value for value in titles if value.casefold() not in _OCR_UI_WORDS), 'Video meeting')
    app_name = str(selected[0].get('appName') or '').strip() or None
    names: list[str] = []
    seen: set[str] = set()
    for row in selected:
        for candidate in _name_candidates(str(row.get('ocrText') or '')):
            if candidate.casefold() == title.casefold():
                continue
            key = candidate.casefold()
            if key in seen:
                continue
            seen.add(key)
            names.append(candidate)
            if len(names) == 12:
                break
        if len(names) == 12:
            break

    return CalendarMeetingContext(
        calendar_event_id='screen-activity',
        title=title,
        participants=[MeetingParticipant(name=name) for name in names],
        platform=app_name,
        start_time=started_at,
        duration_minutes=max(1, int((finished_at - started_at).total_seconds() / 60)),
        calendar_source='screen_activity',
    )


def context_from_calendar_link(link: CalendarEventLink) -> CalendarMeetingContext:
    participants = [MeetingParticipant(name=name) for name in link.attendees]
    participants.extend(MeetingParticipant(email=email) for email in link.attendee_emails)
    return CalendarMeetingContext(
        calendar_event_id=link.event_id,
        title=link.title,
        participants=participants,
        start_time=link.start_time,
        duration_minutes=max(1, int((link.end_time - link.start_time).total_seconds() / 60)),
        meeting_link=link.html_link,
        calendar_source='google',
    )


def merge_meeting_contexts(
    primary: Optional[CalendarMeetingContext], fallback: Optional[CalendarMeetingContext]
) -> Optional[CalendarMeetingContext]:
    if primary is None:
        return fallback
    if fallback is None:
        return primary
    participants = list(primary.participants)
    seen = {
        (participant.name or '').casefold() + '|' + (participant.email or '').casefold() for participant in participants
    }
    for participant in fallback.participants:
        key = (participant.name or '').casefold() + '|' + (participant.email or '').casefold()
        if key not in seen:
            participants.append(participant)
            seen.add(key)
    return primary.model_copy(
        update={
            'participants': participants,
            'platform': primary.platform or fallback.platform,
            'notes': primary.notes or fallback.notes,
        }
    )
