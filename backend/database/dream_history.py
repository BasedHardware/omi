"""Owner-scoped history references and counts, never decrypted content scans."""

from hashlib import sha256

from database._client import get_firestore_client

COLLECTIONS = ('conversations', 'action_items', 'people', 'memory_items')
_MAX_DOCUMENT_ID_LENGTH = 128
_MAX_REVIEW_READ = 40
_DEFAULT_PAGE_LIMIT = 40
_RESERVED_SEGMENTS = frozenset({'', '.', '..', '__reserved__'})


def _clean_owner_uid(uid) -> str:
    """A user document id; an unusable one cannot address an owner-scoped path."""
    if not isinstance(uid, str) or isinstance(uid, bool):
        raise ValueError('dream_history_uid')
    token = uid.strip()
    if token in _RESERVED_SEGMENTS or len(token) > _MAX_DOCUMENT_ID_LENGTH:
        raise ValueError('dream_history_uid')
    if any(char in token for char in '/\\') or '..' in token:
        raise ValueError('dream_history_uid')
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in token):
        raise ValueError('dream_history_uid')
    return token


def _clean_document_id(value, code: str) -> str:
    if not isinstance(value, str) or isinstance(value, bool):
        raise ValueError(code)
    token = value.strip()
    if token in _RESERVED_SEGMENTS or len(token) > _MAX_DOCUMENT_ID_LENGTH:
        raise ValueError(code)
    if any(char in token for char in '/\\') or '..' in token:
        raise ValueError(code)
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in token):
        raise ValueError(code)
    return token


def _clean_limit(limit) -> int:
    """A bounded page size; booleans and non-integers fall back to the default."""
    if isinstance(limit, bool) or not isinstance(limit, int):
        return _DEFAULT_PAGE_LIMIT
    return max(1, min(limit, _DEFAULT_PAGE_LIMIT))


def history_collection(uid, collection, *, firestore_client=None):
    # Deferred: conversations imports dream_store -> dream_history, and import-isolated
    # database tests stub the models package.
    from models.agent_refs import canonical_collection

    collection = canonical_collection(collection)
    if collection not in COLLECTIONS:
        raise ValueError('dream_history_collection')
    uid = _clean_owner_uid(uid)
    database = firestore_client if firestore_client is not None else get_firestore_client()
    return database.collection('users').document(uid).collection(collection)


def history_page(uid, collection, *, after=None, limit=_DEFAULT_PAGE_LIMIT, firestore_client=None):
    source = history_collection(uid, collection, firestore_client=firestore_client)
    query = source.order_by('__name__').select(['id'])
    if after is not None:
        cursor = _clean_document_id(after, 'dream_history_cursor')
        query = query.start_after({'__name__': source.document(cursor)})
    return [snapshot.id for snapshot in query.limit(_clean_limit(limit)).stream(timeout=3)]


def history_count(uid, collection, *, firestore_client=None):
    result = history_collection(uid, collection, firestore_client=firestore_client).count().get(timeout=3)
    try:
        return int(result[0][0].value)
    except (IndexError, TypeError, ValueError, AttributeError):
        return 0


def history_from_key(uid, collection, key, *, firestore_client=None):
    key = _clean_document_id(key, 'dream_history_key')
    source = history_collection(uid, collection, firestore_client=firestore_client)
    query = source.order_by('__name__').select(['id'])
    cursor = {'__name__': source.document(key)}
    found = next((s.id for s in query.start_at(cursor).limit(1).stream(timeout=3)), None)
    return found or next((s.id for s in query.limit(1).stream(timeout=3)), None)


def review_id(ref):
    if not isinstance(ref, str) or isinstance(ref, bool):
        raise ValueError('dream_review_ref')
    return sha256(ref.encode()).hexdigest()


def review_states(uid, refs, *, firestore_client=None):
    """
    Review state by reference; unusable references are skipped, never hashed.
    """
    uid = _clean_owner_uid(uid)
    if isinstance(refs, (str, bytes)) or not hasattr(refs, '__iter__'):
        raise ValueError('dream_review_refs')
    keys = {}
    for ref in refs:
        try:
            keys.setdefault(review_id(ref), ref)
        except ValueError:
            continue
        if len(keys) > _MAX_REVIEW_READ:
            raise ValueError('dream_review_read_limit')
    if not keys:
        return {}
    database = firestore_client if firestore_client is not None else get_firestore_client()
    source = database.collection('dream_users').document(uid).collection('reviews')
    return {
        keys[snapshot.id]: (snapshot.to_dict() or {})
        for snapshot in database.get_all([source.document(key) for key in keys], timeout=3)
    }
