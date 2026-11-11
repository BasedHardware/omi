"""Client read projection with only retained, extant episode members."""

import logging
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, get_args

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from utils.conversations.transcribing_hold import transcription_presentation
from utils.conversations import home_step as home_step_projection
from utils.conversations import phase_shadow

from config.episodes import (
    home_hide_below_floor_rows_enabled,
    HOME_IDLE_CLOSES_PER_READ,
    COMPOSER_LOOKUP_SCHEDULES_PER_WINDOW,
    COMPOSER_MAX_SCHEDULED_PER_READ,
    COMPOSER_READ_THROTTLE_SECONDS,
    MAX_EPISODE_SECONDS,
)
from config.firestore_read_levers import lever_enabled
from database import conversations, episodes
from database._client import get_firestore_client
from database.firestore_cache_metrics import record_request
from database.firestore_retry import FIRESTORE_NO_RETRY
from database.fsr_read_cache import plane_id
from database.firestore_read_origin import read_origin
from utils.read_cache_shadow import compare_hit
from utils.episodes.timeline import ownership_end
from utils.episodes.policy import utc, idle_close_due
from models.episode import EpisodeCloseReason
from utils.episodes import metrics as episode_metrics
from utils.episodes import service
from utils.conversations.fragment_visibility import SETTLING_FIELDS, is_relevance_discarded, is_completed_below_floor
from utils.conversations.home_titles import SUMMARY_DEBT_FIELDS, user_zone_provider

logger = logging.getLogger(__name__)


