"""Bounded, read-only meeting context enrichment before note generation."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

from models.calendar_context import CalendarMeetingContext, MeetingParticipant
from models.conversation import CalendarEventLink

MAX_SCREEN_CONTEXT_ROWS = 80
MAX_SCREEN_CONTEXT_CHARACTERS = 12_000

# Stored-meeting overlap selection. Deliberately the same thresholds as the Google
# Calendar auto-link path (utils/conversations/calendar_linking.py) so a stored
# system-calendar meeting and a Google event are judged by identical rules.
MIN_OVERLAP_SECONDS = 10
MIN_OVERLAP_PERCENTAGE = 0.50
# How far outside the conversation window a stored meeting may start/end and still
# be a candidate. Recording usually starts late and stops early relative to the invite.
MEETING_SEARCH_TOLERANCE_MINUTES = 30

_CONFERENCING_MARKERS = ('zoom', 'microsoft teams', 'webex', 'facetime', 'google meet', 'meet.google')
_CONFERENCING_URL_MARKERS = ('meet.google.com/', 'zoom.us/j/', 'teams.microsoft.com/l/meetup', 'webex.com/meet')
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
    if any(marker in haystack for marker in _CONFERENCING_MARKERS):
        return True
    # Browser-hosted meetings show up as a plain tab title ("Meet - abc-defg-hij"),
    # so the app/title pair alone misses them. Match only unambiguous join URLs in
    # the OCR text — a bare 'zoom'/'meet' substring would sweep in unrelated pages.
    ocr_text = str(row.get('ocrText') or '').casefold()
    return any(marker in ocr_text for marker in _CONFERENCING_URL_MARKERS)


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


def _as_utc(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def stored_meeting_window(record: dict[str, Any]) -> Optional[tuple[datetime, datetime]]:
    """The (start, end) of a stored meeting record, in UTC.

    `end_time` is written by `POST /v1/calendar/meetings`, but older records and
    records round-tripped through `CalendarMeetingContext` only carry
    `duration_minutes`, so derive the end when it is absent.
    """
    start = _as_utc(record.get('start_time'))
    if start is None:
        return None
    end = _as_utc(record.get('end_time'))
    if end is None:
        duration = record.get('duration_minutes')
        if not isinstance(duration, (int, float)) or duration <= 0:
            return None
        end = start + timedelta(minutes=float(duration))
    if end <= start:
        return None
    return start, end


def select_overlapping_meeting(
    records: list[dict[str, Any]],
    *,
    started_at: datetime,
    finished_at: datetime,
) -> Optional[CalendarMeetingContext]:
    """Pick the stored meeting that best overlaps the conversation window.

    Mirrors the Google-Calendar auto-link thresholds: an overlap must be at least
    MIN_OVERLAP_SECONDS long *and* cover MIN_OVERLAP_PERCENTAGE of either the
    meeting or the conversation, so a short recording cannot latch onto an
    all-day block. Ties break on the longest overlap. Returns None when nothing
    qualifies — the caller degrades to the next source.
    """
    conversation_start = _as_utc(started_at)
    conversation_end = _as_utc(finished_at)
    if conversation_start is None or conversation_end is None or conversation_end <= conversation_start:
        return None
    conversation_duration = (conversation_end - conversation_start).total_seconds()

    best_record: Optional[dict[str, Any]] = None
    best_overlap = 0.0
    for record in records:
        window = stored_meeting_window(record)
        if window is None:
            continue
        meeting_start, meeting_end = window
        overlap = (min(meeting_end, conversation_end) - max(meeting_start, conversation_start)).total_seconds()
        if overlap < MIN_OVERLAP_SECONDS:
            continue
        meeting_duration = (meeting_end - meeting_start).total_seconds()
        covers_meeting = meeting_duration > 0 and overlap / meeting_duration >= MIN_OVERLAP_PERCENTAGE
        covers_conversation = conversation_duration > 0 and overlap / conversation_duration >= MIN_OVERLAP_PERCENTAGE
        if not (covers_meeting or covers_conversation):
            continue
        if overlap > best_overlap:
            best_overlap = overlap
            best_record = record

    if best_record is None:
        return None
    parsed = CalendarMeetingContext.from_records([best_record])
    return parsed[0] if parsed else None


def resolve_meeting_context(
    *,
    direct: Optional[CalendarMeetingContext],
    stored: Optional[Callable[[], Optional[CalendarMeetingContext]]] = None,
    calendar: Optional[Callable[[], Optional[CalendarMeetingContext]]] = None,
    screen: Optional[Callable[[], Optional[CalendarMeetingContext]]] = None,
    on_error: Optional[Callable[[str, Exception], None]] = None,
) -> Optional[CalendarMeetingContext]:
    """Layer identity sources, best first, degrading to None.

    `direct` is the context already on the conversation (sent by the client on the
    create request). The suppliers are called in order and each is optional; a
    supplier that is None is a disabled layer, and a supplier that raises is
    reported via `on_error` and skipped. A better source always wins the scalar
    fields; weaker sources only contribute participants the better ones missed.

    Returning None is a normal outcome, not a failure: summarization proceeds
    without a CALENDAR MEETING CONTEXT block.
    """

    def _call(name: str, supplier: Optional[Callable[[], Optional[CalendarMeetingContext]]]):
        if supplier is None:
            return None
        try:
            return supplier()
        except Exception as exc:  # noqa: BLE001 - no identity source may fail the conversation
            if on_error is not None:
                on_error(name, exc)
            return None

    context = merge_meeting_contexts(_call('stored', stored), direct)
    context = merge_meeting_contexts(context, _call('calendar', calendar))
    return merge_meeting_contexts(context, _call('screen', screen))
