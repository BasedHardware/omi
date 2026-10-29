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
FIELDS = ('started_at', 'last_activity_at', 'status', 'close_reason', 'state_version')


def recorded_candidates(uid, started, finished, *, firestore_client=None, transaction=None):
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


def attach_recorded(
    uid, conversation_id, source, started, finished, *, choose: Callable, new_episode: dict, firestore_client=None
):
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
        selected = choose(rows, started, finished)
        # Existing ownership is immutable. Intake retries cannot move a member
        # into another occasion, even if a newer overlapping episode appeared.
        owner_id = member_row.get('episode_id') or (selected['id'] if selected else None)
        existing = None
        if owner_id:
            snapshot = root.collection('episodes').document(owner_id).get(transaction=transaction)
            existing = episodes.unseal(uid, snapshot.to_dict())
            if existing is None:
                raise episodes.EpisodeConflict('recorded_owner_missing')
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
            result['last_activity_at'] = max(existing['last_activity_at'], finished)
            if result.get('status') != 'live':
                result['closed_at'] = result['last_activity_at']
            result['state_version'] = int(existing.get('state_version') or 0) + 1
        else:
            result = dict(new_episode)
            result.update(
                id=str(uuid5(NAMESPACE_URL, f'recorded-episode:{uid}:{conversation_id}')),
                status='closed',
                close_reason='gap',
                closed_at=finished,
                started_at=started,
                last_activity_at=finished,
                state_version=1,
                conversation_ids=[conversation_id],
                recovered_conversation_ids=[conversation_id],
            )
        transaction.set(root.collection('episodes').document(result['id']), episodes.seal(uid, result))
        transaction.set(member, {'episode_id': result['id'], 'updated_at': datetime.now(timezone.utc)})
        transaction.set(fence, {'version': int(fence_row.get('version') or 0) + 1})
        # Never modify current/last_closed navigation pointers for late audio.
        return result

    return run_transactional(client, attach, transient=True)
