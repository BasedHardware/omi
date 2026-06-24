import logging
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Literal, Optional

import database._client as db_client_module
from utils.executors import db_executor, postprocess_executor, run_blocking, submit_with_context

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, ValidationError

import database.memories as memories_db
from database import review_queue
from database.vector_db import (
    delete_memory_vector,
    delete_memory_vectors_batch,
    upsert_memory_vector,
    upsert_memory_vectors_batch,
)
from models.memories import MemoryDB, Memory, MemoryCategory
from utils.apps import update_personas_async
from utils.memory.v3_composed_get_service import V17V3ComposedRequestParams, V17V3ComposedResponse
from utils.memory.v3_production_runtime import build_v17_v3_production_runtime
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem
from utils.memory.surface_routing import pin_memory_system
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter()

# Hard cap on memories per batch request. Keep aligned with the corresponding
# Pydantic max_length validator below and with the Swift client chunker.
MEMORIES_BATCH_MAX = 100

V17V3GetSourceDecision = Literal['disabled', 'legacy_primary', 'v17_read']

_V17_GET_ALLOWLISTED_RESPONSE_HEADERS = frozenset(
    {
        'X-Omi-Memory-Read-Source',
        'X-Omi-Memory-Read-Decision',
        'X-Omi-Memory-Next-Cursor',
        'Link',
        'Cache-Control',
    }
)


@dataclass(frozen=True)
class V17V3GetRuntime:
    """Lazy, overrideable F4 runtime bundle for GET `/v3/memories`.

    The production/default dependency below is structurally disabled in F4. TestClient
    may override the exact dependency to supply a composed service and typed source
    decision. This bundle intentionally does not construct Firestore clients, cursor
    keyrings, projection adapters, production readers, or telemetry emitters at import.
    """

    enabled: bool = False
    source_decision: V17V3GetSourceDecision = 'disabled'
    service: Optional[Callable[[V17V3ComposedRequestParams, object], V17V3ComposedResponse]] = None
    adapters: object = None
    source_selector: object = None
    control_reader: object = None
    legacy_reader: object = None
    projection_reader: object = None
    cursor_keyring: object = None
    cursor_codec: object = None
    clock: object = None
    deadline: object = None
    observer: object = None


def get_v17_v3_get_runtime(uid: str = Depends(auth.get_current_user_uid)):
    """Return the production/default runtime bundle for GET `/v3/memories`.

    Default production behavior is still disabled. Server-owned configuration can
    only enter V17 when all of these are true: `V17_MODE` is not off,
    `V17_MEMORY_ENABLED_USERS` contains the authenticated uid, the persisted
    control state is read-mode, and global/read-convergence gates allow the
    composed service to proceed. Client headers, query params, request bodies,
    and persisted user docs alone cannot activate V17.
    """

    return build_v17_v3_production_runtime(uid=uid, db_client=getattr(db_client_module, 'db', None))


class BatchMemoriesRequest(BaseModel):
    memories: List[Memory] = Field(
        description="List of memories to create in a single batch request",
        max_length=MEMORIES_BATCH_MAX,
    )


class BatchMemoriesResponse(BaseModel):
    memories: List[MemoryDB]
    created_count: int


class ReviewResolutionRequest(BaseModel):
    decision: str = Field(description="accept, reject, correct, or timeout")
    correction: Optional[Dict[str, Any]] = None
    reason: str = ''
    current_veracity: Optional[float] = None


def _legacy_get_memories(uid: str, limit: int, offset: int) -> List[MemoryDB]:
    # Use high limits for the first page
    # Warn: should remove
    if offset == 0:
        limit = 5000
    memories = memories_db.get_memories(uid, limit, offset)

    valid_memories = []
    for memory in memories:
        if memory.get('is_locked', False):
            content = memory.get('content', '')
            memory['content'] = (content[:70] + '...') if len(content) > 70 else content
        try:
            valid_memories.append(MemoryDB.model_validate(memory))
        except ValidationError as e:
            missing_fields = [err['loc'][0] for err in e.errors() if err.get('loc')]
            logger.warning(
                f"Skipping invalid memory doc {memory.get('id', 'unknown')}: missing/invalid fields {missing_fields}"
            )
            continue
    return valid_memories


def _apply_v17_response_headers(http_response: Response, v17_response: V17V3ComposedResponse) -> None:
    for name, value in v17_response.headers.items():
        if name in _V17_GET_ALLOWLISTED_RESPONSE_HEADERS:
            http_response.headers[name] = value
    http_response.headers['Cache-Control'] = 'no-store'


def _v17_allowlisted_headers(v17_response: V17V3ComposedResponse) -> Dict[str, str]:
    return {
        name: value for name, value in v17_response.headers.items() if name in _V17_GET_ALLOWLISTED_RESPONSE_HEADERS
    }


