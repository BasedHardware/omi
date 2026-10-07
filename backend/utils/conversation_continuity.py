"""Shared boundary arithmetic; callers supply their observed timeline coverage."""

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

DEFAULT_GAP_SECONDS = 120
MEETING_END_GRACE_SECONDS = 120


def gap_splits(seconds: float, timeout: float = DEFAULT_GAP_SECONDS) -> bool:
    return seconds >= timeout


def intervals_connect(start: float, end: float, other_start: float, other_end: float) -> bool:
    return not gap_splits(max(start - other_end, other_start - end))


def calendar_continuity_identity(row: Mapping[str, Any]) -> tuple[str, str] | None:
    """An existing event id whose scheduled window still needs a server-side read."""
    external = row.get('external_data')
    external = external if isinstance(external, Mapping) else {}
    context = external.get('calendar_meeting_context')
    context = context if isinstance(context, Mapping) else {}
    if context.get('start_time') is not None and context.get('duration_minutes') is not None:
        return None
    event_id = context.get('calendar_event_id') or external.get('calendar_event_id')
    source = context.get('calendar_source') or external.get('calendar_source') or 'system_calendar'
    link = row.get('calendar_event')
    if not event_id and isinstance(link, Mapping):
        event_id, source = link.get('event_id'), 'google'
    if not isinstance(event_id, str) or not event_id or event_id == 'screen-activity' or source == 'screen_activity':
        return None
    return (event_id, source) if isinstance(source, str) else None


def continuation_timeout(row: Mapping[str, Any], timeout: float = DEFAULT_GAP_SECONDS) -> float:
    """A stored calendar identity extends silence only through its scheduled window.

    No meeting-treatment eligibility gate: that gate controls summarization, not
    capture ownership. Empty generations retain their ordinary deletion deadline.
    """
    segments = row.get('transcript_segments')
    if not (row.get('has_content') or row.get('photos') or (isinstance(segments, list) and segments)):
        # Raw compressed empty transcripts are nonempty blobs. The metadata-only
        # lookup must use the durable marker, never the blob's truthiness.
        return timeout
    external = row.get('external_data')
    context = external.get('calendar_meeting_context') if isinstance(external, Mapping) else None
    if not isinstance(context, Mapping):
        return timeout
    event_id = context.get('calendar_event_id')
    if not event_id or event_id == 'screen-activity' or context.get('calendar_source') == 'screen_activity':
        return timeout

    def utc(value: Any) -> datetime | None:
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except ValueError:
                return None
        if not isinstance(value, datetime):
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    start, finish = utc(context.get('start_time')), utc(row.get('finished_at'))
    duration = context.get('duration_minutes')
    if start is None or finish is None or isinstance(duration, bool) or not isinstance(duration, (int, float)):
        return timeout
    try:
        if duration <= 0:
            return timeout
        deadline = start + timedelta(minutes=duration, seconds=MEETING_END_GRACE_SECONDS)
    except (OverflowError, ValueError):
        return timeout
    if not start <= finish < deadline:
        return timeout
    return (deadline - finish).total_seconds()


def resumable_continuation(
    row: Mapping[str, Any], *, source: str, device_id: str | None, now: datetime, timeout: int
) -> bool:
    """Unknown device is a partition, not permission to join another device."""
    finish = row.get('finished_at')
    return (
        row.get('status') == 'in_progress'
        and not any(row.get(key) for key in ('deleted', 'discarded', 'is_locked'))
        and row.get('source') == source
        and row.get('client_device_id') == device_id
        and isinstance(finish, datetime)
        and not gap_splits((now - finish).total_seconds(), continuation_timeout(row, timeout))
    )
