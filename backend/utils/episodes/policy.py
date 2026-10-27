"""Pure episode boundary and reconciliation rules. No I/O, no model calls.

A moment either continues the open episode, closes it for a deterministic
reason (the hard cap, a long gap, two different calendar events), or lands in
the ambiguous middle where Jev decides whether the user moved on, from the gap,
the source and the speaker set. Overlapping captures from another device of
the same occasion always continue: they add a source, not a new episode.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Mapping, Optional, Sequence

from config.episodes import (
    CLOSE_GAP_SECONDS,
    CONTINUE_GAP_SECONDS,
    FALLBACK_CLOSE_GAP_SECONDS,
    MAX_EPISODE_SECONDS,
    MAX_MOMENTS,
    MOVED_ON_THRESHOLD,
    PROVISIONAL_MATCH_THRESHOLD,
)

CloseReason = Literal['user', 'gap', 'idle', 'hard_cap', 'source_change', 'calendar_boundary', 'moved_on', 'boundary']
CLOSE_REASONS: frozenset[str] = frozenset(
    {'user', 'gap', 'idle', 'hard_cap', 'source_change', 'calendar_boundary', 'moved_on', 'boundary'}
)

CONTINUE = 'continue'
ASK = 'ask'
NEW = 'new'


def utc(value: Any) -> Optional[datetime]:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@dataclass(frozen=True)
class MomentFacts:
    conversation_id: str
    source: Optional[str]
    started_at: datetime
    ended_at: datetime
    calendar_identity: Optional[str] = None
    speakers: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Boundary:
    """``action`` is continue, ask, new (no open episode) or close with ``reason``."""

    action: Literal['continue', 'ask', 'new', 'close']
    reason: Optional[CloseReason] = None
    gap_seconds: Optional[float] = None
    source_changed: bool = False
    parallel: bool = False


def is_live(episode: Optional[Mapping[str, Any]]) -> bool:
    return bool(episode) and episode.get('status') == 'live'


def idle_close_due(episode: Optional[Mapping[str, Any]], now: datetime) -> bool:
    """A live episode with no speech for the close gap is over; reads close it lazily."""
    if episode is None or not is_live(episode):
        return False
    last = utc(episode.get('last_activity_at'))
    return last is not None and (now - last).total_seconds() >= CLOSE_GAP_SECONDS


# Only silence ends are rejoinable by a late sync capture: a user close (finalize,
# wrap-up) or a hard boundary (a meeting window, the caps, a decided move-on) is
# an explicit end of the occasion, and a late WAL row never overrides it.
REJOINABLE_CLOSE_REASONS = frozenset({'gap', 'idle'})


def rejoinable_closed_episode(
    episode: Optional[Mapping[str, Any]], started_at: datetime, finished_at: Optional[datetime]
) -> bool:
    """Whether a late sync clip may rejoin this closed episode.

    The clip's span must meet the closed occasion the way a live conversation's
    first words meet an open one: reach into its documented window
    (``started_at``..``closed_at`` — the close, not the last live moment, is
    the occasion's recorded end, and speech the live stream never carried is
    exactly what that window still covers), begin within the continue gap
    before its start (separate device clocks), or start within the continue gap
    after its end. Audio from an occasion already over stays out.
    """
    if episode is None or is_live(episode):
        return False
    if (episode.get('close_reason') or '') not in REJOINABLE_CLOSE_REASONS:
        return False
    start = utc(episode.get('started_at'))
    end = utc(episode.get('closed_at')) or utc(episode.get('last_activity_at'))
    if start is None or end is None:
        return False
    finished = finished_at or started_at
    if finished < start:
        return (start - started_at).total_seconds() <= CONTINUE_GAP_SECONDS
    if started_at > end:
        # The same edge as a live continue: a gap at or beyond the continue gap
        # is a different occasion, exactly as it is for an open episode.
        return (started_at - end).total_seconds() < CONTINUE_GAP_SECONDS
    return True


def boundary(episode: Optional[Mapping[str, Any]], moment: MomentFacts) -> Boundary:
    if episode is None or not is_live(episode):
        return Boundary(NEW)
    started = utc(episode.get('started_at')) or moment.started_at
    last = utc(episode.get('last_activity_at')) or started
    if (moment.ended_at - started).total_seconds() > MAX_EPISODE_SECONDS:
        return Boundary('close', 'hard_cap')
    if len(episode.get('moments') or []) >= MAX_MOMENTS:
        return Boundary('close', 'hard_cap')
    conversation_ids = set(episode.get('conversation_ids') or [])
    if moment.conversation_id in conversation_ids:
        return Boundary(CONTINUE)
    gap = (moment.started_at - last).total_seconds()
    sources = set(episode.get('sources') or [])
    source_changed = bool(moment.source) and bool(sources) and moment.source not in sources
    if gap < 0:
        # Another device captured the same stretch: one occasion, one more source.
        return Boundary(CONTINUE, gap_seconds=gap, source_changed=source_changed, parallel=True)
    if gap >= CLOSE_GAP_SECONDS:
        return Boundary('close', 'gap', gap_seconds=gap)
    calendar = episode.get('calendar_identity')
    if calendar and moment.calendar_identity and calendar != moment.calendar_identity:
        return Boundary('close', 'calendar_boundary', gap_seconds=gap)
    if gap < CONTINUE_GAP_SECONDS and not source_changed:
        return Boundary(CONTINUE, gap_seconds=gap)
    return Boundary(ASK, gap_seconds=gap, source_changed=source_changed)


def resolve_ask(decision: Boundary, p_same: Optional[float]) -> Boundary:
    """Jev's answer for an ambiguous boundary; no answer falls back to the cheap rules."""
    if p_same is None:
        if decision.source_changed:
            return Boundary('close', 'source_change', gap_seconds=decision.gap_seconds, source_changed=True)
        if (decision.gap_seconds or 0) >= FALLBACK_CLOSE_GAP_SECONDS:
            return Boundary('close', 'gap', gap_seconds=decision.gap_seconds)
        return Boundary(CONTINUE, gap_seconds=decision.gap_seconds, source_changed=decision.source_changed)
    if p_same < MOVED_ON_THRESHOLD:
        reason: CloseReason = 'source_change' if decision.source_changed else 'moved_on'
        return Boundary('close', reason, gap_seconds=decision.gap_seconds, source_changed=decision.source_changed)
    return Boundary(CONTINUE, gap_seconds=decision.gap_seconds, source_changed=decision.source_changed)