def _raise_v17_http_exception(v17_response: V17V3ComposedResponse) -> None:
    raise HTTPException(
        status_code=v17_response.http_status,
        detail=v17_response.public_error or 'v17_read_failed',
        headers=_v17_allowlisted_headers(v17_response),
    )


def _validate_memory(uid: str, memory_id: str) -> dict:
    memory = memories_db.get_memory(uid, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    if memory.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this memory.")

    return memory


@router.post('/v3/memories', tags=['memories'], response_model=MemoryDB)
async def create_memory(
    memory: Memory,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "memories:create")),
):
    # Honor the client-supplied category (the Memory model defaults it to
    # `interesting`). Only memories the user explicitly typed in arrive as
    # `manual`; auto-extracted ones (system/interesting) keep their category so
    # the mobile app files them under "About You"/"Insights" instead of dumping
    # everything into "Manual". manually_added tracks human entry, so derive it
    # from the category rather than forcing it True for every API caller.
    manually_added = memory.category == MemoryCategory.manual
    memory_db = MemoryDB.from_memory(memory, uid, None, manually_added)

    # Build payload outside try so serialization bugs aren't misreported as
    # transient 503s — only the Firestore write should be retryable.
    payload = memory_db.dict()

    try:
        await run_blocking(db_executor, memories_db.create_memory, uid, payload)
    except Exception:
        logger.exception("Firestore create_memory failed uid=%s", uid)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    try:
        await run_blocking(
            postprocess_executor,
            upsert_memory_vector,
            uid,
            memory_db.id,
            memory_db.content,
            memory_db.category.value,
            memory_db.subject_entity_id,
        )
    except Exception:
        logger.exception("Vector upsert failed uid=%s memory_id=%s (memory saved, vector missing)", uid, memory_db.id)

    if memory.visibility == 'public':
        submit_with_context(postprocess_executor, update_personas_async, uid)

    return memory_db


@router.post(
    '/v3/memories/batch',
    tags=['memories'],
    response_model=BatchMemoriesResponse,
)
async def create_memories_batch(
    request: BatchMemoriesRequest,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "memories:batch")),
):
    """
    Create many memories in a single request.

    Solves the Cloud Armor throttling seen on onboarding: the desktop client
    used to fan out one `POST /v3/memories` per local-file memory (up to 2800
    per user), blowing through the 120 req/min per-Authorization Cloud Armor
    rule and collaterally 429-ing unrelated calls (goals, sync, chat).

    One HTTP request here = one Firestore batch write + one embeddings call +
    one Pinecone upsert, regardless of batch size.
    """
    if not request.memories:
        return BatchMemoriesResponse(memories=[], created_count=0)

    # Honor each item's category (defaults to `interesting` per the Memory
    # model). Desktop import/extraction paths send `system`/`interesting` so
    # they land under "About You"/"Insights"; only user-typed memories send
    # `manual`. Derive manually_added from the category instead of forcing it.
    memory_dbs: List[MemoryDB] = []
    has_public = False
    for memory in request.memories:
        manually_added = memory.category == MemoryCategory.manual
        memory_db = MemoryDB.from_memory(memory, uid, None, manually_added)
        memory_dbs.append(memory_db)
        if memory.visibility == 'public':
            has_public = True

    await run_blocking(db_executor, memories_db.save_memories, uid, [m.dict() for m in memory_dbs])

    try:
        await run_blocking(
            postprocess_executor,
            upsert_memory_vectors_batch,
            uid,
            [
                {
                    "memory_id": m.id,
                    "content": m.content,
                    "category": m.category.value,
                    "subject_entity_id": m.subject_entity_id,
                }
                for m in memory_dbs
            ],
        )
    except Exception:
        logger.exception(
            "Batch vector upsert failed uid=%s count=%s (memories saved, vectors missing)", uid, len(memory_dbs)
        )

    if has_public:
        submit_with_context(postprocess_executor, update_personas_async, uid)

    return BatchMemoriesResponse(memories=memory_dbs, created_count=len(memory_dbs))


