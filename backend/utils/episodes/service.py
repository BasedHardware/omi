"""Episode orchestration: moments in, compact state out, conversations untouched.

Entry points (all synchronous, fail-open, run on a worker thread by callers):

- ``attach_conversation``: a conversation's first live speech. Open or join the
  live episode by the cheap rules alone, with no model call, so the episode, its
  start and its member conversations exist from the first words. An ambiguous
  gap joins provisionally (``pending_boundary``) and the conversation's first
  moment settles it with Jev, splitting it off when the user moved on.
- ``record_moment``: a moment ended (a pause or a word-budget rollover in the
  live stream, or its conversation finalized). Decide the boundary, run the one
  cheap incremental update on the previous state plus this moment's new text,
  and store the result with a compare-and-swap.
- ``on_conversation_finalized``: the conversation's normal processing has
  completed. Apply any trailing text the live stream did not deliver, then
  reconcile the provisional items heard in it against the tasks that
  processing saved (the shadow precision metric).
- ``close_on_finalize``: a conversation just ended (a client finalize, or the
  server ending an occasion conversation). Its live episode closes at once, and
  the next words open a new one. The ended conversation never reopens it or
  opens another; its tail and reconciliation land on the closed episode.
- ``wrap_up``: the user asked to wrap up now; the episode closes at once.
- ``live_episode`` / ``episode_for_conversation``: reads for the API, which
  close an idle live episode lazily.

Nothing here writes a conversation, an action item or a memory.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Optional, Sequence
from uuid import uuid4

from config.episodes import CLOSE_GAP_SECONDS, MOMENT_MIN_INTERVAL_SECONDS, MOMENT_MIN_WORDS, episodes_enabled_for
from database import action_items as action_items_db
from database import episodes as episodes_db
from database import notifications as notification_db
from database import users as users_db
from utils.episodes import moment_render, boundary_runtime
from utils.episodes.output_language import resolved_invoke
from utils.episodes import client_gate, incremental, metrics, policy
from utils.episodes.moment import MomentInput
from utils.episodes.state import apply_update, clean_text, provisional_items, render_state

logger = logging.getLogger(__name__)

RECONCILE_TRIGGERS = frozenset({'capture_end', 'client_finalize', 'server_recovery'})
CLIENT_FINALIZE = 'client_finalize'
# A finalization tail this short only costs a call when it might hold a request to Omi.
FINALIZE_MIN_WORDS = 8


@dataclass
class Collaborators:
    """Seams for tests; production uses the module defaults."""

    invoke: Optional[Callable[..., Any]] = None
    ask: Optional[Callable[..., Any]] = None
    tz_name: Optional[str] = None
    firestore_client: Any = None
    saved_tasks: Optional[Callable[[str, str], list[dict]]] = None
    people_names: Optional[Callable[[str, list[str]], dict[str, str]]] = None
    now: Optional[Callable[[], datetime]] = None
    extras: dict[str, Any] = field(default_factory=dict)


def _now(c: Collaborators) -> datetime:
    return c.now() if c.now else datetime.now(timezone.utc)


def _segment_end(segment: Mapping[str, Any]) -> float:
    try:
        return float(segment.get('end') or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _segment_start(segment: Mapping[str, Any]) -> float:
    try:
        return float(segment.get('start') or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _tz(uid: str, c: Collaborators) -> str:
    if c.tz_name:
        return c.tz_name
    try:
        return notification_db.get_user_time_zone(uid) or 'UTC'
    except Exception:
        return 'UTC'


def _named_segments(uid: str, segments: Sequence[Mapping[str, Any]], c: Collaborators) -> list[dict[str, Any]]:
    """Attach stored person names so the model never sees only "Speaker 2" for a known voice."""
    person_ids = sorted({str(s['person_id']) for s in segments if s.get('person_id')})
    names: dict[str, str] = {}
    if person_ids:
        try:
            if c.people_names is not None:
                names = c.people_names(uid, person_ids)
            else:
                names = {
                    str(person.get('id')): str(person.get('name') or '')
                    for person in users_db.get_people_by_ids(uid, person_ids)
                    if person.get('id')
                }
        except Exception as error:
            logger.warning('event=episode_moment people_lookup_failed exception_type=%s', type(error).__name__)
    return moment_render.name_segments(segments, names)


def _empty_episode(moment: MomentInput, now: datetime) -> dict[str, Any]:
    return new_episode(
        conversation_id=moment.conversation_id,
        started_at=moment.started_at,
        last_activity_at=moment.ended_at,
        calendar_identity=moment.calendar_identity,
        now=now,
    )


def new_episode(
    *,
    conversation_id: str,
    started_at: datetime,
    last_activity_at: datetime,
    calendar_identity: Optional[str],
    now: datetime,
) -> dict[str, Any]:
    return {
        'id': episodes_db.new_episode_id(),
        'status': 'live',
        'started_at': started_at,
        'last_activity_at': last_activity_at,
        'closed_at': None,
        'close_reason': None,
        'title': '',
        'bullets': [],
        'people': [],
        'open_questions': [],
        'provisional_items': [],
        'moments': [],
        'conversation_ids': [],
        'sources': [],
        'applied': {},
        'calendar_identity': calendar_identity,
        'pending_boundary': {},
        'primary_conversation_id': conversation_id,
        'closing_conversation_id': None,
        'wrap_up_requested_at': None,
        'state_updated_at': None,
        'created_at': now,
        'usage': {'calls': 0, 'input_tokens': 0, 'output_tokens': 0},
    }


def _with_conversation(episode: Mapping[str, Any], conversation_id: str, source: Optional[str]) -> dict[str, Any]:
    ids = list(episode.get('conversation_ids') or [])
    if conversation_id not in ids:
        ids.append(conversation_id)
    sources = list(episode.get('sources') or [])
    if source and source not in sources:
        sources.append(source)
    return {'conversation_ids': ids, 'sources': sources}


def _close(
    uid: str,
    episode: Mapping[str, Any],
    reason: str,
    c: Collaborators,
    *,
    now: datetime,
    detach: Optional[str] = None,
    closing: Optional[str] = None,
    extra_fields: Optional[Mapping[str, Any]] = None,
) -> None:
    """Close once; resolve any provisional item still open as dropped (never a task).

    ``detach`` removes a conversation that joined provisionally and turned out to
    start the next occasion; its link is rewritten by the episode it opens.
    ``closing`` is the conversation whose end closes the episode: its items stay
    provisional until its processing reconciles them, and it never reopens this
    episode or opens another (``_closed_owner``).
    """
    items = provisional_items(episode)
    dropped = 0
    for item in items:
        if item.get('status') == 'provisional' and item.get('conversation_id') not in {detach, closing}:
            item['status'] = 'dropped'
            dropped += 1
    # A provisional join still unsettled at close stays with this episode (it joined on the cheap rules).
    extra: dict[str, Any] = {'provisional_items': items, 'pending_boundary': {}, **(extra_fields or {})}
    if closing:
        extra['closing_conversation_id'] = closing
    if detach:
        extra['conversation_ids'] = [cid for cid in episode.get('conversation_ids') or [] if cid != detach]
        extra['provisional_items'] = [item for item in items if item.get('conversation_id') != detach]
    closed = episodes_db.close_episode(
        uid,
        str(episode['id']),
        reason,
        closed_at=_idle_closed_at(episode, now) if reason == 'idle' else now,
        extra=extra,
        firestore_client=c.firestore_client,
    )
    if closed is not None:
        metrics.record_episode_closed(reason)
        metrics.record_provisional_outcomes({'dropped': dropped})


def _pending(episode: Optional[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Provisional joins awaiting their first moment, by conversation id."""
    raw = (episode or {}).get('pending_boundary')
    return {str(k): dict(v) for k, v in raw.items() if isinstance(v, Mapping)} if isinstance(raw, Mapping) else {}


