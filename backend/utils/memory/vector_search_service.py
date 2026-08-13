from __future__ import annotations

"""Canonical vector search service module (WS-G8a).

Neutral ``vector_search_service`` is the source of truth. Canonical vector search service.
"""


import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set, cast

try:
    from database.vector_db import query_memory_vector_candidates
except ModuleNotFoundError:
    query_memory_vector_candidates = None

from database.memory_vector_repair_outbox import build_vector_repair_purge_outbox_records
from models.memory_search_gateway import SearchDecision, SearchMode, SearchVectorHit, hydrate_and_filter_vector_hits
from models.product_memory import MemoryAccessPolicy, MemoryItem
from utils.memory.vector_search_telemetry import (
    VectorSearchTelemetryConfig,
    emit_memory_vector_search_telemetry,
)

DEFAULT_MEMORY_VECTOR_SEARCH_LIMIT = 10
MAX_MEMORY_VECTOR_SEARCH_LIMIT = 100
DEFAULT_MEMORY_VECTOR_OVERFETCH_FACTOR = 3
DEFAULT_MEMORY_VECTOR_MAX_CANDIDATES = 50
MAX_MEMORY_VECTOR_OVERFETCH_FACTOR = 10
DEFAULT_MEMORY_VECTOR_MAX_QUERIES = 3
MAX_MEMORY_VECTOR_MAX_QUERIES = 10


