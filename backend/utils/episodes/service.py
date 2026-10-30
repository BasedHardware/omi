"""Episode orchestration: moments in, compact state and atomic membership out.

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
- ``attach_synced_intake``: a sync (WAL) conversation the moment intake
  persisted it. It joins the live episode covering its span right away, so
  Home folds it under the live row from its first appearance instead of only
  after enrichment finishes. Retained speech merges into its notes with content
  receipts. Recorded-time ownership selects a covering live or closed episode;
  without an owner it creates a closed historical episode and leaves live
  navigation alone. The rollback path retains the former last-closed rejoin.
- ``on_conversation_finalized``: the conversation's normal processing has
  completed. Apply any trailing text the live stream did not deliver, then
  reconcile the provisional items heard in it against the tasks that
  processing saved (the shadow precision metric). A sync-finalized
  conversation that never attached (no realtime stream carried it) joins the
  episode covering its span here, as a parallel capture — the safety net
  for a row that landed before intake could attach it.
- ``close_on_finalize``: a conversation just ended (a client finalize, or the
  server ending an occasion conversation). Its live episode closes at once, and
  the next words open a new one. The ended conversation never reopens it or
  opens another; its tail and reconciliation land on the closed episode.
- ``wrap_up``: the user asked to wrap up now; the episode closes at once.
- ``live_episode`` / ``episode_for_conversation``: reads for the API, which
  close an idle live episode lazily.

"""

from __future__ import annotations

import logging
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Optional, Sequence
from uuid import uuid4
from config.recorded_time import recorded_episodes_enabled, live_timer_start_enabled
from utils.conversations.recorded_time import conversation_span, is_late, at_offset as _wall
from utils.conversations.fragment_visibility import is_relevance_discarded
from utils.sync.repeat_work_metrics import conversation_scope
from utils.episodes.timeline import episode_owning_recorded_time, choose_recorded_episode
from utils.episodes.timeline import episode_at as episode_at, episodes_between as episodes_between
from database import episode_timeline

from config.episodes import (
    CLOSE_GAP_SECONDS,
    CONTINUE_GAP_SECONDS,
    LAST_CLOSED_CACHE_SECONDS,
    MAX_EPISODE_SECONDS,
    MAX_MOMENTS,
    MOMENT_MIN_INTERVAL_SECONDS,
    MOMENT_MIN_WORDS,
    episode_hard_cap_across_conversations_enabled,
    episode_output_language_pinned,
    episodes_enabled_for,
)
from database import action_items as action_items_db
from database import conversations as conversations_db
from database import episode_receipts
from database import episodes as episodes_db
from database import notifications as notification_db
from database import users as users_db
from database.auth import get_user_name
from utils.episodes import moment_render, boundary_runtime
from utils.episodes import output_language as episode_language
from utils.episodes import client_gate, incremental, metrics, policy, recovery
from utils.episodes import capture_groups as episode_groups
from utils.episodes.capture_groups import calendar_identity as _calendar_identity
from utils.episodes.recovery import segment_end as _segment_end, segment_start as _segment_start
from utils.episodes.moment import MomentInput
from utils.episodes.state import apply_update, clean_text, provisional_items, render_state
from utils.episodes.visibility import visible_episode, hidden_conversation
from utils.episodes.recorded_recovery import record_windows

logger = logging.getLogger(__name__)

# The live-poll recap cache (see ``last_closed_episode``): bounded per process,
# simple whole-eviction on overflow, mirroring ``client_gate``'s memos.
_LAST_CLOSED_CACHE_MAX = 10_000
_last_closed_cache: dict[str, tuple[Optional[dict[str, Any]], float]] = {}
_last_closed_lock = threading.Lock()
_OUTPUT_LANGUAGE_CACHE_SECONDS = 4 * 60 * 60
_OUTPUT_LANGUAGE_CACHE_MAX = 20_000
_output_language_cache: dict[tuple[str, str, str, str, int], tuple[str, float]] = {}
_output_language_cache_lock = threading.Lock()

RECONCILE_TRIGGERS = frozenset({'capture_end', 'client_finalize', 'server_recovery', 'sync_update', 'capture_group'})
CLIENT_FINALIZE = 'client_finalize'
SYNC_UPDATE = 'sync_update'
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
    owner_name: Optional[Callable[[str], Optional[str]]] = None
    now: Optional[Callable[[], datetime]] = None
    extras: dict[str, Any] = field(default_factory=dict)


def _now(c: Collaborators) -> datetime:
    return c.now() if c.now else datetime.now(timezone.utc)


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


def _owner_name(uid: str, c: Collaborators) -> str:
    """Look up the owner's name once; an explicit fallback avoids a second auth read."""
    try:
        return (c.owner_name(uid) if c.owner_name is not None else get_user_name(uid, use_default=False)) or 'You'
    except Exception as error:
        logger.warning('event=episode_moment owner_name_failed exception_type=%s', type(error).__name__)
        return 'You'


def _conversation_language(uid: str, conversation_id: str, c: Collaborators) -> Optional[str]:
    """The conversation's dominant language tag, for moments the stream did not carry one."""
    if not conversation_id:
        return ''
    try:
        row = conversations_db.get_conversation_raw_snapshot(
            uid, conversation_id, field_paths=['language'], firestore_client=c.firestore_client
        )
        return str((row or {}).get('language') or '')
    except Exception as error:
        logger.warning('event=episode_moment conversation_language_failed exception_type=%s', type(error).__name__)
        return None


def _language_cache_get(key: tuple[str, str, str, str, int]) -> Optional[str]:
    now = time.monotonic()
    with _output_language_cache_lock:
        cached = _output_language_cache.get(key)
        if cached is None:
            return None
        language, expires_at = cached
        if now >= expires_at:
            _output_language_cache.pop(key, None)
            return None
        return language


def _language_cache_set(key: tuple[str, str, str, str, int], language: str) -> None:
    with _output_language_cache_lock:
        if len(_output_language_cache) >= _OUTPUT_LANGUAGE_CACHE_MAX:
            now = time.monotonic()
            expired = [cache_key for cache_key, (_, expiry) in _output_language_cache.items() if expiry <= now]
            for cache_key in expired:
                _output_language_cache.pop(cache_key, None)
            while len(_output_language_cache) >= _OUTPUT_LANGUAGE_CACHE_MAX:
                _output_language_cache.pop(next(iter(_output_language_cache)))
        _output_language_cache[key] = (language, time.monotonic() + _OUTPUT_LANGUAGE_CACHE_SECONDS)


def _episode_language_inputs(
    uid: str,
    session_id: str,
    moment: MomentInput,
    c: Collaborators,
) -> tuple[str, str]:
    """Resolve and memoize conversation language and user preference for this session."""
    client_key = id(c.firestore_client)
    conversation_key = ('conversation', uid, session_id, moment.conversation_id, client_key)
    conversation_language = _language_cache_get(conversation_key)
    if conversation_language is None:
        stored = _conversation_language(uid, moment.conversation_id, c)
        authority = stored if stored is not None and stored.strip() else (moment.language or '')
        conversation_language = episode_language.normalize_language(authority)
        if not conversation_language:
            conversation_language = episode_language.dominant_segment_language(moment.segments)
        _language_cache_set(conversation_key, conversation_language)

    preference_key = ('preference', uid, session_id, '', client_key)
    preference = _language_cache_get(preference_key)
    if preference is None:
        preference = episode_language.language_preference(uid)
        _language_cache_set(preference_key, preference)
    return conversation_language, preference


