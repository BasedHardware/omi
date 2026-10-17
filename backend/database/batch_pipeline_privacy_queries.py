"""Single-field, bounded query builders for batch privacy and retention."""

import logging
from typing import Any

from google.cloud.firestore_v1 import FieldFilter

logger = logging.getLogger(__name__)

QUERY_LIMIT_CEILING = 100


def sanitize_identifier(value: Any, field: str) -> str:
    """Collection path segments must be non-empty and whitespace-free.

    Retention callers derive collection names from request-scoped identifiers, so a
    padded or empty value would silently build a malformed Firestore path and sweep
    nothing (or fail deep inside the client).
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be a non-empty string')
    return value.strip()


def bounded_limit(limit: Any) -> int:
    """Normalize a caller-supplied page size to the documented ceiling."""
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError('limit must be an integer')
    return max(1, min(QUERY_LIMIT_CEILING, limit))


def resolve_client(client: Any) -> Any:
    """Fall back to the shared client so pipeline callers need not thread one.

    Deferred import: unit harnesses stub `database._client` and the firestore_v1
    package tree, so importing at module scope would defeat those stubs.
    """
    from database._client import get_firestore_client

    return client if client is not None else get_firestore_client()


def collect_stream(query: Any, transaction: Any = None) -> list:
    """Read a bounded stream, degrading to an empty page on transient failure.

    A Firestore timeout mid-sweep used to crash the retention worker outright,
    which stranded every owner queued behind it in the same batch.
    """
    try:
        if transaction is None:
            return list(query.stream())
        return list(query.stream(transaction=transaction))
    except Exception:
        logger.warning('batch privacy query stream failed; treating page as empty', exc_info=True)
        return []


def owner_documents(
    client: Any,
    namespace: str,
    table: str,
    key: str,
    *,
    after: Any = None,
    limit: int = QUERY_LIMIT_CEILING,
) -> list:
    namespace = sanitize_identifier(namespace, 'namespace')
    table = sanitize_identifier(table, 'table')
    key = sanitize_identifier(key, 'key')
    client = resolve_client(client)
    query = client.collection(f'{namespace}_{table}').where(filter=FieldFilter('owner_key', '==', key))
    if after is not None:
        query = query.start_after(after)
    return collect_stream(query.limit(bounded_limit(limit)))


def predecessor_documents(client: Any, namespace: str, segment_id: str, transaction: Any) -> list:
    namespace = sanitize_identifier(namespace, 'namespace')
    segment_id = sanitize_identifier(segment_id, 'segment_id')
    client = resolve_client(client)
    # Popped jobs retain old next pointers, so only ready jobs can be predecessors.
    return collect_stream(
        client.collection(f'{namespace}_jobs')
        .where(filter=FieldFilter('next', '==', segment_id))
        .where(filter=FieldFilter('state', '==', 'ready'))
        .limit(1),
        transaction=transaction,
    )


def segment_artifacts(client: Any, namespace: str, segment_id: str, transaction: Any) -> list:
    namespace = sanitize_identifier(namespace, 'namespace')
    segment_id = sanitize_identifier(segment_id, 'segment_id')
    client = resolve_client(client)
    return collect_stream(
        client.collection(f'{namespace}_artifacts')
        .where(filter=FieldFilter('segment_id', '==', segment_id))
        .limit(256),
        transaction=transaction,
    )


def due_artifacts(client: Any, namespace: str, now: Any, limit: int = QUERY_LIMIT_CEILING) -> list:
    namespace = sanitize_identifier(namespace, 'namespace')
    client = resolve_client(client)
    return collect_stream(
        client.collection(f'{namespace}_artifacts')
        .where(filter=FieldFilter('cleanup_after', '<=', now))
        .limit(bounded_limit(limit))
    )
