"""Advice — proactive coaching items.

Collection: users/{uid}/advice
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from database.store import Filter, get_document_store

logger = logging.getLogger(__name__)

BATCH_LIMIT = 500  # chunk large batched writes for throughput


def _store():
    return get_document_store()


def _advice_col(uid: str) -> str:
    """Logical path of the users/{uid}/advice collection."""
    return f'users/{uid}/advice'


def create_advice(uid: str, content: str, category: str = 'other', **kwargs: Any) -> Dict[str, Any]:
    advice_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    doc: Dict[str, Any] = {
        'id': advice_id,
        'content': content,
        'category': category,
        'reasoning': kwargs.get('reasoning'),
        'source_app': kwargs.get('source_app'),
        'confidence': kwargs.get('confidence', 0.5),
        'context_summary': kwargs.get('context_summary'),
        'current_activity': kwargs.get('current_activity'),
        'created_at': now,
        'updated_at': now,
        'is_read': False,
        'is_dismissed': False,
    }
    _store().set(f'{_advice_col(uid)}/{advice_id}', doc)
    return doc


def get_advice(
    uid: str, category: Optional[str] = None, limit: int = 50, offset: int = 0, include_dismissed: bool = False
) -> List[Dict[str, Any]]:
    filters: List[Filter] = []
    if category:
        filters.append(('category', '==', category))
    if not include_dismissed:
        filters.append(('is_dismissed', '==', False))

    docs = _store().query(
        _advice_col(uid),
        filters=filters,
        order_by='created_at',
        direction='desc',
        limit=limit,
        offset=offset if offset > 0 else None,
    )

    items: List[Dict[str, Any]] = []
    for doc in docs:
        raw: object = doc.to_dict()
        data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        data['id'] = doc.id
        items.append(data)
    return items


def update_advice(
    uid: str, advice_id: str, is_read: Optional[bool] = None, is_dismissed: Optional[bool] = None
) -> Optional[Dict[str, Any]]:
    path = f'{_advice_col(uid)}/{advice_id}'
    updates: Dict[str, Any] = {'updated_at': datetime.now(timezone.utc)}
    if is_read is not None:
        updates['is_read'] = is_read
    if is_dismissed is not None:
        updates['is_dismissed'] = is_dismissed

    # Read-then-write atomically: if the advice is gone (deleted concurrently) return None (404)
    # rather than resurrecting it or crashing. A plain update() diverges across backends on a
    # missing doc (Firestore raises, Mongo no-ops, the fake creates), so the existence gate and the
    # write must share one transaction.
    def _apply(tx: Any) -> Optional[Dict[str, Any]]:
        snap = tx.get(path)
        if not snap.exists:
            return None
        tx.update(path, updates)
        raw: object = snap.to_dict()
        result: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
        result.update(updates)
        result['id'] = advice_id
        return result

    return _store().run_transaction(_apply)


def delete_advice(uid: str, advice_id: str) -> bool:
    path = f'{_advice_col(uid)}/{advice_id}'
    if not _store().get(path).exists:
        return False
    _store().delete(path)
    return True


def mark_all_advice_read(uid: str) -> int:
    """Mark every unread advice as read, one bounded page at a time.

    Fetching the whole ``is_read == False`` set before the first commit is unbounded memory for a
    large backlog. Each committed page leaves the unread set (its docs become ``is_read == True``),
    so re-running the same bounded query returns the next page until it drains — bounded memory
    regardless of backlog size.
    """
    store = _store()
    col = _advice_col(uid)
    total = 0
    while True:
        page = store.query(col, filters=[('is_read', '==', False)], limit=BATCH_LIMIT)
        if not page:
            break
        batch = store.batch()
        for doc in page:
            batch.update(doc.path, {'is_read': True, 'updated_at': datetime.now(timezone.utc)})
        batch.commit()
        total += len(page)
        if len(page) < BATCH_LIMIT:
            break
    return total
