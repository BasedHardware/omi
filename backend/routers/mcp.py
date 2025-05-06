from datetime import datetime
import threading
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel

import database.memories as memories_db
import database.conversations as conversations_db

# from database.redis_db import get_filter_category_items
# from database.vector_db import query_vectors_by_metadata
from models.memories import MemoryDB, Memory, MemoryCategory
from models.memory import CategoryEnum
from utils.apps import update_personas_async
from utils.llm import identify_category_for_memory
from firebase_admin import auth

router = APIRouter()


@router.post("/v1/mcp/memories", tags=["mcp"], response_model=Memory)
def create_memory(memory: Memory, uid: str = Header(None)):
    categories = [category for category in MemoryCategory]
    memory.category = identify_category_for_memory(memory.content, categories)
    memory_db = MemoryDB.from_memory(memory, uid, None, True)
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


@router.get("/v1/mcp/memories", tags=["mcp"], response_model=List[Memory])
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


class SimpleStructured(BaseModel):
    title: str
    overview: str
    category: CategoryEnum


class SimpleTranscriptSegment(BaseModel):
    id: Optional[str] = None
    text: str
    speaker_id: Optional[int] = None
    start: float
    end: float


class SimpleConversation(BaseModel):
    id: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    structured: SimpleStructured
    transcript_segments: List[SimpleTranscriptSegment] = []
    language: Optional[str] = None


# Step 2 do retrieval
# @router.get("/v1/mcp/conversations/available-filters", tags=["mcp"])
# def get_conversations_available_filters(uid: str = Header(None)):
#     return {
#         "people": get_filter_category_items(uid, "people"),
#         "topics": get_filter_category_items(uid, "topics"),
#         "entities": get_filter_category_items(uid, "entities"),
#     }


@router.get(
    "/v1/mcp/conversations", response_model=List[SimpleConversation], tags=["mcp"]
)
def get_conversations(
    include_transcript_segments: bool = False,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    categories: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
    uid: str = Header(None),
):
    print("get_conversations", uid, limit, offset, start_date, end_date, categories)
    category_list = (
        [CategoryEnum(c.strip()) for c in categories.split(",") if c.strip()]
        if categories
        else []
    )
    conversations = conversations_db.get_conversations(
        uid,
        limit,
        offset,
        include_discarded=False,
        statuses=["completed"],
        start_date=start_date,
        end_date=end_date,
        categories=[c.value for c in category_list],
    )
    for i in range(len(conversations)):
        if not include_transcript_segments:
            conversations[i]["transcript_segments"] = []
    return conversations

    # TODO: further steps, perform retrieval
    # related_to_people = (
    #     [p.strip() for p in related_to_people.split(",")] if related_to_people else []
    # )
    # related_to_topics = (
    #     [t.strip() for t in related_to_topics.split(",")] if related_to_topics else []
    # )
    # related_to_entities = (
    #     [e.strip() for e in related_to_entities.split(",")]
    #     if related_to_entities
    #     else []
    # )

    # vector = [0] * 3072  # pass something closer?
    # memories_id = query_vectors_by_metadata(
    #     uid,
    #     vector,
    #     dates_filter=[start_date, end_date],
    #     people=related_to_people,
    #     topics=related_to_topics,
    #     entities=related_to_entities,
    #     dates=[],
    #     limit=200,
    # )

    # conversations = conversations_db.get_conversations_by_id(uid, memories_id)


class UserCredentials(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


@router.post("/v1/mcp/users", tags=["mcp"])
def create_user(credentials: UserCredentials):
    try:
        user = auth.create_user(
            email=credentials.email,
            password=credentials.password,
            display_name=credentials.name,
        )
        return {"status": "ok", "message": "User created successfully", "uid": user.uid}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
