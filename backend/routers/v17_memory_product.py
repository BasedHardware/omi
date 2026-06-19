from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from database._client import db
from models.v17_product_memory import MemoryAccessPolicy
from utils.memory.v17_default_read_rollout import (
    V17ReadDecision,
    build_v17_default_read_rollout_observability,
    read_v17_archive_read_rollout,
    read_v17_default_read_rollout,
)
from utils.memory.v17_product_memory_read_service import (
    MAX_PRODUCT_MEMORY_READ_LIMIT,
    fetch_archive_product_memory_search,
    fetch_default_product_memory_search,
)
from utils.memory.v17_vector_search_service import (
    MAX_V17_VECTOR_SEARCH_LIMIT,
    fetch_default_v17_vector_memory_search,
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
    if limit < 1 or limit > MAX_V17_VECTOR_SEARCH_LIMIT:
        raise HTTPException(status_code=400, detail=f'limit must be between 1 and {MAX_V17_VECTOR_SEARCH_LIMIT}')


def _policy_payload(policy: MemoryAccessPolicy) -> dict:
    return {
        'consumer': policy.consumer.value,
        'app_has_default_memory_grant': policy.app_has_default_memory_grant,
        'archive_capability': policy.archive_capability,
        'raw_provenance_capability': policy.raw_provenance_capability,
    }


@router.get('/v17/memory/search', tags=['memories', 'v17'])
def search_v17_product_memory(
    query: str = Query(''),
    limit: int = Query(100),
    offset: int = Query(0),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Search default-visible V17 product memory for the authenticated user.

    This product endpoint constructs the default Omi-chat access policy explicitly
    and delegates Firestore reads/filtering to the V17 product read service. It
    never enables Archive capability, so Archive and stale Short-term records are
    excluded from default responses.
    """

    _validate_search_pagination(limit, offset)
    rollout = read_v17_default_read_rollout(uid=uid, db_client=db, consumer='omi_chat')
    rollout_observability = build_v17_default_read_rollout_observability(rollout)
    if rollout.read_decision != V17ReadDecision.USE_V17:
        raise HTTPException(status_code=403, detail=rollout_observability)

    policy = _default_omi_chat_policy()
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
    response['rollout'] = rollout_observability
    response['archive_default_visible'] = False
    return response


@router.get('/v17/memory/vector/search', tags=['memories', 'v17'])
def search_v17_vector_memory(
    query: str = Query(...),
    limit: int = Query(10),
    uid: str = Depends(auth.get_current_user_uid),
    vector_query=None,
):
    """Search default-visible V17 memory through hydrated vector candidates.

    The route fails closed unless the persisted server-owned default-read rollout
    state enables `omi_chat` V17 reads and default memory. Vector hits are only
    candidates: the service hydrates authoritative `users/{uid}/memory_items`
    before returning default-visible Short-term/Long-term results. Archive is
    never available through this default vector route.
    """

    _validate_vector_limit(limit)
    rollout = read_v17_default_read_rollout(uid=uid, db_client=db, consumer='omi_chat')
    rollout_observability = build_v17_default_read_rollout_observability(rollout)
    if rollout.read_decision != V17ReadDecision.USE_V17:
        raise HTTPException(status_code=403, detail=rollout_observability)

    policy = _default_omi_chat_policy()
    try:
        response = fetch_default_v17_vector_memory_search(
            uid=uid,
            query=query,
            db_client=db,
            policy=policy,
            vector_query=vector_query if callable(vector_query) else None,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response['policy'] = _policy_payload(policy)
    response['rollout'] = rollout_observability
    response['archive_default_visible'] = False
    return response


@router.get('/v17/memory/archive/search', tags=['memories', 'v17'])
def search_v17_archive_memory(
    query: str = Query(''),
    limit: int = Query(100),
    offset: int = Query(0),
    include_archive: bool = Query(False),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Search explicit V17 Archive memory for archive-capable product callers only.

    This route is intentionally separate from `/v17/memory/search` and requires
    both an explicit caller opt-in flag and a persisted server-owned Archive
    capability before it constructs a policy with Archive access. The default
    search route remains Archive-free.
    """

    _validate_search_pagination(limit, offset)
    if not include_archive:
        raise HTTPException(status_code=403, detail='explicit archive capability is required')

    rollout = read_v17_archive_read_rollout(uid=uid, db_client=db, consumer='omi_chat')
    rollout_observability = build_v17_default_read_rollout_observability(rollout)
    if rollout.read_decision != V17ReadDecision.USE_V17 or not rollout.archive_capability:
        raise HTTPException(status_code=403, detail=rollout_observability)

    policy = _archive_omi_chat_policy()
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
    response['rollout'] = rollout_observability
    response['archive_default_visible'] = False
    response['archive_capability_required'] = True
    response['archive_capability_granted'] = policy.archive_capability
    return response
