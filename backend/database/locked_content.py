"""Shared bounded mechanics for upgrade/reset access restoration."""

from typing import Any, Callable

from google.cloud.firestore_v1 import FieldFilter

from ._client import db
from .memory_collections import MemoryCollections


def unlock_query_rows(
    database: Any,
    query: Any,
    update: dict[str, Any],
    *,
    limit: int | None = None,
    on_commit: Callable[[], None] | None = None,
) -> int:
    if limit is not None:
        if not 1 <= limit <= 499:
            raise ValueError('unlock limit must be between 1 and 499')
        query = query.select([]).limit(limit)
    batch = database.batch()
    count = total = 0
    for doc in query.stream():
        batch.update(doc.reference, update)
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


def has_recoverable_locked_content(uid: str) -> bool:
    """True when any paid-lock row still needs the upgrade unlock.

    One keys-only document per collection, stopping at the first hit. Callers
    use this to skip an unbounded rewrite when nothing is locked.
    """
    user_ref = db.collection('users').document(uid)
    checks = (
        (user_ref.collection('conversations'), 'is_locked'),
        (user_ref.collection('memories'), 'is_locked'),
        (db.collection(MemoryCollections(uid=uid).memory_items), 'promotion.is_locked'),
        (user_ref.collection('action_items'), 'is_locked'),
    )
    for collection, field in checks:
        query = collection.where(filter=FieldFilter(field, '==', True)).select([]).limit(1)
        if next(iter(query.stream()), None) is not None:
            return True
    return False
