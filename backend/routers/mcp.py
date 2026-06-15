from datetime import datetime
from typing import List, Optional

from utils.executors import db_executor, postprocess_executor

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

import database.memories as memories_db
import database.conversations as conversations_db
import database.users as users_db
import database.action_items as action_items_db
import database.goals as goals_db
import database.chat as chat_db
import database.screen_activity as screen_activity_db
import database.daily_summaries as daily_summaries_db

# from database.redis_db import get_filter_category_items
# from database.vector_db import query_vectors_by_metadata
from database.vector_db import upsert_memory_vector, delete_memory_vector
import database.vector_db as vector_db
from models.memories import MemoryDB, Memory, MemoryCategory
from models.conversation_enums import CategoryEnum
from utils.conversations.render import populate_speaker_names, redact_conversations_for_list
from utils.apps import update_personas_async
from utils.llm.memories import identify_category_for_memory
from utils.retrieval.hybrid import rrf_rerank
from dependencies import get_uid_from_mcp_api_key, get_current_user_id
from utils.other.endpoints import with_rate_limit
from utils.log_sanitizer import sanitize_pii
from utils.mcp_data import clean_action_item, clean_chat_message, clean_person, clean_screen_activity_row
from utils.mcp_memories import (
    collect_filtered_memories,
    parse_mcp_bool,
    parse_mcp_datetime,
    parse_mcp_int,
    parse_optional_mcp_bool,
)
import database.mcp_api_key as mcp_api_key_db
from models.mcp_api_key import McpApiKey, McpApiKeyCreate, McpApiKeyCreated
import logging

logger = logging.getLogger(__name__)

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
def create_memory(memory: Memory, uid: str = Depends(with_rate_limit(get_uid_from_mcp_api_key, "memories:create"))):
    # Auto-categorize memories from external sources
    memory.category = identify_category_for_memory(memory.content)
    memory_db = MemoryDB.from_memory(memory, uid, None, True)
    memories_db.create_memory(uid, memory_db.model_dump())
    try:
        upsert_memory_vector(uid, memory_db.id, memory_db.content, memory_db.category.value)
    except Exception:
        logger.exception("Vector upsert failed uid=%s memory_id=%s (memory saved, vector missing)", uid, memory_db.id)
    postprocess_executor.submit(update_personas_async, uid)
    return memory_db


