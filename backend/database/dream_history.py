"""Owner-scoped history references and counts, never decrypted content scans."""

from hashlib import sha256

from database._client import get_firestore_client

COLLECTIONS = ('conversations', 'action_items', 'people', 'memory_items')


def history_collection(uid, collection, *, firestore_client=None):
    # Deferred: conversations imports dream_store -> dream_history, and import-isolated
    # database tests stub the models package.
    from models.agent_refs import canonical_collection

    collection = canonical_collection(collection)
    if collection not in COLLECTIONS:
        raise ValueError('dream_history_collection')
    database = firestore_client if firestore_client is not None else get_firestore_client()
    return database.collection('users').document(uid).collection(collection)


def history_page(uid, collection, *, after=None, limit=40, firestore_client=None):
    source = history_collection(uid, collection, firestore_client=firestore_client)
    query = source.order_by('__name__').select(['id'])
    if after:
        query = query.start_after({'__name__': source.document(after)})
    return [snapshot.id for snapshot in query.limit(max(1, min(limit, 40))).stream(timeout=3)]


def history_count(uid, collection, *, firestore_client=None):
    return int(
        history_collection(uid, collection, firestore_client=firestore_client).count().get(timeout=3)[0][0].value
    )


def history_from_key(uid, collection, key, *, firestore_client=None):
    if not key or '/' in key:
        raise ValueError('dream_history_key')
    source = history_collection(uid, collection, firestore_client=firestore_client)
    query = source.order_by('__name__').select(['id'])
    found = next((s.id for s in query.start_at({'__name__': source.document(key)}).limit(1).stream(timeout=3)), None)
    return found or next((s.id for s in query.limit(1).stream(timeout=3)), None)


def review_id(ref):
    return sha256(ref.encode()).hexdigest()


def review_states(uid, refs, *, firestore_client=None):
    database = firestore_client if firestore_client is not None else get_firestore_client()
    source = database.collection('dream_users').document(uid).collection('reviews')
    keys = {review_id(ref): ref for ref in refs}
    if len(keys) > 40:
        raise ValueError('dream_review_read_limit')
    if not keys:
        return {}
    return {
        keys[snapshot.id]: snapshot.to_dict() or {}
        for snapshot in database.get_all([source.document(key) for key in keys], timeout=3)
    }
