"""Episode-join variant F: admission, marking an uncertain recorded-time join, and settling it.

Owns the F cohort and its fail-open contract: any failure keeps today's time-only join.

- ``admitted``: the Omi flag store rule ``episode_f_join`` first (``scripts/omi_flags.py set
  episode_f_join --rollout N`` ramps, ``--inactive`` kills within 15 to 60 s). With no rule, an
  unconfigured store, or one that never loaded, ``EPISODE_F_JOIN_PERCENT`` decides (default 0).
  ``EPISODE_F_JOIN_ENABLED=off`` overrides both.
- ``arm_fields``: stamps an episode with the arm admitted when it opened (``f_join_arm``), so
  closed-episode size is attributed to the arm that was live, not to the arm at close.
- ``uncertain`` / ``mark_pending``: at attach, a join to a live recorded-time owner 2 to 30 minutes
  after its last speech is marked ``pending_boundary[cid]``, naming the predecessor member it was
  measured against. Shorter gaps, overlaps, closes and meeting-held joins keep today's rules.
- ``settle``: at the conversation's first moment, Jev answers P(same occasion) over the
  predecessor's transcript tail and the new speech. Below ``MOVED_ON_THRESHOLD`` the join splits off.
- ``record_closed_size``: closed-episode size by arm for the ramp guardrails.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Mapping, Optional, Sequence

from config.episodes import (
    CONTINUE_GAP_SECONDS,
    F_JOIN_FLAG_KEY,
    F_JOIN_VARIANT,
    MOVED_ON_THRESHOLD,
    f_join_enabled,
    f_join_env_admitted,
)
from database import conversations as conversations_db
from database import episodes as episodes_db
from database.episodes import EpisodeConflict
from utils import omi_flags
from utils.episodes import boundary_runtime, incremental, metrics, policy
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
ARM_FIELD = 'f_join_arm'


def admitted(uid: str) -> bool:
    try:
        if not uid or not f_join_enabled():
            return False
        resolved = omi_flags.resolve(F_JOIN_FLAG_KEY, uid)
        if resolved is not None:
            return resolved.enabled
        return f_join_env_admitted(uid)
    except Exception as error:
        logger.warning('event=episode_f_join outcome=admission_failed exception_type=%s', type(error).__name__)
        return False


def arm_fields(uid: str) -> dict[str, str]:
    """Attach to a newly opened episode: the arm live at open, for the closed-size metrics."""
    try:
        return {ARM_FIELD: 'f' if admitted(uid) else 'control'}
    except Exception:
        return {}


def latest_member(episode: Mapping[str, Any], exclude: str) -> Optional[str]:
    """The member with the latest recorded activity, other than ``exclude`` (the candidate)."""
    activity = episode.get('member_activity') or {}
    members = [cid for cid in episode.get('conversation_ids') or [] if cid != exclude]
    if not members:
        return None

    def recency(item: tuple[int, str]) -> tuple[bool, float, int]:
        at = policy.utc(activity.get(item[1]))
        return at is not None, at.timestamp() if at else 0.0, item[0]

    return max(enumerate(members), key=recency)[1]


def uncertain(
    uid: str,
    owner: Optional[Mapping[str, Any]],
    conversation_id: str,
    source: Optional[str],
    started_at: datetime,
    *,
    firestore_client: Any = None,
) -> Optional[policy.Boundary]:
    """The ambiguous decision for an admitted join to a live owner after a 2 to 30 minute gap, else None."""
    if not owner or not policy.is_live(owner) or not admitted(uid):
        return None
    facts = policy.MomentFacts(
        conversation_id=conversation_id,
        source=source,
        started_at=started_at,
        ended_at=started_at,
        calendar_identity=None,
        speakers=frozenset(),
    )
    legacy = policy.boundary(owner, facts)
    if legacy.action != policy.ASK or (legacy.gap_seconds or 0.0) < CONTINUE_GAP_SECONDS:
        return None
    # The active meeting authority can keep this join whole; only an ASK it does not override is F's.
    authoritative = boundary_runtime.decision(uid, owner, facts, legacy, firestore_client=firestore_client)
    return legacy if authoritative.action == policy.ASK else None


def mark_pending(
    uid: str,
    owner: Mapping[str, Any],
    placed: Mapping[str, Any],
    conversation_id: str,
    decision: policy.Boundary,
    pending: Mapping[str, Any],
    firestore_client: Any,
) -> None:
    """Keep the time-only join (Home hides it under the live row) and mark it for F at its first moment.

    A lost compare-and-swap or any error leaves today's join unmarked.
    """
    if str(placed.get('id')) != str(owner.get('id')) or not policy.is_live(placed):
        return
    marker = {
        'gap_seconds': decision.gap_seconds or 0.0,
        'source_changed': decision.source_changed,
        'variant': F_JOIN_VARIANT,
        'previous': latest_member(owner, conversation_id),
    }
    try:
        episodes_db.commit_moment(
            uid,
            expected_episode_id=str(placed['id']),
            expected_version=placed.get('state_version'),
            updates={'pending_boundary': {**pending, conversation_id: marker}},
            firestore_client=firestore_client,
        )
        metrics.record_boundary('f_pending')
    except EpisodeConflict:
        metrics.record_boundary('f_pending_conflict')
        _fallback('other')
    except Exception as error:
        metrics.record_boundary('f_pending_error')
        _fallback('other')
        logger.warning('event=episode_f_join outcome=pending_failed exception_type=%s', type(error).__name__)


def previous_transcript(
    uid: str,
    episode: Mapping[str, Any],
    conversation_id: str,
    pending: Mapping[str, Any],
    name: Callable[[Sequence[Mapping[str, Any]]], Sequence[Mapping[str, Any]]],
    firestore_client: Any,
) -> str:
    """The predecessor recorded when the join was marked, rendered as variant F saw it."""
    previous = pending.get('previous') or latest_member(episode, conversation_id)
    if not previous:
        return ''
    row = conversations_db.get_conversation(uid, str(previous), firestore_client=firestore_client) or {}
    segments = [s for s in row.get('transcript_segments') or [] if isinstance(s, Mapping)]
    return incremental.render_f_transcript(name(segments))


def _fallback(reason: str) -> None:
    record_fallback(
        component='episode_f_join',
        from_mode='jev_f',
        to_mode='time_join',
        reason=reason,
        outcome='degraded',
        log=logger,
    )


def later_member(episode: Mapping[str, Any], conversation_id: str, started_at: datetime) -> bool:
    """Another member recorded past the candidate's start. A split would leave the episode's recorded end
    past the successor's start (recorded_window_overlap), so such a join keeps today's shape."""
    start = policy.utc(started_at)
    if start is None:
        return False
    activity = episode.get('member_activity') or {}
    for cid in episode.get('conversation_ids') or []:
        if cid == conversation_id:
            continue
        at = policy.utc(activity.get(cid))
        if at is not None and at > start:
            return True
    return False


def _split_still_clear(
    uid: str, episode: Mapping[str, Any], conversation_id: str, started_at: datetime, c: Any
) -> bool:
    """Re-reads the episode after Jev answered: a split is clear only while the episode is live and no
    member recorded past the candidate's start. An unreadable episode keeps today's join."""
    try:
        fresh = episodes_db.get_episode(uid, str(episode['id']), firestore_client=c.firestore_client)
    except Exception as error:
        logger.warning('event=episode_f_join outcome=recheck_failed exception_type=%s', type(error).__name__)
        _fallback('other')
        return False
    if fresh is None:
        return False
    return policy.is_live(fresh) and not later_member(fresh, conversation_id, started_at)


def settle(
    uid: str,
    episode: Mapping[str, Any],
    conversation_id: str,
    pending: Mapping[str, Any],
    named: Sequence[Mapping[str, Any]],
    name: Callable[[Sequence[Mapping[str, Any]]], Sequence[Mapping[str, Any]]],
    c: Any,
    *,
    started_at: datetime,
) -> policy.Boundary:
    """F's answer for a marked join. Killed, no answer, an error or a timeout keeps today's join."""
    gap = float(pending.get('gap_seconds') or 0.0)
    source_changed = bool(pending.get('source_changed'))
    keep = policy.Boundary(policy.CONTINUE, gap_seconds=gap, source_changed=source_changed)
    if not admitted(uid):
        metrics.record_boundary('f_disabled')
        return keep
    if later_member(episode, conversation_id, started_at):
        # Settled without a question: the candidate's split would overlap a member that recorded later.
        metrics.record_boundary('f_later_member')
        return keep
    try:
        previous = previous_transcript(uid, episode, conversation_id, pending, name, c.firestore_client)
    except Exception as error:
        logger.warning('event=episode_f_join outcome=previous_failed exception_type=%s', type(error).__name__)
        metrics.record_boundary('f_no_answer')
        _fallback('other')
        return keep
    state = incremental.f_boundary_state(previous, incremental.render_f_transcript(named))
    p_same = incremental.ask_same_occasion_f(state, ask=c.ask)
    if p_same is None:
        metrics.record_boundary('f_no_answer')
        _fallback('unknown')
        return keep
    if p_same < MOVED_ON_THRESHOLD and not _split_still_clear(uid, episode, conversation_id, started_at, c):
        # A member attached while Jev was answering; the split would now overlap it.
        metrics.record_boundary('f_later_member')
        return keep
    if p_same < MOVED_ON_THRESHOLD:
        metrics.record_boundary('f_close')
        reason = 'source_change' if source_changed else 'moved_on'
        return policy.Boundary('close', reason, gap_seconds=gap, source_changed=source_changed)
    metrics.record_boundary('f_continue')
    return keep


def record_closed_size(closed: Mapping[str, Any]) -> None:
    """Members and recorded span of a closed episode by the arm it opened under (pre-ramp episodes: none)."""
    try:
        arm = closed.get(ARM_FIELD)
        if arm not in ('f', 'control'):
            return
        start, end = policy.utc(closed.get('started_at')), policy.utc(closed.get('closed_at'))
        span = (end - start).total_seconds() if start and end else None
        metrics.record_closed_size(arm, len(closed.get('conversation_ids') or []), span)
    except Exception:
        pass
