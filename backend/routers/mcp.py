from datetime import datetime
import threading
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

import database.memories as memories_db
import database.conversations as conversations_db
import database.users as users_db

# from database.redis_db import get_filter_category_items
# from database.vector_db import query_vectors_by_metadata
from models.memories import MemoryDB, Memory, MemoryCategory
from models.conversation import CategoryEnum
from utils.apps import update_personas_async
from utils.llm.memories import identify_category_for_memory
from dependencies import get_uid_from_mcp_api_key, get_current_user_id
import database.mcp_api_key as mcp_api_key_db
from models.mcp_api_key import McpApiKey, McpApiKeyCreate, McpApiKeyCreated

router = APIRouter()


@router.get("/v1/mcp/keys", response_model=List[McpApiKey], tags=["mcp"])
def get_keys(uid: str = Depends(get_current_user_id)):
    return mcp_api_key_db.get_mcp_keys_for_user(uid)


@router.post("/v1/mcp/keys", response_model=McpApiKeyCreated, tags=["mcp"])
def create_key(key_data: McpApiKeyCreate, uid: str = Depends(get_current_user_id)):
    if not key_data.name or len(key_data.name.strip()) == 0:
        raise HTTPException(status_code=422, detail="Key name cannot be empty")

    raw_key, api_key_data = mcp_api_key_db.create_mcp_key(uid, key_data.name.strip())
    return McpApiKeyCreated(**api_key_data.model_dump(), key=raw_key)


@router.delete("/v1/mcp/keys/{key_id}", status_code=204, tags=["mcp"])
def delete_key(key_id: str, uid: str = Depends(get_current_user_id)):
    mcp_api_key_db.delete_mcp_key(uid, key_id)
    return


@router.post("/v1/mcp/memories", tags=["mcp"], response_model=Memory)
def create_memory(memory: Memory, uid: str = Depends(get_uid_from_mcp_api_key)):
    # Auto-categorize memories from external sources
    memory.category = identify_category_for_memory(memory.content)
    memory_db = MemoryDB.from_memory(memory, uid, None, True)
    memories_db.create_memory(uid, memory_db.model_dump())
    threading.Thread(target=update_personas_async, args=(uid,)).start()
    return memory_db


@router.delete("/v1/mcp/memories/{memory_id}", tags=["mcp"])
def delete_memory(memory_id: str, uid: str = Depends(get_uid_from_mcp_api_key)):
    memories_db.delete_memory(uid, memory_id)
    return {"status": "ok"}


@router.patch("/v1/mcp/memories/{memory_id}", tags=["mcp"])
def edit_memory(memory_id: str, value: str, uid: str = Depends(get_uid_from_mcp_api_key)):
    memories_db.edit_memory(uid, memory_id, value)
    return {"status": "ok"}


class CleanerMemory(BaseModel):
    id: str
    content: str
    category: MemoryCategory


@router.get("/v1/mcp/memories", tags=["mcp"], response_model=List[CleanerMemory])
def get_memories(
    uid: str = Depends(get_uid_from_mcp_api_key),
    limit: int = 25,
    offset: int = 0,
    categories: Optional[str] = None,
):
    category_list = []
    if categories:
        try:
            category_list = [MemoryCategory(c.strip()) for c in categories.split(",") if c.strip()]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid category {str(e)}")
    memories = memories_db.get_memories(uid, limit, offset, [c.value for c in category_list])
    for memory in memories:
        if memory.get('is_locked', False):
            content = memory.get('content', '')
            memory['content'] = (content[:70] + '...') if len(content) > 70 else content
    return memories


class SimpleStructured(BaseModel):
    title: str
    overview: str
    category: CategoryEnum


class SimpleTranscriptSegment(BaseModel):
    id: Optional[str] = None
    text: str
    speaker_id: Optional[int] = None
    speaker_name: Optional[str] = None
    start: float
    end: float


def _add_speaker_names_to_segments(uid, conversations: list):
    """Add speaker_name to transcript segments based on person_id mappings."""
    user_profile = users_db.get_user_profile(uid)
    user_name = user_profile.get('name') or 'User'

    all_person_ids = set()
    for conv in conversations:
        for seg in conv.get('transcript_segments', []):
            if seg.get('person_id'):
                all_person_ids.add(seg['person_id'])

    people_map = {}
    if all_person_ids:
        people_data = users_db.get_people_by_ids(uid, list(all_person_ids))
        people_map = {p['id']: p['name'] for p in people_data}

    for conv in conversations:
        for seg in conv.get('transcript_segments', []):
            if seg.get('is_user'):
                seg['speaker_name'] = user_name
            elif seg.get('person_id') and seg['person_id'] in people_map:
                seg['speaker_name'] = people_map[seg['person_id']]
            else:
                seg['speaker_name'] = f"Speaker {seg.get('speaker_id', 0)}"


class SimpleConversation(BaseModel):
    id: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    structured: SimpleStructured
    language: Optional[str] = None


class FullConversation(SimpleConversation):
    transcript_segments: List[SimpleTranscriptSegment] = []


# Step 2 do retrieval
# @router.get("/v1/mcp/conversations/available-filters", tags=["mcp"])
# def get_conversations_available_filters(uid: str = Header(None)):
#     return {
#         "people": get_filter_category_items(uid, "people"),
#         "topics": get_filter_category_items(uid, "topics"),
#         "entities": get_filter_category_items(uid, "entities"),
#     }


@router.get("/v1/mcp/conversations", response_model=List[SimpleConversation], tags=["mcp"])
def get_conversations(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    categories: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    print("get_conversations", uid, limit, offset, start_date, end_date, categories)
    try:
        category_list = [CategoryEnum(c.strip()) for c in categories.split(",") if c.strip()] if categories else []
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid category {str(e)}")

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

    # Paywall is enforced on the detail endpoint, list view can show basic data.
    return conversations


@router.get(
    "/v1/mcp/conversations/{conversation_id}",
    response_model=FullConversation,
    tags=["mcp"],
)
def get_conversation_by_id(conversation_id: str, uid: str = Depends(get_uid_from_mcp_api_key)):
    print("get_conversation_by_id", uid, conversation_id)
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if conversation.get('is_locked', False):
        raise HTTPException(status_code=402, detail="Unlimited Plan Required to access this conversation.")

    _add_speaker_names_to_segments(uid, [conversation])

    return conversation
