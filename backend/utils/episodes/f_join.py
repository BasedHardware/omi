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
from typing import Any, Mapping, Optional, Sequence

from config.episodes import (
    CONTINUE_GAP_SECONDS,
    F_JOIN_FLAG_KEY,
    F_JOIN_VARIANT,
    MOVED_ON_THRESHOLD,
    f_join_enabled,
    f_join_env_admitted,
    EPISODE_F_JOIN_PERCENT_ENV,
    F_JOIN_NEW_CHARS,
    F_JOIN_PREVIOUS_CHARS,
    F_JOIN_PEOPLE_READ_LIMIT,
)
from config.jev_decisions import percentage
from database._client import get_firestore_client
from database import conversations as conversations_db
from database import episodes as episodes_db
from database.episodes import EpisodeConflict
from utils import omi_flags
from utils.episodes import boundary_runtime, incremental, metrics, policy, moment_render
from utils.episodes.visibility import hidden_member
from utils.sync.processing_hold import FIELD as HOLD_FIELD
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
ARM_FIELD = 'f_join_arm'
# Marking a join re-reads the live episode after a lost compare-and-swap: one try plus two retries.
MARK_PENDING_ATTEMPTS = 3


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
    if not uid or not f_join_enabled():
        return {}
    try:
        rule = omi_flags.snapshot().rules.get(F_JOIN_FLAG_KEY)
        if rule is not None:
            if not rule.active or (rule.rollout_percentage <= 0 and uid not in rule.allow_uids):
                return {}
            enabled = omi_flags.evaluate(rule, uid).enabled
        else:
            if percentage(EPISODE_F_JOIN_PERCENT_ENV, default=0.0) <= 0:
                return {}
            enabled = f_join_env_admitted(uid)
        return {ARM_FIELD: 'f' if enabled else 'control'}
    except Exception:
        return {}


def latest_member(episode: Mapping[str, Any], exclude: str) -> Optional[str]:
    """The member with the latest recorded activity, other than ``exclude`` (the candidate)."""
    activity = episode.get('member_activity') or {}
    hidden = set(episode.get('discarded_conversation_ids') or []) | set(episode.get('duplicate_conversation_ids') or [])
    members = [cid for cid in episode.get('conversation_ids') or [] if cid != exclude and cid not in hidden]
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
    episode_id = str(placed['id'])
    version = placed.get('state_version')
    for attempt in range(MARK_PENDING_ATTEMPTS):
        try:
            episodes_db.commit_moment(
                uid,
                expected_episode_id=episode_id,
                expected_version=version,
                updates={'pending_boundary': {**pending, conversation_id: marker}},
                firestore_client=firestore_client,
            )
            metrics.record_boundary('f_pending')
            return
        except EpisodeConflict as conflict:
            # A live episode takes a write on every moment, so the version read at attach is often stale
            # by now. Re-read and retry while the join still stands; otherwise today's join is kept.
            reason = str(conflict) or 'conflict'
            fresh = None
            if attempt + 1 < MARK_PENDING_ATTEMPTS:
                try:
                    fresh = episodes_db.get_episode(
                        uid, episode_id, firestore_client=firestore_client, follow_redirects=False
                    )
                except Exception:
                    fresh = None
            if (
                fresh is None
                or not policy.is_live(fresh)
                or conversation_id not in (fresh.get('conversation_ids') or [])
                or conversation_id in (fresh.get('pending_boundary') or {})
            ):
                metrics.record_boundary('f_pending_conflict')
                _fallback('other', site='pending_conflict')
                logger.warning(
                    'event=episode_f_join outcome=pending_conflict reason=%s attempts=%d', reason, attempt + 1
                )
                return
            version = fresh.get('state_version')
            pending = fresh.get('pending_boundary') or {}
        except Exception as error:
            metrics.record_boundary('f_pending_error')
            _fallback('other', site='pending_error')
            logger.warning('event=episode_f_join outcome=pending_failed exception_type=%s', type(error).__name__)
            return


def synced_failed(error: BaseException) -> None:
    """A sync or late join's F decision raised: today's time-only join stands and the fallback is reported."""
    _fallback('other', site='synced_failed')
    logger.warning('event=episode_f_join outcome=synced_failed exception_type=%s', type(error).__name__)


