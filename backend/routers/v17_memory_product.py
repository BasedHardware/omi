from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from database._client import db
from models.v17_product_memory import MemoryAccessPolicy
from utils.memory.v17_product_memory_read_service import (
    MAX_PRODUCT_MEMORY_READ_LIMIT,
    fetch_archive_product_memory_search,
    fetch_default_product_memory_search,
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

    response['policy'] = {
        'consumer': policy.consumer.value,
        'app_has_default_memory_grant': policy.app_has_default_memory_grant,
        'archive_capability': policy.archive_capability,
        'raw_provenance_capability': policy.raw_provenance_capability,
    }
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
    an explicit caller opt-in flag before it constructs a policy with Archive
    capability. The default search route remains Archive-free.
    """

    _validate_search_pagination(limit, offset)
    if not include_archive:
        raise HTTPException(status_code=403, detail='explicit archive capability is required')

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

    response['policy'] = {
        'consumer': policy.consumer.value,
        'app_has_default_memory_grant': policy.app_has_default_memory_grant,
        'archive_capability': policy.archive_capability,
        'raw_provenance_capability': policy.raw_provenance_capability,
    }
    response['archive_default_visible'] = False
    response['archive_capability_required'] = True
    response['archive_capability_granted'] = policy.archive_capability
    return response
