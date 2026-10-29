"""Metadata-only recorded-time lookup and serialized historical attachment."""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import NAMESPACE_URL, uuid5

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from config.episodes import MAX_EPISODE_SECONDS, CLOSE_GAP_SECONDS
from database._client import get_firestore_client, run_transactional
from database import episodes

PAGE_LIMIT = 128
FIELDS = ('started_at', 'last_activity_at', 'closed_at', 'status', 'close_reason', 'state_version')


def recorded_candidates(
    uid: str, started: datetime, finished: datetime, *, firestore_client: Any = None, transaction: Any = None
) -> list[dict[str, Any]]:
    client = firestore_client if firestore_client is not None else get_firestore_client()
    # Single-field range: uses Firestore's automatic started_at index.
    query = (
        client.collection('users')
        .document(uid)
        .collection('episodes')
        .where(
            filter=FieldFilter('started_at', '>=', started - timedelta(seconds=MAX_EPISODE_SECONDS + CLOSE_GAP_SECONDS))
        )
        .where(filter=FieldFilter('started_at', '<=', finished + timedelta(seconds=CLOSE_GAP_SECONDS)))
        .order_by('started_at')
        .select(FIELDS)
        .limit(PAGE_LIMIT)
    )
    rows = [dict(doc.to_dict(), id=doc.id) for doc in query.stream(transaction=transaction)]
    if len(rows) >= PAGE_LIMIT:
        raise episodes.EpisodeConflict('recorded_window_incomplete')
    return rows


def recorded_end(episode):
    """Explicit closes own their recorded window; quiet padding is not speech."""
    if episode.get('status') == 'closed' and episode.get('close_reason') not in {'gap', 'idle'}:
        return episode.get('closed_at') or episode.get('last_activity_at')
    return episode.get('last_activity_at')


def check_window(transaction, client, uid, episode, *, rows=None):
    """Serialize live writes with recorded attachment; reject overlapping windows."""
    lo, hi = episode.get('started_at'), recorded_end(episode)
    if not isinstance(lo, datetime) or not isinstance(hi, datetime):
        return
    fence = client.collection('users').document(uid).collection('episode_links').document('recorded_timeline')
    fence_row = fence.get(transaction=transaction).to_dict() or {}
    if rows is None:
        rows = recorded_candidates(uid, lo, hi, firestore_client=client, transaction=transaction)
    for row in rows:
        a, b = row.get('started_at'), recorded_end(row)
        if row['id'] != episode['id'] and isinstance(a, datetime) and isinstance(b, datetime):
            if lo == a or (lo < b and a < hi) or (lo == hi and a <= lo < b):
                raise episodes.EpisodeConflict('recorded_window_overlap')
    return fence, int(fence_row.get('version') or 0) + 1


def _attach_recorded_window(
    uid: str,
    conversation_id: str,
    source: str | None,
    started: datetime,
    finished: datetime,
    *,
    choose: Callable,
    new_episode: dict[str, Any],
    firestore_client: Any = None,
) -> dict[str, Any]:
    client = firestore_client if firestore_client is not None else get_firestore_client()

    @firestore.transactional
    def attach(transaction):
        root = client.collection('users').document(uid)
        links = root.collection('episode_links')
        fence = links.document('recorded_timeline')
        fence_row = fence.get(transaction=transaction).to_dict() or {}
        member = links.document(conversation_id)
        member_row = member.get(transaction=transaction).to_dict() or {}
        rows = recorded_candidates(uid, started, finished, firestore_client=client, transaction=transaction)
        selected = choose(rows, started, started)
        # A conversation belongs to the episode it started in, even past a cap.
        owner_id = member_row.get('episode_id')
        existing = None
        if owner_id:
            snapshot = root.collection('episodes').document(owner_id).get(transaction=transaction)
            existing = episodes.unseal(uid, snapshot.to_dict())
            if existing is None:
                raise episodes.EpisodeConflict('recorded_owner_missing')
            if started >= existing['started_at'] + timedelta(seconds=MAX_EPISODE_SECONDS):
                return {**existing, '_window_end': finished}
        if existing is None and selected:
            snapshot = root.collection('episodes').document(selected['id']).get(transaction=transaction)
            existing = episodes.unseal(uid, snapshot.to_dict())
        lo = min(existing['started_at'], started) if existing else started
        window_end = min(finished, lo + timedelta(seconds=MAX_EPISODE_SECONDS))
        if existing and existing.get('status') != 'live' and existing.get('close_reason') not in {'gap', 'idle'}:
            boundary_end = recorded_end(existing)
            if not isinstance(boundary_end, datetime):
                raise episodes.EpisodeConflict('recorded_owner_missing_end')
            window_end = min(window_end, boundary_end)
        if existing is None or existing.get('status') == 'live' or existing.get('close_reason') in {'gap', 'idle'}:
            # A late prefix that would overflow an existing capped occasion
            # ends at that occasion; it must not create an overlapping 4h row.
            following = [
                row['started_at'] for row in rows if row['id'] != (existing or {}).get('id') and row['started_at'] > lo
            ]
            if following:
                window_end = min(window_end, min(following))
        if window_end < started or (window_end == started and finished > started):
            raise episodes.EpisodeConflict('recorded_window_no_progress')
        if existing:
            result = dict(existing)
            result['conversation_ids'] = list(
                dict.fromkeys([*(existing.get('conversation_ids') or []), conversation_id])
            )
            result['recovered_conversation_ids'] = list(
                dict.fromkeys([*(existing.get('recovered_conversation_ids') or []), conversation_id])
            )
            result['sources'] = list(dict.fromkeys([*(existing.get('sources') or []), *([source] if source else [])]))
            result['started_at'] = min(existing['started_at'], started)
            result['last_activity_at'] = max(existing['last_activity_at'], window_end)
            result['member_activity'] = {**(existing.get('member_activity') or {}), conversation_id: window_end}
            if result.get('status') != 'live':
                if result.get('close_reason') in {'gap', 'idle'}:
                    result['closed_at'] = result['last_activity_at']
                if window_end < finished and result.get('close_reason') in {'gap', 'idle'}:
                    result['close_reason'] = (
                        'hard_cap' if window_end == lo + timedelta(seconds=MAX_EPISODE_SECONDS) else 'boundary'
                    )
            result['state_version'] = int(existing.get('state_version') or 0) + 1
        else:
            result = dict(new_episode)
            result.update(
                id=str(uuid5(NAMESPACE_URL, f'recorded-episode:{uid}:{conversation_id}:{started.isoformat()}')),
                status='closed',
                close_reason=(
                    ('hard_cap' if window_end == lo + timedelta(seconds=MAX_EPISODE_SECONDS) else 'boundary')
                    if window_end < finished
                    else 'gap'
                ),
                closed_at=window_end,
                started_at=started,
                last_activity_at=window_end,
                state_version=1,
                conversation_ids=[conversation_id],
                member_activity={conversation_id: window_end},
                recovered_conversation_ids=[conversation_id],
            )
        check_window(transaction, client, uid, result, rows=rows)
        transaction.set(root.collection('episodes').document(result['id']), episodes.seal(uid, result))
        transaction.set(member, {'episode_id': result['id'], 'updated_at': datetime.now(timezone.utc)})
        transaction.set(fence, {'version': int(fence_row.get('version') or 0) + 1})
        # Never modify current/last_closed navigation pointers for late audio.
        return {**result, '_window_end': window_end}

    return run_transactional(client, attach, transient=True)


