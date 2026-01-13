import threading
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

import database.memories as memories_db
from database.vector_db import upsert_memory_vector, delete_memory_vector
from models.memories import MemoryDB, Memory, MemoryCategory
from utils.apps import update_personas_async
from utils.other import endpoints as auth

router = APIRouter()


def _validate_memory(uid: str, memory_id: str) -> dict:
    memory = memories_db.get_memory(uid, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    if memory.get('is_locked', False):
        raise HTTPException(status_code=402, detail="Unlimited Plan Required to access this memory.")

    return memory


@router.post('/v3/memories', tags=['memories'], response_model=MemoryDB)
def create_memory(memory: Memory, uid: str = Depends(auth.get_current_user_uid)):
    memory.category = MemoryCategory.manual
    memory_db = MemoryDB.from_memory(memory, uid, None, True)
    memories_db.create_memory(uid, memory_db.dict())

    upsert_memory_vector(uid, memory_db.id, memory_db.content, memory_db.category.value)

    if memory.visibility == 'public':
        threading.Thread(target=update_personas_async, args=(uid,)).start()
    return memory_db


@router.get('/v3/memories', tags=['memories'], response_model=List[MemoryDB])
def get_memories(limit: int = 100, offset: int = 0, uid: str = Depends(auth.get_current_user_uid)):
    # Use high limits for the first page
    # Warn: should remove
    if offset == 0:
        limit = 5000
    memories = memories_db.get_memories(uid, limit, offset)
    for memory in memories:
        if memory.get('is_locked', False):
            content = memory.get('content', '')
            memory['content'] = (content[:70] + '...') if len(content) > 70 else content
    return memories


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
    threading.Thread(target=update_personas_async, args=(uid,)).start()
    return {'status': 'ok'}
