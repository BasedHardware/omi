"""Owner-scoped history references and counts, never decrypted content scans."""

from hashlib import sha256
from typing import Any, Dict, List, Optional, cast

from database._client import get_firestore_client

COLLECTIONS = ('conversations', 'action_items', 'people', 'memory_items')


def _sanitize_uid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError('dream_history_uid')
    cleaned = value.strip()
    if (
        not cleaned
        or len(cleaned) > 128
        or any(ch in cleaned for ch in ('/', '\\', '\x00', '\r', '\n'))
        or '..' in cleaned
    ):
        raise ValueError('dream_history_uid')
    return cleaned


def _sanitize_doc_key(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError('dream_history_key')
    cleaned = value.strip()
    if (
        not cleaned
        or len(cleaned) > 128
        or any(ch in cleaned for ch in ('/', '\\', '\x00', '\r', '\n'))
        or '..' in cleaned
    ):
        raise ValueError('dream_history_key')
    return cleaned


def _sanitize_limit(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError('dream_history_limit')
    return max(1, min(value, 40))


def history_collection(uid: Any, collection: Any, *, firestore_client: Optional[Any] = None) -> Any:
    # Deferred: conversations imports dream_store -> dream_history, and import-isolated
    # database tests stub the models package.
    from models.agent_refs import canonical_collection

    clean_uid = _sanitize_uid(uid)
    if not isinstance(collection, str):
        raise ValueError('dream_history_collection')
    resolved = canonical_collection(collection.strip())
    if resolved not in COLLECTIONS:
        raise ValueError('dream_history_collection')
    database = firestore_client if firestore_client is not None else get_firestore_client()
    return database.collection('users').document(clean_uid).collection(resolved)


def history_page(
    uid: Any,
    collection: Any,
    *,
    after: Optional[Any] = None,
    limit: Any = 40,
    firestore_client: Optional[Any] = None,
) -> List[str]:
    bounded_limit = _sanitize_limit(limit)
    source = history_collection(uid, collection, firestore_client=firestore_client)
    query = source.order_by('__name__').select(['id'])
    if after is not None and after != '':
        clean_after = _sanitize_doc_key(after)
        query = query.start_after({'__name__': source.document(clean_after)})
    return [snapshot.id for snapshot in query.limit(bounded_limit).stream(timeout=3)]


def history_count(uid: Any, collection: Any, *, firestore_client: Optional[Any] = None) -> int:
    agg = history_collection(uid, collection, firestore_client=firestore_client).count().get(timeout=3)
    try:
        raw_val = agg[0][0].value
        if isinstance(raw_val, bool):
            return 0
        return max(0, int(raw_val))
    except (IndexError, TypeError, ValueError, AttributeError):
        return 0


def history_from_key(uid: Any, collection: Any, key: Any, *, firestore_client: Optional[Any] = None) -> Optional[str]:
    clean_key = _sanitize_doc_key(key)
    source = history_collection(uid, collection, firestore_client=firestore_client)
    query = source.order_by('__name__').select(['id'])
    found = next(
        (s.id for s in query.start_at({'__name__': source.document(clean_key)}).limit(1).stream(timeout=3)),
        None,
    )
    return found or next((s.id for s in query.limit(1).stream(timeout=3)), None)


def review_id(ref: object) -> str:
    if not isinstance(ref, str) or not ref.strip():
        raise ValueError('dream_review_ref')
    return sha256(ref.strip().encode()).hexdigest()


def review_states(uid: Any, refs: Any, *, firestore_client: Optional[Any] = None) -> Dict[str, Dict[str, Any]]:
    clean_uid = _sanitize_uid(uid)
    if isinstance(refs, (str, bytes)) or not hasattr(refs, '__iter__'):
        raise ValueError('dream_review_refs')
    database = firestore_client if firestore_client is not None else get_firestore_client()
    source = database.collection('dream_users').document(clean_uid).collection('reviews')
    keys = {review_id(ref): ref.strip() for ref in refs}
    if len(keys) > 40:
        raise ValueError('dream_review_read_limit')
    if not keys:
        return {}
    result: Dict[str, Dict[str, Any]] = {}
    for snapshot in database.get_all([source.document(key) for key in keys], timeout=3):
        snap_id = getattr(snapshot, 'id', None)
        if snap_id not in keys:
            continue
        raw_payload: object = snapshot.to_dict() if getattr(snapshot, 'exists', True) else {}
        payload: Dict[str, Any] = cast(Dict[str, Any], raw_payload) if isinstance(raw_payload, dict) else {}
        result[keys[snap_id]] = payload
    return result