def attach_recorded(
    uid: str,
    conversation_id: str,
    source: str | None,
    started: datetime,
    finished: datetime,
    *,
    choose: Callable,
    new_episode: dict[str, Any],
    firestore_client: Any = None,
) -> dict[str, Any]:
    """Place a capture once. Its owner never changes when the capture spans a cap.

    The episode's recorded window stops at four hours or the next occasion;
    the next episode starts only with a different conversation.
    """
    if finished < started or (finished - started).total_seconds() > MAX_EPISODE_SECONDS * PAGE_LIMIT:
        raise episodes.EpisodeConflict('recorded_capture_window_exhausted')
    result = _attach_recorded_window(
        uid,
        conversation_id,
        source,
        started,
        finished,
        choose=choose,
        new_episode=new_episode,
        firestore_client=firestore_client,
    )
    result.pop('_window_end')
    return {**result, '_recorded_windows': [result]}


def member_episodes(uid: str, conversation_id: str, *, firestore_client: Any = None) -> list[dict[str, Any]]:
    """The canonical owner only; legacy multi-window links cannot add membership."""
    owner = episodes.get_episode_for_conversation(uid, conversation_id, firestore_client=firestore_client)
    return [owner] if owner else []


def resume_recorded(uid, episode_id, at, *, expected_version, choose: Callable, firestore_client=None):
    """Only fresh live speech can resume a silence-closed recorded occasion.

    A sync intake never calls this. The current-pointer and timeline fences
    prevent a concurrent live open from being overwritten by the resume.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()

    @firestore.transactional
    def resume(transaction):
        root = client.collection('users').document(uid)
        links = root.collection('episode_links')
        fence = links.document('recorded_timeline')
        fence_row = fence.get(transaction=transaction).to_dict() or {}
        current = links.document('current').get(transaction=transaction).to_dict() or {}
        ref = root.collection('episodes').document(episode_id)
        owner = episodes.unseal(uid, ref.get(transaction=transaction).to_dict())
        if (
            current.get('episode_id')
            or not owner
            or owner.get('status') != 'closed'
            or owner.get('close_reason') not in {'gap', 'idle'}
        ):
            return None
        if owner.get('state_version') != expected_version:
            raise episodes.EpisodeConflict('state_version_changed')
        if choose([owner], at, at) is None:
            return None
        last_closed = links.document('last_closed').get(transaction=transaction).to_dict() or {}
        result = {
            **owner,
            'status': 'live',
            'closed_at': None,
            'close_reason': None,
            'closing_conversation_id': None,
            'wrap_up_requested_at': None,
            'state_version': expected_version + 1,
        }
        transaction.set(ref, episodes.seal(uid, result))
        transaction.set(links.document('current'), {'episode_id': episode_id, 'updated_at': datetime.now(timezone.utc)})
        if last_closed.get('episode_id') == episode_id:
            transaction.set(links.document('last_closed'), {'episode_id': None})
        transaction.set(fence, {'version': int(fence_row.get('version') or 0) + 1})
        return result

    return run_transactional(client, resume, transient=True)