def previous_transcript(
    uid: str,
    episode: Mapping[str, Any],
    conversation_id: str,
    pending: Mapping[str, Any],
    c: Any,
    *,
    people_read_limit: int = F_JOIN_PEOPLE_READ_LIMIT,
) -> str:
    """Read one retained predecessor, rechecking processing visibility before decoding or naming.

    No photos or people projections: one conversation document and at most eight name documents.
    The ordinary owner-only sharing visibility (``private``) does not block owner processing.
    """
    # An explicit None is a pinned absence, not permission to choose a later attachment.
    previous = pending['previous'] if 'previous' in pending else latest_member(episode, conversation_id)
    hidden = set(episode.get('discarded_conversation_ids') or []) | set(episode.get('duplicate_conversation_ids') or [])
    if (
        not previous
        or previous == conversation_id
        or previous not in (episode.get('conversation_ids') or [])
        or previous in hidden
    ):
        return ''
    row = conversations_db.get_conversation_raw_snapshot(uid, str(previous), firestore_client=c.firestore_client)
    if not row or not _may_feed_llm(uid, row):
        return ''
    segments = conversations_db.decode_transcript_segments_blob(
        uid, row.get('transcript_segments'), bool(row.get('transcript_segments_compressed')), require_decryption=True
    )
    selected = _transcript_tail(segments)
    person_ids = list(
        dict.fromkeys(str(s['person_id']) for s in selected if s.get('person_id') and not s.get('is_user'))
    )[:people_read_limit]
    names = {}
    if person_ids:
        if c.people_names is not None:
            names = c.people_names(uid, person_ids)
        else:
            client = c.firestore_client if c.firestore_client is not None else get_firestore_client()
            people = client.collection('users').document(uid).collection('people')
            for person_id in person_ids:
                person = people.document(person_id).get(field_paths=['name']).to_dict() or {}
                names[person_id] = str(person.get('name') or '')
    return incremental.render_f_transcript(moment_render.name_segments(selected, names))


def may_feed_llm(uid: str, row: Mapping[str, Any]) -> bool:
    """The privacy gate for any conversation whose speech F may send to Jev, as predecessor or candidate.

    Fail-closed: a missing required field is not permission (``is_locked`` and ``discarded`` must be False).
    """
    return gate_refusal_reason(uid, row) is None


def gate_refusal_reason(uid: str, row: Mapping[str, Any]) -> Optional[str]:
    """First refusal in the privacy gate's evaluation order; no additional reads."""
    # Reuse the episode composer/build visibility predicates. Missing required processing metadata
    # is unknown, not permission; optional tombstone/redirect fields retain their schema defaults.
    if row.get('owner_uid', uid) != uid or row.get('uid', uid) != uid:
        return 'owner'
    if row.get('data_protection_level') not in {'standard', 'enhanced'}:
        return 'row_consent'
    # Private cloud sync is the user's retention consent. Only an explicit True permits speech to reach Jev;
    # an absent or false value keeps today's join (the same explicit-opt-in rule as the batch attach gate).
    if row.get('private_cloud_sync_enabled') is not True:
        return 'row_consent'
    if row.get('is_locked') is not False or row.get('discarded') is not False:
        return 'locked_discarded'
    if any(row.get(key, False) is not False for key in ('deleted', 'deferred', 'processing_deferred')):
        return 'deferred'
    if row.get('status') not in {'completed', 'processing', 'in_progress'}:
        return 'status'
    if row.get('processing_state') == 'local_pending':
        return 'local_pending'
    if row.get('terminal_no_derived_effects'):
        return 'other'
    if row.get('client_processing'):
        return 'client_processing'
    if row.get('summary_blocked_reason') == 'local_only':
        return 'local_only'
    hold = row.get(HOLD_FIELD, {})
    if not isinstance(hold, Mapping) or hold.get('held', False) is not False:
        return 'held'
    if hidden_member(dict(row)) or not conversations_db.is_visible_conversation(row):
        return 'hidden'
    return None


# ``previous_transcript`` is a pinned People-reader body (backend/docs/people-generation-writers.json), so it keeps
# calling the private name. Changing that call would invalidate the audit without changing what is checked.
_may_feed_llm = may_feed_llm


