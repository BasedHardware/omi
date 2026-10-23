"""Candidate-only MCP memory reads. MemoryService policies remain authoritative."""

import logging
from typing import Any, Optional

from google.api_core.exceptions import FailedPrecondition
from google.cloud.firestore_v1 import FieldFilter

from database._client import get_firestore_client
from database.firestore_index_registry import MCP_MEMORY_FILTER_QUERIES
from utils.observability.fallback import record_fallback
from utils.other.list_budget import ListReadBudget, budgeted_stream_list

logger = logging.getLogger(__name__)
MCP_FILTER_SCAN_LIMIT = 5000


def read_mcp_memory_candidates(
    uid: str,
    *,
    origin: str,
    filters: dict,
    firestore_client: Any = None,
    budget: Optional[ListReadBudget] = None,
    max_candidates: int = MCP_FILTER_SCAN_LIMIT
) -> list[Any]:
    """Read a complete bounded candidate window, never a success-shaped prefix.

    The strongest safe predicate is indexed. Missing legacy booleans/category
    are coalesced by the adapter, so false/default filters stay post-read.
    Fallback uses the automatic updated_at index and retains the date bound;
    the caller checks the cap before applying policy or claiming exhaustion.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    scan_limit = max(1, min(max_candidates, MCP_FILTER_SCAN_LIMIT))
    collection = client.collection('users').document(uid).collection(origin)
    if filters.get('updated_after') is not None:
        predicate = 'updated_after'
    elif filters.get('reviewed') is True:
        predicate = 'reviewed'
    elif filters.get('manually_added') is True:
        predicate = 'manually_added'
    elif filters.get('categories') and 'interesting' not in filters['categories']:
        predicate = 'categories'
    else:
        predicate = 'all'
    spec = MCP_MEMORY_FILTER_QUERIES[(origin, predicate)]
    query = spec.build(collection, filters, field_filter_factory=FieldFilter)
    try:
        snapshots = budgeted_stream_list(
            query.order_by('updated_at', direction='DESCENDING').order_by('__name__').limit(scan_limit + 1),
            budget,
        )
    except FailedPrecondition:
        record_fallback(
            component='other', from_mode='indexed', to_mode='scan', reason='other', outcome='degraded', log=logger
        )
        query = collection.order_by('updated_at', direction='DESCENDING')
        if filters.get('updated_after') is not None:
            query = query.where(filter=FieldFilter('updated_at', '>=', filters['updated_after']))
        snapshots = budgeted_stream_list(query.limit(scan_limit + 1), budget)
    if origin == 'memories' and filters.get('updated_after') is None:
        created = budgeted_stream_list(
            collection.order_by('created_at', direction='DESCENDING').limit(scan_limit + 1), budget
        )
        if len(created) > scan_limit:
            # Do not claim a complete false/default filter over a bounded legacy scan.
            return created
        by_id = {snapshot.id: snapshot for snapshot in snapshots}
        for snapshot in created:
            if (snapshot.to_dict() or {}).get('updated_at') is None:
                by_id[snapshot.id] = snapshot
        snapshots = list(by_id.values())
    return snapshots
