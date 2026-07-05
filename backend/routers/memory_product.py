"""Canonical product memory router (WS-G9).

Neutral ``memory_product`` is the source of truth. Legacy ``memory_product``
remains an importable alias. Registers ``/memory/*`` product paths.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from database._client import db
from database.memory_vector_repair_outbox import write_vector_repair_purge_outbox_records
from models.product_memory import MemoryAccessPolicy
from models.memory_product import (
    ArchiveProductMemorySearchResponse,
    ProductMemorySearchResponse,
    VectorMemorySearchResponse,
)
from utils.memory.default_read_rollout import GLOBAL_READ_GATE_PATH
from utils.memory.product_authorization import (
    ProductAuthorizationContext,
    authorize_memory_product_memory_route,
)
from utils.memory.product_memory_read_service import (
    MAX_PRODUCT_MEMORY_READ_LIMIT,
    fetch_archive_product_memory_search,
    fetch_default_product_memory_search,
)
from utils.memory.vector_search_service import (
    MAX_MEMORY_VECTOR_SEARCH_LIMIT,
    fetch_default_vector_memory_search,
)
from utils.other import endpoints as auth

router = APIRouter()


def _current_time() -> datetime:
    return datetime.now(timezone.utc)


def _default_omi_chat_policy() -> MemoryAccessPolicy:
    return MemoryAccessPolicy.for_omi_chat(archive_capability=False)


def _archive_omi_chat_policy() -> MemoryAccessPolicy:
    return MemoryAccessPolicy.for_omi_chat(archive_capability=True)


def _validate_search_pagination(limit: int, offset: int) -> None:
    if limit < 1 or limit > MAX_PRODUCT_MEMORY_READ_LIMIT:
        raise HTTPException(status_code=400, detail=f'limit must be between 1 and {MAX_PRODUCT_MEMORY_READ_LIMIT}')
    if offset < 0:
        raise HTTPException(status_code=400, detail='offset must be non-negative')


def _validate_vector_limit(limit: int) -> None:
    if limit < 1 or limit > MAX_MEMORY_VECTOR_SEARCH_LIMIT:
        raise HTTPException(status_code=400, detail=f'limit must be between 1 and {MAX_MEMORY_VECTOR_SEARCH_LIMIT}')


def _policy_payload(policy: MemoryAccessPolicy) -> dict:
    return {
        'consumer': policy.consumer.value,
        'app_has_default_memory_grant': policy.app_has_default_memory_grant,
        'archive_capability': policy.archive_capability,
        'raw_provenance_capability': policy.raw_provenance_capability,
    }


def _write_vector_repair_purge_outbox_records(records: list[dict]) -> list[dict]:
    return write_vector_repair_purge_outbox_records(db_client=db, records=records)


def _global_read_gate_observability(gate) -> dict:
    return {
        'source_path': gate.source_path,
        'read_decision': gate.read_decision.value,
        'fallback_reason': gate.fallback_reason,
        'reason': gate.fallback_reason or gate.reason,
    }


def _require_product_authorization(context: ProductAuthorizationContext):
    decision = authorize_memory_product_memory_route(context, db_client=db)
    if not decision.allowed:
        raise HTTPException(status_code=decision.status_code, detail=decision.observability)
    return decision


@router.get('/memory/search', tags=['memories', 'memory'], response_model=ProductMemorySearchResponse)
def search_product_memory(
    query: str = Query(''),
    limit: int = Query(100),
    offset: int = Query(0),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Search default-visible memory product memory for the authenticated user.

    This product endpoint constructs the default Omi-chat access policy explicitly
    and delegates Firestore reads/filtering to the memory product read service. It
    never enables Archive capability, so Archive and stale Short-term records are
    excluded from default responses.
    """

    _validate_search_pagination(limit, offset)
    authz = _require_product_authorization(
        ProductAuthorizationContext(uid=uid, consumer='omi_chat', surface='product_default_search')
    )
    global_read_gate = _global_read_gate_observability(authz.global_gate)
    rollout_observability = authz.observability
    policy = authz.policy or _default_omi_chat_policy()
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
    response['global_read_gate'] = global_read_gate
    response['rollout'] = rollout_observability
    response['archive_default_visible'] = False
    return response


