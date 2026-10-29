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
FIELDS = (
    'started_at',
    'last_activity_at',
    'status',
    'close_reason',
    'state_version',
    'recorded_merged_into',
    'recorded_members',
)


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
    return [row for row in rows if not row.get('recorded_merged_into')]


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
        members = episodes.read_memberships(transaction, client, uid, [conversation_id])
        rows = recorded_candidates(uid, started, finished, firestore_client=client, transaction=transaction)
        rows = [row for row in rows if not row.get('recorded_merged_into')]
        selected = choose(rows, started, finished) or choose(rows, started, started)
        # Membership stays stable inside a window. A continuing conversation
        # can also appear in a successor after a recorded hard/user boundary.
        owner_id = member_row.get('episode_id')
        existing = None
        if owner_id:
            snapshot = root.collection('episodes').document(owner_id).get(transaction=transaction)
            existing = episodes.unseal(uid, snapshot.to_dict())
            if existing is None:
                raise episodes.EpisodeConflict('recorded_owner_missing')
            if choose([existing], started, started) is None:
                existing = None
        if existing is None and selected:
            snapshot = root.collection('episodes').document(selected['id']).get(transaction=transaction)
            existing = episodes.unseal(uid, snapshot.to_dict())
        lo = min(existing['started_at'], started) if existing else started
        window_end = min(finished, lo + timedelta(seconds=MAX_EPISODE_SECONDS))
        if existing and existing.get('status') != 'live' and existing.get('close_reason') not in {'gap', 'idle'}:
            window_end = min(window_end, existing['last_activity_at'])
        elif existing is None:
            # A late prefix that would overflow an existing capped occasion
            # ends at that occasion; it must not create an overlapping 4h row.
            following = [row['started_at'] for row in rows if row['started_at'] > started]
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
            if result.get('status') != 'live':
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
                recovered_conversation_ids=[conversation_id],
            )
        transaction.set(root.collection('episodes').document(result['id']), episodes.seal(uid, result))
        episodes.write_memberships(transaction, client, uid, result['id'], members, datetime.now(timezone.utc))
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
    """Place a complete capture, splitting only at existing or 4h boundaries.

    The conversation may remain one storage row across capped episodes, like a
    live hard-cap rotation. The ordinary membership link names its latest window.
    Returned windows are transient recovery inputs, never stored on the episode.
    """
    if finished < started or (finished - started).total_seconds() > MAX_EPISODE_SECONDS * PAGE_LIMIT:
        raise episodes.EpisodeConflict('recorded_capture_window_exhausted')
    from database import episode_recorded_components

    client = firestore_client if firestore_client is not None else get_firestore_client()
    canonical = episode_recorded_components.attach(
        uid,
        conversation_id,
        source,
        started,
        finished,
        candidates=recorded_candidates,
        template=new_episode,
        choose=choose,
        firestore_client=client,
        page_limit=PAGE_LIMIT,
    )
    if canonical is not None:
        return canonical
    cursor, windows = started, []
    while True:
        result = _attach_recorded_window(
            uid,
            conversation_id,
            source,
            cursor,
            finished,
            choose=choose,
            new_episode=new_episode,
            firestore_client=firestore_client,
        )
        until = result.pop('_window_end')
        windows.append(result)
        if until >= finished:
            return {**result, '_recorded_windows': windows}
        cursor = until


def member_episodes(uid: str, conversation_id: str, *, firestore_client: Any = None) -> list[dict[str, Any]]:
    """All capped windows for a member, including the legacy single-owner link."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    raw = (
        client.collection('users').document(uid).collection('episode_links').document(conversation_id).get().to_dict()
        or {}
    )
    ids = list(
        dict.fromkeys(
            value
            for value in [*(raw.get('episode_ids') or []), *([raw['episode_id']] if raw.get('episode_id') else [])]
            if isinstance(value, str) and value
        )
    )
    resolved = [episode for eid in ids if (episode := episodes.get_episode(uid, eid, firestore_client=client))]
    return list({episode['id']: episode for episode in resolved}.values())


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


def between(uid: str, start: datetime, end: datetime, *, firestore_client: Any = None) -> list[dict[str, Any]]:
    """Complete ordered time-index scan using the automatic started_at index.

    Paginate rather than silently dropping episodes after PAGE_LIMIT. Only the
    selected overlapping rows are decrypted by the service. No composite index.
    """
    if end < start:
        raise ValueError('episode window end precedes start')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    query = (
        client.collection('users')
        .document(uid)
        .collection('episodes')
        .where(filter=FieldFilter('started_at', '>=', start - timedelta(seconds=MAX_EPISODE_SECONDS)))
        .where(filter=FieldFilter('started_at', '<=', end))
        .order_by('started_at')
        .select(FIELDS)
        .limit(PAGE_LIMIT)
    )
    result = []
    while True:
        page = list(query.stream())
        result.extend(
            dict(doc.to_dict(), id=doc.id) for doc in page if not (doc.to_dict() or {}).get('recorded_merged_into')
        )
        if len(page) < PAGE_LIMIT:
            return result
        query = query.start_after(page[-1])


def repointed_members(episode, donor_id, survivor_id):
    """Transfer recorded evidence with a conversation absorption, in the same CAS."""
    members = episode.get('recorded_members')
    if members is None or donor_id not in members:
        return {}
    members = dict(members)
    donor = members.pop(donor_id)
    survivor = members.get(survivor_id, donor)
    members[survivor_id] = {
        **donor,
        **survivor,
        'start': min(donor['start'], survivor['start']),
        'end': max(donor['end'], survivor['end']),
    }
    return {'recorded_members': members}
