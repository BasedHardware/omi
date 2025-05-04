import threading
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Header

import database.memories as memories_db
from models.memories import MemoryDB, Memory, MemoryCategory
from models.memory import CategoryEnum
from utils.apps import update_personas_async
from utils.llm import identify_category_for_memory

router = APIRouter()


@router.post("/v1/mcp/memories", tags=["mcp"], response_model=MemoryDB)
def create_memory(memory: Memory, uid: str = Header(None)):
    categories = [category for category in MemoryCategory]
    memory.category = identify_category_for_memory(memory.content, categories)
    memory_db = MemoryDB.from_memory(memory, uid, None, None, True)
    memories_db.create_memory(uid, memory_db.model_dump())
    threading.Thread(target=update_personas_async, args=(uid,)).start()
    return memory_db


@router.get("/v1/mcp/memories", tags=["mcp"], response_model=List[MemoryDB])
def get_memories(
    limit: int = 25,
    offset: int = 0,
    categories: List[CategoryEnum] = [], # TODO: finish
    # visibility: Literal["public", "private"] = None, # TODO: is this working
    uid: str = Header(None),
):
    return memories_db.get_memories(uid, limit, offset, categories)