def _transcript_tail(segments: Sequence[Any]) -> list[dict[str, Any]]:
    """Keep a bounded text tail before collecting any person ids for naming."""
    rows = sorted(
        (s for s in segments if isinstance(s, Mapping) and str(s.get('text') or '').strip()),
        key=lambda s: float(s.get('start') or 0.0),
    )
    selected = []
    remaining = F_JOIN_PREVIOUS_CHARS
    for segment in reversed(rows):
        if remaining <= 0:
            break
        text = str(segment['text']).strip()[-remaining:]
        selected.append({**segment, 'text': text})
        remaining -= len(text) + 1
    return list(reversed(selected))


def candidate_head(segments: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The candidate's first ``F_JOIN_NEW_CHARS`` of speech, naming at most ``F_JOIN_PEOPLE_READ_LIMIT`` voices.

    Bounded before any name lookup, so a long transcript costs the spec's reads and not one per voice.
    Only the head reaches Jev (``f_boundary_state``), so the rest is never needed for naming.
    """
    rows = sorted(
        (s for s in segments if str(s.get('text') or '').strip()),
        key=lambda s: float(s.get('start') or 0.0),
    )
    head: list[dict[str, Any]] = []
    remaining = F_JOIN_NEW_CHARS
    for segment in rows:
        if remaining <= 0:
            break
        text = str(segment['text']).strip()[:remaining]
        head.append({**segment, 'text': text})
        remaining -= len(text) + 1
    named_ids = list(dict.fromkeys(str(s['person_id']) for s in head if s.get('person_id')))
    allowed = set(named_ids[:F_JOIN_PEOPLE_READ_LIMIT])
    capped: list[dict[str, Any]] = []
    for segment in head:
        person = str(segment.get('person_id') or '')
        if person and person not in allowed:
            segment = {key: value for key, value in segment.items() if key != 'person_id'}
        capped.append(segment)
    return capped


def _candidate_refusal_reason(
    uid: str, conversation_id: str, row: Optional[Mapping[str, Any]], c: Any
) -> Optional[str]:
    """The candidate's own privacy gate. A caller that holds the row passes it; otherwise one snapshot read."""
    if row is None:
        row = conversations_db.get_conversation_raw_snapshot(uid, conversation_id, firestore_client=c.firestore_client)
    return gate_refusal_reason(uid, row) if row else 'other'


def _user_consent_allows(uid: str, c: Any) -> bool:
    """The user's current private cloud sync consent, checked just before Jev.

    The conversation row carries a snapshot of the consent, so a toggle after the row was written is seen here.
    A missing user document or field is not permission (fail closed).
    """
    client = c.firestore_client if c.firestore_client is not None else get_firestore_client()
    snapshot = client.collection('users').document(uid).get(field_paths=['private_cloud_sync_enabled'])
    data = snapshot.to_dict() or {}
    return data.get('private_cloud_sync_enabled') is True


def _fallback(reason: str, *, site: str) -> None:
    metrics.record_f_fallback(site)
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
    uid: str, episode: Mapping[str, Any], conversation_id: str, started_at: datetime, c: Any, *, member: bool = True
) -> bool:
    """Re-reads the episode after Jev answered: a split is clear only while the episode is live and no
    member recorded past the candidate's start. An unreadable episode keeps today's join."""
    try:
        fresh = episodes_db.get_episode_membership_snapshot(
            uid, str(episode['id']), firestore_client=c.firestore_client
        )
    except Exception as error:
        logger.warning('event=episode_f_join outcome=recheck_failed exception_type=%s', type(error).__name__)
        _fallback('other', site='recheck_failed')
        return False
    if fresh is None:
        return False
    return bool(
        fresh
        and not fresh.get('recorded_merged_into')
        and isinstance(fresh.get('conversation_ids'), list)
        and (not member or conversation_id in fresh['conversation_ids'])
        and isinstance(fresh.get('member_activity'), Mapping)
        and policy.is_live(fresh)
        and not later_member(fresh, conversation_id, started_at)
    )