def speaker_keys(segments: Sequence[Mapping[str, Any]]) -> frozenset[str]:
    keys: set[str] = set()
    for segment in segments:
        if segment.get('is_user'):
            keys.add('owner')
        elif segment.get('person_id'):
            keys.add(f"person:{segment['person_id']}")
        elif segment.get('speaker_id') is not None:
            keys.add(f"speaker:{segment['speaker_id']}")
    return frozenset(keys)


# --------------------------------------------------------------------------- provisional reconciliation

_WORD = re.compile(r'[^\W_]+', re.UNICODE)
_STOP = frozenset({'the', 'a', 'an', 'to', 'for', 'and', 'of', 'on', 'at', 'in', 'with', 'my', 'me', 'i'})


def _tokens(text: str) -> set[str]:
    return {word for word in _WORD.findall((text or '').casefold()) if word not in _STOP}


def similarity(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    overlap = len(a & b)
    # Containment favors a short saved task that restates a longer provisional one.
    return max(overlap / len(a | b), overlap / min(len(a), len(b)) * 0.9)


def match_saved_tasks(
    items: Sequence[Mapping[str, Any]], saved: Sequence[Mapping[str, Any]]
) -> dict[str, Optional[str]]:
    """item id -> the saved task it became, or None. Each saved task matches one item at most."""
    pairs: list[tuple[float, str, str]] = []
    for item in items:
        for task in saved:
            score = similarity(str(item.get('text') or ''), str(task.get('description') or ''))
            if score >= PROVISIONAL_MATCH_THRESHOLD and item.get('id') and task.get('id'):
                pairs.append((score, str(item['id']), str(task['id'])))
    result: dict[str, Optional[str]] = {str(item['id']): None for item in items if item.get('id')}
    used: set[str] = set()
    for _score, item_id, task_id in sorted(pairs, reverse=True):
        if result.get(item_id) is None and task_id not in used:
            result[item_id] = task_id
            used.add(task_id)
    return result
