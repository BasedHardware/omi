"""Shared bounded mechanics for upgrade/reset access restoration."""

import logging
from typing import Any, Callable, Optional

from google.cloud.firestore_v1 import FieldFilter

from ._client import db
from .memory_collections import MemoryCollections

logger = logging.getLogger(__name__)


def _sanitize_uid(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError('uid must be a non-empty string')
    cleaned = value.strip()
    if (
        not cleaned
        or len(cleaned) > 128
        or any(ch in cleaned for ch in ('/', '\\', '\x00', '\r', '\n'))
        or '..' in cleaned
    ):
        raise ValueError('uid must be a safe document id')
    return cleaned


def _clean_optional_uid(value: object) -> str:
    try:
        return _sanitize_uid(value)
    except ValueError:
        return ''


def unlock_query_rows(
    database: Any,
    query: Any,
    update: dict[str, Any],
    *,
    limit: int | None = None,
    on_commit: Callable[[], None] | None = None,
) -> int:
    if not isinstance(update, dict) or not update:
        raise ValueError('unlock update must be a non-empty dict')
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 499:
            raise ValueError('unlock limit must be between 1 and 499')
        query = query.select([]).limit(limit)
    batch = database.batch()
    count = total = 0
    for doc in query.stream():
        ref = getattr(doc, 'reference', None)
        if ref is None:
            continue
        batch.update(ref, update)
        count += 1
        total += 1
        if count == 499:
            batch.commit()
            if on_commit:
                on_commit()
            batch = database.batch()
            count = 0
    if count:
        batch.commit()
        if on_commit:
            on_commit()
    if limit is not None and total == 0 and on_commit:
        # A retry repairs invalidation after an ambiguous successful commit.
        on_commit()
    return total


def has_recoverable_locked_content(uid: str, *, firestore_client: Optional[Any] = None) -> bool:
    """True when any paid-lock row still needs the upgrade unlock.

    One keys-only document per collection, stopping at the first hit. Callers
    use this to skip an unbounded rewrite when nothing is locked.
    """
    clean_uid = _clean_optional_uid(uid)
    if not clean_uid:
        return False
    client = firestore_client if firestore_client is not None else db
    user_ref = client.collection('users').document(clean_uid)
    checks = (
        (user_ref.collection('conversations'), 'is_locked'),
        (user_ref.collection('memories'), 'is_locked'),
        (client.collection(MemoryCollections(uid=clean_uid).memory_items), 'promotion.is_locked'),
        (user_ref.collection('action_items'), 'is_locked'),
    )
    for collection, field in checks:
        try:
            query = collection.where(filter=FieldFilter(field, '==', True)).select([]).limit(1)
            if next(iter(query.stream()), None) is not None:
                return True
        except Exception as exc:
            logger.warning('Failed to probe locked content on field %s for %s: %s', field, clean_uid, exc)
            continue
    return False