def settle(
    uid: str,
    episode: Mapping[str, Any],
    conversation_id: str,
    pending: Mapping[str, Any],
    named: Sequence[Mapping[str, Any]],
    c: Any,
    *,
    started_at: datetime,
    member: bool = True,
    candidate_row: Optional[Mapping[str, Any]] = None,
    people_read_limit: int = F_JOIN_PEOPLE_READ_LIMIT,
) -> policy.Boundary:
    """F's answer for a marked join. Killed, no answer, an error or a timeout keeps today's join.

    ``member=False`` answers for a candidate not yet in the episode (a sync or late conversation placed
    after the answer); the split then needs only the episode still live and no later member.
    """
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
        # Predecessor and name reads come first. The candidate's stored privacy is checked just before Jev,
        # so a lock, deletion, discard or consent change during those reads still keeps today's join.
        previous = previous_transcript(uid, episode, conversation_id, pending, c, people_read_limit=people_read_limit)
    except Exception as error:
        logger.warning('event=episode_f_join outcome=previous_failed exception_type=%s', type(error).__name__)
        metrics.record_boundary('f_no_answer')
        _fallback('other', site='previous_failed')
        return keep
    try:
        # The candidate's stored privacy, then the user's current consent, before the ownership recheck.
        refusal = _candidate_refusal_reason(uid, conversation_id, candidate_row, c)
        if refusal is None and not _user_consent_allows(uid, c):
            refusal = 'user_consent'
        allowed = refusal is None
    except Exception as error:
        logger.warning('event=episode_f_join outcome=gate_failed exception_type=%s', type(error).__name__)
        metrics.record_boundary('f_no_answer')
        _fallback('other', site='gate_failed')
        return keep
    if not allowed:
        # Locked, deferred, local-only, held, opted out or another owner's conversation: its speech never reaches Jev.
        metrics.record_f_gate(refusal or 'other')
        metrics.record_boundary('f_no_answer')
        return keep
    if not previous:
        metrics.record_boundary('f_no_answer')
        _fallback('unknown', site='unknown_previous')
        return keep
    state = incremental.f_boundary_state(previous, incremental.render_f_transcript(named))
    if not member:
        # Sync/late candidates must still be unplaced after predecessor, name and privacy reads.
        # This narrows the race window; another request can still attach after this snapshot.
        try:
            owner = episodes_db.get_episode_owner_snapshot(uid, conversation_id, firestore_client=c.firestore_client)
        except Exception as error:
            logger.warning('event=episode_f_join outcome=recheck_failed exception_type=%s', type(error).__name__)
            metrics.record_boundary('f_no_answer')
            _fallback('other', site='recheck_failed_settle')
            return keep
        if owner is not None:
            metrics.record_boundary('f_no_answer')
            return keep
    p_same = incremental.ask_same_occasion_f(state, ask=c.ask)
    if p_same is None:
        metrics.record_boundary('f_no_answer')
        _fallback('unknown', site='unknown_jev')
        return keep
    if p_same < MOVED_ON_THRESHOLD and not _split_still_clear(
        uid, episode, conversation_id, started_at, c, member=member
    ):
        # A member attached while Jev was answering; the split would now overlap it.
        metrics.record_boundary('f_later_member')
        return keep
    if p_same < MOVED_ON_THRESHOLD:
        metrics.record_boundary('f_close')
        reason = 'source_change' if source_changed else 'moved_on'
        return policy.Boundary('close', reason, gap_seconds=gap, source_changed=source_changed)
    metrics.record_boundary('f_continue')
    return keep


def record_orphans(uid: str, detached: set[str], c: Any) -> None:
    """Observe each actual F detach once after record_moment's bounded retries.

    At most two owner-link/episode reads for the one candidate in this call.
    A transient gap between close and a successful successor is not an orphan.
    No reads occur for flag-off or non-splitting moments (``detached`` is empty).
    """
    for conversation_id in detached:
        try:
            owner = episodes_db.get_episode_owner_snapshot(uid, conversation_id, firestore_client=c.firestore_client)
            if owner and (
                owner.get('recorded_merged_into')
                or owner.get('status') not in {'live', 'closed'}
                or not isinstance(owner.get('conversation_ids'), list)
            ):
                raise EpisodeConflict('unknown_owner')
            orphan = (
                not owner or not policy.is_live(owner) or conversation_id not in (owner.get('conversation_ids') or [])
            )
        except Exception as error:
            metrics.record_boundary('f_orphan_check_error')
            logger.warning('event=episode_f_join_orphan outcome=check_failed exception_type=%s', type(error).__name__)
            continue
        if orphan:
            metrics.record_boundary('f_orphan')
            logger.error('event=episode_f_join_orphan outcome=no_live_successor')


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
