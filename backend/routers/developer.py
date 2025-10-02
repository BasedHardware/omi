from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

import database.memories as memories_db
import database.conversations as conversations_db
import database.dev_api_key as dev_api_key_db
import database.action_items as action_items_db

from models.memories import MemoryCategory
from models.conversation import CategoryEnum
from dependencies import get_uid_from_dev_api_key, get_current_user_id
from models.dev_api_key import DevApiKey, DevApiKeyCreate, DevApiKeyCreated

router = APIRouter()


# ******************************************************
# ****************** API KEY MANAGEMENT ****************
# ******************************************************


@router.get("/v1/dev/keys", response_model=List[DevApiKey], tags=["developer"])
def get_keys(uid: str = Depends(get_current_user_id)):
    return dev_api_key_db.get_dev_keys_for_user(uid)


@router.post("/v1/dev/keys", response_model=DevApiKeyCreated, tags=["developer"])
def create_key(key_data: DevApiKeyCreate, uid: str = Depends(get_current_user_id)):
    if not key_data.name or len(key_data.name.strip()) == 0:
        raise HTTPException(status_code=422, detail="Key name cannot be empty")

    raw_key, api_key_data = dev_api_key_db.create_dev_key(uid, key_data.name.strip())
    return DevApiKeyCreated(**api_key_data.model_dump(), key=raw_key)


@router.delete("/v1/dev/keys/{key_id}", status_code=204, tags=["developer"])
def delete_key(key_id: str, uid: str = Depends(get_current_user_id)):
    dev_api_key_db.delete_dev_key(uid, key_id)
    return


# ******************************************************
# ****************** READ-ONLY MEMORIES ****************
# ******************************************************


class CleanerMemory(BaseModel):
    id: str
    content: str
    category: MemoryCategory


@router.get("/v1/dev/user/memories", tags=["developer"], response_model=List[CleanerMemory])
def get_memories(
    uid: str = Depends(get_uid_from_dev_api_key),
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


# ******************************************************
# *************** READ-ONLY ACTION ITEMS ***************
# ******************************************************


class ActionItemResponse(BaseModel):
    id: str
    description: str
    completed: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    conversation_id: Optional[str] = None


@router.get("/v1/dev/user/action-items", tags=["developer"], response_model=List[ActionItemResponse])
def get_action_items(
    uid: str = Depends(get_uid_from_dev_api_key),
    conversation_id: Optional[str] = None,
    completed: Optional[bool] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
):
    """
    Get action items with optional filters. Locked action items are excluded.

    - **conversation_id**: Filter by conversation ID (None for standalone items)
    - **completed**: Filter by completion status
    - **start_date**: Filter by start date (inclusive)
    - **end_date**: Filter by end date (inclusive)
    - **limit**: Maximum number of items to return
    - **offset**: Number of items to skip
    """
    action_items = action_items_db.get_action_items(
        uid=uid,
        conversation_id=conversation_id,
        completed=completed,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

    # Filter out locked action items
    unlocked_action_items = [item for item in action_items if not item.get('is_locked', False)]

    return unlocked_action_items


# ******************************************************
# *************** READ-ONLY CONVERSATIONS **************
# ******************************************************


class ActionItem(BaseModel):
    description: str
    completed: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    conversation_id: Optional[str] = None


class Event(BaseModel):
    title: str
    description: str = ''
    start: datetime
    duration: int = 30
    created: bool = False


class SimpleStructured(BaseModel):
    title: str
    overview: str
    emoji: str = '🧠'
    category: CategoryEnum
    action_items: List[ActionItem] = []
    events: List[Event] = []


class SimpleTranscriptSegment(BaseModel):
    id: Optional[str] = None
    text: str
    speaker_id: Optional[int] = None
    start: float
    end: float


class Conversation(BaseModel):
    id: str
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    structured: SimpleStructured
    language: Optional[str] = None
    source: Optional[str] = None
    transcript_segments: Optional[List[SimpleTranscriptSegment]] = None


@router.get("/v1/dev/user/conversations", response_model=List[Conversation], tags=["developer"])
def get_conversations(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    categories: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
    include_transcript: bool = False,
    uid: str = Depends(get_uid_from_dev_api_key),
):
    """
    Get conversations with optional transcript inclusion.

    - **include_transcript**: If True, includes full transcript_segments in the response
    """
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

    # Filter out locked conversations completely
    unlocked_conversations = [conv for conv in conversations if not conv.get('is_locked', False)]

    # Remove transcript_segments if not requested
    if not include_transcript:
        for conv in unlocked_conversations:
            conv.pop('transcript_segments', None)

    return unlocked_conversations
