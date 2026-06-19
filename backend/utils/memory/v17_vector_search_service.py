from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Set

try:
    from database.vector_db import query_v17_memory_vector_candidates
except ModuleNotFoundError:
    query_v17_memory_vector_candidates = None

from database.v17_vector_repair_outbox import build_v17_vector_repair_purge_outbox_records
from models.v17_memory_search_gateway import SearchDecision, SearchMode, SearchVectorHit, hydrate_and_filter_vector_hits
from models.v17_product_memory import MemoryAccessPolicy, V17MemoryItem

DEFAULT_V17_VECTOR_SEARCH_LIMIT = 10
MAX_V17_VECTOR_SEARCH_LIMIT = 100
DEFAULT_V17_VECTOR_OVERFETCH_FACTOR = 3
DEFAULT_V17_VECTOR_MAX_CANDIDATES = 50
MAX_V17_VECTOR_OVERFETCH_FACTOR = 10


def fetch_default_v17_vector_memory_search(
    uid: str,
    query: str,
    *,
    db_client,
    policy: MemoryAccessPolicy,
    vector_query: Optional[Callable[..., Any]] = None,
    repair_purge_callback: Optional[Callable[[List[Dict[str, Any]]], Any]] = None,
    repair_purge_outbox_writer: Optional[Callable[[List[Dict[str, Any]]], Any]] = None,
    limit: int = DEFAULT_V17_VECTOR_SEARCH_LIMIT,
    overfetch_factor: int = DEFAULT_V17_VECTOR_OVERFETCH_FACTOR,
    max_candidates: int = DEFAULT_V17_VECTOR_MAX_CANDIDATES,
    required_projection_commit_id: str,
    required_account_generation: int,
) -> Dict[str, Any]:
    """Hydrate V17 vector candidates through authoritative `memory_items` before returning results.

    Vector DB is only a candidate source. This service asks for a bounded overfetch
    window, hydrates candidates by ID from `users/{uid}/memory_items`, and refills
    by increasing the vector candidate request up to a hard `max_candidates` cap
    when early candidates are removed by freshness/access checks. Archive search
    remains a separate explicit capability path.
    """

    bounded_limit = _validate_limit(limit)
    bounded_overfetch_factor = _validate_overfetch_factor(overfetch_factor)
    candidate_budget = _validate_max_candidates(max_candidates=max_candidates, bounded_limit=bounded_limit)
    _validate_freshness_fence(
        required_projection_commit_id=required_projection_commit_id,
        required_account_generation=required_account_generation,
    )
    candidate_query = vector_query or query_v17_memory_vector_candidates
    if candidate_query is None:
        raise RuntimeError('query_v17_memory_vector_candidates is unavailable')

    candidate_request_limit = min(max(bounded_limit * bounded_overfetch_factor, bounded_limit), candidate_budget)
    vector_query_count = 0
    vector_rejected_count = 0
    all_hits: List[SearchVectorHit] = []
    hydrated_items: Dict[str, V17MemoryItem] = {}
    missing_authoritative_memory_ids: Set[str] = set()

    while True:
        candidate_result = candidate_query(uid, query, mode=SearchMode.default, limit=candidate_request_limit)
        vector_query_count += 1
        vector_rejected_count += int(getattr(candidate_result, 'rejected_count', 0))
        all_hits = list(candidate_result.hits)[:candidate_budget]
        _hydrate_vector_candidate_items_by_id(
            uid=uid,
            db_client=db_client,
            hits=all_hits,
            hydrated_items=hydrated_items,
            missing_authoritative_memory_ids=missing_authoritative_memory_ids,
        )
        gateway_result = hydrate_and_filter_vector_hits(
            hits=all_hits,
            authoritative_items=hydrated_items,
            policy=policy,
            mode=SearchMode.default,
            required_projection_commit_id=required_projection_commit_id,
            required_account_generation=required_account_generation,
        )
        if len(gateway_result.results) >= bounded_limit:
            break
        if candidate_request_limit >= candidate_budget:
            break
        if len(all_hits) < candidate_request_limit:
            break
        candidate_request_limit = min(
            candidate_budget, max(candidate_request_limit + bounded_limit, candidate_request_limit * 2)
        )

    returned_results = list(gateway_result.results)[:bounded_limit]
    repair_purge_candidates = list(gateway_result.repair_purge_candidates)
    repair_purge_outbox_records = build_v17_vector_repair_purge_outbox_records(
        uid=uid, candidates=repair_purge_candidates
    )
    if repair_purge_candidates and repair_purge_callback is not None:
        repair_purge_callback(repair_purge_candidates)
    if repair_purge_outbox_records and repair_purge_outbox_writer is not None:
        repair_purge_outbox_writer(repair_purge_outbox_records)
    return {
        'uid': uid,
        'query': query,
        'items': [result.item.model_dump(mode='json') for result in returned_results],
        'scores_by_memory_id': {result.item.memory_id: result.score for result in returned_results},
        'projection_commit_ids_by_memory_id': {
            result.item.memory_id: result.projection_commit_id for result in returned_results
        },
        'decisions': {memory_id: decision.value for memory_id, decision in gateway_result.decisions.items()},
        'total_count': len(gateway_result.results),
        'returned_count': len(returned_results),
        'limit': bounded_limit,
        'overfetch_factor': bounded_overfetch_factor,
        'candidate_budget': candidate_budget,
        'candidate_request_limit': candidate_request_limit,
        'candidate_budget_exhausted': candidate_request_limit >= candidate_budget
        and len(returned_results) < bounded_limit,
        'vector_query_count': vector_query_count,
        'queried_candidate_count': len(all_hits),
        'hydrated_candidate_count': len(hydrated_items),
        'hydration_rejected_missing_count': _count_decisions(
            gateway_result.decisions, SearchDecision.missing_authoritative_item
        ),
        'hydration_rejected_stale_projection_count': _count_decisions(
            gateway_result.decisions, SearchDecision.stale_projection
        ),
        'hydration_rejected_stale_vector_count': _count_decisions(
            gateway_result.decisions, SearchDecision.stale_vector
        ),
        'hydration_rejected_access_denied_count': _count_decisions(
            gateway_result.decisions, SearchDecision.access_denied
        ),
        'vector_rejected_count': vector_rejected_count,
        'repair_purge_candidate_count': len(repair_purge_candidates),
        'repair_purge_candidates': repair_purge_candidates,
        'repair_purge_outbox_record_count': len(repair_purge_outbox_records),
        'repair_purge_outbox_records': repair_purge_outbox_records,
        'archive_default_visible': False,
    }