def _empty_episode(
    moment: MomentInput,
    now: datetime,
    *,
    started_at: Optional[datetime] = None,
    previous: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    current_start = started_at or moment.current_started_at or moment.started_at
    return new_episode(
        conversation_id=moment.conversation_id,
        started_at=current_start,
        last_activity_at=moment.current_ended_at or moment.ended_at,
        calendar_identity=moment.calendar_identity,
        now=now,
    ) | {
        key: list(previous.get(key) or []) if isinstance(previous.get(key), list) else previous.get(key)
        for key in ('title', 'bullets', 'people', 'open_questions', 'speaker_display_order', 'speaker_keys')
        if previous is not None and previous.get(key) is not None
    }


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
        'member_activity': {conversation_id: last_activity_at} if conversation_id else {},
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


def _carry_hard_cap_state(
    successor: dict[str, Any], previous: Mapping[str, Any], carried_items: Sequence[Mapping[str, Any]]
) -> None:
    """Keep the running summary and unresolved tasks when a long occasion rotates at its cap."""
    for key in ('title', 'bullets', 'people', 'open_questions', 'speaker_display_order', 'speaker_keys'):
        value = previous.get(key)
        if value is not None:
            successor[key] = list(value) if isinstance(value, list) else value
    successor['provisional_items'] = [dict(item) for item in carried_items]


def _retain_activity(
    uid: str, episode: Optional[dict[str, Any]], conversation_id: str, at: datetime, c: Collaborators
) -> Optional[dict[str, Any]]:
    """Speech owns liveness; notes consumption and its provider are independent."""
    if not episode or not policy.is_live(episode) or conversation_id not in (episode.get('conversation_ids') or []):
        return episode
    last = policy.utc(episode.get('last_activity_at'))
    if last is not None and at <= last:
        return episode
    activity = episodes_db.record_activity(
        uid,
        str(episode['id']),
        conversation_id,
        at,
        firestore_client=c.firestore_client,
    )
    return (
        {**episode, 'last_activity_at': activity}
        if activity
        else episodes_db.get_current_episode(uid, firestore_client=c.firestore_client)
    )


def _close(
    uid: str,
    episode: Mapping[str, Any],
    reason: str,
    c: Collaborators,
    *,
    now: datetime,
    detach: Optional[str] = None,
    closing: Optional[str] = None,
    carry_to_successor: Optional[str] = None,
    carried_items: Optional[list[dict[str, Any]]] = None,
    preserve_for_reconciliation: bool = False,
    extra_fields: Optional[Mapping[str, Any]] = None,
) -> bool:
    """Close once; resolve any provisional item still open as dropped (never a task).

    ``detach`` removes a conversation that joined provisionally and turned out to
    start the next occasion; its link is rewritten by the episode it opens.
    ``closing`` is the conversation whose end closes the episode: its items stay
    provisional until its processing reconciles them, and it never reopens this
    episode or opens another (``_closed_owner``).
    ``preserve_for_reconciliation`` leaves other members' items provisional on
    this closed episode so their own finalizers can still reconcile them.
    """
    expected_activity_at = policy.utc(episode.get('last_activity_at')) if reason == 'idle' else None
    # A WAL member may have gained speech since its last incremental update (or
    # the provider was down at attach). Merge only unapplied member snapshots
    # into these notes before closing. Explicit targeting avoids idle-close
    # recursion and prevents a late member from opening/joining another episode.
    for cid in episode.get('recovered_conversation_ids') or []:
        if cid == detach:
            continue
        row = conversations_db.get_conversation(uid, cid, firestore_client=c.firestore_client)
        if row and not any(row.get(key) for key in ('deleted', 'discarded', 'sync_merged_into')):
            _record_recovered(uid, str(episode['id']), cid, row, c)
    episode = episodes_db.get_episode(uid, str(episode['id']), firestore_client=c.firestore_client) or episode
    items = provisional_items(episode)
    transferred = [
        dict(item)
        for item in items
        if carry_to_successor
        and item.get('status') == 'provisional'
        and item.get('conversation_id') == carry_to_successor
    ]
    dropped = 0
    for item in items:
        if (
            item.get('status') == 'provisional'
            and item.get('conversation_id') not in {detach, closing, carry_to_successor}
            and not preserve_for_reconciliation
        ):
            item['status'] = 'dropped'
            dropped += 1
    # A provisional join still unsettled at close stays with this episode (it joined on the cheap rules).
    transfer_ids = {item.get('id') for item in transferred}
    extra: dict[str, Any] = {
        'provisional_items': [item for item in items if item.get('id') not in transfer_ids],
        'pending_boundary': {},
        **(extra_fields or {}),
    }
    if closing:
        extra['closing_conversation_id'] = closing
    if detach:
        extra['conversation_ids'] = [cid for cid in episode.get('conversation_ids') or [] if cid != detach]
        extra['provisional_items'] = [item for item in items if item.get('conversation_id') != detach]
        activity = {cid: at for cid, at in (episode.get('member_activity') or {}).items() if cid != detach}
        extra.update(
            member_activity=activity, last_activity_at=min(now, max(activity.values(), default=episode['started_at']))
        )
    closed_at = _idle_closed_at(episode, now) if reason == 'idle' else now
    if reason == 'hard_cap' and (start := policy.utc(episode.get('started_at'))) is not None:
        closed_at = start + timedelta(seconds=MAX_EPISODE_SECONDS)
    if recorded_episodes_enabled():
        if reason == 'gap':
            closed_at = _idle_closed_at(episode, now)
    closed = episodes_db.close_episode(
        uid,
        str(episode['id']),
        reason,
        closed_at=closed_at,
        extra=extra,
        expected_activity_at=expected_activity_at,
        firestore_client=c.firestore_client,
    )
    if closed is not None:
        if carried_items is not None:
            carried_items.extend(transferred)
        metrics.record_episode_closed(reason)
        metrics.record_provisional_outcomes({'dropped': dropped})
    return closed is not None


def _pending(episode: Optional[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Provisional joins awaiting their first moment, by conversation id."""
    raw = (episode or {}).get('pending_boundary')
    return {str(k): dict(v) for k, v in raw.items() if isinstance(v, Mapping)} if isinstance(raw, Mapping) else {}


def _idle_closed_at(episode: Mapping[str, Any], now: datetime) -> datetime:
    """An idle episode ended when its quiet reached the close gap, not when a later read noticed."""
    last = policy.utc(episode.get('last_activity_at'))
    end = last + timedelta(seconds=CLOSE_GAP_SECONDS) if last else now
    start = policy.utc(episode.get('started_at'))
    if recorded_episodes_enabled() and episode_hard_cap_across_conversations_enabled() and start is not None:
        end = min(end, start + timedelta(seconds=MAX_EPISODE_SECONDS))
    return min(now, end)


def _close_stale_current(
    uid: str, episode: Optional[Mapping[str, Any]], c: Collaborators, now: datetime
) -> Optional[dict[str, Any]]:
    """Close an idle live episode, or one a wrap-up left live (written before wrap-ups closed at once)."""
    if episode is not None and policy.hard_cap_due(episode, policy.utc(episode.get('last_activity_at')) or now):
        if _close(uid, episode, 'hard_cap', c, now=now, preserve_for_reconciliation=True):
            return None
        episode = episodes_db.get_current_episode(uid, firestore_client=c.firestore_client)
    if episode is not None and policy.idle_close_due(episode, now):
        if _close(uid, episode, 'idle', c, now=now):
            return None
        episode = episodes_db.get_current_episode(uid, firestore_client=c.firestore_client)
    if _close_pending_wrap_up(uid, episode, c, now):
        return None
    return dict(episode) if episode is not None else None


def _close_pending_wrap_up(uid: str, episode: Optional[Mapping[str, Any]], c: Collaborators, now: datetime) -> bool:
    if episode is None or not policy.is_live(episode) or not episode.get('wrap_up_requested_at'):
        return False
    _close(uid, episode, 'user', c, now=now, closing=episode.get('closing_conversation_id') or None)
    return True


def _closed_owner(
    uid: str, episode: Optional[Mapping[str, Any]], moment: MomentInput, c: Collaborators
) -> Optional[dict[str, Any]]:
    """Every closed member stays with its original owner; only a new conversation opens the successor."""
    if episode and moment.conversation_id in (episode.get('conversation_ids') or []):
        return None
    owner = episodes_db.get_episode_for_conversation(uid, moment.conversation_id, firestore_client=c.firestore_client)
    if not owner or policy.is_live(owner):
        return None
    return owner


def _select_carried_segments(
    uid: str,
    episode: Mapping[str, Any],
    fragments: Sequence[Any],
    c: Collaborators,
    *,
    all_shards: bool,
) -> tuple[list[Mapping[str, Any]], dict[str, set[str]], dict[str, set[str]], dict[str, float]]:
    """Select pending transcript groups already owned by the same episode.

    Conversation-local cursors and receipts stay separate even when their text
    is folded into one LLM update. A boundary that opened another episode never
    calls this helper, so an earlier occasion's buffer remains for finalization.
    """
    members = set(episode.get('conversation_ids') or [])
    applied = dict(episode.get('applied') or {})
    selected_segments: list[Mapping[str, Any]] = []
    receipt_ids: dict[str, set[str]] = {}
    content_ids: dict[str, set[str]] = {}
    applied_until: dict[str, float] = {}
    for fragment in fragments:
        conversation_id = str(getattr(fragment, 'conversation_id', '') or '')
        if not conversation_id or conversation_id not in members:
            continue
        raw_segments = list(getattr(fragment, 'segments', ()) or ())
        if not raw_segments:
            continue
        consumed, receipts_exist = episode_receipts.get_consumed_ids(
            uid, conversation_id, all_shards=all_shards, firestore_client=c.firestore_client
        )
        if not receipts_exist:
            consumed |= set(((episode.get('applied_segment_ids') or {}).get(conversation_id)) or [])
        consumed_content, _ = episode_receipts.get_consumed_ids(
            uid,
            recovery.receipt_namespace(conversation_id),
            all_shards=True,
            firestore_client=c.firestore_client,
        )
        cursor = float(applied.get(conversation_id, -1.0))
        chosen, ids, _ = recovery.select_segments(raw_segments, consumed, consumed_content, cursor, recovered=False)
        if not chosen:
            continue
        selected_segments.extend(chosen)
        receipt_ids.setdefault(conversation_id, set()).update(ids)
        content_ids.setdefault(conversation_id, set()).update(recovery.content_receipts(chosen))
        if not receipts_exist:
            receipt_ids[conversation_id].update(consumed)
        end_offset = max((_segment_end(segment) for segment in chosen), default=-1.0)
        applied_until[conversation_id] = max(applied_until.get(conversation_id, -1.0), end_offset)
    return selected_segments, receipt_ids, content_ids, applied_until


def attach_conversation(
    uid: str,
    conversation_id: str,
    source: Optional[str],
    *,
    started_at: datetime,
    ended_at: Optional[datetime] = None,
    collaborators: Optional[Collaborators] = None,
) -> str:
    """A conversation's first live speech joins or opens the live episode. No model call; never raises."""
    c = collaborators or Collaborators()
    if not episodes_enabled_for(uid) or not conversation_id:
        return 'disabled'
    outcome = 'conflict'
    for _ in range(2):
        try:
            outcome = _attach_once(uid, conversation_id, source, started_at, c, ended_at=ended_at)
        except episodes_db.EpisodeConflict:
            outcome = 'conflict'
            continue
        except Exception as error:
            logger.warning('event=episode_attach outcome=error exception_type=%s', type(error).__name__)
            outcome = 'error'
        break
    return outcome


def _attach_once(
    uid: str,
    conversation_id: str,
    source: Optional[str],
    started_at: datetime,
    c: Collaborators,
    *,
    ended_at: Optional[datetime] = None,
) -> str:
    now = _now(c)
    if hidden_conversation(uid, conversation_id, firestore_client=c.firestore_client):
        return 'skipped_discarded'
    owner = episodes_db.get_episode_for_conversation(uid, conversation_id, firestore_client=c.firestore_client)
    if owner:
        if policy.is_live(owner):
            if policy.hard_cap_due(owner, ended_at or started_at):
                owner = _retain_activity(uid, owner, conversation_id, ended_at or started_at, c) or owner
                _close(uid, owner, 'hard_cap', c, now=now, preserve_for_reconciliation=True)
            else:
                _retain_activity(uid, owner, conversation_id, ended_at or started_at, c)
        return 'attached'
    if recorded_episodes_enabled():
        owner = episode_owning_recorded_time(uid, started_at, firestore_client=c.firestore_client)
        late = is_late((started_at, ended_at or started_at), now)
        if owner or late:
            placed = _attach_recorded(uid, conversation_id, {'source': source}, started_at, started_at, c)
            if owner and not policy.is_live(owner) and not late:
                resumed = episode_timeline.resume_recorded(
                    uid,
                    str(placed['id']),
                    started_at,
                    expected_version=int(placed['state_version']),
                    choose=choose_recorded_episode,
                    firestore_client=c.firestore_client,
                )
                if resumed is not None:
                    return 'joined'
            return 'joined' if owner and policy.is_live(owner) else 'recorded'
    episode = episodes_db.get_current_episode(uid, firestore_client=c.firestore_client)
    episode = _close_stale_current(uid, episode, c, now)
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
    updates: dict[str, Any] = {
        **_with_conversation(episode, conversation_id, source),
        'member_activity': {conversation_id: ended_at or started_at},
    }
    if decision.parallel:
        metrics.record_boundary('parallel')
    else:
        last = policy.utc(episode.get('last_activity_at'))
        updates['last_activity_at'] = max(ended_at or started_at, last) if last else ended_at or started_at
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


@conversation_scope
def record_moment(
    uid: str,
    moment: MomentInput,
    collaborators: Optional[Collaborators] = None,
    *,
    member_episode_id: Optional[str] = None,
) -> str:
    """Returns a bounded outcome label. Never raises."""
    c = collaborators or Collaborators()
    if not episodes_enabled_for(uid):
        return 'disabled'
    outcome = 'error'
    for _ in range(2):
        try:
            outcome = _record_moment_once(uid, moment, c, member_episode_id=member_episode_id)
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
    """Settle provisional joins and keep continuing members with their original owner."""
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
    carried_items: list[dict[str, Any]] = []
    successor_started_at = facts.started_at
    carry_previous_state = False
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
        if detach is None and moment.conversation_id in (episode.get('conversation_ids') or []):
            _close(uid, episode, decision.reason or 'gap', c, now=now, preserve_for_reconciliation=True)
            return 'skipped_closed'
        carry_previous_state = decision.reason == 'hard_cap' and episode_hard_cap_across_conversations_enabled()
        if carry_previous_state:
            started = policy.utc(episode.get('started_at'))
            if started and policy.hard_cap_due(episode, max(facts.started_at, facts.ended_at)):
                successor_started_at = max(facts.started_at, started + timedelta(seconds=MAX_EPISODE_SECONDS))
        _close(
            uid,
            episode,
            decision.reason or 'gap',
            c,
            now=facts.started_at if recorded_episodes_enabled() else now,
            detach=detach,
            closing=moment.conversation_id if carry_previous_state else None,
            carry_to_successor=moment.conversation_id if carry_previous_state else None,
            carried_items=carried_items if carry_previous_state else None,
            preserve_for_reconciliation=carry_previous_state,
        )
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
            updates={
                **_with_conversation(episode, moment.conversation_id, moment.source),
                'member_activity': {moment.conversation_id: moment.current_ended_at or moment.ended_at},
            },
            link_conversation_ids=[moment.conversation_id],
            firestore_client=c.firestore_client,
        )
        return 'parallel'
    else:
        metrics.record_boundary('continue')
    return episode, pending, carried_items, successor_started_at, carry_previous_state


def _record_moment_once(
    uid: str, moment: MomentInput, c: Collaborators, *, member_episode_id: Optional[str] = None
) -> str:
    now = _now(c)
    if hidden_conversation(uid, moment.conversation_id, firestore_client=c.firestore_client):
        return 'skipped_discarded'
    recovered = moment.trigger == 'sync_recovery'
    episode = (
        episodes_db.get_episode(uid, member_episode_id, firestore_client=c.firestore_client)
        if member_episode_id
        else episodes_db.get_current_episode(uid, firestore_client=c.firestore_client)
    )
    if episode and moment.conversation_id in (episode.get('duplicate_conversation_ids') or []):
        return 'skipped_applied'
    if member_episode_id and (not episode or moment.conversation_id not in (episode.get('conversation_ids') or [])):
        return 'no_episode'
    # This entrypoint is also used without the realtime tracker. Record speech before
    # any short/rate-limit/model-error return, without consuming it for notes.
    if (
        not member_episode_id
        and moment.trigger != 'finalize'
        and any(str(s.get('text') or '').strip() for s in moment.segments)
    ):
        episode = _retain_activity(uid, episode, moment.conversation_id, moment.current_ended_at or moment.ended_at, c)
    if not member_episode_id:
        episode = _close_stale_current(uid, episode, c, now)
    closed = episode if member_episode_id and not policy.is_live(episode) else None
    if not member_episode_id:
        closed = _closed_owner(uid, episode, moment, c)
    if closed is not None:
        if moment.trigger != 'finalize' and not recovered:
            metrics.record_moment_update(trigger=moment.trigger, outcome='skipped_closed')
            return 'skipped_closed'
        # The tail of a conversation whose episode already closed completes that episode's notes.
        episode = closed
    applied_until = -1.0
    if episode and moment.conversation_id in (episode.get('conversation_ids') or []):
        applied_until = float((episode.get('applied') or {}).get(moment.conversation_id, -1.0))
    consumption_owner = episode
    if not episode or moment.conversation_id not in (episode.get('conversation_ids') or []):
        consumption_owner = episodes_db.get_episode_for_conversation(
            uid, moment.conversation_id, firestore_client=c.firestore_client
        )
    consumed, receipts_exist = episode_receipts.get_consumed_ids(
        uid,
        moment.conversation_id,
        # The finalization tail replays the whole stored transcript: only the
        # archives hold ids old enough to matter there. Live batches are recent.
        all_shards=moment.trigger == 'finalize' or recovered,
        firestore_client=c.firestore_client,
    )
    if not receipts_exist:
        # Pre-receipts episodes kept consumption in their document; adopt it into
        # the receipts on this write so the finalization tail still dedupes.
        consumed |= set(((consumption_owner or {}).get('applied_segment_ids') or {}).get(moment.conversation_id) or [])
    consumed_content, _ = (
        episode_receipts.get_consumed_ids(
            uid,
            recovery.receipt_namespace(moment.conversation_id),
            all_shards=True,
            firestore_client=c.firestore_client,
        )
        if recovered
        else (set(), False)
    )
    segments, selected_ids, selected_content = recovery.select_segments(
        recovery.uncovered_segments(moment, episode),
        consumed,
        consumed_content,
        applied_until,
        recovered=recovered,
    )
    named = _named_segments(uid, segments, c)
    owner_name = _owner_name(uid, c)
    text = incremental.render_moment(
        named,
        uid=uid,
        conversation_id=moment.conversation_id,
        owner_name=owner_name,
        voice_order=(episode or {}).get('speaker_display_order') or [],
    )
    if recovered and text.truncated:
        return 'error'  # Never consume recovered words the prompt did not carry.
    if text.words == 0 and not moment.carried:
        metrics.record_moment_update(trigger=moment.trigger, outcome='skipped_applied')
        return 'skipped_applied'
    facts = policy.MomentFacts(
        conversation_id=moment.conversation_id,
        source=moment.source,
        started_at=moment.current_started_at or moment.started_at,
        ended_at=moment.current_ended_at or moment.ended_at,
        calendar_identity=moment.calendar_identity,
        speakers=policy.speaker_keys(segments),
    )
    pending: Optional[dict[str, Any]] = None
    carried_items: list[dict[str, Any]] = []
    successor_started_at = moment.current_started_at or moment.started_at
    hard_cap_previous: Optional[dict[str, Any]] = None
    carry_previous_state = False
    if closed is None and not member_episode_id:
        previous_episode_id = episode.get('id') if episode else None
        hard_cap_previous = dict(episode) if episode else None
        settled = _settle_boundary(uid, episode, moment, facts, text.text, c, now)
        if isinstance(settled, str):
            return settled
        episode, pending, carried_items, successor_started_at, carry_previous_state = settled
        if episode is None and previous_episode_id is not None and text.voice_order:
            # A boundary opened a fresh occasion: do not carry its predecessor's labels.
            text = incremental.render_moment(
                named, uid=uid, conversation_id=moment.conversation_id, owner_name=owner_name, voice_order=[]
            )

    carried_segments: list[Mapping[str, Any]] = []
    carried_receipts: dict[str, set[str]] = {}
    carried_content: dict[str, set[str]] = {}
    carried_applied: dict[str, float] = {}
    if episode is not None and moment.carried:
        carried_segments, carried_receipts, carried_content, carried_applied = _select_carried_segments(
            uid,
            episode,
            moment.carried,
            c,
            all_shards=moment.trigger == 'finalize' or recovered,
        )
        if carried_segments:
            named = _named_segments(uid, [*carried_segments, *segments], c)
            text = incremental.render_moment(
                named,
                uid=uid,
                conversation_id=moment.conversation_id,
                owner_name=owner_name,
                voice_order=(episode or {}).get('speaker_display_order') or [],
            )

    if text.words == 0:
        metrics.record_moment_update(trigger=moment.trigger, outcome='skipped_applied')
        return 'skipped_applied'
    base = (
        dict(episode)
        if episode
        else _empty_episode(
            moment,
            now,
            started_at=successor_started_at,
            previous=hard_cap_previous if carry_previous_state else None,
        )
    )
    if episode is None and carry_previous_state and hard_cap_previous is not None:
        _carry_hard_cap_state(base, hard_cap_previous, carried_items)
    if (
        not recovered
        and moment.trigger != 'session_end'
        and text.words < (FINALIZE_MIN_WORDS if moment.trigger == 'finalize' else MOMENT_MIN_WORDS)
    ):
        if episode is None and carry_previous_state:
            episodes_db.commit_moment(
                uid,
                expected_episode_id=None,
                expected_version=None,
                new_episode={**base, **_with_conversation(base, moment.conversation_id, moment.source)},
                link_conversation_ids=[moment.conversation_id],
                firestore_client=c.firestore_client,
            )
        metrics.record_moment_update(trigger=moment.trigger, outcome='skipped_short')
        return 'skipped_short'

    state_updated_at = policy.utc(episode.get('state_updated_at')) if episode else None
    if (
        moment.trigger == 'pause'
        and state_updated_at is not None
        and (now - state_updated_at).total_seconds() < MOMENT_MIN_INTERVAL_SECONDS
    ):
        metrics.record_moment_update(trigger=moment.trigger, outcome='rate_limited')
        return 'rate_limited'

    known_ids = [item['id'] for item in provisional_items(base) if item.get('status') == 'provisional']
    output_language, repair = '', None
    conversation_language = moment.language or ''
    if episode_output_language_pinned():
        session_id = str(base.get('primary_conversation_id') or moment.conversation_id)
        conversation_language, preference = _episode_language_inputs(uid, session_id, moment, c)
        output_language = episode_language.resolve_episode_language(uid, conversation_language, preference=preference)
        prior = episode_language.state_language(base, hint_language=conversation_language)
        if prior and not episode_language.languages_match(prior, output_language):
            repair = episode_language.repair_instruction(prior, output_language)
    try:
        result = incremental.run_incremental_update(
            uid,
            render_state(base),
            text.text,
            known_item_ids=known_ids,
            now=now,
            tz_name=_tz(uid, c),
            invoke=episode_language.resolved_invoke(uid, output_language or conversation_language, c.invoke),
            conversation_language=conversation_language,
            output_language=output_language or None,
            repair_instruction=repair,
        )
    except incremental.ModelCallFailed as failure:
        metrics.record_moment_update(
            trigger=moment.trigger,
            outcome=failure.outcome,
            input_tokens=failure.input_tokens,
            output_tokens=failure.output_tokens,
            latency_seconds=failure.latency_seconds,
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
    detected_output_language = (
        episode_language.detected_state_language({**base, **changes}, hint_language=output_language)
        if output_language
        else ''
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
        last.update({'ended_at': moment.current_ended_at or moment.ended_at, 'end_offset': end_offset})
    else:
        moments.append(
            {
                'id': uuid4().hex[:12],
                'conversation_id': moment.conversation_id,
                'started_at': moment.current_started_at or moment.started_at,
                'ended_at': moment.current_ended_at or moment.ended_at,
                'start_offset': start_offset,
                'end_offset': end_offset,
                'heading': heading,
            }
        )
    applied = dict(base.get('applied') or {})
    applied[moment.conversation_id] = max(float(applied.get(moment.conversation_id, -1.0)), end_offset)
    for conversation_id, carried_end in carried_applied.items():
        applied[conversation_id] = max(float(applied.get(conversation_id, -1.0)), carried_end)
    # Record only what this moment consumed: when receipts already exist their archives
    # hold the older ids, and re-recording them would duplicate every shard. A missing
    # receipt document adopts the legacy in-document ids on its first write instead.
    adopt = set() if receipts_exist else consumed
    receipt_ids = selected_ids | adopt
    segment_receipts = {moment.conversation_id: sorted(receipt_ids)} if receipt_ids else {}
    for conversation_id, ids in carried_receipts.items():
        if ids:
            segment_receipts[conversation_id] = sorted(set(segment_receipts.get(conversation_id, [])) | ids)
    consumed_segments = [*carried_segments, *segments]
    all_consumed_rendered = (
        not recovered
        and not text.truncated
        and text.words == sum(len(str(s.get('text') or '').split()) for s in consumed_segments)
    )
    if all_consumed_rendered:
        selected_content = recovery.content_receipts(segments)
    if selected_content:
        segment_receipts[recovery.receipt_namespace(moment.conversation_id)] = sorted(selected_content)
    if all_consumed_rendered:
        for conversation_id, content_ids in carried_content.items():
            if content_ids:
                namespace = recovery.receipt_namespace(conversation_id)
                segment_receipts[namespace] = sorted(set(segment_receipts.get(namespace, [])) | content_ids)
    usage = dict(base.get('usage') or {})
    usage['calls'] = int(usage.get('calls') or 0) + result.model_calls
    usage['input_tokens'] = int(usage.get('input_tokens') or 0) + result.input_tokens
    usage['output_tokens'] = int(usage.get('output_tokens') or 0) + result.output_tokens
    last_activity = policy.utc(base.get('last_activity_at'))
    updates = {
        **changes,
        **_with_conversation(base, moment.conversation_id, moment.source),
        'member_activity': {moment.conversation_id: moment.current_ended_at or moment.ended_at},
        'moments': moments[-MAX_MOMENTS:],
        'applied': applied,
        'usage': usage,
        'speaker_display_order': list(text.voice_order),
        'speaker_keys': sorted(set(base.get('speaker_keys') or []) | set(facts.speakers)),
        'last_activity_at': (
            max(moment.current_ended_at or moment.ended_at, last_activity)
            if last_activity
            else (moment.current_ended_at or moment.ended_at)
        ),
        'calendar_identity': base.get('calendar_identity') or moment.calendar_identity,
    }
    if output_language:
        # A prompt instruction does not prove the model followed it. Only stamp
        # observed state text; otherwise the next update detects and repairs it.
        updates['output_language'] = (
            output_language if episode_language.languages_match(detected_output_language, output_language) else None
        )
    if pending is not None:
        updates['pending_boundary'] = {k: v for k, v in _pending(base).items() if k != moment.conversation_id}
    if episode is None:
        episodes_db.commit_moment(
            uid,
            expected_episode_id=None,
            expected_version=None,
            new_episode={**base, **updates},
            link_conversation_ids=[moment.conversation_id],
            segment_receipts=segment_receipts,
            firestore_client=c.firestore_client,
        )
    elif closed is not None or member_episode_id:
        episodes_db.update_episode(
            uid,
            str(episode['id']),
            expected_version=int(episode.get('state_version') or 0),
            updates=updates,
            segment_receipts=segment_receipts,
            firestore_client=c.firestore_client,
        )
    else:
        episodes_db.commit_moment(
            uid,
            expected_episode_id=str(episode['id']),
            expected_version=episode.get('state_version'),
            updates=updates,
            link_conversation_ids=[moment.conversation_id],
            segment_receipts=segment_receipts,
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
        from utils.episodes.live import tracker

        pending = tracker.flush(uid, conversation_id, trigger='finalize')
        if pending is not None:
            record_moment(uid, pending, c)
        episode = episodes_db.get_episode_for_conversation(uid, conversation_id, firestore_client=c.firestore_client)
        return _close_for_finalize(uid, episode, conversation_id, trigger, c, _now(c))
    except Exception as error:
        logger.warning('event=episode_finalize_close outcome=error exception_type=%s', type(error).__name__)
        return 'error'


def _finalize_closes(uid: str, trigger: str, source: Any) -> bool:
    """A client finalize always ends the occasion; the server ending a conversation does when it is one.

    An occasion conversation (``config/occasion_conversations.py``) spans the whole occasion, so its
    end by silence or recovery is the episode's end. Other conversations (desktop capture) still
    split on short silences and keep their episode until the boundary rules close it. A sync
    conversation is never a boundary: its finalize is when offline sync processed it, not when
    its speech ended.
    """
    if trigger in {SYNC_UPDATE, 'capture_group'}:
        return False
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
    if recorded_episodes_enabled() and trigger != CLIENT_FINALIZE and not policy.idle_close_due(episode, now):
        # A live conversation can finalize sooner than the episode's quiet
        # window. Processing that row is not a recorded occasion boundary.
        return 'continued'
    _close(uid, episode, 'user' if trigger == CLIENT_FINALIZE else 'gap', c, now=now, closing=conversation_id)
    return 'closed'


def _sync_member_updates(
    episode: Mapping[str, Any],
    conversation_id: str,
    source: Optional[str],
    *,
    finished: Optional[datetime],
    started: datetime,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Membership plus the clip's speech as activity: sync speech keeps the occasion's clock honest.

    ``commit_moment``/``update_episode`` merge ``last_activity_at`` as a max, so a
    join racing a live moment can never move the clock backwards.
    """
    updates = _with_conversation(episode, conversation_id, source)
    updates['recovered_conversation_ids'] = list(
        dict.fromkeys([*(episode.get('recovered_conversation_ids') or []), conversation_id])
    )
    last = policy.utc(episode.get('last_activity_at'))
    activity = finished or started
    if now is not None and activity > now:
        activity = now  # A pendant clock running ahead must never pin the episode open.
    updates['member_activity'] = {conversation_id: activity}
    if last is None or activity > last:
        updates['last_activity_at'] = activity
    return updates


def _join_live_synced(
    uid: str,
    episode: Mapping[str, Any],
    conversation_id: str,
    row: Mapping[str, Any],
    started: datetime,
    finished: Optional[datetime],
    c: Collaborators,
) -> str:
    episode_started = policy.utc(episode.get('started_at'))
    if episode_started is not None and started < episode_started:
        # Older audio than this episode's first recorded words still belongs to the
        # occasion in progress when its span reaches the episode (a parallel capture
        # that caught the opening words) or it began within the continue gap (the
        # pendant and the phone clock separately, and the episode's recorded start
        # can sit slightly after the speech). A clip that ended earlier than that is
        # an occasion already over.
        reached = (finished or started) >= episode_started
        began_within_gap = (episode_started - started).total_seconds() <= CONTINUE_GAP_SECONDS
        if not (reached or began_within_gap):
            return 'no_episode'
    source = str(row.get('source') or '') or None
    facts = policy.MomentFacts(
        conversation_id=conversation_id,
        source=source,
        started_at=started,
        ended_at=finished or started,
        calendar_identity=_calendar_identity(row),
        speakers=frozenset(),
    )
    decision = boundary_runtime.decision(
        uid, episode, facts, policy.boundary(episode, facts), firestore_client=c.firestore_client
    )
    if decision.action != policy.CONTINUE:
        # An ambiguous gap, a different calendar event or the hard cap is no basis for a
        # late WAL row to join the occasion: it stays an ordinary Home row.
        return 'no_episode'
    metrics.record_boundary('parallel' if decision.parallel else 'continue')
    episodes_db.commit_moment(
        uid,
        expected_episode_id=str(episode['id']),
        expected_version=episode.get('state_version'),
        updates=_sync_member_updates(episode, conversation_id, source, finished=finished, started=started, now=_now(c)),
        link_conversation_ids=[conversation_id],
        firestore_client=c.firestore_client,
    )
    return 'joined'


def _rejoin_closed_synced(
    uid: str,
    conversation_id: str,
    row: Mapping[str, Any],
    started: datetime,
    finished: Optional[datetime],
    c: Collaborators,
    *,
    allow_reopen: bool,
) -> str:
    """A late WAL clip lands on the silence-closed episode it belongs to, never a newer one.

    Only ``gap``/``idle`` closes rejoin — silence, not a user's finalize or
    wrap-up and not a hard boundary. When the closed episode is the most recent
    one and no newer episode exists it reopens (the occasion's late captures
    continue it); when a newer episode owns the now, the clip attaches as a
    member of the closed one without reopening it. Sync still never opens a
    brand-new episode.
    """
    closed = episodes_db.get_last_closed_episode(uid, firestore_client=c.firestore_client)
    if closed is None or not policy.rejoinable_closed_episode(closed, started, finished):
        return 'no_episode'
    source = str(row.get('source') or '') or None
    if allow_reopen and finished is not None and (_now(c) - finished).total_seconds() >= policy.CLOSE_GAP_SECONDS:
        # Speech already older than the close gap (a backfill) would only make the
        # episode live until the next read re-closes it: attach as a member instead.
        allow_reopen = False
    if allow_reopen:
        reopened = episodes_db.reopen_episode(
            uid,
            str(closed['id']),
            expected_version=int(closed.get('state_version') or 0),
            updates=_sync_member_updates(
                closed, conversation_id, source, finished=finished, started=started, now=_now(c)
            ),
            link_conversation_ids=[conversation_id],
            firestore_client=c.firestore_client,
        )
        if reopened is not None:
            metrics.record_boundary('sync_rejoin')
            return 'rejoined'
        # The reopen lost its race (a newer episode went live, or this episode
        # already reopened): attach to the episode as it stands now.
        closed = episodes_db.get_episode(uid, str(closed['id']), firestore_client=c.firestore_client)
        if closed is None:
            return 'no_episode'
        if conversation_id in (closed.get('conversation_ids') or []):
            return 'rejoined'
    episodes_db.update_episode(
        uid,
        str(closed['id']),
        expected_version=int(closed.get('state_version') or 0),
        updates=_sync_member_updates(closed, conversation_id, source, finished=finished, started=started, now=_now(c)),
        link_conversation_ids=[conversation_id],
        firestore_client=c.firestore_client,
    )
    metrics.record_boundary('sync_rejoin_member')
    return 'rejoined_member'


def _attach_synced_once(uid: str, conversation_id: str, row: Mapping[str, Any], c: Collaborators) -> str:
    """A sync-finalized conversation joins its recorded-time owner (or forms a closed one).

    The branch below the recorded-time switch is the legacy rollback path.

    Offline-sync (WAL) conversations never attach at first words: no realtime
    stream carries them. When one lands inside the live episode's span it joins
    as a parallel capture — a member, so Home folds it under the live row. Its speech
    also extends the episode's last activity, so an idle close cannot fire while
    sync speech keeps landing late. When the covering episode already closed on
    silence (``gap``/``idle``) the clip rejoins it (``_rejoin_closed_synced``).
    A sync conversation is never an occasion boundary: it cannot close the live
    episode, cannot open one, and a user, wrap-up or hard-boundary close stays
    closed.
    """
    started = policy.utc(row.get('started_at')) or policy.utc(row.get('created_at'))
    if recorded_episodes_enabled() and started is not None:
        span = conversation_span(row)
        if span is None:
            return 'no_episode'
        _attach_recorded(uid, conversation_id, row, span.recorded_start, span.recorded_end, c)
        return 'recorded'
    if started is None:
        return 'no_episode'
    finished = policy.utc(row.get('finished_at'))
    now = _now(c)
    episode = _close_stale_current(
        uid, episodes_db.get_current_episode(uid, firestore_client=c.firestore_client), c, now
    )
    if episode is not None:
        if conversation_id in (episode.get('conversation_ids') or []):
            return 'attached'
        if _join_live_synced(uid, episode, conversation_id, row, started, finished, c) == 'joined':
            return 'joined'
        # The clip does not meet this live episode (older audio, an ambiguous
        # gap): it may belong to the closed occasion before it.
        return _rejoin_closed_synced(uid, conversation_id, row, started, finished, c, allow_reopen=False)
    return _rejoin_closed_synced(uid, conversation_id, row, started, finished, c, allow_reopen=True)


def _attach_recorded(uid, conversation_id, row, started, finished, c) -> dict[str, Any]:
    template = new_episode(
        conversation_id=conversation_id,
        started_at=started,
        last_activity_at=finished,
        calendar_identity=_calendar_identity(row),
        now=_now(c),
    )
    source = getattr(row.get('source'), 'value', row.get('source'))
    template['sources'] = [source] if source else []
    placed = episode_timeline.attach_recorded(
        uid,
        conversation_id,
        source,
        started,
        finished,
        choose=choose_recorded_episode,
        new_episode=template,
        firestore_client=c.firestore_client,
    )
    placed.pop('_recorded_windows', None)
    return placed


def _record_recovered(uid: str, episode_id: str, conversation_id: str, row: Mapping[str, Any], c: Collaborators) -> str:
    if recorded_episodes_enabled():
        owner = episodes_db.get_episode(uid, episode_id, firestore_client=c.firestore_client)
        return record_windows(uid, conversation_id, row, [owner] if owner else [], c, record_moment, now=_now(c))
    outcome = 'skipped_applied'
    for moment in recovery.moments(conversation_id, row, now=_now(c), calendar_identity=_calendar_identity(row)):
        outcome = record_moment(uid, moment, c, member_episode_id=episode_id)
        if outcome not in {'applied', 'skipped_applied'}:
            return outcome
    return outcome


def _attach_synced(
    uid: str, conversation_id: str, row: Mapping[str, Any], c: Collaborators, *, absorbed_from: Optional[str] = None
) -> str:
    if is_relevance_discarded(row) or hidden_conversation(uid, conversation_id, firestore_client=c.firestore_client):
        _end_discarded(uid, conversation_id, row, SYNC_UPDATE, c)
        return 'skipped_discarded'
    if canonical := episode_groups.canonical_row(uid, conversation_id, row, firestore_client=c.firestore_client):
        primary = str(canonical.get('id') or episode_groups.primary_id(row))
        owner = episodes_db.get_episode_for_conversation(uid, primary, firestore_client=c.firestore_client)
        if owner and primary in (owner.get('recovered_conversation_ids') or []):
            episode_groups.join_duplicates(uid, owner, primary, canonical, firestore_client=c.firestore_client)
            return 'attached'
        return _attach_synced(uid, primary, canonical, c)
    # Re-read both membership and the boundary on every lost CAS. A last WAL
    # append cannot rely on another append arriving to repair a lost attachment.
    for attempt in range(3):
        try:
            if absorbed_from:
                donor = episodes_db.get_episode_for_conversation(
                    uid, absorbed_from, firestore_client=c.firestore_client
                )
                if donor and absorbed_from in (donor.get('conversation_ids') or []):
                    _repoint_absorbed(uid, donor, absorbed_from, conversation_id, c)
            _repoint_sync_donors(uid, conversation_id, row, c)
            owner = episodes_db.get_episode_for_conversation(uid, conversation_id, firestore_client=c.firestore_client)
            outcome = (
                _attach_synced_once(uid, conversation_id, row, c)
                if recorded_episodes_enabled() or not owner
                else 'attached'
            )
            owner = episodes_db.get_episode_for_conversation(uid, conversation_id, firestore_client=c.firestore_client)
            if owner is not None:
                if conversation_id not in (owner.get('recovered_conversation_ids') or []):
                    recovered_ids = [*(owner.get('recovered_conversation_ids') or []), conversation_id]
                    episodes_db.update_episode(
                        uid,
                        str(owner['id']),
                        expected_version=int(owner.get('state_version') or 0),
                        updates={'recovered_conversation_ids': list(dict.fromkeys(recovered_ids))},
                        firestore_client=c.firestore_client,
                    )
                episode_groups.join_duplicates(uid, owner, conversation_id, row, firestore_client=c.firestore_client)
                _record_recovered(uid, str(owner['id']), conversation_id, row, c)
            return outcome
        except episodes_db.EpisodeConflict:
            if attempt == 2:
                return 'conflict'
            time.sleep(random.uniform(0.01, 0.05) * (attempt + 1))
    return 'conflict'


def attach_synced_intake(
    uid: str,
    conversation_id: str,
    row: Mapping[str, Any],
    *,
    collaborators: Optional[Collaborators] = None,
) -> str:
    """A sync conversation at the moment intake persisted it: join the episode covering it now.

    Without this, a landed WAL clip stays a standalone Home row until its
    enrichment finalizes (``on_conversation_finalized``), which offline sync
    can leave minutes behind. The join is the same one the finalize-time path
    makes (``_attach_synced``): never opens an episode, merges retained speech into
    the member's notes through idempotent recovery moments, and joins
    only the current live episode covering its span or rejoins the
    silence-closed one it belongs to, and a conversation already owned by an
    episode (live or closed) never moves.
    Fail-open; returns a bounded outcome label; never raises.
    """
    c = collaborators or Collaborators()
    if not episodes_enabled_for(uid) or not conversation_id:
        return 'disabled'
    try:
        if not client_gate.client_seen_cached(uid):
            return 'skipped_no_client'
        if is_relevance_discarded(row) or row.get('deleted') or row.get('sync_merged_into'):
            # Only isolated final verdicts skip intake; occasion-aware sync intake
            # defers fragment discards, so their content joins before finalization.
            return 'skipped_discarded'
        owner = episodes_db.get_episode_for_conversation(uid, conversation_id, firestore_client=c.firestore_client)
        if owner is not None and not policy.is_live(owner):
            _attach_synced(uid, conversation_id, row, c)
            return 'no_episode'
        return _attach_synced(uid, conversation_id, row, c)
    except Exception as error:
        logger.warning('event=episode_sync_intake_attach outcome=error exception_type=%s', type(error).__name__)
        return 'error'


def _repoint_sync_donors(uid: str, survivor_id: str, row: Mapping[str, Any], c: Collaborators) -> None:
    """Sync intake merged earlier clips into this one: live-episode members follow the survivor.

    Clips join at intake, so a donor can already be a member when a later
    segment folds it into the canonical row (``sync_merged_from``). Same
    repoint as a smart-merge donor, so Home never keeps a dead member.
    """
    donors = [str(d) for d in (row.get('sync_merged_from') or []) if d and str(d) != survivor_id]
    for donor_id in donors:
        owners = (
            episode_timeline.member_episodes(uid, donor_id, firestore_client=c.firestore_client)
            if recorded_episodes_enabled()
            else [episodes_db.get_current_episode(uid, firestore_client=c.firestore_client)]
        )
        for episode in owners:
            if episode is None or (not recorded_episodes_enabled() and not policy.is_live(episode)):
                continue
            if donor_id in (episode.get('conversation_ids') or []):
                _repoint_absorbed(uid, episode, donor_id, survivor_id, c)


def _on_finalized(
    uid: str,
    conversation_id: str,
    row: Mapping[str, Any],
    trigger: str,
    absorbed_from: Optional[str],
    c: Collaborators,
) -> str:
    if row.get('deleted') or is_relevance_discarded(row):
        _end_discarded(uid, conversation_id, row, trigger, c)
        return 'skipped_discarded'
    if episode_groups.canonical_row(uid, conversation_id, row, firestore_client=c.firestore_client):
        return _attach_synced(uid, conversation_id, row, c)
    started = policy.utc(row.get('started_at')) or policy.utc(row.get('created_at'))
    segments = [s for s in row.get('transcript_segments') or [] if isinstance(s, Mapping)]
    episode = episodes_db.get_episode_for_conversation(
        uid, absorbed_from or conversation_id, firestore_client=c.firestore_client
    )
    if absorbed_from and episode and trigger != SYNC_UPDATE:
        _repoint_absorbed(uid, episode, absorbed_from, conversation_id, c)
        episode = episodes_db.get_episode(uid, str(episode['id']), firestore_client=c.firestore_client)
    if trigger == SYNC_UPDATE:
        # Absorb callbacks carry the donor row; notes must read the survivor.
        sync_row = (
            (conversations_db.get_conversation(uid, conversation_id, firestore_client=c.firestore_client) or {})
            if absorbed_from
            else row
        )
        outcome = _attach_synced(uid, conversation_id, sync_row, c, absorbed_from=absorbed_from)
        if outcome == 'conflict' or (episode is None and not recorded_episodes_enabled()):
            return outcome
        episode = episodes_db.get_episode_for_conversation(uid, conversation_id, firestore_client=c.firestore_client)
    if (
        (episode is None or trigger == 'capture_group')
        and not absorbed_from
        and trigger != SYNC_UPDATE
        and recorded_episodes_enabled()
    ):
        outcome = _attach_synced(uid, conversation_id, row, c)
        if outcome == 'conflict':
            return outcome
        episode = episodes_db.get_episode_for_conversation(uid, conversation_id, firestore_client=c.firestore_client)
    if segments and not absorbed_from and trigger not in {SYNC_UPDATE, 'capture_group'}:
        # Sync members use content receipts at attachment instead of this live cursor.
        span = conversation_span(row)
        ended = span.recorded_end if span else _wall(started, max(_segment_end(s) for s in segments))
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
    """Hide discarded members and remove their contribution to recorded activity."""
    for attempt in range(3):
        episode = episodes_db.get_episode_for_conversation(uid, conversation_id, firestore_client=c.firestore_client)
        if not episode:
            return
        try:
            episodes_db.update_episode(
                uid,
                str(episode['id']),
                expected_version=int(episode.get('state_version') or 0),
                updates={
                    'discarded_conversation_ids': [*(episode.get('discarded_conversation_ids') or []), conversation_id],
                },
                firestore_client=c.firestore_client,
            )
            return
        except episodes_db.EpisodeConflict:
            if attempt == 2:
                raise


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
    donor_ids, receipts_exist = episode_receipts.get_consumed_ids(
        uid,
        donor_id,
        all_shards=True,
        firestore_client=c.firestore_client,
    )
    if not receipts_exist:
        donor_ids |= set((episode.get('applied_segment_ids') or {}).get(donor_id) or [])
    donor_content, _ = episode_receipts.get_consumed_ids(
        uid,
        recovery.receipt_namespace(donor_id),
        all_shards=True,
        firestore_client=c.firestore_client,
    )
    receipt_transfer = {}
    if donor_ids:
        receipt_transfer[survivor_id] = sorted(donor_ids)
    if donor_content:
        receipt_transfer[recovery.receipt_namespace(survivor_id)] = sorted(donor_content)
    episodes_db.update_episode(
        uid,
        str(episode['id']),
        expected_version=int(episode.get('state_version') or 0),
        updates={
            **episode_timeline.repointed_members(episode, donor_id, survivor_id),
            'conversation_ids': list(dict.fromkeys(ids)),
            'recovered_conversation_ids': list(
                dict.fromkeys(
                    survivor_id if cid == donor_id else cid for cid in episode.get('recovered_conversation_ids') or []
                )
            ),
            'moments': moments,
            'provisional_items': items,
            'primary_conversation_id': (
                survivor_id
                if episode.get('primary_conversation_id') == donor_id
                else episode.get('primary_conversation_id')
            ),
        },
        segment_receipts=receipt_transfer,
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
    from utils.episodes.live import tracker

    pending = tracker.flush(uid, trigger='finalize')
    if pending is not None:
        record_moment(uid, pending, c)
    episode = episodes_db.get_episode(uid, episode_id, firestore_client=c.firestore_client)
    if not episode or episode.get('status') != 'live':
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
    episode = _close_stale_current(uid, episode, c, now)
    return visible_episode(uid, episode, firestore_client=c.firestore_client) if policy.is_live(episode) else None


def episode_for_conversation(
    uid: str, conversation_id: str, *, collaborators: Optional[Collaborators] = None
) -> Optional[dict[str, Any]]:
    c = collaborators or Collaborators()
    episode = episodes_db.get_episode_for_conversation(uid, conversation_id, firestore_client=c.firestore_client)
    if episode and policy.idle_close_due(episode, _now(c)):
        _close(uid, episode, 'idle', c, now=_now(c))
        episode = episodes_db.get_episode(uid, str(episode['id']), firestore_client=c.firestore_client)
    return visible_episode(uid, episode, firestore_client=c.firestore_client)


def last_closed_episode(
    uid: str,
    *,
    collaborators: Optional[Collaborators] = None,
    fresh: bool = False,
    now: Optional[float] = None,
) -> Optional[dict[str, Any]]:
    """The discoverable closed recap, behind the short live-poll cache.

    ``/v1/episodes/live`` polls often while a live surface is on screen, and the
    recap changes only when an episode closes, so it is served from a per-process
    cache for ``LAST_CLOSED_CACHE_SECONDS``. Callers reading it for
    recovery navigation (no live episode on screen) pass ``fresh`` and always
    read through; that also refreshes the cache.
    """
    wall = time.monotonic() if now is None else now
    if not fresh:
        with _last_closed_lock:
            cached = _last_closed_cache.get(uid)
        if cached is not None and wall - cached[1] < LAST_CLOSED_CACHE_SECONDS:
            return visible_episode(uid, cached[0], firestore_client=(collaborators or Collaborators()).firestore_client)
    c = collaborators or Collaborators()
    episode = episodes_db.get_last_closed_episode(uid, firestore_client=c.firestore_client)
    with _last_closed_lock:
        if len(_last_closed_cache) > _LAST_CLOSED_CACHE_MAX:
            _last_closed_cache.clear()
        _last_closed_cache[uid] = (episode, wall)
    return visible_episode(uid, episode, firestore_client=c.firestore_client)


def reset_for_tests() -> None:
    with _last_closed_lock:
        _last_closed_cache.clear()
    with _output_language_cache_lock:
        _output_language_cache.clear()


def episode_by_id(
    uid: str, episode_id: str, *, collaborators: Optional[Collaborators] = None
) -> Optional[dict[str, Any]]:
    c = collaborators or Collaborators()
    episode = episodes_db.get_episode(uid, episode_id, firestore_client=c.firestore_client)
    return visible_episode(uid, episode, firestore_client=c.firestore_client)


def to_wire(episode: Optional[Mapping[str, Any]]) -> Optional[dict[str, Any]]:
    """Only the client-visible projection; applied offsets, usage and speaker keys stay server-side."""
    if not episode:
        return None
    return {
        'id': episode['id'],
        'status': episode.get('status') or 'closed',
        'started_at': episode.get('started_at'),
        'timer_started_at': (
            episode.get('started_at') if live_timer_start_enabled() and policy.is_live(episode) else None
        ),
        'last_activity_at': episode.get('last_activity_at') or episode.get('started_at'),
        'closed_at': episode.get('closed_at'),
        'close_reason': episode.get('close_reason'),
        'title': clean_text(episode.get('title'), 240),
        'bullets': [clean_text(line, 400) for line in episode.get('bullets') or []],
        'people': [clean_text(name, 60) for name in episode.get('people') or [] if clean_text(name, 60) != 'a speaker'],
        'provisional_items': [
            {
                'id': item['id'],
                'text': clean_text(item['text'], 400),
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
                'heading': clean_text(m.get('heading'), 240),
            }
            for m in episode.get('moments') or []
            if m.get('id') and m.get('conversation_id') and m.get('started_at')
        ],
        'conversation_ids': [
            cid
            for cid in episode.get('conversation_ids') or []
            if cid not in (episode.get('duplicate_conversation_ids') or [])
        ],
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
