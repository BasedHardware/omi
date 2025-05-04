import threading
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Header

import database.memories as memories_db
import database.conversations as conversations_db
from models.conversation import Conversation
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


@router.delete("/v1/mcp/memories/{memory_id}", tags=["mcp"])
def delete_memory(memory_id: str, uid: str = Header(None)):
    memories_db.delete_memory(uid, memory_id)
    return {"status": "ok"}


@router.patch("/v1/mcp/memories/{memory_id}", tags=["mcp"])
def edit_memory(memory_id: str, value: str, uid: str = Header(None)):
    memories_db.edit_memory(uid, memory_id, value)
    return {"status": "ok"}


@router.get("/v1/mcp/memories", tags=["mcp"], response_model=List[MemoryDB])
def get_memories(
    limit: int = 25,
    offset: int = 0,
    categories: Optional[str] = None,
    uid: str = Header(None),
):
    category_list = []
    if categories:
        try:
            category_list = [
                CategoryEnum(c.strip()) for c in categories.split(",") if c.strip()
            ]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid category")
    return memories_db.get_memories(
        uid, limit, offset, [c.value for c in category_list]
    )


@router.get("/v1/mcp/conversations", response_model=List[Conversation], tags=["mcp"])
def get_conversations(
    include_discarded: bool = False,
    limit: int = 25,
    offset: int = 0,
    uid: str = Header(None),
):
    # TODO: do retrieval, + mixed db search, this works for now.
    # --- should rather send lots of context? and let front do retrieval? or add as potential other endpoint?
    print("get_conversations", uid, limit, offset)
    return conversations_db.get_conversations(
        uid,
        limit,
        offset,
        include_discarded=include_discarded,
        statuses=[],  # statuses.split(",") if len(statuses) > 0 else [],
    )
