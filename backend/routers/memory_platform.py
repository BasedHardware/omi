from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from database._client import db
from models.memories import Memory, MemoryCategory, MemoryDB
from models.memory_product import ProductMemorySearchResponse
from models.memory_platform import MemoryPlatformCapability, MemoryPlatformIngestResponse
from utils.memory.canonical_activation import canonical_write_decision
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem
from utils.memory.product_authorization import (
    ProductAuthorizationContext,
    authorize_memory_product_memory_route,
)
from utils.memory.product_memory_read_service import (
    MAX_PRODUCT_MEMORY_READ_LIMIT,
    fetch_default_product_memory_search,
)
from utils.other import endpoints as auth

from utils.memory.platform import build_memory_platform_capability

router = APIRouter()
MAX_PLATFORM_SEARCH_QUERY_LENGTH = 500
MAX_PLATFORM_SEARCH_OFFSET = 100_000


def _rate_limited_uid(policy_name: str):
    rate_limiter = getattr(auth, 'with_rate_limit', None)
    if rate_limiter is None:
        return auth.get_current_user_uid
    return rate_limiter(auth.get_current_user_uid, policy_name)


def _current_time() -> datetime:
    return datetime.now(timezone.utc)


def _validate_search_bounds(query: str, limit: int, offset: int) -> None:
    if len(query) > MAX_PLATFORM_SEARCH_QUERY_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f'query must be at most {MAX_PLATFORM_SEARCH_QUERY_LENGTH} characters',
        )
    if limit < 1 or limit > MAX_PRODUCT_MEMORY_READ_LIMIT:
        raise HTTPException(status_code=400, detail=f'limit must be between 1 and {MAX_PRODUCT_MEMORY_READ_LIMIT}')
    if offset < 0 or offset > MAX_PLATFORM_SEARCH_OFFSET:
        raise HTTPException(status_code=400, detail=f'offset must be between 0 and {MAX_PLATFORM_SEARCH_OFFSET}')


def _policy_payload(policy) -> dict:
    return {
        'consumer': policy.consumer.value,
        'app_has_default_memory_grant': policy.app_has_default_memory_grant,
        'archive_capability': policy.archive_capability,
        'raw_provenance_capability': policy.raw_provenance_capability,
    }


def _global_read_gate_observability(gate) -> dict:
    return {
        'source_path': gate.source_path,
        'read_decision': gate.read_decision.value,
        'fallback_reason': gate.fallback_reason,
        'reason': gate.fallback_reason or gate.reason,
    }


def _require_product_authorization(uid: str):
    decision = authorize_memory_product_memory_route(
        ProductAuthorizationContext(uid=uid, consumer='omi_chat', surface='platform_search'),
        db_client=db,
    )
    if not decision.allowed:
        raise HTTPException(status_code=decision.status_code, detail=decision.observability)
    return decision


@router.get(
    '/v1/memory/platform',
    tags=['v1', 'memory'],
    response_model=MemoryPlatformCapability,
)
def get_memory_platform(uid: str = Depends(auth.get_current_user_uid)) -> MemoryPlatformCapability:
    return build_memory_platform_capability()


@router.get(
    '/v1/memory/platform/search',
    tags=['v1', 'memory'],
    response_model=ProductMemorySearchResponse,
)
def search_memory_platform(
    query: str = Query('', max_length=MAX_PLATFORM_SEARCH_QUERY_LENGTH),
    limit: int = Query(100, ge=1, le=MAX_PRODUCT_MEMORY_READ_LIMIT),
    offset: int = Query(0, ge=0, le=MAX_PLATFORM_SEARCH_OFFSET),
    uid: str = Depends(_rate_limited_uid('tools:search')),
):
    _validate_search_bounds(query, limit, offset)
    authz = _require_product_authorization(uid)
    policy = authz.policy
    if policy is None or authz.global_gate is None:
        raise HTTPException(status_code=503, detail='Service temporarily unavailable')
    try:
        response = fetch_default_product_memory_search(
            uid=uid,
            query=query,
            db_client=db,
            policy=policy,
            now=_current_time(),
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response['policy'] = _policy_payload(policy)
    response['global_read_gate'] = _global_read_gate_observability(authz.global_gate)
    response['rollout'] = authz.observability
    response['archive_default_visible'] = False
    return response


@router.post(
    '/v1/memory/platform/ingest',
    tags=['v1', 'memory'],
    response_model=MemoryPlatformIngestResponse,
)
def ingest_memory_platform(
    memory: Memory,
    uid: str = Depends(_rate_limited_uid('memories:create')),
) -> MemoryPlatformIngestResponse:
    if not memory.content.strip():
        raise HTTPException(status_code=400, detail='content must not be blank')

    decision = canonical_write_decision(uid, db_client=db)
    if decision.memory_system != MemorySystem.CANONICAL or not decision.enabled:
        raise HTTPException(
            status_code=503,
            detail={'reason': decision.reason, 'memory_system': decision.memory_system.value},
        )

    memory_db = MemoryDB.from_memory(
        memory,
        uid,
        None,
        memory.category == MemoryCategory.manual,
        source_type='memory_platform',
        source_signal='memory_platform',
        extractor_id='memory_platform_ingest',
    )
    try:
        created = MemoryService(db_client=db).create_external_memory(
            uid,
            memory_db,
            memory_system=MemorySystem.CANONICAL,
            consumer='memory_platform',
            operation='memory_platform_ingest',
            upsert_vector=False,
            require_canonical_promotion=True,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail='Service temporarily unavailable') from exc

    return MemoryPlatformIngestResponse(memory_id=created.id)


__all__ = ['get_memory_platform', 'ingest_memory_platform', 'router', 'search_memory_platform']
