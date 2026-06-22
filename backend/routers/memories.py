import logging
from typing import List, Optional

from utils.executors import db_executor, postprocess_executor, run_blocking, submit_with_context

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError

import database.memories as memories_db
from database.vector_db import (
    delete_memory_vector,
    delete_memory_vectors_batch,
    upsert_memory_vector,
    upsert_memory_vectors_batch,
)
from models.memories import MemoryDB, Memory, MemoryCategory
from utils.apps import update_personas_async
from utils.other import endpoints as auth

logger = logging.getLogger(__name__)

router = APIRouter()

# Hard cap on memories per batch request. Keep aligned with the corresponding
# Pydantic max_length validator below and with the Swift client chunker.
MEMORIES_BATCH_MAX = 100


class BatchMemoriesRequest(BaseModel):
    memories: List[Memory] = Field(
        description="List of memories to create in a single batch request",
        max_length=MEMORIES_BATCH_MAX,
    )


class BatchMemoriesResponse(BaseModel):
    memories: List[MemoryDB]
    created_count: int


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
            postprocess_executor, upsert_memory_vector, uid, memory_db.id, memory_db.content, memory_db.category.value
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

    # Firestore batch write + Pinecone batch upsert run on a worker thread so a
    # slow embeddings/Pinecone call can't starve the FastAPI sync threadpool.
    def _persist():
        memories_db.save_memories(uid, [m.dict() for m in memory_dbs])
        upsert_memory_vectors_batch(
            uid,
            [
                {
                    "memory_id": m.id,
                    "content": m.content,
                    "category": m.category.value,
                }
                for m in memory_dbs
            ],
        )

    await run_blocking(db_executor, _persist)

    if has_public:
        submit_with_context(postprocess_executor, update_personas_async, uid)

    return BatchMemoriesResponse(memories=memory_dbs, created_count=len(memory_dbs))


@router.get('/v3/memories', tags=['memories'], response_model=List[MemoryDB])
def get_memories(limit: int = 100, offset: int = 0, uid: str = Depends(auth.get_current_user_uid)):
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
        upsert_memory_vector(uid, memory_id, value, memory.get('category', 'system'))
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