def _validate_mcp_memory(uid: str, memory_id: str) -> dict:
    memory = memories_db.get_memory(uid, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    if memory.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this memory.")
    return memory


@router.delete("/v1/mcp/memories/{memory_id}", tags=["mcp"])
def delete_memory(memory_id: str, uid: str = Depends(get_uid_from_mcp_api_key)):
    _validate_mcp_memory(uid, memory_id)
    memories_db.delete_memory(uid, memory_id)
    try:
        delete_memory_vector(uid, memory_id)
    except Exception:
        logger.exception("Vector delete failed uid=%s memory_id=%s (Firestore deleted)", uid, memory_id)
    return {"status": "ok"}


@router.patch("/v1/mcp/memories/{memory_id}", tags=["mcp"])
def edit_memory(memory_id: str, value: str, uid: str = Depends(get_uid_from_mcp_api_key)):
    memory = _validate_mcp_memory(uid, memory_id)
    memories_db.edit_memory(uid, memory_id, value)
    try:
        upsert_memory_vector(uid, memory_id, value, memory.get('category', 'other'))
    except Exception:
        logger.exception("Vector upsert failed uid=%s memory_id=%s (memory edited, vector stale)", uid, memory_id)
    return {"status": "ok"}


class UserProfile(BaseModel):
    profile_text: Optional[str] = None
    generated_at: Optional[str] = None
    data_sources_used: Optional[int] = None


@router.get("/v1/mcp/profile", tags=["mcp"], response_model=UserProfile)
def get_user_profile(uid: str = Depends(get_uid_from_mcp_api_key)):
    """Omi's cached high-level user profile, if one has been generated."""
    profile = users_db.get_ai_user_profile(uid) or {}
    generated_at = profile.get("generated_at")
    return UserProfile(
        profile_text=profile.get("profile_text"),
        generated_at=str(generated_at) if generated_at is not None else None,
        data_sources_used=profile.get("data_sources_used"),
    )


class CleanerMemory(BaseModel):
    id: str
    content: str
    category: MemoryCategory


class SearchedMemory(CleanerMemory):
    relevance_score: float


@router.get("/v1/mcp/memories/search", tags=["mcp"], response_model=List[SearchedMemory])
def search_memories(
    query: str,
    limit: int = 10,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    logger.info(f"search_memories {uid} query={sanitize_pii(query)} limit={limit}")
    limit = max(1, min(limit, 20))
    fetch_limit = min(limit * 3, 60)
    matches = vector_db.find_similar_memories(uid, query, threshold=0.0, limit=fetch_limit)
    if not matches:
        return []
    memory_ids = [m.get("memory_id") for m in matches if m.get("memory_id")]
    scores = {m.get("memory_id"): m.get("score", 0) for m in matches}
    if not memory_ids:
        return []
    docs = {m.get("id"): m for m in memories_db.get_memories_by_ids(uid, memory_ids)}

    # Build candidates in vector-relevance order, excluding rejected / locked / superseded
    # memories so the brain never returns a fact that is no longer true.
    candidates = []
    for mid in memory_ids:
        m = docs.get(mid)
        if not m:
            continue
        if m.get('user_review') is False or m.get('is_locked', False) or m.get('invalid_at') is not None:
            continue
        candidates.append(
            {
                "id": m.get("id", ""),
                "content": m.get("content", ""),
                "category": m.get("category", "other"),
                "vector_score": scores.get(mid, 0),
            }
        )

    # Order by semantic score first (RRF uses this as the vector rank), then fuse with
    # keyword (BM25) ranking so exact-keyword lookups surface reliably.
    candidates.sort(key=lambda c: c.get("vector_score", 0), reverse=True)
    reranked = rrf_rerank(query, candidates, limit)
    return [
        {
            "id": c["id"],
            "content": c["content"],
            "category": c["category"],
            "relevance_score": round(c.get("vector_score", 0), 4),
        }
        for c in reranked
    ]


@router.get("/v1/mcp/memories", tags=["mcp"], response_model=List[CleanerMemory])
def get_memories(
    uid: str = Depends(get_uid_from_mcp_api_key),
    limit: int = 25,
    offset: int = 0,
    categories: Optional[str] = None,
    sort: str = "created_desc",
    reviewed: Optional[bool] = None,
    manually_added: Optional[bool] = None,
    updated_after: Optional[str] = None,
    include_activity: bool = False,
    include_sensitive: bool = True,
):
    try:
        limit = parse_mcp_int(limit, "limit", default=25, minimum=1, maximum=500)
        offset = parse_mcp_int(offset, "offset", default=0, minimum=0, maximum=100000)
        reviewed = parse_optional_mcp_bool(reviewed, "reviewed")
        manually_added = parse_optional_mcp_bool(manually_added, "manually_added")
        include_activity = parse_mcp_bool(include_activity, "include_activity", default=False)
        include_sensitive = parse_mcp_bool(include_sensitive, "include_sensitive", default=True)
        parsed_updated_after = parse_mcp_datetime(updated_after, "updated_after")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if sort not in {"scoring_desc", "created_desc", "updated_desc", "manual_first"}:
        raise HTTPException(
            status_code=400,
            detail="Invalid sort. Expected one of: scoring_desc, created_desc, updated_desc, manual_first.",
        )

    category_list = []
    if categories:
        try:
            category_list = [MemoryCategory(c.strip()) for c in categories.split(",") if c.strip()]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid category {str(e)}")
    result = collect_filtered_memories(
        lambda batch_offset, batch_limit: memories_db.get_memories(
            uid, batch_limit, batch_offset, [c.value for c in category_list], sort=sort
        ),
        limit=limit,
        offset=offset,
        reviewed=reviewed,
        manually_added=manually_added,
        include_activity=include_activity,
        include_sensitive=include_sensitive,
        updated_after=parsed_updated_after,
        sort=sort,
    )
    memories = result["memories"]
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
    limit: int = 100,
    offset: int = 0,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    logger.info(f"get_conversations {uid} {limit} {offset} {start_date} {end_date} {categories}")
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

    redact_conversations_for_list(conversations)
    return conversations


@router.get("/v1/mcp/conversations/search", response_model=List[SimpleConversation], tags=["mcp"])
def search_conversations(
    query: str,
    limit: int = 10,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    logger.info(f"search_conversations {uid} query={sanitize_pii(query)} limit={limit}")

    starts_at = None
    ends_at = None
    if start_date:
        try:
            starts_at = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp())
        except ValueError:
            raise HTTPException(
                status_code=400, detail=f"Invalid start_date format: '{start_date}'. Expected YYYY-MM-DD."
            )
    if end_date:
        try:
            ends_at = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid end_date format: '{end_date}'. Expected YYYY-MM-DD.")

    conversation_ids = vector_db.query_vectors(query, uid, starts_at=starts_at, ends_at=ends_at, k=limit)
    if not conversation_ids:
        return []

    conversations = conversations_db.get_conversations_by_id(uid, conversation_ids)
    redact_conversations_for_list(conversations)
    return conversations


@router.get(
    "/v1/mcp/conversations/{conversation_id}",
    response_model=FullConversation,
    tags=["mcp"],
)
def get_conversation_by_id(conversation_id: str, uid: str = Depends(get_uid_from_mcp_api_key)):
    logger.info(f"get_conversation_by_id {uid} {conversation_id}")
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if conversation.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this conversation.")

    populate_speaker_names(uid, [conversation])

    return conversation


# ---------------------------------------------------------------------------
# Action items — the user's actionable task layer (to-dos with due dates)
# ---------------------------------------------------------------------------


class SimpleActionItem(BaseModel):
    id: str
    description: str
    completed: bool = False
    created_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    conversation_id: Optional[str] = None


@router.get("/v1/mcp/action-items", response_model=List[SimpleActionItem], tags=["mcp"])
def get_action_items(
    completed: Optional[bool] = None,
    due_start_date: Optional[datetime] = None,
    due_end_date: Optional[datetime] = None,
    limit: int = 100,
    offset: int = 0,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    logger.info(f"get_action_items {uid} completed={completed} limit={limit} offset={offset}")
    limit = max(1, min(limit, 500))
    offset = max(0, offset)
    items = action_items_db.get_action_items(
        uid,
        completed=completed,
        due_start_date=due_start_date,
        due_end_date=due_end_date,
        limit=limit,
        offset=offset,
    )
    return [clean_action_item(i) for i in items if not i.get("deleted", False)]


# ---------------------------------------------------------------------------
# Goals — the user's stated objectives
# ---------------------------------------------------------------------------


@router.get("/v1/mcp/goals", tags=["mcp"])
def get_goals(include_inactive: bool = False, uid: str = Depends(get_uid_from_mcp_api_key)):
    logger.info(f"get_goals {uid} include_inactive={include_inactive}")
    return goals_db.get_all_goals(uid, include_inactive=include_inactive)


# ---------------------------------------------------------------------------
# Chat — the user's prior conversations with Omi (intent / preferences signal)
# ---------------------------------------------------------------------------


class SimpleChatMessage(BaseModel):
    id: str
    text: str
    sender: str
    type: Optional[str] = None
    created_at: Optional[datetime] = None


@router.get("/v1/mcp/chat", response_model=List[SimpleChatMessage], tags=["mcp"])
def get_chat_messages(limit: int = 50, offset: int = 0, uid: str = Depends(get_uid_from_mcp_api_key)):
    logger.info(f"get_chat_messages {uid} limit={limit} offset={offset}")
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    messages = chat_db.get_messages(uid, limit=limit, offset=offset)
    return [clean_chat_message(m) for m in messages]


# ---------------------------------------------------------------------------
# People — the contacts/speakers the user interacts with
# ---------------------------------------------------------------------------


class SimplePerson(BaseModel):
    id: str
    name: str
    created_at: Optional[datetime] = None
    speech_sample_transcripts: List[str] = []


@router.get("/v1/mcp/people", response_model=List[SimplePerson], tags=["mcp"])
def get_people(uid: str = Depends(get_uid_from_mcp_api_key)):
    logger.info(f"get_people {uid}")
    return [clean_person(p) for p in users_db.get_people(uid)]


# ---------------------------------------------------------------------------
# Screen activity — desktop Rewind (app, window title, OCR text)
# ---------------------------------------------------------------------------


@router.get("/v1/mcp/screen-activity", tags=["mcp"])
def get_screen_activity(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    app: Optional[str] = None,
    summary: bool = False,
    limit: int = 200,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    logger.info(f"get_screen_activity {uid} summary={summary} app={app} limit={limit}")
    if summary:
        return screen_activity_db.get_screen_activity_summary(uid, start_date=start_date, end_date=end_date)
    limit = max(1, min(limit, 1000))
    rows = screen_activity_db.get_screen_activity(
        uid, start_date=start_date, end_date=end_date, app_filter=app, limit=limit
    )
    return [clean_screen_activity_row(r) for r in rows]


# ---------------------------------------------------------------------------
# Daily summaries — Omi's per-day digest of the user's life
# ---------------------------------------------------------------------------


@router.get("/v1/mcp/daily-summaries", tags=["mcp"])
def get_daily_summaries(
    limit: int = 30,
    offset: int = 0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    logger.info(f"get_daily_summaries {uid} limit={limit} offset={offset}")
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    return daily_summaries_db.get_daily_summaries(
        uid, limit=limit, offset=offset, start_date=start_date, end_date=end_date
    )