def _idle_closed_at(episode: Mapping[str, Any], now: datetime) -> datetime:
    """An idle episode ended when its quiet reached the close gap, not when a later read noticed."""
    last = policy.utc(episode.get('last_activity_at'))
    return min(now, last + timedelta(seconds=CLOSE_GAP_SECONDS)) if last else now


def _close_stale_current(uid: str, episode: Optional[Mapping[str, Any]], c: Collaborators, now: datetime):
    """Close an idle live episode, or one a wrap-up left live (written before wrap-ups closed at once)."""
    if episode is not None and policy.idle_close_due(episode, now):
        _close(uid, episode, 'idle', c, now=now)
        return None
    if _close_pending_wrap_up(uid, episode, c, now):
        return None
    return episode


def _close_pending_wrap_up(uid: str, episode: Optional[Mapping[str, Any]], c: Collaborators, now: datetime) -> bool:
    if episode is None or not policy.is_live(episode) or not episode.get('wrap_up_requested_at'):
        return False
    _close(uid, episode, 'user', c, now=now, closing=episode.get('closing_conversation_id') or None)
    return True


def _closed_owner(
    uid: str, episode: Optional[Mapping[str, Any]], moment: MomentInput, c: Collaborators
) -> Optional[dict[str, Any]]:
    """The closed episode a conversation stays with, when it may not feed the live one.

    A conversation whose end closed its episode, and any conversation's
    finalization tail, belong to the episode they were in: they never reopen it
    and never open or join another by themselves. The next live words do that.
    """
    if episode and moment.conversation_id in (episode.get('conversation_ids') or []):
        return None
    owner = episodes_db.get_episode_for_conversation(uid, moment.conversation_id, firestore_client=c.firestore_client)
    if not owner or policy.is_live(owner):
        return None
    if moment.trigger == 'finalize' or owner.get('closing_conversation_id') == moment.conversation_id:
        return owner
    return None


