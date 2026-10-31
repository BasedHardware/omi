"""Client read projection with only retained, extant episode members."""

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, get_args

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from config.episodes import (
    COMPOSER_LOOKUP_SCHEDULES_PER_WINDOW,
    COMPOSER_MAX_SCHEDULED_PER_READ,
    COMPOSER_READ_THROTTLE_SECONDS,
    MAX_EPISODE_SECONDS,
)
from database import conversations, episodes
from database._client import get_firestore_client
from utils.episodes.timeline import ownership_end
from utils.episodes.policy import utc
from models.episode import EpisodeCloseReason
from utils.episodes import service
from utils.conversations.fragment_visibility import is_relevance_discarded

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
    'sync_relevance_user_kept',
    'has_photos',
    'photos',
    'starred',
    'folder_user_set',
]


def _read_members(uid: str, rows: list[dict[str, Any]], *, firestore_client: Any = None) -> dict[str, dict[str, Any]]:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    root = client.collection('users').document(uid).collection('conversations')
    all_ids: list[str] = []
    for row in rows:
        row_ids: list[str] = row.get('conversation_ids') or []
        all_ids.extend(row_ids)
    ids = list(dict.fromkeys(all_ids))
    members: dict[str, dict[str, Any]] = {}
    for offset in range(0, len(ids), episodes.MEMBERSHIP_BATCH_LIMIT):
        refs = [root.document(cid) for cid in ids[offset : offset + episodes.MEMBERSHIP_BATCH_LIMIT]]
        for snapshot in client.get_all(refs, field_paths=MEMBER_FIELDS):
            if snapshot.exists:
                row = conversations.prepare_conversation_for_read(snapshot.to_dict(), uid)
                if row is not None:
                    members[snapshot.id] = row
    return members


def project_episodes(uid: str, rows: list[dict[str, Any]], *, firestore_client: Any = None) -> list[dict[str, Any]]:
    members = _read_members(uid, rows, firestore_client=firestore_client) if rows else {}
    wires = [wire for row in rows if (wire := project_episode(uid, row, members=members)) is not None]
    schedule_missed_composes(uid, rows, wires)
    return wires


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
    Returns how many were queued."""
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
            if composer.schedule(uid, str(row.get('id')), throttle=True):
                queued += 1
    except Exception as error:
        logger.warning(
            'event=episode_compose_schedule outcome=error source=read exception_type=%s', type(error).__name__
        )
    return queued


def project_episode(
    uid: str, episode: dict[str, Any] | None, *, members: dict[str, dict[str, Any]] | None = None
) -> dict[str, Any] | None:
    if episode is None:
        return None
    by_id = members if members is not None else _read_members(uid, [episode])
    retained: list[dict[str, Any]] = []
    for cid in dict.fromkeys(episode.get('conversation_ids') or []):
        row = by_id.get(cid)
        if (
            row is None
            or not conversations.is_visible_conversation(row)
            or is_relevance_discarded(row)
            or row.get('sync_merged_into')
        ):
            continue
        structured: dict[str, Any] = row.get('structured') or {}
        retained.append(
            {
                'id': cid,
                'title': structured.get('title') or '',
                'emoji': structured.get('emoji') or '',
                'started_at': row.get('started_at') or row.get('created_at') or episode['started_at'],
                'finished_at': row.get('finished_at'),
                'status': row.get('status') or 'completed',
            }
        )
    if not retained:
        return None
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
