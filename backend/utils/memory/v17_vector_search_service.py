from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

try:
    from database.vector_db import query_v17_memory_vector_candidates
except ModuleNotFoundError:
    query_v17_memory_vector_candidates = None

from models.v17_memory_search_gateway import SearchMode, hydrate_and_filter_vector_hits
from models.v17_product_memory import MemoryAccessPolicy
from utils.memory.v17_product_memory_read_service import fetch_authoritative_product_memory_items

DEFAULT_V17_VECTOR_SEARCH_LIMIT = 10
MAX_V17_VECTOR_SEARCH_LIMIT = 100


def fetch_default_v17_vector_memory_search(
    uid: str,
    query: str,
    *,
    db_client,
    policy: MemoryAccessPolicy,
    vector_query: Optional[Callable[..., Any]] = None,
    repair_purge_callback: Optional[Callable[[List[Dict[str, Any]]], Any]] = None,
    limit: int = DEFAULT_V17_VECTOR_SEARCH_LIMIT,
    required_projection_commit_id: str,
    required_account_generation: int,
) -> Dict[str, Any]:
    """Hydrate V17 vector candidates through authoritative `memory_items` before returning results.

    This is the narrow T20 service/gateway slice over the existing `ns2` vector
    namespace. The vector database is only a candidate source: every hit is
    hydrated from `users/{uid}/memory_items` and re-checked by the V17 search
    gateway so stale Short-term, Archive, tombstoned, hidden, sensitive, or
    projection-stale records cannot become default-visible through vector
    metadata alone. Archive search remains a separate explicit capability path.
    """

    bounded_limit = _validate_limit(limit)
    _validate_freshness_fence(
        required_projection_commit_id=required_projection_commit_id,
        required_account_generation=required_account_generation,
    )
    candidate_query = vector_query or query_v17_memory_vector_candidates
    if candidate_query is None:
        raise RuntimeError('query_v17_memory_vector_candidates is unavailable')
    candidate_result = candidate_query(uid, query, mode=SearchMode.default, limit=bounded_limit)
    authoritative_items = {
        item.memory_id: item for item in fetch_authoritative_product_memory_items(uid=uid, db_client=db_client)
    }
    gateway_result = hydrate_and_filter_vector_hits(
        hits=list(candidate_result.hits),
        authoritative_items=authoritative_items,
        policy=policy,
        mode=SearchMode.default,
        required_projection_commit_id=required_projection_commit_id,
        required_account_generation=required_account_generation,
    )
    repair_purge_candidates = list(gateway_result.repair_purge_candidates)
    if repair_purge_candidates and repair_purge_callback is not None:
        repair_purge_callback(repair_purge_candidates)
    return {
        'uid': uid,
        'query': query,
        'items': [result.item.model_dump(mode='json') for result in gateway_result.results],
        'scores_by_memory_id': {result.item.memory_id: result.score for result in gateway_result.results},
        'projection_commit_ids_by_memory_id': {
            result.item.memory_id: result.projection_commit_id for result in gateway_result.results
        },
        'decisions': {memory_id: decision.value for memory_id, decision in gateway_result.decisions.items()},
        'total_count': len(gateway_result.results),
        'returned_count': len(gateway_result.results),
        'limit': bounded_limit,
        'vector_rejected_count': int(getattr(candidate_result, 'rejected_count', 0)),
        'repair_purge_candidate_count': len(repair_purge_candidates),
        'repair_purge_candidates': repair_purge_candidates,
        'archive_default_visible': False,
    }


def _validate_limit(limit: int) -> int:
    if limit < 1 or limit > MAX_V17_VECTOR_SEARCH_LIMIT:
        raise ValueError(f'limit must be between 1 and {MAX_V17_VECTOR_SEARCH_LIMIT}')
    return limit


def _validate_freshness_fence(*, required_projection_commit_id: str, required_account_generation: int) -> None:
    if not isinstance(required_projection_commit_id, str) or not required_projection_commit_id.strip():
        raise ValueError('required_projection_commit_id is required')
    if not isinstance(required_account_generation, int) or required_account_generation < 0:
        raise ValueError('required_account_generation must be a nonnegative integer')