def attach_conversation(
    uid: str,
    conversation_id: str,
    source: Optional[str],
    *,
    started_at: datetime,
    collaborators: Optional[Collaborators] = None,
) -> str:
    """A conversation's first live speech joins or opens the live episode. No model call; never raises."""
    c = collaborators or Collaborators()
    if not episodes_enabled_for(uid) or not conversation_id:
        return 'disabled'
    outcome = 'conflict'
    for _ in range(2):
        try:
            outcome = _attach_once(uid, conversation_id, source, started_at, c)
        except episodes_db.EpisodeConflict:
            outcome = 'conflict'
            continue
        except Exception as error:
            logger.warning('event=episode_attach outcome=error exception_type=%s', type(error).__name__)
            outcome = 'error'
        break
    return outcome


def _attach_once(uid: str, conversation_id: str, source: Optional[str], started_at: datetime, c: Collaborators) -> str:
    now = _now(c)
    episode = _close_stale_current(
        uid, episodes_db.get_current_episode(uid, firestore_client=c.firestore_client), c, now
    )
    if episode and conversation_id in (episode.get('conversation_ids') or []):
        return 'attached'
    owner = episodes_db.get_episode_for_conversation(uid, conversation_id, firestore_client=c.firestore_client)
    if owner and (episode is None or owner.get('closing_conversation_id') == conversation_id):
        # Already owned by a closed episode (it finalized first, or its end closed it): never reopen
        # that one, and never carry it into the next.
        return 'attached'
    facts = policy.MomentFacts(
        conversation_id=conversation_id,
        source=source,
        started_at=started_at,
        ended_at=started_at,
        calendar_identity=None,
        speakers=frozenset(),
    )
    decision = boundary_runtime.decision(
        uid, episode, facts, policy.boundary(episode, facts), firestore_client=c.firestore_client
    )
    if decision.action == 'close' and episode:
        metrics.record_boundary('close')
        _close(uid, episode, decision.reason or 'gap', c, now=now)
        episode = None
    if episode is None:
        metrics.record_boundary('new')
        base = new_episode(
            conversation_id=conversation_id,
            started_at=started_at,
            last_activity_at=started_at,
            calendar_identity=None,
            now=now,
        )
        episodes_db.commit_moment(
            uid,
            expected_episode_id=None,
            expected_version=None,
            new_episode={**base, **_with_conversation(base, conversation_id, source)},
            link_conversation_ids=[conversation_id],
            firestore_client=c.firestore_client,
        )
        return 'opened'
    updates: dict[str, Any] = _with_conversation(episode, conversation_id, source)
    if decision.parallel:
        metrics.record_boundary('parallel')
    else:
        last = policy.utc(episode.get('last_activity_at'))
        updates['last_activity_at'] = max(started_at, last) if last else started_at
    if decision.action == policy.ASK:
        # Join now so the app hides it under the live episode; its first moment asks Jev.
        metrics.record_boundary('pending')
        updates['pending_boundary'] = {
            **_pending(episode),
            conversation_id: {'gap_seconds': decision.gap_seconds or 0.0, 'source_changed': decision.source_changed},
        }
    elif not decision.parallel:
        metrics.record_boundary('continue')
    episodes_db.commit_moment(
        uid,
        expected_episode_id=str(episode['id']),
        expected_version=episode.get('state_version'),
        updates=updates,
        link_conversation_ids=[conversation_id],
        firestore_client=c.firestore_client,
    )
    return 'pending' if decision.action == policy.ASK else 'joined'


def record_moment(uid: str, moment: MomentInput, collaborators: Optional[Collaborators] = None) -> str:
    """Returns a bounded outcome label. Never raises."""
    c = collaborators or Collaborators()
    if not episodes_enabled_for(uid):
        return 'disabled'
    outcome = 'error'
    for _ in range(2):
        try:
            outcome = _record_moment_once(uid, moment, c)
        except episodes_db.EpisodeConflict:
            outcome = 'conflict'
            continue
        except Exception as error:
            logger.warning('event=episode_moment outcome=error exception_type=%s', type(error).__name__)
            outcome = 'error'
        break
    if outcome in {'conflict', 'error'}:
        metrics.record_moment_update(trigger=moment.trigger, outcome=outcome)
    return outcome