@router.get('/memory/vector/search', tags=['memories', 'memory'], response_model=VectorMemorySearchResponse)
def search_vector_memory(
    query: str = Query(...),
    limit: int = Query(10),
    uid: str = Depends(auth.get_current_user_uid),
    vector_query=None,
):
    """Search default-visible memory memory through hydrated vector candidates.

    The route fails closed unless the persisted server-owned default-read rollout
    state enables `omi_chat` memory reads and default memory. Vector hits are only
    candidates: the service hydrates authoritative `users/{uid}/memory_items`
    before returning default-visible Short-term/Long-term results. Archive is
    never available through this default vector route.
    """

    _validate_vector_limit(limit)
    authz = _require_product_authorization(
        ProductAuthorizationContext(uid=uid, consumer='omi_chat', surface='product_vector_search')
    )
    rollout = authz.rollout
    if rollout is None:
        raise HTTPException(status_code=403, detail=authz.observability)
    global_read_gate = _global_read_gate_observability(authz.global_gate)
    rollout_observability = authz.observability
    rollout_observability['vector_repair_outbox_enabled'] = rollout.vector_repair_outbox_enabled
    if not rollout.vector_projection_commit_id:
        rollout_observability['fallback_reason'] = 'missing_vector_projection_commit_id'
        raise HTTPException(status_code=403, detail=rollout_observability)

    policy = authz.policy or _default_omi_chat_policy()
    try:
        response = fetch_default_vector_memory_search(
            uid=uid,
            query=query,
            db_client=db,
            policy=policy,
            vector_query=vector_query if callable(vector_query) else None,
            repair_purge_outbox_writer=(
                _write_vector_repair_purge_outbox_records if rollout.vector_repair_outbox_enabled else None
            ),
            limit=limit,
            required_projection_commit_id=rollout.vector_projection_commit_id,
            required_account_generation=rollout.rollout_capabilities.account_generation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response['policy'] = _policy_payload(policy)
    response['global_read_gate'] = global_read_gate
    response['rollout'] = rollout_observability
    response['archive_default_visible'] = False
    return response


@router.get('/memory/archive/search', tags=['memories', 'memory'], response_model=ArchiveProductMemorySearchResponse)
def search_archive_memory(
    query: str = Query(''),
    limit: int = Query(100),
    offset: int = Query(0),
    include_archive: bool = Query(False),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Search explicit memory Archive memory for archive-capable product callers only.

    This route is intentionally separate from `/memory/search` and requires
    both an explicit caller opt-in flag and a persisted server-owned Archive
    capability before it constructs a policy with Archive access. The default
    search route remains Archive-free.
    """

    _validate_search_pagination(limit, offset)
    if not include_archive:
        raise HTTPException(status_code=403, detail='explicit archive capability is required')

    authz = _require_product_authorization(
        ProductAuthorizationContext(
            uid=uid,
            consumer='omi_chat',
            surface='product_archive_search',
            explicit_archive_request=include_archive,
            requires_archive_capability=True,
        )
    )
    global_read_gate = _global_read_gate_observability(authz.global_gate)
    rollout_observability = authz.observability
    policy = authz.policy or _archive_omi_chat_policy()
    try:
        response = fetch_archive_product_memory_search(
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
    response['global_read_gate'] = global_read_gate
    response['rollout'] = rollout_observability
    response['archive_default_visible'] = False
    response['archive_capability_required'] = True
    response['archive_capability_granted'] = policy.archive_capability
    return response


__all__ = [
    "MEMORY_GLOBAL_READ_GATE_PATH",
    "db",
    "fetch_archive_product_memory_search",
    "fetch_default_product_memory_search",
    "router",
    "search_archive_memory",
    "search_product_memory",
    "search_vector_memory",
]