def list_episode_window(
    uid: str,
    start: datetime,
    end: datetime,
    *,
    limit: int = 50,
    cursor: str | None = None,
    firestore_client: Any = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Bounded Firestore page; use the canonical half-open ownership predicate.

    Filter overlap/donors after advancing the storage cursor, so an empty page
    still makes progress without scanning the entire window on every request.
    Snapshot cursors include Firestore's implicit document-ID tie breaker.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    root = client.collection('users').document(uid).collection('episodes')
    query = (
        root.where(filter=FieldFilter('started_at', '>=', start - timedelta(seconds=MAX_EPISODE_SECONDS)))
        .where(filter=FieldFilter('started_at', '<=' if start == end else '<', end))
        .order_by('started_at', direction=firestore.Query.DESCENDING)
        .limit(limit + 1)
    )
    if cursor:
        anchor = root.document(cursor).get()
        if not anchor.exists:
            raise ValueError('Episode cursor no longer exists')
        query = query.start_after(anchor)
    scanned = list(query.stream())
    page = scanned[:limit]
    rows: list[dict[str, Any]] = []
    for snapshot in page:
        raw: dict[str, Any] = snapshot.to_dict() or {}
        lo, hi = utc(raw.get('started_at')), ownership_end(raw)
        overlaps = (
            lo is not None
            and hi is not None
            and (lo <= start < hi or lo == hi == start if start == end else lo < end and hi > start)
        )
        if not raw.get('recorded_merged_into') and overlaps:
            row = episodes.unseal(uid, dict(raw, id=snapshot.id))
            if row is not None:
                rows.append(row)
    return rows, page[-1].id if len(scanned) > limit else None


def wire_episode(episode: dict[str, Any] | None) -> dict[str, Any] | None:
    """Additive read fields, without changing the shared lifecycle service's wire helper."""
    if episode is None:
        return None
    wire = service.to_wire(episode)
    assert wire is not None  # Non-null input always has a wire projection.
    # Storage may gain internal boundary reasons before released clients can decode them.
    # Absence is already part of the released wire contract; never widen that enum.
    if wire.get('close_reason') not in get_args(EpisodeCloseReason):
        wire['close_reason'] = None
    return {**wire, 'emoji': episode.get('emoji') or '', 'members': []}


MEMBER_FIELDS = [
    'structured',
    'user_title',
    'data_protection_level',
    'relevance_decision',
    'discarded',
    'deleted',
    'sync_merged_into',
    'dream_duplicate_of',
    'started_at',
    'finished_at',
    'created_at',
    'status',
    'finalization_status',
    'sync_relevance_user_kept',
    'has_photos',
    'photos',
    'starred',
    'folder_user_set',
    'episode_transcription_pending_at',
    'episode_transcription_deadline_at',
    'server_batch_audio_start',
    'server_batch_audio_end',
    *SETTLING_FIELDS,
    *SUMMARY_DEBT_FIELDS,
]


MEMBERS_CACHE_TTL_SECONDS = 60
MEMBERS_CACHE_MAX_ENTRIES = 128
MEMBERS_CACHE_MAX_IDS = 1000
_members_cache: OrderedDict[tuple[str, tuple[str, ...]], tuple[float, dict[str, dict[str, Any]]]] = OrderedDict()
_members_cache_lock = threading.Lock()


def _read_members(uid: str, rows: list[dict[str, Any]], *, firestore_client: Any = None) -> dict[str, dict[str, Any]]:
    """Read prepared members, optionally accepting a snapshot up to 60 seconds old.

    With episode_members_cache on, the same uid and member set reuse the map:
    edits, deletions and visibility changes may remain stale until expiry. Hits
    never extend the TTL; expired entries must read again (including on errors).
    This memo is only a read projection, never authority for a mutation.
    Cache misses share only calls enrolled before the owner starts fetching.
    Later arrivals read fresh; single-flight never retains completed results.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    all_ids: list[str] = []
    for row in rows:
        row_ids: list[str] = row.get('conversation_ids') or []
        all_ids.extend(row_ids)
    ids = list(dict.fromkeys(all_ids))
    cache_key = None
    cache_deadline = 0.0
    if lever_enabled('episode_members_cache', uid) and len(ids) <= MEMBERS_CACHE_MAX_IDS:
        cache_key = (uid, tuple(sorted(ids)))
        cache_deadline = time.monotonic() + MEMBERS_CACHE_TTL_SECONDS
        with _members_cache_lock:
            cached = _members_cache.pop(cache_key, None)
            if cached is not None and time.monotonic() < cached[0]:
                _members_cache[cache_key] = cached
            else:
                cached = None
        if cached is not None:
            try:
                record_request('fsr_s4_episode_members_cache', 'hit')
            except Exception:
                pass
            try:
                compare_hit(
                    'episode_members', cached[1], lambda timeout: _fetch_members(uid, ids, client, timeout=timeout)
                )
            except Exception:
                pass  # Even broken observation must preserve the cached response.
            return deepcopy(cached[1])
    result = _fetch_members_coalesced(uid, ids, client)
    if cache_key is not None:
        with _members_cache_lock:
            # Count read/prepare latency against the TTL, so a slow fetch never
            # publishes a snapshot older than the promised staleness window.
            if time.monotonic() < cache_deadline:
                _members_cache[cache_key] = (cache_deadline, deepcopy(result))
                _members_cache.move_to_end(cache_key)
                while len(_members_cache) > MEMBERS_CACHE_MAX_ENTRIES:
                    _members_cache.popitem(last=False)
    return result


MEMBERS_FLIGHT_MAX_ENTRIES = 128
MEMBERS_FLIGHT_MAX_IDS = 1000


@dataclass
class _MembersFlight:
    future: Future[dict[str, dict[str, Any]]]
    accepting: bool = True


_members_flights: dict[tuple[str, str, tuple[str, ...]], _MembersFlight] = {}
_members_flights_lock = threading.Lock()
_members_flight_local = threading.local()


def _flight_event(result: str) -> None:
    try:
        record_request('fsr_episode_members_flight', result)
    except Exception:
        pass  # Observation must never change a serving read.


def _fetch_members_coalesced(uid: str, ids: list[str], client: Any) -> dict[str, dict[str, Any]]:
    """Enroll only before the owner fetch starts, never into an older snapshot.

    Closing enrollment under the map lock before _fetch_members ensures each
    enrolled request began before the underlying read. An unfinished read may
    already hold a snapshot predating a later request's completed deletion/edit;
    that later request must bypass, even while preparation is still running.
    The closed record stays until completion for bounded capacity accounting.

    The owner fetches inline: no child executor job can queue behind its own
    waiters. Nested reads bypass *all* flights to avoid self-waits and cycles
    between keys. Sync-route cancellation cannot cancel another caller's read;
    BaseException completion still wakes every waiter and permits a fresh retry.
    """
    if not ids or not lever_enabled('episode_members_singleflight', uid):
        return _fetch_members(uid, ids, client)
    if len(ids) > MEMBERS_FLIGHT_MAX_IDS or getattr(_members_flight_local, 'active', False):
        _flight_event('bypass')
        return _fetch_members(uid, ids, client)
    key = (plane_id(client), uid, tuple(sorted(ids)))
    with _members_flights_lock:
        flight = _members_flights.get(key)
        owner = flight is None
        if owner and len(_members_flights) < MEMBERS_FLIGHT_MAX_ENTRIES:
            flight = _MembersFlight(Future())
            flight.future.set_running_or_notify_cancel()  # Private; waiters cannot cancel the shared read.
            _members_flights[key] = flight
        elif flight is not None and not flight.accepting:
            flight = None  # Keep the closed record; never overwrite another owner's flight.
    if flight is None:
        _flight_event('bypass')
        return _fetch_members(uid, ids, client)
    if not owner:
        _flight_event('coalesced')
        return deepcopy(flight.future.result())  # Owner runs inline, not queued behind its waiters.
    _members_flight_local.active = True
    try:
        _flight_event('owner')
        with _members_flights_lock:
            flight.accepting = False
        result = _fetch_members(uid, ids, client)
    except BaseException as error:
        with _members_flights_lock:
            if _members_flights.get(key) is flight:
                del _members_flights[key]
        flight.future.set_exception(error)
        _flight_event('error')
        raise
    else:
        with _members_flights_lock:
            if _members_flights.get(key) is flight:
                del _members_flights[key]
        flight.future.set_result(result)
        return deepcopy(result)
    finally:
        _members_flight_local.active = False


def _fetch_members(uid, ids, client, *, timeout=None):
    root = client.collection('users').document(uid).collection('conversations')
    deadline = time.monotonic() + timeout if timeout is not None else None
    members: dict[str, dict[str, Any]] = {}
    for offset in range(0, len(ids), episodes.MEMBERSHIP_BATCH_LIMIT):
        options = {}
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('shadow read deadline')
            options = {'timeout': remaining, 'retry': FIRESTORE_NO_RETRY}
        refs = [root.document(cid) for cid in ids[offset : offset + episodes.MEMBERSHIP_BATCH_LIMIT]]
        with read_origin('job:read_cache_shadow') if deadline is not None else nullcontext():
            for snapshot in client.get_all(refs, field_paths=[] if deadline is not None else MEMBER_FIELDS, **options):
                if snapshot.exists:
                    members[snapshot.id] = (
                        {} if deadline is not None else dict(snapshot.to_dict() or {}, id=snapshot.id)
                    )
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError('shadow read deadline')
    if deadline is not None:
        # MEMBER_FIELDS excludes transcripts: prepare cannot drop an extant row
        # via blob/decode/decrypt failures. Display visibility is applied later,
        # not by this cache: even deleted rows retain their keys here.
        return members
    return {
        cid: row
        for cid, raw in members.items()
        if (row := conversations.prepare_conversation_for_read(raw, uid)) is not None
    }


def project_episodes(uid: str, rows: list[dict[str, Any]], *, firestore_client: Any = None) -> list[dict[str, Any]]:
    client = firestore_client if firestore_client is not None else conversations.db
    c = service.Collaborators(firestore_client=client)
    # Close only a fixed number; remaining live rows retain their members.
    due = [row['id'] for row in rows if idle_close_due(row, datetime.now(timezone.utc))][:HOME_IDLE_CLOSES_PER_READ]
    settled = [service.settle_episode_for_read(uid, row, c) if row['id'] in due else row for row in rows]
    just_closed = {
        new['id'] for old, new in zip(rows, settled) if old.get('status') == 'live' and new.get('status') == 'closed'
    }
    rows = settled
    members = _read_members(uid, rows, firestore_client=firestore_client) if rows else {}
    wires = [wire for row in rows if (wire := project_episode(uid, row, members=members, list_row=True)) is not None]
    contained = _contained_ids(rows, wires)
    wires = [wire for wire in wires if wire['id'] not in contained]
    schedule_missed_composes(uid, [row for row in rows if row.get('id') not in contained | just_closed], wires)
    return wires


def _contained_ids(rows: list[dict[str, Any]], wires: list[dict[str, Any]]) -> set[str]:
    """Closed episodes whose visible members another closed episode on the page already shows. Episodes
    from before membership became singular (2026-10-30) can share members, and each would otherwise
    get its own row and its own paid compose over the same speech."""
    closed = {str(row.get('id')): row for row in rows if row.get('status') != 'live'}
    visible = {wire['id']: {m['id'] for m in wire.get('members') or []} for wire in wires if wire['id'] in closed}

    def preference(episode_id: str) -> tuple[bool, int, str]:
        return (not closed[episode_id].get('composed_fingerprint'), -len(visible[episode_id]), episode_id)

    kept: list[set[str]] = []
    contained = set()
    for episode_id in sorted(visible, key=preference):
        if any(visible[episode_id] <= members for members in kept):
            contained.add(episode_id)
        else:
            kept.append(visible[episode_id])
    return contained


def project_lookup(uid: str, episode: dict[str, Any] | None) -> dict[str, Any] | None:
    """One episode for the per-conversation lookup; it carries the same safety net as the list read.

    A fully hidden episode projects to nothing but is still checked, so the composer clears its notes.
    Lookups arrive one per conversation row, so a per-user budget caps distinct episodes queued across them.
    """
    wire = project_episode(uid, episode)
    if episode is not None and (claim := _lookup_reserve(uid)) is not None:
        if not schedule_missed_composes(uid, [episode], [wire] if wire is not None else []):
            _lookup_refund(uid, claim)
    return wire


_lookup_lock = threading.Lock()
_lookup_spend: dict[str, list[float]] = {}


def _lookup_reserve(uid: str) -> float | None:
    """Claim one of the user's lookup schedules for this window atomically; refunded if nothing queues."""
    now = time.monotonic()
    with _lookup_lock:
        if len(_lookup_spend) > 10_000:
            # Drop only users with no spend left in the window, so active budgets survive the bound.
            for key in [k for k, ats in _lookup_spend.items() if not _live(ats, now)]:
                del _lookup_spend[key]
        recent = _live(_lookup_spend.get(uid, []), now)
        if len(recent) >= COMPOSER_LOOKUP_SCHEDULES_PER_WINDOW:
            _lookup_spend[uid] = recent
            return None
        _lookup_spend[uid] = [*recent, now]
        return now


def _lookup_refund(uid: str, claim: float) -> None:
    """Return this lookup's own reservation, never a concurrent lookup's."""
    with _lookup_lock:
        spent = _lookup_spend.get(uid)
        if spent and claim in spent:
            spent.remove(claim)


def _live(spent: list[float], now: float) -> list[float]:
    return [at for at in spent if now - at < COMPOSER_READ_THROTTLE_SECONDS]


def schedule_missed_composes(uid: str, rows: list[dict[str, Any]], wires: list[dict[str, Any]]) -> int:
    """Safety net for the composer: a closed episode that is uncomposed, drifted, or whose visible
    members changed since its compose (a direct discard or delete) gets one, at most a few per read.
    A deferred late episode is left alone until its grace window ends. Returns how many were queued."""
    from utils.episodes import composer

    queued = 0
    try:
        visible = {wire['id']: [m['id'] for m in wire.get('members') or []] for wire in wires}
        now = datetime.now(timezone.utc)
        for row in rows:
            if queued >= COMPOSER_MAX_SCHEDULED_PER_READ:
                break
            closed_at = utc(row.get('closed_at'))
            if closed_at is None or (now - closed_at).total_seconds() < 60:
                continue
            if not composer.needs_compose(row, visible_member_ids=visible.get(str(row.get('id')), [])):
                continue
            if composer.schedule(uid, str(row.get('id')), throttle=True, trigger='read'):
                queued += 1
    except Exception as error:
        logger.warning(
            'event=episode_compose_schedule outcome=error source=read exception_type=%s', type(error).__name__
        )
    return queued


def schedule_opened_compose(uid: str, episode: dict[str, Any] | None) -> bool:
    """The episode page was opened: a deferred late episode composes now, at most once per window."""
    from utils.episodes import composer

    try:
        return composer.schedule_opened(uid, episode)
    except Exception as error:
        logger.warning(
            'event=episode_compose_schedule outcome=error source=open exception_type=%s', type(error).__name__
        )
        return False


def _too_short_for_a_home_row(row: dict[str, Any]) -> bool:
    """A settled below-floor verdict stays off Home, regardless of age or duration.

    List only: search, a direct link and Show discarded still reach it, and nothing is stored.
    """
    if not home_hide_below_floor_rows_enabled():
        return False
    return is_completed_below_floor(row)


def project_episode(
    uid: str,
    episode: dict[str, Any] | None,
    *,
    members: dict[str, dict[str, Any]] | None = None,
    list_row: bool = False,
) -> dict[str, Any] | None:
    if episode is None:
        return None
    by_id = members if members is not None else _read_members(uid, [episode])
    retained: list[dict[str, Any]] = []
    hidden = 0
    now = datetime.now(timezone.utc)
    zone = user_zone_provider(uid)
    for cid in dict.fromkeys(episode.get('conversation_ids') or []):
        row = by_id.get(cid)
        if row is None:
            continue
        if list_row and _too_short_for_a_home_row(row):
            phase_shadow.observe('episode_member', row, False, episode=episode)
            hidden += 1
            continue
        # A transcription-failed member stays projected with its "Couldn't
        # transcribe" wire status so the user keeps the bounded recovery exit;
        # the size-ceiling terminal's failed-status visibility exclusion does
        # not apply to this episode member surface.
        visibility_row = {**row, 'status': 'completed'} if row.get('status') == 'failed' else row
        if (
            not conversations.is_visible_conversation(visibility_row, include_discarded=not list_row)
            or row.get('dream_duplicate_of')
            or conversations.bridge_pending.hidden(row)
            or is_relevance_discarded(row)
            or row.get('sync_merged_into')
        ):
            phase_shadow.observe('episode_member', row, False, episode=episode)
            continue
        phase_shadow.observe('episode_member', row, True, episode=episode)
        from utils.conversations.home_titles import neutralize_minimum_title

        # Classify on the stored read copy, before the presentation rewrite below.
        step = home_step_projection.classify(row)
        row = neutralize_minimum_title(row, tz_name_provider=zone)
        structured: dict[str, Any] = row.get('structured') or {}
        title = structured.get('title') or ''
        status = row.get('status') or 'completed'
        started = row.get('started_at') or row.get('created_at') or episode['started_at']
        finished = row.get('finished_at')
        deadline = utc(row.get('episode_transcription_deadline_at'))
        if deadline is not None and not row.get('record_projection_revision'):
            overdue = now >= deadline
            failed = (
                row.get('finalization_status') == 'dead_letter' or status == 'failed' or row.get('record_upload_failed')
            )
            title, status = transcription_presentation(deadline, failed=bool(failed), now=now)
            # Audio bounds remain truthful even when finalization never filled its clocks.
            for key, value in (
                ('start', row.get('server_batch_audio_start')),
                ('end', row.get('server_batch_audio_end')),
            ):
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    if key == 'start':
                        started = datetime.fromtimestamp(value, timezone.utc)
                    else:
                        finished = datetime.fromtimestamp(value, timezone.utc)
            if overdue:
                episode_metrics.record_batch_pending_overdue()
        retained.append(
            {
                'id': cid,
                'title': title,
                'emoji': structured.get('emoji') or '',
                'gist': str(structured.get('gist') or ''),
                **({'home_step': step} if step else {}),
                'started_at': started,
                'finished_at': finished,
                'status': status,
            }
        )
    if list_row:
        episode_metrics.record_home_members(shown=len(retained), hidden=hidden)
    if not retained:
        return None
    retained.sort(key=lambda member: str(member['started_at']))
    ids = {member['id'] for member in retained}
    wire = wire_episode(episode)
    assert wire is not None  # Non-null input always has a wire projection.
    wire.update(
        emoji=episode.get('emoji') or '',
        members=retained,
        # Include hidden, extant members for episode-wide Delete; only members render.
        conversation_ids=[
            cid
            for cid in dict.fromkeys(episode.get('conversation_ids') or [])
            if cid in by_id and not by_id[cid].get('deleted')
        ],
        moments=[moment for moment in wire['moments'] if moment['conversation_id'] in ids],
        provisional_items=[
            item
            for item in wire['provisional_items']
            if not item.get('conversation_id') or item.get('conversation_id') in ids
        ],
    )
    return wire