def _settle_boundary(
    uid: str,
    episode: Optional[Mapping[str, Any]],
    moment: MomentInput,
    facts: policy.MomentFacts,
    text: str,
    c: Collaborators,
    now: datetime,
):
    """Whether this moment continues, splits from or runs parallel to the live episode.

    Returns ``(episode, pending)`` for the moment to apply (``episode`` is None when it opens a new
    one), or the outcome label when the moment is already handled.
    """
    decision = boundary_runtime.decision(
        uid, episode, facts, policy.boundary(episode, facts), firestore_client=c.firestore_client
    )
    pending = _pending(episode).get(moment.conversation_id)
    if episode and pending is not None and decision.action == policy.CONTINUE:
        # It joined provisionally at its first words; with its text in hand, settle it now.
        decision = policy.Boundary(
            policy.ASK,
            gap_seconds=float(pending.get('gap_seconds') or 0.0),
            source_changed=bool(pending.get('source_changed')),
        )
    detach = moment.conversation_id if pending is not None else None
    if decision.action == policy.ASK and episode:
        prior_speakers = frozenset(episode.get('speaker_keys') or [])
        p_same = incremental.ask_same_occasion(
            incremental.boundary_state(
                episode,
                text,
                gap_seconds=decision.gap_seconds or 0.0,
                source_changed=decision.source_changed,
                episode_source=(episode.get('sources') or [None])[0],
                moment_source=moment.source,
                speakers_changed=bool(prior_speakers) and not (prior_speakers & facts.speakers - {'owner'}),
            ),
            ask=c.ask,
        )
        metrics.record_boundary('jev_no_answer' if p_same is None else 'jev_continue')
        decision = policy.resolve_ask(decision, p_same)
        if p_same is not None and decision.action == 'close':
            metrics.record_boundary('jev_close')
    if decision.action == 'close' and episode:
        metrics.record_boundary('close')
        _close(uid, episode, decision.reason or 'gap', c, now=now, detach=detach)
        episode = None
    elif decision.action == policy.NEW:
        metrics.record_boundary('new')
    elif decision.parallel and episode:
        # Another device's capture of the same stretch: attach it, never feed its text twice.
        metrics.record_boundary('parallel')
        episodes_db.commit_moment(
            uid,
            expected_episode_id=str(episode['id']),
            expected_version=episode.get('state_version'),
            updates=_with_conversation(episode, moment.conversation_id, moment.source),
            link_conversation_ids=[moment.conversation_id],
            firestore_client=c.firestore_client,
        )
        return 'parallel'
    else:
        metrics.record_boundary('continue')
    return episode, pending


