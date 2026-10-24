"""One hard-boundary policy for live conversations, episodes and smart merge."""

from __future__ import annotations

from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Mapping

from config.occasion_conversations import EPISODE_BOUNDARIES_MODE_ENV
from config.refactor_modes import serving_for, shadow_or_serve
from models.boundary_evidence import BoundaryParticipant, BoundarySignal
from utils.conversations.lifecycle_clocks import utc, speech_clock
from utils.conversations.lifecycle_metrics import observe
from utils.episodes import boundary_store

QUIET_SECONDS = 15 * 60


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
    if context and shadow_or_serve(EPISODE_BOUNDARIES_MODE_ENV):
        signal = context_signal(context)
        if signal is not None:
            boundary_store.record_context(
                uid, signal, firestore_client=firestore_client, allow_reschedule=allow_reschedule
            )


def active(windows: Mapping[str, Mapping], at: datetime) -> list[str]:
    return sorted(
        key
        for key, w in windows.items()
        if (start := utc(w.get('started_at'))) is not None
        and start <= at
        and ((end := utc(w.get('ended_at'))) is None or at < end)
    )


def crossed(windows: Mapping[str, Mapping], start: datetime, end: datetime) -> bool:
    return any(
        start < edge <= end
        for w in windows.values()
        for name in ('started_at', 'ended_at')
        if (edge := utc(w.get(name))) is not None
    )


@_safe('legacy')
def conversation_decision(uid: str, row: Mapping[str, Any], now: datetime, *, firestore_client: Any = None) -> str:
    """close on an edge, hold within a meeting, legacy outside; shadow never serves."""
    if not shadow_or_serve(EPISODE_BOUNDARIES_MODE_ENV):
        return 'legacy'
    context = (row.get('external_data') or {}).get('calendar_meeting_context')
    ingest_context(uid, context, firestore_client=firestore_client)
    known = boundary_store.windows(uid, firestore_client=firestore_client)
    start = utc(row.get('started_at'))
    if start is None:
        return 'legacy'
    speech = speech_clock(uid, row) or start
    decision = 'legacy'
    if crossed(known, start, now):
        decision = 'close'
    elif meeting_keys := active(known, start):
        quiet = (now - speech).total_seconds() >= QUIET_SECONDS
        decision = 'close' if quiet else 'hold'
        if quiet and serving_for(EPISODE_BOUNDARIES_MODE_ENV, uid):
            boundary_store.end_at(
                uid, meeting_keys, speech + timedelta(seconds=QUIET_SECONDS), firestore_client=firestore_client
            )
    observe('conversation_boundary', decision == 'legacy')
    return decision if serving_for(EPISODE_BOUNDARIES_MODE_ENV, uid) else 'legacy'


@_safe(True)
def merge_allowed(uid: str, left: Mapping[str, Any], right: Mapping[str, Any], *, firestore_client: Any = None) -> bool:
    if not shadow_or_serve(EPISODE_BOUNDARIES_MODE_ENV):
        return True
    a, b = utc(left.get('started_at')), utc(right.get('started_at'))
    if a is None or b is None:
        return True
    known = boundary_store.windows(uid, firestore_client=firestore_client)
    allowed = not crossed(known, min(a, b), max(a, b))
    observe('merge_boundary', allowed)
    return allowed if serving_for(EPISODE_BOUNDARIES_MODE_ENV, uid) else True


def boundary_roster(
    uid: str, conversation_id: str, *, conversation: Mapping[str, Any] | None = None
) -> list[BoundaryParticipant]:
    """Roster candidates only; L2 owns identity probabilities and projections."""
    if not shadow_or_serve(EPISODE_BOUNDARIES_MODE_ENV):
        return []
    if conversation is None:
        from database.conversations import get_conversation

        conversation = get_conversation(uid, conversation_id)
    row = conversation
    if not row:
        return []
    start = utc(row.get('started_at'))
    end = speech_clock(uid, row) or utc(row.get('finished_at'))
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
