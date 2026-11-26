"""Shared calendar, screen and participant evidence."""

from __future__ import annotations

from datetime import timedelta
from functools import wraps
from typing import Any, Mapping

from models.boundary_evidence import BoundaryParticipant, BoundarySignal
from utils.conversations.lifecycle_clocks import utc
from utils.conversations.recorded_time import conversation_span
from utils.conversations.lifecycle_metrics import observe
from utils.episodes import boundary_store


def _safe(default):
    def decorate(fn):
        @wraps(fn)
        def call(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:
                observe('boundary_unavailable', None)
                return default

        return call

    return decorate


def context_signal(context: Mapping[str, Any]) -> BoundarySignal | None:
    start = utc(context.get('start_time') or context.get('started_at'))
    end = utc(context.get('end_time') or context.get('ended_at'))
    duration = context.get('duration_minutes')
    if end is None and start and isinstance(duration, (int, float)) and not isinstance(duration, bool):
        end = start + timedelta(minutes=duration)
    if start is None:
        return None
    participants = context.get('participants') or []
    screen = context.get('calendar_source') == 'screen_activity'
    # Screen windows carry the shared sentinel id 'screen-activity'; it is not an event identity.
    # Leaving external_id empty keys each window by its own start (boundary_store.signal_id).
    external_id = context.get('calendar_event_id') or context.get('id')
    if screen or external_id == 'screen-activity':
        external_id = None
    return BoundarySignal(
        kind='screen_meeting' if screen else 'calendar_event',
        started_at=start,
        ended_at=end,
        title=context.get('title'),
        meeting_link=context.get('meeting_link'),
        call_controls_detected=context.get('call_controls_detected'),
        call_platform=context.get('platform'),
        participants=[BoundaryParticipant.model_validate(p) for p in participants if isinstance(p, dict)],
        external_id=external_id,
    )


@_safe(None)
def ingest_context(
    uid: str, context: Mapping[str, Any] | None, *, firestore_client: Any = None, allow_reschedule: bool = False
) -> None:
    if context:
        signal = context_signal(context)
        if signal is not None:
            boundary_store.record_context(
                uid, signal, firestore_client=firestore_client, allow_reschedule=allow_reschedule
            )


def boundary_roster(
    uid: str, conversation_id: str, *, conversation: Mapping[str, Any] | None = None
) -> list[BoundaryParticipant]:
    """Roster candidates only; L2 owns identity probabilities and projections."""
    if conversation is None:
        from database.conversations import get_conversation

        conversation = get_conversation(uid, conversation_id)
    row = conversation
    if not row:
        return []
    span = conversation_span(row)
    start, end = (span.recorded_start, span.recorded_end) if span else (None, None)
    if start is None or end is None:
        return []
    known = boundary_store.windows(uid)
    keys = [
        key
        for key, w in known.items()
        if (s := utc(w.get('started_at'))) is not None and s <= end and (utc(w.get('ended_at')) or end) >= start
    ]
    unique = {}
    for signal in boundary_store.load(uid, keys):
        for person in signal.participants:
            unique[(person.name, person.email)] = person
    return list(unique.values())