def _record_moment_once(uid: str, moment: MomentInput, c: Collaborators) -> str:
    now = _now(c)
    episode = _close_stale_current(
        uid, episodes_db.get_current_episode(uid, firestore_client=c.firestore_client), c, now
    )
    closed = _closed_owner(uid, episode, moment, c)
    if closed is not None:
        if moment.trigger != 'finalize':
            metrics.record_moment_update(trigger=moment.trigger, outcome='skipped_closed')
            return 'skipped_closed'
        # The tail of a conversation whose episode already closed completes that episode's notes.
        episode = closed
    applied_until = -1.0
    if episode and moment.conversation_id in (episode.get('conversation_ids') or []):
        applied_until = float((episode.get('applied') or {}).get(moment.conversation_id, -1.0))
    segments = [s for s in moment.segments if _segment_end(s) > applied_until and str(s.get('text') or '').strip()]
    named = _named_segments(uid, segments, c)
    text = incremental.render_moment(named, uid=uid, conversation_id=moment.conversation_id)
    if text.words == 0:
        metrics.record_moment_update(trigger=moment.trigger, outcome='skipped_applied')
        return 'skipped_applied'
    if text.words < (FINALIZE_MIN_WORDS if moment.trigger == 'finalize' else MOMENT_MIN_WORDS):
        metrics.record_moment_update(trigger=moment.trigger, outcome='skipped_short')
        return 'skipped_short'
    facts = policy.MomentFacts(
        conversation_id=moment.conversation_id,
        source=moment.source,
        started_at=moment.started_at,
        ended_at=moment.ended_at,
        calendar_identity=moment.calendar_identity,
        speakers=policy.speaker_keys(segments),
    )
    pending: Optional[dict[str, Any]] = None
    if closed is None:
        settled = _settle_boundary(uid, episode, moment, facts, text.text, c, now)
        if isinstance(settled, str):
            return settled
        episode, pending = settled

    state_updated_at = policy.utc(episode.get('state_updated_at')) if episode else None
    if (
        moment.trigger == 'pause'
        and state_updated_at is not None
        and (now - state_updated_at).total_seconds() < MOMENT_MIN_INTERVAL_SECONDS
    ):
        metrics.record_moment_update(trigger=moment.trigger, outcome='rate_limited')
        return 'rate_limited'

    base = episode or _empty_episode(moment, now)
    known_ids = [item['id'] for item in provisional_items(base) if item.get('status') == 'provisional']
    try:
        result = incremental.run_incremental_update(
            uid,
            render_state(base),
            text.text,
            known_item_ids=known_ids,
            now=now,
            tz_name=_tz(uid, c),
            invoke=resolved_invoke(uid, moment.language, c.invoke),
            conversation_language=moment.language,
        )
    except incremental.ModelCallFailed as failure:
        metrics.record_moment_update(
            trigger=moment.trigger, outcome=failure.outcome, latency_seconds=failure.latency_seconds
        )
        if episode is None:
            # The notes failed, the occasion did not: open it without notes (a split already closed
            # the old one), so the live row and its hidden fragments survive until the next moment.
            episodes_db.commit_moment(
                uid,
                expected_episode_id=None,
                expected_version=None,
                new_episode={**base, **_with_conversation(base, moment.conversation_id, moment.source)},
                link_conversation_ids=[moment.conversation_id],
                firestore_client=c.firestore_client,
            )
        return failure.outcome

    end_offset = max((_segment_end(s) for s in segments), default=0.0)
    start_offset = min((_segment_start(s) for s in segments), default=0.0)
    changes = apply_update(
        base, result.update, conversation_id=moment.conversation_id, segment_offset=end_offset, now=now
    )
    moments = [dict(m) for m in base.get('moments') or []]
    heading = result.update.moment_heading or clean_text(result.update.title, 48)
    last = moments[-1] if moments else None
    if (
        last
        and last.get('conversation_id') == moment.conversation_id
        and heading
        and str(last.get('heading') or '').casefold() == heading.casefold()
    ):
        last.update({'ended_at': moment.ended_at, 'end_offset': end_offset})
    else:
        moments.append(
            {
                'id': uuid4().hex[:12],
                'conversation_id': moment.conversation_id,
                'started_at': moment.started_at,
                'ended_at': moment.ended_at,
                'start_offset': start_offset,
                'end_offset': end_offset,
                'heading': heading,
            }
        )
    applied = dict(base.get('applied') or {})
    applied[moment.conversation_id] = max(float(applied.get(moment.conversation_id, -1.0)), end_offset)
    usage = dict(base.get('usage') or {})
    usage['calls'] = int(usage.get('calls') or 0) + 1
    usage['input_tokens'] = int(usage.get('input_tokens') or 0) + result.input_tokens
    usage['output_tokens'] = int(usage.get('output_tokens') or 0) + result.output_tokens
    last_activity = policy.utc(base.get('last_activity_at'))
    updates = {
        **changes,
        **_with_conversation(base, moment.conversation_id, moment.source),
        'moments': moments,
        'applied': applied,
        'usage': usage,
        'speaker_keys': sorted(set(base.get('speaker_keys') or []) | set(facts.speakers)),
        'last_activity_at': max(moment.ended_at, last_activity) if last_activity else moment.ended_at,
        'calendar_identity': base.get('calendar_identity') or moment.calendar_identity,
    }
    if pending is not None:
        updates['pending_boundary'] = {k: v for k, v in _pending(base).items() if k != moment.conversation_id}
    if episode is None:
        episodes_db.commit_moment(
            uid,
            expected_episode_id=None,
            expected_version=None,
            new_episode={**base, **updates},
            link_conversation_ids=[moment.conversation_id],
            firestore_client=c.firestore_client,
        )
    elif closed is not None:
        episodes_db.update_episode(
            uid,
            str(episode['id']),
            expected_version=int(episode.get('state_version') or 0),
            updates=updates,
            firestore_client=c.firestore_client,
        )
    else:
        episodes_db.commit_moment(
            uid,
            expected_episode_id=str(episode['id']),
            expected_version=episode.get('state_version'),
            updates=updates,
            link_conversation_ids=[moment.conversation_id],
            firestore_client=c.firestore_client,
        )
    metrics.record_moment_update(
        trigger=moment.trigger,
        outcome='applied',
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_seconds=result.latency_seconds,
    )
    return 'applied'


# --------------------------------------------------------------------------- finalization


def _wall(base: Optional[datetime], offset: float) -> Optional[datetime]:
    return base + timedelta(seconds=max(0.0, offset)) if base else None


def _saved_tasks(uid: str, conversation_id: str, c: Collaborators) -> list[dict]:
    if c.saved_tasks is not None:
        return c.saved_tasks(uid, conversation_id)
    return action_items_db.get_action_items_by_conversation(uid, conversation_id)


def on_conversation_finalized(
    uid: str,
    conversation_id: str,
    row: Mapping[str, Any],
    *,
    trigger: str,
    absorbed_from: Optional[str] = None,
    collaborators: Optional[Collaborators] = None,
) -> str:
    """After the conversation's normal processing. Returns an outcome label; never raises."""
    c = collaborators or Collaborators()
    if not episodes_enabled_for(uid) or trigger not in RECONCILE_TRIGGERS:
        return 'skipped'
    try:
        if not client_gate.client_seen(uid):
            # No app of this user can show episodes: no tail update, no reconciliation reads.
            metrics.record_moment_skipped_no_client('finalize')
            return 'skipped_no_client'
        return _on_finalized(uid, conversation_id, row, trigger, absorbed_from, c)
    except Exception as error:
        logger.warning('event=episode_finalize outcome=error exception_type=%s', type(error).__name__)
        return 'error'


