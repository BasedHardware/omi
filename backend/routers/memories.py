import threading
from typing import List

from fastapi import APIRouter, Depends, HTTPException

import database.memories as memories_db
from models.memories import MemoryDB, Memory, MemoryCategory
from utils.apps import update_personas_async
from utils.llm.memories import identify_category_for_memory
from utils.other import endpoints as auth

router = APIRouter()


@router.post('/v3/memories', tags=['memories'], response_model=MemoryDB)
def create_memory(memory: Memory, uid: str = Depends(auth.get_current_user_uid)):
    # Only use the two primary categories for new memories
    categories = [MemoryCategory.interesting.value, MemoryCategory.system.value]
    memory.category = identify_category_for_memory(memory.content, categories)
    memory_db = MemoryDB.from_memory(memory, uid, None, True)
    memories_db.create_memory(uid, memory_db.dict())
    threading.Thread(target=update_personas_async, args=(uid,)).start()
    return memory_db


@router.get('/v3/memories', tags=['memories'], response_model=List[MemoryDB])
def get_memories(limit: int = 100, offset: int = 0, uid: str = Depends(auth.get_current_user_uid)):
    # Use high limits for the first page
    # Warn: should remove
    if offset == 0:
        limit = 5000
    memories = memories_db.get_memories(uid, limit, offset)
    return memories


@router.delete('/v3/memories/{memory_id}', tags=['memories'])
def delete_memory(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
    memories_db.delete_memory(uid, memory_id)
    return {'status': 'ok'}


@router.delete('/v3/memories', tags=['memories'])
def delete_memories(uid: str = Depends(auth.get_current_user_uid)):
    memories_db.delete_all_memories(uid)
    return {'status': 'ok'}


@router.post('/v3/memories/{memory_id}/review', tags=['memories'])
def review_memory(memory_id: str, value: bool, uid: str = Depends(auth.get_current_user_uid)):
    memories_db.review_memory(uid, memory_id, value)
    return {'status': 'ok'}


@router.patch('/v3/memories/{memory_id}', tags=['memories'])
def edit_memory(memory_id: str, value: str, uid: str = Depends(auth.get_current_user_uid)):
    # first_word = value.split(' ')[0]
    # user_name = get_user_name(uid, use_default=False)
    # if user_name == first_word:
    #     value = value[len(first_word):].strip()

    memories_db.edit_memory(uid, memory_id, value)
    return {'status': 'ok'}


@router.patch('/v3/memories/{memory_id}/visibility', tags=['memories'])
def update_memory_visibility(memory_id: str, value: str, uid: str = Depends(auth.get_current_user_uid)):
    if value not in ['public', 'private']:
        raise HTTPException(status_code=400, detail='Invalid visibility value')
    memories_db.change_memory_visibility(uid, memory_id, value)
    threading.Thread(target=update_personas_async, args=(uid,)).start()
    return {'status': 'ok'}
