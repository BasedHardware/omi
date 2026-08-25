import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from database._client import db, document_id_from_seed
from models.memories import Memory, MemoryDB
from models.memory_product import ProductMemorySearchResponse
from models.memory_platform import MemoryPlatformCapability, MemoryPlatformIngestResponse
from utils.client_device import resolve_client_device_from_request
from utils.executors import db_executor, run_blocking
from utils.memory.canonical_activation import canonical_write_decision
from utils.memory.import_write_guard import (
    import_write_block_mode,
    import_write_violation_for_guard,
    is_per_file_local_import_tags,
)
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem, resolve_memory_system
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
logger = logging.getLogger(__name__)


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


async def _guard_import_memory_write(request: Request, *, endpoint: str, uid: str) -> None:
    """Shared import-write boundary, mirroring the /v3/memories guard.

    Import-marked payloads (import source types/tags/metadata) must enter
    through the evidence ingress (`/v3/memory-imports/batch`), not this
    platform surface. Per-file local-file items are exempt here exactly as on
    /v3/memories — this route acknowledges-and-drops them below.
    """
    mode = import_write_block_mode()
    if mode == 'off':
        return
    try:
        raw: object = await request.json()
    except Exception:
        return
    if not isinstance(raw, dict):
        return
    violation = import_write_violation_for_guard(raw)
    if not violation:
        return
    logger.warning(
        'memory_import.direct_memory_write_blocked endpoint=%s uid=%s mode=%s violation=%s',
        endpoint,
        uid,
        mode,
        violation,
    )
    if mode == 'enforce':
        raise HTTPException(
            status_code=409,
            detail={
                'error': 'import_must_use_evidence_ingress',
                'use_endpoint': '/v3/memory-imports/batch',
            },
        )


@router.post(
    '/v1/memory/platform/ingest',
    tags=['v1', 'memory'],
    response_model=MemoryPlatformIngestResponse,
)
async def ingest_memory_platform(
    request: Request,
    memory: Memory,
    uid: str = Depends(_rate_limited_uid('memories:create')),
) -> MemoryPlatformIngestResponse:
    if not memory.content.strip():
        raise HTTPException(status_code=400, detail='content must not be blank')

    await _guard_import_memory_write(request, endpoint='/v1/memory/platform/ingest', uid=uid)

    # Per-file local-file import items are dropped unconditionally on
    # /v3/memories; they carry no durable signal and must not be reintroduced
    # through this platform surface either. Acknowledge without persisting.
    try:
        raw_payload: object = await request.json()
    except Exception:
        raw_payload = None
    if isinstance(raw_payload, dict) and is_per_file_local_import_tags(raw_payload.get('tags')):
        logger.info('memory_import.per_file_item_dropped endpoint=/v1/memory/platform/ingest uid=%s', uid)
        return MemoryPlatformIngestResponse(memory_id=document_id_from_seed(memory.content), status='dropped')

    decision = await run_blocking(db_executor, canonical_write_decision, uid, db_client=db)
    if decision.memory_system != MemorySystem.CANONICAL or not decision.enabled:
        raise HTTPException(
            status_code=503,
            detail={'reason': decision.reason, 'memory_system': decision.memory_system.value},
        )

    # Explicit platform submissions are user-authored facts no matter which
    # content category the caller picked; provenance is not inferred from the
    # category (unlike /v3/memories, where auto-extracted traffic also lands).
    # Without this the unknown-subject promotion check keeps these memories
    # short-term forever instead of letting consolidation make them durable.
    memory_db = MemoryDB.from_memory(
        memory,
        uid,
        None,
        True,
        source_type='memory_platform',
        source_signal='memory_platform',
        extractor_id='memory_platform_ingest',
        client_device_id=resolve_client_device_from_request(request).client_device_id,
    )
    try:
        created = await run_blocking(
            db_executor,
            MemoryService(db_client=db).create_external_memory,
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