def close_on_finalize(
    uid: str,
    conversation_id: str,
    *,
    trigger: str,
    source: Any = None,
    collaborators: Optional[Collaborators] = None,
) -> str:
    """A conversation just ended: close the live episode it belongs to now. Never raises.

    Callers run this when the finalize starts, before the conversation's processing, so the app's
    next read shows no live episode and the next words open a new one. ``on_conversation_finalized``
    repeats it after processing; a second close is a no-op.
    """
    c = collaborators or Collaborators()
    if not conversation_id or trigger not in RECONCILE_TRIGGERS or not episodes_enabled_for(uid):
        return 'skipped'
    try:
        if not client_gate.client_seen(uid):
            return 'skipped_no_client'
        if not _finalize_closes(uid, trigger, source):
            return 'kept_open'
        episode = episodes_db.get_episode_for_conversation(uid, conversation_id, firestore_client=c.firestore_client)
        return _close_for_finalize(uid, episode, conversation_id, trigger, c, _now(c))
    except Exception as error:
        logger.warning('event=episode_finalize_close outcome=error exception_type=%s', type(error).__name__)
        return 'error'


def _finalize_closes(uid: str, trigger: str, source: Any) -> bool:
    """A client finalize always ends the occasion; the server ending a conversation does when it is one.

    An occasion conversation (``config/occasion_conversations.py``) spans the whole occasion, so its
    end by silence or recovery is the episode's end. Other conversations (desktop capture) still
    split on short silences and keep their episode until the boundary rules close it.
    """
    return trigger == CLIENT_FINALIZE or client_gate.occasion_mode(uid, source)


def _close_for_finalize(
    uid: str,
    episode: Optional[Mapping[str, Any]],
    conversation_id: str,
    trigger: str,
    c: Collaborators,
    now: datetime,
) -> str:
    if episode is None or not policy.is_live(episode):
        return 'not_live'
    ids = list(episode.get('conversation_ids') or [])
    if conversation_id not in ids:
        return 'not_live'
    if trigger != CLIENT_FINALIZE and ids[-1] != conversation_id:
        # A conversation joined after this one (a rollover, a second device): the occasion goes on.
        return 'continued'
    _close(uid, episode, 'user' if trigger == CLIENT_FINALIZE else 'gap', c, now=now, closing=conversation_id)
    return 'closed'


def _on_finalized(
    uid: str,
    conversation_id: str,
    row: Mapping[str, Any],
    trigger: str,
    absorbed_from: Optional[str],
    c: Collaborators,
) -> str:
    if row.get('deleted') or row.get('discarded'):
        _end_discarded(uid, conversation_id, row, trigger, c)
        return 'skipped_discarded'
    started = policy.utc(row.get('started_at')) or policy.utc(row.get('created_at'))
    segments = [s for s in row.get('transcript_segments') or [] if isinstance(s, Mapping)]
    episode = episodes_db.get_episode_for_conversation(
        uid, absorbed_from or conversation_id, firestore_client=c.firestore_client
    )
    if absorbed_from and episode:
        _repoint_absorbed(uid, episode, absorbed_from, conversation_id, c)
        episode = episodes_db.get_episode(uid, str(episode['id']), firestore_client=c.firestore_client)
    if segments and not absorbed_from:
        ended = policy.utc(row.get('finished_at')) or _wall(started, max(_segment_end(s) for s in segments))
        tail = MomentInput(
            conversation_id=conversation_id,
            source=str(row.get('source') or '') or None,
            segments=segments,
            started_at=started or ended or _now(c),
            ended_at=ended or _now(c),
            trigger='finalize',
            calendar_identity=_calendar_identity(row),
            language=row.get('language'),
        )
        record_moment(uid, tail, c)
        episode = episodes_db.get_episode_for_conversation(uid, conversation_id, firestore_client=c.firestore_client)
    if not episode:
        return 'no_episode'
    if not absorbed_from and _finalize_closes(uid, trigger, row.get('source')):
        # The close at finalize start failed or never ran: close now, before reconciling.
        if _close_for_finalize(uid, episode, conversation_id, trigger, c, _now(c)) == 'closed':
            episode = episodes_db.get_episode(uid, str(episode['id']), firestore_client=c.firestore_client) or episode
    return _reconcile(uid, episode, conversation_id, absorbed_from, row, c)


