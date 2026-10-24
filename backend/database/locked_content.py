"""Shared bounded mechanics for upgrade/reset access restoration."""

import logging
from typing import Any, Callable, Optional

from google.cloud.firestore_v1 import FieldFilter

from ._client import db
from .memory_collections import MemoryCollections

logger = logging.getLogger(__name__)

_MAX_ID_LENGTH = 128


def _sanitize_uid(uid: Any) -> str:
    """Return a Firestore-safe ``uid`` or raise ``ValueError``.

    A blank id, a path separator, a traversal segment, a control character or an
    overlong id either composes an invalid document path that the SDK rejects far
    from the call site, or silently addresses a different document.
    """
    if not isinstance(uid, str):
        raise ValueError('uid must be a string')
    text = uid.strip()
    if not text:
        raise ValueError('uid must not be empty')
    if len(text) > _MAX_ID_LENGTH:
        raise ValueError(f'uid must be at most {_MAX_ID_LENGTH} characters')
    if '/' in text or '\\' in text or '..' in text:
        raise ValueError('uid must not contain path separators or traversal segments')
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in text):
        raise ValueError('uid must not contain control characters')
    return text


def _validate_limit(limit: Any) -> int:
    """Return the batch page size or raise ``ValueError``.

    ``bool`` is a subclass of ``int``, so ``1 <= True <= 499`` is true and ``True``
    reaches ``query.limit()`` as a silent 1. A float passes the range check too
    (``1 <= 1.5 <= 499``) and only fails inside the SDK, and a string raises
    ``TypeError`` on the comparison itself instead of a typed error here.
    """
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError('unlock limit must be an integer between 1 and 499')
    if not 1 <= limit <= 499:
        raise ValueError('unlock limit must be between 1 and 499')
    return limit


def _validate_update(update: Any) -> dict[str, Any]:
    """Return a non-empty field mapping or raise ``ValueError``.

    An empty mapping is accepted by this helper today and only fails at
    ``batch.update`` after the whole query has streamed, so the caller pays for a
    full read before learning the write was impossible.
    """
    if not isinstance(update, dict):
        raise ValueError('unlock update must be a dict of fields')
    if not update:
        raise ValueError('unlock update must not be empty')
    return update


def unlock_query_rows(
    database: Any,
    query: Any,
    update: dict[str, Any],
    *,
    limit: Optional[int] = None,
    on_commit: Optional[Callable[[], None]] = None,
) -> int:
    fields = _validate_update(update)
    if limit is not None:
        query = query.select([]).limit(_validate_limit(limit))
    batch = database.batch()
    count = total = 0
    for doc in query.stream():
        reference = getattr(doc, 'reference', None)
        if reference is None:
            # A projection row without a document reference cannot be updated; skip it
            # rather than raising AttributeError halfway through a committed batch run.
            # Log it: a skipped row is a locked document we did not unlock, and the
            # caller only ever sees the returned count.
            logger.warning('locked-content row skipped reason=missing_reference')
            continue
        batch.update(reference, fields)
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

    The probe is an optimisation, not the authority: one collection failing to
    stream must not hide a lock that the remaining collections can still report,
    so each probe is isolated and a failure is logged and skipped.
    """
    safe_uid = _sanitize_uid(uid)
    client = firestore_client if firestore_client is not None else db
    user_ref = client.collection('users').document(safe_uid)
    checks = (
        (user_ref.collection('conversations'), 'is_locked'),
        (user_ref.collection('memories'), 'is_locked'),
        (client.collection(MemoryCollections(uid=safe_uid).memory_items), 'promotion.is_locked'),
        (user_ref.collection('action_items'), 'is_locked'),
    )
    for collection, field in checks:
        try:
            query = collection.where(filter=FieldFilter(field, '==', True)).select([]).limit(1)
            if next(iter(query.stream()), None) is not None:
                return True
        except Exception as error:  # noqa: BLE001 - one probe failure must not hide the others
            logger.warning('locked-content probe failed uid=%s field=%s: %s', safe_uid, field, error)
    return False