def fetch_default_vector_memory_search(
    uid: str,
    query: str,
    *,
    db_client: Any,
    policy: MemoryAccessPolicy,
    vector_query: Optional[Callable[..., Any]] = None,
    repair_purge_callback: Optional[Callable[[List[Dict[str, Any]]], Any]] = None,
    repair_purge_outbox_writer: Optional[Callable[[List[Dict[str, Any]]], Any]] = None,
    telemetry_emitter: Optional[Callable[[Dict[str, Any]], Any]] = None,
    telemetry_config: Optional[VectorSearchTelemetryConfig] = None,
    limit: int = DEFAULT_MEMORY_VECTOR_SEARCH_LIMIT,
    overfetch_factor: int = DEFAULT_MEMORY_VECTOR_OVERFETCH_FACTOR,
    max_candidates: int = DEFAULT_MEMORY_VECTOR_MAX_CANDIDATES,
    max_vector_queries: int = DEFAULT_MEMORY_VECTOR_MAX_QUERIES,
    max_candidate_hydration_reads: Optional[int] = None,
    timeout_seconds: Optional[float] = None,
    clock: Optional[Callable[[], float]] = None,
    required_projection_commit_id: str,
    required_account_generation: int,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Hydrate memory vector candidates through authoritative `memory_items` before returning results.

    Vector DB is only a candidate source. This service asks for a bounded overfetch
    window, hydrates candidates by ID from `users/{uid}/memory_items`, and refills
    by increasing the vector candidate request up to a hard `max_candidates` cap
    when early candidates are removed by freshness/access checks. Archive search
    remains a separate explicit capability path.
    """

    bounded_limit = _validate_limit(limit)
    bounded_overfetch_factor = _validate_overfetch_factor(overfetch_factor)
    candidate_budget = _validate_max_candidates(max_candidates=max_candidates, bounded_limit=bounded_limit)
    vector_query_budget = _validate_max_vector_queries(max_vector_queries)
    hydration_read_budget = _validate_max_candidate_hydration_reads(
        max_candidate_hydration_reads=max_candidate_hydration_reads,
        candidate_budget=candidate_budget,
    )
    bounded_timeout_seconds = _validate_timeout_seconds(timeout_seconds)
    _validate_freshness_fence(
        required_projection_commit_id=required_projection_commit_id,
        required_account_generation=required_account_generation,
    )
    candidate_query = vector_query or query_memory_vector_candidates
    if candidate_query is None:
        raise RuntimeError('query_memory_vector_candidates is unavailable')

    candidate_request_limit = min(max(bounded_limit * bounded_overfetch_factor, bounded_limit), candidate_budget)
    vector_query_count = 0
    vector_rejected_count = 0
    all_hits: List[SearchVectorHit] = []
    hydrated_items: Dict[str, MemoryItem] = {}
    missing_authoritative_memory_ids: Set[str] = set()
    hydration_read_count = 0
    timeout_exhausted = False
    vector_query_budget_exhausted = False
    hydration_read_budget_exhausted = False
    monotonic_clock = clock or time.monotonic
    deadline = None if bounded_timeout_seconds is None else monotonic_clock() + bounded_timeout_seconds
    gateway_result = hydrate_and_filter_vector_hits(
        hits=[],
        authoritative_items=hydrated_items,
        policy=policy,
        mode=SearchMode.default,
        required_projection_commit_id=required_projection_commit_id,
        required_account_generation=required_account_generation,
        now=now,
    )

    while True:
        if _is_deadline_exhausted(deadline=deadline, clock=monotonic_clock):
            timeout_exhausted = True
            break
        if vector_query_count >= vector_query_budget:
            vector_query_budget_exhausted = True
            break
        candidate_result = candidate_query(uid, query, mode=SearchMode.default, limit=candidate_request_limit)
        vector_query_count += 1
        vector_rejected_count += int(getattr(candidate_result, 'rejected_count', 0))
        all_hits = list(candidate_result.hits)[:candidate_budget]
        hydration_result = _hydrate_vector_candidate_items_by_id(
            uid=uid,
            db_client=db_client,
            hits=all_hits,
            hydrated_items=hydrated_items,
            missing_authoritative_memory_ids=missing_authoritative_memory_ids,
            max_candidate_hydration_reads=hydration_read_budget,
            candidate_hydration_read_count=hydration_read_count,
            deadline=deadline,
            clock=monotonic_clock,
        )
        hydration_read_count = hydration_result['candidate_hydration_read_count']
        hydration_read_budget_exhausted = bool(hydration_result['hydration_read_budget_exhausted'])
        timeout_exhausted = bool(hydration_result['timeout_exhausted'])
        gateway_result = hydrate_and_filter_vector_hits(
            hits=_filter_read_candidate_hits(
                hits=all_hits,
                hydrated_items=hydrated_items,
                missing_authoritative_memory_ids=missing_authoritative_memory_ids,
            ),
            authoritative_items=hydrated_items,
            policy=policy,
            mode=SearchMode.default,
            required_projection_commit_id=required_projection_commit_id,
            required_account_generation=required_account_generation,
            now=now,
        )
        if timeout_exhausted or hydration_read_budget_exhausted:
            break
        if len(gateway_result.results) >= bounded_limit:
            break
        if candidate_request_limit >= candidate_budget:
            break
        if len(all_hits) < candidate_request_limit:
            break
        if vector_query_count >= vector_query_budget:
            vector_query_budget_exhausted = True
            break
        candidate_request_limit = min(
            candidate_budget, max(candidate_request_limit + bounded_limit, candidate_request_limit * 2)
        )

    returned_results = list(gateway_result.results)[:bounded_limit]
    repair_purge_candidates = list(gateway_result.repair_purge_candidates)
    repair_purge_outbox_records = build_vector_repair_purge_outbox_records(uid=uid, candidates=repair_purge_candidates)
    if repair_purge_candidates and repair_purge_callback is not None:
        repair_purge_callback(repair_purge_candidates)
    if repair_purge_outbox_records and repair_purge_outbox_writer is not None:
        repair_purge_outbox_writer(repair_purge_outbox_records)
    response = {
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
        'max_vector_queries': vector_query_budget,
        'max_candidate_hydration_reads': hydration_read_budget,
        'timeout_seconds': bounded_timeout_seconds,
        'candidate_request_limit': candidate_request_limit,
        'candidate_budget_exhausted': candidate_request_limit >= candidate_budget
        and len(returned_results) < bounded_limit,
        'vector_query_budget_exhausted': vector_query_budget_exhausted,
        'hydration_read_budget_exhausted': hydration_read_budget_exhausted,
        'timeout_exhausted': timeout_exhausted,
        'search_status': _search_status(
            timeout_exhausted=timeout_exhausted,
            hydration_read_budget_exhausted=hydration_read_budget_exhausted,
            vector_query_budget_exhausted=vector_query_budget_exhausted,
            candidate_budget_exhausted=candidate_request_limit >= candidate_budget
            and len(returned_results) < bounded_limit,
        ),
        'legacy_fallback_used': False,
        'vector_query_count': vector_query_count,
        'queried_candidate_count': len(all_hits),
        'hydrated_candidate_count': len(hydrated_items),
        'candidate_hydration_read_count': hydration_read_count,
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
    response['telemetry'] = _emit_vector_search_telemetry(
        response=response,
        telemetry_emitter=telemetry_emitter,
        telemetry_config=telemetry_config,
    )
    return response


def _emit_vector_search_telemetry(
    *,
    response: Dict[str, Any],
    telemetry_emitter: Optional[Callable[[Dict[str, Any]], Any]],
    telemetry_config: Optional[VectorSearchTelemetryConfig],
) -> Dict[str, Any]:
    if telemetry_emitter is None or telemetry_config is None:
        return {'enabled': False, 'emitted_count': 0, 'failed_count': 0, 'errors': []}
    return emit_memory_vector_search_telemetry(
        search_summary=response,
        emitter=telemetry_emitter,
        config=telemetry_config,
    )


def _validate_limit(limit: int) -> int:
    if limit < 1 or limit > MAX_MEMORY_VECTOR_SEARCH_LIMIT:
        raise ValueError(f'limit must be between 1 and {MAX_MEMORY_VECTOR_SEARCH_LIMIT}')
    return limit


def _validate_overfetch_factor(overfetch_factor: Any) -> int:
    if (
        not isinstance(overfetch_factor, int)
        or overfetch_factor < 1
        or overfetch_factor > MAX_MEMORY_VECTOR_OVERFETCH_FACTOR
    ):
        raise ValueError(f'overfetch_factor must be between 1 and {MAX_MEMORY_VECTOR_OVERFETCH_FACTOR}')
    return overfetch_factor


def _validate_max_candidates(*, max_candidates: Any, bounded_limit: int) -> int:
    if (
        not isinstance(max_candidates, int)
        or max_candidates < bounded_limit
        or max_candidates > MAX_MEMORY_VECTOR_SEARCH_LIMIT
    ):
        raise ValueError(f'max_candidates must be between limit and {MAX_MEMORY_VECTOR_SEARCH_LIMIT}')
    return max_candidates


def _validate_max_vector_queries(max_vector_queries: Any) -> int:
    if (
        not isinstance(max_vector_queries, int)
        or max_vector_queries < 1
        or max_vector_queries > MAX_MEMORY_VECTOR_MAX_QUERIES
    ):
        raise ValueError(f'max_vector_queries must be between 1 and {MAX_MEMORY_VECTOR_MAX_QUERIES}')
    return max_vector_queries


def _validate_max_candidate_hydration_reads(*, max_candidate_hydration_reads: Any, candidate_budget: int) -> int:
    if max_candidate_hydration_reads is None:
        return candidate_budget
    if (
        not isinstance(max_candidate_hydration_reads, int)
        or max_candidate_hydration_reads < 0
        or max_candidate_hydration_reads > candidate_budget
    ):
        raise ValueError('max_candidate_hydration_reads must be between 0 and max_candidates')
    return max_candidate_hydration_reads


def _validate_timeout_seconds(timeout_seconds: Any) -> Optional[float]:
    if timeout_seconds is None:
        return None
    if not isinstance(timeout_seconds, (int, float)) or timeout_seconds < 0:
        raise ValueError('timeout_seconds must be a nonnegative number')
    return float(timeout_seconds)


def _validate_freshness_fence(*, required_projection_commit_id: Any, required_account_generation: Any) -> None:
    if not isinstance(required_projection_commit_id, str) or not required_projection_commit_id.strip():
        raise ValueError('required_projection_commit_id is required')
    if not isinstance(required_account_generation, int) or required_account_generation < 0:
        raise ValueError('required_account_generation must be a nonnegative integer')


def _hydrate_vector_candidate_items_by_id(
    *,
    uid: str,
    db_client: Any,
    hits: List[SearchVectorHit],
    hydrated_items: Dict[str, MemoryItem],
    missing_authoritative_memory_ids: Set[str],
    max_candidate_hydration_reads: int,
    candidate_hydration_read_count: int,
    deadline: Optional[float],
    clock: Callable[[], float],
) -> Dict[str, Any]:
    hydration_read_budget_exhausted = False
    timeout_exhausted = False
    for hit in hits:
        if hit.memory_id in hydrated_items or hit.memory_id in missing_authoritative_memory_ids:
            continue
        if _is_deadline_exhausted(deadline=deadline, clock=clock):
            timeout_exhausted = True
            break
        if candidate_hydration_read_count >= max_candidate_hydration_reads:
            hydration_read_budget_exhausted = True
            break
        snapshot = db_client.document(f'users/{uid}/memory_items/{hit.memory_id}').get()
        candidate_hydration_read_count += 1
        raw_payload: object = snapshot.to_dict()
        payload = cast(Dict[str, Any], raw_payload) if isinstance(raw_payload, dict) else {}
        if not payload:
            missing_authoritative_memory_ids.add(hit.memory_id)
            continue
        item = MemoryItem.model_validate(payload)
        if item.uid != uid:
            raise ValueError(f'memory item uid mismatch: expected {uid}, got {item.uid}')
        hydrated_items[item.memory_id] = item
    return {
        'candidate_hydration_read_count': candidate_hydration_read_count,
        'hydration_read_budget_exhausted': hydration_read_budget_exhausted,
        'timeout_exhausted': timeout_exhausted,
    }


def _filter_read_candidate_hits(
    *,
    hits: List[SearchVectorHit],
    hydrated_items: Dict[str, MemoryItem],
    missing_authoritative_memory_ids: Set[str],
) -> List[SearchVectorHit]:
    read_memory_ids = set(hydrated_items) | set(missing_authoritative_memory_ids)
    return [hit for hit in hits if hit.memory_id in read_memory_ids]


def _is_deadline_exhausted(*, deadline: Optional[float], clock: Callable[[], float]) -> bool:
    return deadline is not None and clock() > deadline


def _search_status(
    *,
    timeout_exhausted: bool,
    hydration_read_budget_exhausted: bool,
    vector_query_budget_exhausted: bool,
    candidate_budget_exhausted: bool,
) -> str:
    if timeout_exhausted:
        return 'timeout_exhausted'
    if hydration_read_budget_exhausted:
        return 'hydration_read_budget_exhausted'
    if vector_query_budget_exhausted:
        return 'vector_query_budget_exhausted'
    if candidate_budget_exhausted:
        return 'candidate_budget_exhausted'
    return 'ok'


def _count_decisions(decisions: Dict[str, SearchDecision], decision: SearchDecision) -> int:
    return sum(1 for observed in decisions.values() if observed == decision)


# Neutral symbol aliases (memory names remain valid via shim)
DEFAULT_VECTOR_SEARCH_LIMIT = DEFAULT_MEMORY_VECTOR_SEARCH_LIMIT
MAX_VECTOR_SEARCH_LIMIT = MAX_MEMORY_VECTOR_SEARCH_LIMIT
fetch_default_vector_memory_search = fetch_default_vector_memory_search