def _end_discarded(uid: str, conversation_id: str, row: Mapping[str, Any], trigger: str, c: Collaborators) -> None:
    """A discarded conversation still ends its episode, and its items never become tasks."""
    episode = episodes_db.get_episode_for_conversation(uid, conversation_id, firestore_client=c.firestore_client)
    if episode and _finalize_closes(uid, trigger, row.get('source')):
        if _close_for_finalize(uid, episode, conversation_id, trigger, c, _now(c)) == 'closed':
            episode = episodes_db.get_episode(uid, str(episode['id']), firestore_client=c.firestore_client)
    if not episode or policy.is_live(episode):
        # A live episode drops them when it closes.
        return
    items = provisional_items(episode)
    dropped = 0
    for item in items:
        if item.get('status') == 'provisional' and item.get('conversation_id') == conversation_id:
            item['status'] = 'dropped'
            dropped += 1
    if dropped:
        episodes_db.update_episode(
            uid,
            str(episode['id']),
            expected_version=int(episode.get('state_version') or 0),
            updates={'provisional_items': items},
            firestore_client=c.firestore_client,
        )
        metrics.record_provisional_outcomes({'dropped': dropped})


def _calendar_identity(row: Mapping[str, Any]) -> Optional[str]:
    external = row.get('external_data') if isinstance(row.get('external_data'), Mapping) else {}
    context = external.get('calendar_meeting_context') if isinstance(external, Mapping) else None
    event_id = (context or {}).get('calendar_event_id') if isinstance(context, Mapping) else None
    event_id = event_id or (external or {}).get('calendar_event_id')
    return str(event_id) if event_id else None


def _repoint_absorbed(uid: str, episode: Mapping[str, Any], donor_id: str, survivor_id: str, c: Collaborators) -> None:
    """Smart merge folded the donor into the survivor: the episode follows the survivor id."""
    ids = [survivor_id if cid == donor_id else cid for cid in episode.get('conversation_ids') or []]
    moments = [
        {**m, 'conversation_id': survivor_id} if m.get('conversation_id') == donor_id else dict(m)
        for m in episode.get('moments') or []
    ]
    items = [
        {**i, 'conversation_id': survivor_id} if i.get('conversation_id') == donor_id else dict(i)
        for i in provisional_items(episode)
    ]
    episodes_db.update_episode(
        uid,
        str(episode['id']),
        expected_version=int(episode.get('state_version') or 0),
        updates={
            'conversation_ids': list(dict.fromkeys(ids)),
            'moments': moments,
            'provisional_items': items,
            'primary_conversation_id': (
                survivor_id
                if episode.get('primary_conversation_id') == donor_id
                else episode.get('primary_conversation_id')
            ),
        },
        link_conversation_ids=[survivor_id],
        firestore_client=c.firestore_client,
    )


def _reconcile(
    uid: str,
    episode: Mapping[str, Any],
    conversation_id: str,
    absorbed_from: Optional[str],
    row: Mapping[str, Any],
    c: Collaborators,
) -> str:
    """Provisional items heard in this conversation become kept (a saved task) or dropped."""
    items = provisional_items(episode)
    pending = [i for i in items if i.get('status') == 'provisional' and i.get('conversation_id') == conversation_id]
    counts = {'kept': 0, 'dropped': 0}
    if pending:
        saved = [t for t in _saved_tasks(uid, conversation_id, c) if not t.get('deleted')]
        matches = policy.match_saved_tasks(pending, saved)
        for item in items:
            if item.get('id') in matches:
                task_id = matches[item['id']]
                item['status'] = 'kept' if task_id else 'dropped'
                item['action_item_id'] = task_id
                counts['kept' if task_id else 'dropped'] += 1
    now = _now(c)
    closing = episode.get('wrap_up_requested_at') and (
        episode.get('closing_conversation_id') in {conversation_id, absorbed_from, None}
    )
    if pending:
        episodes_db.update_episode(
            uid,
            str(episode['id']),
            expected_version=int(episode.get('state_version') or 0),
            updates={'provisional_items': items},
            firestore_client=c.firestore_client,
        )
        metrics.record_provisional_outcomes(counts)
        episode = episodes_db.get_episode(uid, str(episode['id']), firestore_client=c.firestore_client) or episode
    if closing and episode.get('status') == 'live':
        # A wrap-up stored before wrap-ups closed at once.
        _close(uid, episode, 'user', c, now=now)
        finished = policy.utc(row.get('finished_at'))
        if finished:
            metrics.record_wrapup_latency('user', (now - finished).total_seconds())
    return 'reconciled' if pending else 'finalized'


# --------------------------------------------------------------------------- user actions and reads