@router.get('/v3/memories', tags=['memories'], response_model=List[MemoryDB])
def get_memories(
    response: Response,
    limit: int = 100,
    offset: int = 0,
    cursor: Optional[str] = None,
    uid: str = Depends(auth.get_current_user_uid),
    v17_runtime: V17V3GetRuntime = Depends(get_v17_v3_get_runtime),
):
    if pin_memory_system(uid, db_client=getattr(db_client_module, 'db', None)) == MemorySystem.CANONICAL:
        return MemoryService(db_client=getattr(db_client_module, 'db', None)).read(uid, limit=limit, offset=offset)

    if not v17_runtime.enabled or v17_runtime.source_decision == 'disabled':
        return _legacy_get_memories(uid, limit, offset)

    if v17_runtime.source_decision == 'legacy_primary':
        return _legacy_get_memories(uid, limit, offset)

    if v17_runtime.source_decision != 'v17_read' or v17_runtime.service is None:
        logger.info("v17_v3_get route=GET /v3/memories source=none status=503 decision=malformed_runtime_dependency")
        raise HTTPException(status_code=503, detail='infrastructure_failure')

    params = V17V3ComposedRequestParams(limit=limit, offset=offset, cursor=cursor)
    v17_response = v17_runtime.service(params, v17_runtime.adapters)
    if not isinstance(v17_response, V17V3ComposedResponse):
        logger.info("v17_v3_get route=GET /v3/memories source=none status=503 decision=adapter_contract")
        raise HTTPException(status_code=503, detail='infrastructure_failure')

    _apply_v17_response_headers(response, v17_response)
    logger.info(
        "v17_v3_get route=GET /v3/memories source=%s status=%s decision=%s",
        v17_response.source,
        v17_response.http_status,
        v17_response.public_error or v17_response.decision,
    )
    if v17_response.http_status != 200:
        _raise_v17_http_exception(v17_response)
    return [MemoryDB.model_validate(item) for item in v17_response.body or []]


@router.get('/v3/memories/review-queue', tags=['memories'])
def list_memory_review_queue(
    status: str = Query('pending'),
    limit: int = Query(100, ge=1, le=500),
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "memories:review")),
):
    return review_queue.list_review_conflicts(uid, status=status, limit=limit)


@router.post('/v3/memories/review-queue/{review_id}/resolve', tags=['memories'])
def resolve_memory_review_item(
    review_id: str,
    request: ReviewResolutionRequest,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "memories:review")),
):
    if request.decision not in ('accept', 'reject', 'correct', 'timeout'):
        raise HTTPException(status_code=400, detail='Invalid review decision')
    result = review_queue.resolve_review_conflict(
        uid,
        review_id,
        request.decision,
        correction=request.correction,
        reason=request.reason,
        current_veracity=request.current_veracity,
    )
    if result.get('status') == 'not_found':
        raise HTTPException(status_code=404, detail='Review item not found')
    return result


@router.delete('/v3/memories/{memory_id}', tags=['memories'])
def delete_memory(
    memory_id: str,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "memories:delete")),
):
    _validate_memory(uid, memory_id)
    memories_db.delete_memory(uid, memory_id)
    try:
        delete_memory_vector(uid, memory_id)
    except Exception:
        logger.exception("Vector delete failed uid=%s memory_id=%s (Firestore deleted)", uid, memory_id)
    return {'status': 'ok'}


@router.delete('/v3/memories', tags=['memories'])
def delete_memories(
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "memories:delete_all")),
):
    # Collect all memory IDs before Firestore delete so we can also purge
    # their Pinecone vectors — otherwise orphaned vectors become search
    # noise that never gets cleaned up.
    memory_ids = []
    offset = 0
    batch_size = 1000
    while True:
        memories = memories_db.get_memories(uid, limit=batch_size, offset=offset, include_invalidated=True)
        if not memories:
            break
        batch_ids = [m.get('id') for m in memories if m.get('id')]
        memory_ids.extend(batch_ids)
        offset += batch_size

    memories_db.delete_all_memories(uid)

    if memory_ids:
        delete_memory_vectors_batch(uid, memory_ids)

    return {'status': 'ok'}


@router.post('/v3/memories/{memory_id}/review', tags=['memories'])
def review_memory(
    memory_id: str,
    value: bool,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "memories:modify")),
):
    _validate_memory(uid, memory_id)
    memories_db.review_memory(uid, memory_id, value)
    return {'status': 'ok'}


@router.patch('/v3/memories/{memory_id}', tags=['memories'])
def edit_memory(
    memory_id: str,
    value: str,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "memories:modify")),
):
    memory = _validate_memory(uid, memory_id)
    memories_db.edit_memory(uid, memory_id, value)
    # Re-embed so semantic search reflects the new content. Without this the Pinecone
    # vector keeps matching the OLD text — a silent staleness bug that breaks the
    # "constantly updated brain" (search would still surface the pre-edit fact).
    try:
        upsert_memory_vector(
            uid, memory_id, value, memory.get('category', 'system'), subject_entity_id=memory.get('subject_entity_id')
        )
    except Exception:
        logger.exception("Vector upsert failed uid=%s memory_id=%s (memory edited, vector stale)", uid, memory_id)
    return {'status': 'ok'}


@router.patch('/v3/memories/{memory_id}/visibility', tags=['memories'])
def update_memory_visibility(
    memory_id: str,
    value: str,
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "memories:modify")),
):
    _validate_memory(uid, memory_id)
    if value not in ['public', 'private']:
        raise HTTPException(status_code=400, detail='Invalid visibility value')
    memories_db.change_memory_visibility(uid, memory_id, value)
    postprocess_executor.submit(update_personas_async, uid)
    return {'status': 'ok'}