def _validate_limit(limit: int) -> int:
    if limit < 1 or limit > MAX_V17_VECTOR_SEARCH_LIMIT:
        raise ValueError(f'limit must be between 1 and {MAX_V17_VECTOR_SEARCH_LIMIT}')
    return limit


def _validate_overfetch_factor(overfetch_factor: int) -> int:
    if (
        not isinstance(overfetch_factor, int)
        or overfetch_factor < 1
        or overfetch_factor > MAX_V17_VECTOR_OVERFETCH_FACTOR
    ):
        raise ValueError(f'overfetch_factor must be between 1 and {MAX_V17_VECTOR_OVERFETCH_FACTOR}')
    return overfetch_factor


def _validate_max_candidates(*, max_candidates: int, bounded_limit: int) -> int:
    if (
        not isinstance(max_candidates, int)
        or max_candidates < bounded_limit
        or max_candidates > MAX_V17_VECTOR_SEARCH_LIMIT
    ):
        raise ValueError(f'max_candidates must be between limit and {MAX_V17_VECTOR_SEARCH_LIMIT}')
    return max_candidates


def _validate_freshness_fence(*, required_projection_commit_id: str, required_account_generation: int) -> None:
    if not isinstance(required_projection_commit_id, str) or not required_projection_commit_id.strip():
        raise ValueError('required_projection_commit_id is required')
    if not isinstance(required_account_generation, int) or required_account_generation < 0:
        raise ValueError('required_account_generation must be a nonnegative integer')


def _hydrate_vector_candidate_items_by_id(
    *,
    uid: str,
    db_client,
    hits: List[SearchVectorHit],
    hydrated_items: Dict[str, V17MemoryItem],
    missing_authoritative_memory_ids: Set[str],
) -> None:
    for hit in hits:
        if hit.memory_id in hydrated_items or hit.memory_id in missing_authoritative_memory_ids:
            continue
        snapshot = db_client.document(f'users/{uid}/memory_items/{hit.memory_id}').get()
        payload = snapshot.to_dict() or {}
        if not payload:
            missing_authoritative_memory_ids.add(hit.memory_id)
            continue
        item = V17MemoryItem.model_validate(payload)
        if item.uid != uid:
            raise ValueError(f'memory item uid mismatch: expected {uid}, got {item.uid}')
        hydrated_items[item.memory_id] = item


def _count_decisions(decisions: Dict[str, SearchDecision], decision: SearchDecision) -> int:
    return sum(1 for observed in decisions.values() if observed == decision)
