"""Single-field, bounded query builders for batch privacy and retention."""

from typing import Any
from google.cloud.firestore_v1 import FieldFilter

QUERY_LIMIT_CEILING = 100


def sanitize_identifier(value: Any, field: str) -> str:
    """Collection path segments must be non-empty and whitespace-free.

    Retention callers derive collection names from request-scoped identifiers, so a
    padded or empty value would silently build a malformed Firestore path and sweep
    nothing (or fail deep inside the client).
    """
    if isinstance(value, bool) or not isinstance(value, str) or not value.strip():
        raise ValueError(f'{field} must be a non-empty string')
    return value.strip()


def bounded_limit(limit: Any) -> int:
    """Normalize a caller-supplied page size to the documented ceiling."""
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError('limit must be an integer')
    return max(1, min(QUERY_LIMIT_CEILING, limit))


def _validate_client(client: Any) -> Any:
    if client is None:
        raise ValueError('client must not be None')
    return client


def owner_documents(
    client: Any,
    namespace: str,
    table: str,
    key: str,
    *,
    after: Any = None,
    limit: int = QUERY_LIMIT_CEILING,
) -> list:
    """Bounded, paginated owner query for batch pipeline privacy erasure.

    Errors during stream read are propagated so that calling sweeps (e.g.
    purge_batch_owner) crash and retry rather than falsely concluding that
    the collection has reached end-of-data.
    """
    client = _validate_client(client)
    namespace = sanitize_identifier(namespace, 'namespace')
    table = sanitize_identifier(table, 'table')
    key = sanitize_identifier(key, 'key')
    limit = bounded_limit(limit)

    query = client.collection(f'{namespace}_{table}').where(filter=FieldFilter('owner_key', '==', key))
    if after is not None:
        query = query.start_after(after)
    return list(query.limit(limit).stream())


def predecessor_documents(client: Any, namespace: str, segment_id: str, transaction: Any) -> list:
    """Find predecessor jobs for a segment under transactional lock.

    Popped jobs retain old next pointers, so only ready jobs can be predecessors.
    Errors propagate out of the read to allow the transaction to abort and retry safely.
    """
    client = _validate_client(client)
    namespace = sanitize_identifier(namespace, 'namespace')
    segment_id = sanitize_identifier(segment_id, 'segment_id')

    return list(
        client.collection(f'{namespace}_jobs')
        .where(filter=FieldFilter('next', '==', segment_id))
        .where(filter=FieldFilter('state', '==', 'ready'))
        .limit(1)
        .stream(transaction=transaction)
    )


def segment_artifacts(client: Any, namespace: str, segment_id: str, transaction: Any) -> list:
    """Bounded transactional query for artifacts associated with a segment.

    Stream errors are propagated so calling transactions (e.g. expire_completed_segment)
    abort and re-evaluate rather than silently skipping arming cleanup_after.
    """
    client = _validate_client(client)
    namespace = sanitize_identifier(namespace, 'namespace')
    segment_id = sanitize_identifier(segment_id, 'segment_id')

    return list(
        client.collection(f'{namespace}_artifacts')
        .where(filter=FieldFilter('segment_id', '==', segment_id))
        .limit(256)
        .stream(transaction=transaction)
    )


def due_artifacts(client: Any, namespace: str, now: Any, limit: int = QUERY_LIMIT_CEILING) -> list:
    """Bounded query for artifacts due for retention cleanup.

    Errors propagate so that retention workers retry the sweep on transient failures.
    """
    client = _validate_client(client)
    namespace = sanitize_identifier(namespace, 'namespace')
    limit = bounded_limit(limit)

    return list(
        client.collection(f'{namespace}_artifacts')
        .where(filter=FieldFilter('cleanup_after', '<=', now))
        .limit(limit)
        .stream()
    )
