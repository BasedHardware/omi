"""Single-field, bounded query builders for batch privacy and retention."""

import logging
from typing import Any, Optional
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client

logger = logging.getLogger(__name__)


def owner_documents(
    client: Any,
    namespace: str,
    table: str,
    key: str,
    *,
    after: Any = None,
    limit: int = 100,
) -> list:
    clean_ns = namespace.strip() if isinstance(namespace, str) else ''
    clean_table = table.strip() if isinstance(table, str) else ''
    clean_key = key.strip() if isinstance(key, str) else ''
    if not clean_ns or not clean_table or not clean_key:
        return []
    bounded_limit = max(1, min(100, limit)) if isinstance(limit, int) and not isinstance(limit, bool) else 100
    try:
        firestore_client = client if client is not None else get_firestore_client()
        query = firestore_client.collection(f'{clean_ns}_{clean_table}').where(
            filter=FieldFilter('owner_key', '==', clean_key)
        )
        if after is not None:
            query = query.start_after(after)
        return list(query.limit(bounded_limit).stream())
    except Exception as e:
        logger.warning("Error querying owner_documents for %s_%s: %s", clean_ns, clean_table, e)
        return []


def predecessor_documents(client: Any, namespace: str, segment_id: str, transaction: Any) -> list:
    # Popped jobs retain old next pointers, so only ready jobs can be predecessors.
    clean_ns = namespace.strip() if isinstance(namespace, str) else ''
    clean_seg = segment_id.strip() if isinstance(segment_id, str) else ''
    if not clean_ns or not clean_seg:
        return []
    try:
        firestore_client = client if client is not None else get_firestore_client()
        return list(
            firestore_client.collection(f'{clean_ns}_jobs')
            .where(filter=FieldFilter('next', '==', clean_seg))
            .where(filter=FieldFilter('state', '==', 'ready'))
            .limit(1)
            .stream(transaction=transaction)
        )
    except Exception as e:
        logger.warning("Error querying predecessor_documents for %s_jobs: %s", clean_ns, e)
        return []


def segment_artifacts(client: Any, namespace: str, segment_id: str, transaction: Any) -> list:
    clean_ns = namespace.strip() if isinstance(namespace, str) else ''
    clean_seg = segment_id.strip() if isinstance(segment_id, str) else ''
    if not clean_ns or not clean_seg:
        return []
    try:
        firestore_client = client if client is not None else get_firestore_client()
        return list(
            firestore_client.collection(f'{clean_ns}_artifacts')
            .where(filter=FieldFilter('segment_id', '==', clean_seg))
            .limit(256)
            .stream(transaction=transaction)
        )
    except Exception as e:
        logger.warning("Error querying segment_artifacts for %s_artifacts: %s", clean_ns, e)
        return []


def due_artifacts(client: Any, namespace: str, now: Any, limit: int = 100) -> list:
    clean_ns = namespace.strip() if isinstance(namespace, str) else ''
    if not clean_ns or now is None:
        return []
    bounded_limit = max(1, min(100, limit)) if isinstance(limit, int) and not isinstance(limit, bool) else 100
    try:
        firestore_client = client if client is not None else get_firestore_client()
        return list(
            firestore_client.collection(f'{clean_ns}_artifacts')
            .where(filter=FieldFilter('cleanup_after', '<=', now))
            .limit(bounded_limit)
            .stream()
        )
    except Exception as e:
        logger.warning("Error querying due_artifacts for %s_artifacts: %s", clean_ns, e)
        return []