def wrap_up(
    uid: str, episode_id: str, *, conversation_id: Optional[str], collaborators: Optional[Collaborators] = None
) -> Optional[dict[str, Any]]:
    """The user's "Wrap up now": the episode closes at once, and a second wrap-up is a no-op.

    ``conversation_id`` is the conversation still being finished: its items stay provisional
    until its processing reconciles them onto this closed episode, and it never reopens it.
    """
    c = collaborators or Collaborators()
    episode = episodes_db.get_episode(uid, episode_id, firestore_client=c.firestore_client)
    if not episode:
        return None
    if episode.get('status') != 'live':
        return episode
    now = _now(c)
    _close(
        uid,
        episode,
        'user',
        c,
        now=now,
        closing=conversation_id or None,
        extra_fields={'wrap_up_requested_at': now},
    )
    return episodes_db.get_episode(uid, episode_id, firestore_client=c.firestore_client)


def dismiss_item(
    uid: str, episode_id: str, item_id: str, *, collaborators: Optional[Collaborators] = None
) -> Optional[dict[str, Any]]:
    """The user's Undo on a captured item: it is dismissed, and never reconciled into a task."""
    c = collaborators or Collaborators()
    episode = episodes_db.get_episode(uid, episode_id, firestore_client=c.firestore_client)
    if not episode:
        return None
    items = provisional_items(episode)
    target = next((item for item in items if item.get('id') == item_id), None)
    if target is None or target.get('status') != 'provisional':
        return episode
    target['status'] = 'dismissed'
    updated = episodes_db.update_episode(
        uid,
        episode_id,
        expected_version=int(episode.get('state_version') or 0),
        updates={'provisional_items': items},
        firestore_client=c.firestore_client,
    )
    metrics.record_provisional_outcomes({'dismissed': 1})
    return updated


def live_episode(uid: str, *, collaborators: Optional[Collaborators] = None) -> Optional[dict[str, Any]]:
    c = collaborators or Collaborators()
    episode = episodes_db.get_current_episode(uid, firestore_client=c.firestore_client)
    now = _now(c)
    if episode and policy.idle_close_due(episode, now):
        _close(uid, episode, 'idle', c, now=now)
        return None
    if _close_pending_wrap_up(uid, episode, c, now):
        return None
    return episode if policy.is_live(episode) else None


def episode_for_conversation(
    uid: str, conversation_id: str, *, collaborators: Optional[Collaborators] = None
) -> Optional[dict[str, Any]]:
    c = collaborators or Collaborators()
    episode = episodes_db.get_episode_for_conversation(uid, conversation_id, firestore_client=c.firestore_client)
    if episode and policy.idle_close_due(episode, _now(c)):
        _close(uid, episode, 'idle', c, now=_now(c))
        episode = episodes_db.get_episode(uid, str(episode['id']), firestore_client=c.firestore_client)
    return episode


def to_wire(episode: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    """Only the client-visible projection; applied offsets, usage and speaker keys stay server-side."""
    if not episode:
        return None
    return {
        'id': episode['id'],
        'status': episode.get('status') or 'closed',
        'started_at': episode.get('started_at'),
        'last_activity_at': episode.get('last_activity_at') or episode.get('started_at'),
        'closed_at': episode.get('closed_at'),
        'close_reason': episode.get('close_reason'),
        'title': episode.get('title') or '',
        'bullets': list(episode.get('bullets') or []),
        'people': list(episode.get('people') or []),
        'provisional_items': [
            {
                'id': item['id'],
                'text': item['text'],
                'kind': item.get('kind') or 'task',
                'status': item.get('status') or 'provisional',
                'explicit': item.get('explicit') is True,
                'due_at': item.get('due_at'),
                'conversation_id': item.get('conversation_id'),
                'segment_offset': item.get('segment_offset'),
                'created_at': item['created_at'],
                'action_item_id': item.get('action_item_id'),
            }
            for item in provisional_items(episode)
            if item.get('id') and item.get('text') and item.get('created_at')
        ],
        'moments': [
            {
                'id': m['id'],
                'conversation_id': m['conversation_id'],
                'started_at': m.get('started_at'),
                'ended_at': m.get('ended_at') or m.get('started_at'),
                'start_offset': float(m.get('start_offset') or 0.0),
                'end_offset': float(m.get('end_offset') or 0.0),
                'heading': m.get('heading') or '',
            }
            for m in episode.get('moments') or []
            if m.get('id') and m.get('conversation_id') and m.get('started_at')
        ],
        'conversation_ids': list(episode.get('conversation_ids') or []),
        'sources': list(episode.get('sources') or []),
        'state_updated_at': episode.get('state_updated_at'),
    }


def mentor_episode_state(uid: str) -> Optional[str]:
    """The compact live state for the mentor lane, or None. Never raises."""
    try:
        if not client_gate.episode_work_enabled(uid):
            return None
        episode = live_episode(uid)
        return render_state(episode) if episode else None
    except Exception as error:
        logger.warning('event=episode_mentor_state outcome=error exception_type=%s', type(error).__name__)
        return None
