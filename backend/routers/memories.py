import asyncio
import logging
from typing import List, Optional

from utils.executors import critical_executor

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError

import database.memories as memories_db
from database.vector_db import (
    delete_memory_vector,
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
def create_memory(memory: Memory, uid: str = Depends(auth.get_current_user_uid)):
    memory.category = MemoryCategory.manual
    memory_db = MemoryDB.from_memory(memory, uid, None, True)
    memories_db.create_memory(uid, memory_db.dict())

    upsert_memory_vector(uid, memory_db.id, memory_db.content, memory_db.category.value)

    if memory.visibility == 'public':
        critical_executor.submit(update_personas_async, uid)
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

    # Hardcode category to manual to match the single-create endpoint. Callers
    # that need auto-categorization should use the dev API.
    memory_dbs: List[MemoryDB] = []
    has_public = False
    for memory in request.memories:
        memory.category = MemoryCategory.manual
        memory_db = MemoryDB.from_memory(memory, uid, None, True)
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

    await asyncio.to_thread(_persist)

    if has_public:
        loop = asyncio.get_running_loop()
        loop.run_in_executor(critical_executor, update_personas_async, uid)

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
def delete_memory(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
    _validate_memory(uid, memory_id)
    memories_db.delete_memory(uid, memory_id)
    delete_memory_vector(uid, memory_id)
    return {'status': 'ok'}


@router.delete('/v3/memories', tags=['memories'])
def delete_memories(uid: str = Depends(auth.get_current_user_uid)):
    memories_db.delete_all_memories(uid)
    return {'status': 'ok'}


@router.post('/v3/memories/{memory_id}/review', tags=['memories'])
def review_memory(memory_id: str, value: bool, uid: str = Depends(auth.get_current_user_uid)):
    _validate_memory(uid, memory_id)
    memories_db.review_memory(uid, memory_id, value)
    return {'status': 'ok'}


@router.patch('/v3/memories/{memory_id}', tags=['memories'])
def edit_memory(memory_id: str, value: str, uid: str = Depends(auth.get_current_user_uid)):
    _validate_memory(uid, memory_id)
    # first_word = value.split(' ')[0]
    # user_name = get_user_name(uid, use_default=False)
    # if user_name == first_word:
    #     value = value[len(first_word):].strip()

    memories_db.edit_memory(uid, memory_id, value)
    return {'status': 'ok'}


@router.patch('/v3/memories/{memory_id}/visibility', tags=['memories'])
def update_memory_visibility(memory_id: str, value: str, uid: str = Depends(auth.get_current_user_uid)):
    _validate_memory(uid, memory_id)
    if value not in ['public', 'private']:
        raise HTTPException(status_code=400, detail='Invalid visibility value')
    memories_db.change_memory_visibility(uid, memory_id, value)
    critical_executor.submit(update_personas_async, uid)
    return {'status': 'ok'}
