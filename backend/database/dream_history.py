"""Owner-scoped history references and counts, never decrypted content scans."""

from hashlib import sha256

from database._client import get_firestore_client

COLLECTIONS = ('conversations', 'action_items', 'people', 'memory_items')


def history_collection(uid, collection, firestore_client=None):
    if collection not in COLLECTIONS:
        raise ValueError('dream_history_collection')
    database = firestore_client if firestore_client is not None else get_firestore_client()
    return database.collection('users').document(uid).collection(collection)


def history_page(uid, collection, *, after=None, limit=40, firestore_client=None):
    source = history_collection(uid, collection, firestore_client)
    query = source.order_by('__name__').select(['id'])
    if after:
        query = query.start_after({'__name__': source.document(after)})
    return [snapshot.id for snapshot in query.limit(max(1, min(limit, 40))).stream(timeout=3)]


def history_count(uid, collection, *, firestore_client=None):
    return int(history_collection(uid, collection, firestore_client).count().get(timeout=3)[0][0].value)


def history_at_rank(uid, collection, rank, *, firestore_client=None):
    if rank < 0:
        raise ValueError('dream_history_rank')
    query = history_collection(uid, collection, firestore_client).order_by('__name__').select(['id'])
    return next((snapshot.id for snapshot in query.offset(rank).limit(1).stream(timeout=3)), None)


def review_id(ref):
    return sha256(ref.encode()).hexdigest()


def last_reviewed(uid, refs, *, firestore_client=None):
    database = firestore_client if firestore_client is not None else get_firestore_client()
    source = database.collection('dream_users').document(uid).collection('reviews')
    return {ref: (source.document(review_id(ref)).get().to_dict() or {}).get('last_reviewed_at') for ref in refs}
