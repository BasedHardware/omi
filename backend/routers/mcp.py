from datetime import datetime
from typing import Any, Dict, List, Optional, Union

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
import database.calendar_meetings as calendar_meetings_db
from database._client import db
import database.phone_calls as phone_calls_db
from firebase_admin import auth as firebase_auth

# from database.redis_db import get_filter_category_items
# from database.vector_db import query_vectors_by_metadata
from database.vector_db import upsert_memory_vector, delete_memory_vector
import database.vector_db as vector_db
from models.memories import MemoryDB, Memory, MemoryCategory
from models.conversation_enums import CategoryEnum
from models.conversation import AppResult
from utils.conversations.render import populate_speaker_names, redact_conversations_for_list
from utils.apps import update_personas_async
from utils.llm.memories import identify_category_for_memory
from utils.memory.canonical_memory_adapter import _read_canonical_memory_item, memory_item_to_memorydb
from utils.memory.memory_service import MemoryService, fetch_memory_dict
from utils.memory.memory_system import MemorySystem
from utils.memory.surface_routing import memorydb_list_with_locked_preview, pin_memory_system
from dependencies import (
    get_uid_from_mcp_api_key,
    get_current_user_id,
    get_mcp_memory_default_memory_read_context,
    get_mcp_memory_default_memory_write_context,
)
from utils.other.endpoints import with_rate_limit, with_rate_limit_context
from utils.log_sanitizer import sanitize_pii
from utils.mcp_data import (
    clean_action_item,
    clean_chat_message,
    clean_meeting,
    clean_person,
    clean_screen_activity_row,
    inclusive_end_of_day,
)
from utils.memory.default_read_rollout import (
    MemoryReadDecision,
    guard_legacy_memory_write,
    read_default_read_rollout,
)
from utils.memory.product_authorization import (
    ProductAuthorizationContext,
    authorize_memory_external_default_memory_read,
    authorize_memory_external_default_memory_write,
)
import utils.mcp_action_items as mcp_action_items
from utils.mcp_memories import (
    collect_filtered_memories,
    list_default_mcp_memories,
    mcp_legacy_read_authorized,
    parse_mcp_bool,
    parse_mcp_datetime,
    parse_mcp_int,
    parse_optional_mcp_bool,
    search_default_mcp_memories_vector,
)
import database.mcp_oauth as mcp_oauth_db
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class McpStatusResponse(BaseModel):
    status: str


class McpOauthGrantsResponse(BaseModel):
    grants: List[Dict[str, Any]] = []


class McpScreenActivityRow(BaseModel):
    id: Optional[str] = None
    timestamp: Optional[datetime] = None
    app_name: Optional[str] = None
    window_title: Optional[str] = None
    ocr_text: Optional[str] = None


class McpScreenActivityAppSummary(BaseModel):
    count: int = 0
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    window_titles: List[str] = []


class McpScreenActivitySummaryResponse(BaseModel):
    apps: Dict[str, McpScreenActivityAppSummary] = {}
    total_screenshots: int = 0


@router.get("/v1/mcp/oauth/grants", tags=["mcp"], response_model=McpOauthGrantsResponse)
def get_oauth_grants(uid: str = Depends(get_current_user_id)):
    return {"grants": mcp_oauth_db.list_user_grants(uid)}


@router.delete("/v1/mcp/oauth/grants/{grant_id}", status_code=204, tags=["mcp"])
def revoke_oauth_grant(grant_id: str, uid: str = Depends(get_current_user_id)):
    if not mcp_oauth_db.revoke_user_grant(uid, grant_id):
        raise HTTPException(status_code=404, detail="OAuth grant not found")
    return


@router.post("/v1/mcp/memories", tags=["mcp"], response_model=Memory)
def create_memory(
    memory: Memory,
    auth_context: ProductAuthorizationContext = Depends(
        with_rate_limit_context(get_mcp_memory_default_memory_write_context, "memories:create")
    ),
):
    # Fail closed: a legacy/read-only MCP key (no persisted memories.write grant)
    # must not mutate canonical memories.
    write_grant = authorize_memory_external_default_memory_write(auth_context, db_client=db)
    if not write_grant.allowed:
        raise HTTPException(
            status_code=write_grant.status_code,
            detail=write_grant.observability,
        )
    uid = auth_context.uid
    memory_system = pin_memory_system(uid, db_client=db)
    memory.category = identify_category_for_memory(memory.content)
    memory_db = MemoryDB.from_memory(memory, uid, None, True)
    memory_service = MemoryService(db_client=db)
    memory_db = memory_service.create_external_memory(
        uid,
        memory_db,
        memory_system=memory_system,
        consumer='mcp',
        operation="mcp_memory_create",
        require_canonical_promotion=True,
    )
    postprocess_executor.submit(update_personas_async, uid)
    return memory_db


def _validate_mcp_memory(uid: str, memory_id: str) -> dict:
    return fetch_memory_dict(uid, memory_id, db_client=db)


@router.delete("/v1/mcp/memories/{memory_id}", tags=["mcp"], response_model=McpStatusResponse)
def delete_memory(
    memory_id: str,
    auth_context: ProductAuthorizationContext = Depends(get_mcp_memory_default_memory_write_context),
):
    # Fail closed: a legacy/read-only MCP key (no persisted memories.write grant)
    # must not mutate canonical memories.
    write_grant = authorize_memory_external_default_memory_write(auth_context, db_client=db)
    if not write_grant.allowed:
        raise HTTPException(
            status_code=write_grant.status_code,
            detail=write_grant.observability,
        )
    uid = auth_context.uid
    memory_system = pin_memory_system(uid, db_client=db)
    if memory_system != MemorySystem.CANONICAL:
        _validate_mcp_memory(uid, memory_id)
    MemoryService(db_client=db).delete_external_memory(
        uid,
        memory_id,
        memory_system=memory_system,
        consumer='mcp',
        operation="mcp_memory_delete",
    )
    return {"status": "ok"}


@router.patch("/v1/mcp/memories/{memory_id}", tags=["mcp"], response_model=McpStatusResponse)
def edit_memory(
    memory_id: str,
    value: str,
    auth_context: ProductAuthorizationContext = Depends(get_mcp_memory_default_memory_write_context),
):
    # Fail closed: a legacy/read-only MCP key (no persisted memories.write grant)
    # must not mutate canonical memories.
    write_grant = authorize_memory_external_default_memory_write(auth_context, db_client=db)
    if not write_grant.allowed:
        raise HTTPException(
            status_code=write_grant.status_code,
            detail=write_grant.observability,
        )
    uid = auth_context.uid
    memory_system = pin_memory_system(uid, db_client=db)
    _validate_mcp_memory(uid, memory_id)
    MemoryService(db_client=db).update_external_memory_content(
        uid,
        memory_id,
        value,
        memory_system=memory_system,
        consumer='mcp',
        operation="mcp_memory_edit",
    )
    return {"status": "ok"}


class UserProfile(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    profile_text: Optional[str] = None
    generated_at: Optional[str] = None
    data_sources_used: Optional[int] = None


def _get_user_contact(uid: str) -> dict:
    """Best-effort name/email/phone for the profile. Never raises — a contact
    lookup failure must not break the profile response."""
    name = email = phone_number = None
    try:
        user = firebase_auth.get_user(uid)
        name = user.display_name or None
        email = user.email or None
        phone_number = user.phone_number or None
    except Exception as e:
        # Expected for uids with no Firebase Auth record; warn (no traceback).
        logger.warning("get_user_profile: firebase contact lookup failed uid=%s: %s", uid, e)
    if not phone_number:
        try:
            # get_phone_numbers returns decrypted dicts; prefer the primary one.
            numbers = phone_calls_db.get_phone_numbers(uid) or []
            primary = next((n for n in numbers if n.get("is_primary")), None) or (numbers[0] if numbers else None)
            if primary:
                phone_number = primary.get("phone_number")
        except Exception as e:
            logger.warning("get_user_profile: phone_numbers lookup failed uid=%s: %s", uid, e)
    return {"name": name, "email": email, "phone_number": phone_number}


@router.get("/v1/mcp/profile", tags=["mcp"], response_model=UserProfile)
def get_user_profile(uid: str = Depends(get_uid_from_mcp_api_key)):
    """Omi's cached high-level user profile, if one has been generated."""
    profile = users_db.get_ai_user_profile(uid) or {}
    generated_at = profile.get("generated_at")
    contact = _get_user_contact(uid)
    return UserProfile(
        name=contact["name"],
        email=contact["email"],
        phone_number=contact["phone_number"],
        profile_text=profile.get("profile_text"),
        generated_at=str(generated_at) if generated_at is not None else None,
        data_sources_used=profile.get("data_sources_used"),
    )


class CleanerMemory(BaseModel):
    id: str
    content: str
    category: MemoryCategory
    category_source: Optional[str] = None
    reviewed: Optional[bool] = None
    reviewed_source: Optional[str] = None
    manually_added: Optional[bool] = None
    manually_added_source: Optional[str] = None
    memory_default_memory: Optional[bool] = None
    archive_default_visible: Optional[bool] = None
    policy: Optional[dict] = None


class SearchedMemory(CleanerMemory):
    relevance_score: float


@router.get("/v1/mcp/memories/search", tags=["mcp"], response_model=List[SearchedMemory])
def search_memories(
    query: str,
    limit: int = 10,
    auth_context: ProductAuthorizationContext = Depends(get_mcp_memory_default_memory_read_context),
):
    app_key_grant = authorize_memory_external_default_memory_read(auth_context, db_client=db)
    if not app_key_grant.allowed:
        raise HTTPException(
            status_code=app_key_grant.status_code,
            detail=app_key_grant.observability,
        )

    uid = auth_context.uid
    logger.info(f"search_memories {uid} query={sanitize_pii(query)} limit={limit}")
    limit = max(1, min(limit, 20))
    memory_system = pin_memory_system(uid, db_client=db)
    memory_service = MemoryService(db_client=db)

    if memory_system == MemorySystem.CANONICAL:
        return memory_service.search_mcp(uid, query, limit=limit)

    memory_rollout = read_default_read_rollout(uid=uid, db_client=db, consumer='mcp')
    vector_search_results = search_default_mcp_memories_vector(
        uid=uid,
        query=query,
        limit=limit,
        db_client=db,
        rollout_decision=memory_rollout,
    )
    if vector_search_results.read_decision == MemoryReadDecision.USE_MEMORY:
        return vector_search_results.memories
    if not mcp_legacy_read_authorized(vector_search_results):
        return []

    return memory_service.search_mcp(uid, query, limit=limit)


@router.get("/v1/mcp/memories", tags=["mcp"], response_model=List[CleanerMemory])
def get_memories(
    auth_context: ProductAuthorizationContext = Depends(get_mcp_memory_default_memory_read_context),
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
    uid = auth_context.uid
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

    memory_system = pin_memory_system(uid, db_client=db)

    # Fail closed: authorize memory read before any system branch, matching
    # the search route. Legacy keys without persisted memories.read scope
    # cannot list canonical memories.
    app_key_grant = authorize_memory_external_default_memory_read(auth_context, db_client=db)
    if not app_key_grant.allowed:
        raise HTTPException(
            status_code=app_key_grant.status_code,
            detail=app_key_grant.observability,
        )

    if memory_system == MemorySystem.CANONICAL:
        # Over-fetch then apply the same filters the legacy path applies, so
        # canonical callers honoring categories/reviewed/sensitive/sort never
        # receive memories they explicitly excluded. The fetch lambda returns
        # raw (unfiltered) batches so collect_filtered_memories can advance by
        # raw page size — filtering inside the lambda would make short batches
        # look like end-of-source.
        filtered = collect_filtered_memories(
            lambda batch_offset, batch_limit: [
                m.model_dump(mode='json')
                for m in MemoryService(db_client=db).read(uid, limit=batch_limit, offset=batch_offset)
            ],
            limit=limit,
            offset=offset,
            reviewed=reviewed,
            manually_added=manually_added,
            include_activity=include_activity,
            include_sensitive=include_sensitive,
            updated_after=parsed_updated_after,
            sort=sort,
            categories=[c.value for c in category_list] if category_list else None,
        )
        memories = filtered['memories']
        for memory in memories:
            if memory.get('is_locked', False):
                content = memory.get('content', '')
                memory['content'] = (content[:70] + '...') if len(content) > 70 else content
        return memories

    memory_rollout = read_default_read_rollout(uid=uid, db_client=db, consumer='mcp')
    memory_list_results = list_default_mcp_memories(
        uid=uid,
        limit=limit,
        offset=offset,
        db_client=db,
        rollout_decision=memory_rollout,
        categories=[category.value for category in category_list],
        reviewed=reviewed,
        manually_added=manually_added,
    )
    if memory_list_results.read_decision == MemoryReadDecision.USE_MEMORY:
        return memory_list_results.memories
    if not mcp_legacy_read_authorized(memory_list_results):
        return []

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
    apps_results: List[AppResult] = []


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
    # Clamp pagination so a negative value cannot reach Firestore .limit()/.offset() (which
    # raises -> HTTP 500) and an oversized value cannot stream/skip the whole collection.
    # Mirrors the sibling MCP tool (routers/mcp_sse.py get_conversations) and every other
    # paginated list endpoint in this file (get_action_items, get_chat_messages, etc.).
    limit = max(1, min(limit, 1000))
    offset = max(0, min(offset, 100000))
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
    # Validate each record individually so one malformed conversation (e.g. a category
    # no longer in CategoryEnum) cannot 500 the whole page via response_model coercion.
    valid_conversations = []
    for conv in conversations:
        try:
            valid_conversations.append(SimpleConversation.model_validate(conv))
        except Exception as e:  # noqa: BLE001 - one bad record must not 500 the page
            logger.warning(f"Skipping malformed conversation {conv.get('id', 'unknown')} in MCP list: {e}")
    return valid_conversations


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
    valid = []
    for conv in conversations:
        try:
            valid.append(SimpleConversation.model_validate(conv))
        except Exception as e:  # noqa: BLE001 - one malformed record must not 500 the page
            logger.warning(f"Skipping malformed conversation {conv.get('id', 'unknown')} in MCP search: {e}")
    return valid


@router.get(
    "/v1/mcp/conversations/{conversation_id}",
    response_model=FullConversation,
    tags=["mcp"],
)
def get_conversation_by_id(
    conversation_id: str,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    logger.info(f"get_conversation_by_id {uid} {conversation_id}")
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if conversation.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this conversation.")

    populate_speaker_names(uid, [conversation])

    # A legacy/poisoned record (e.g. a structured.category no longer in CategoryEnum)
    # must not 500 this single-item fetch via response_model coercion — mirror the
    # per-record guard already used by the list/search siblings above.
    try:
        return FullConversation.model_validate(conversation)
    except Exception as e:  # noqa: BLE001 - malformed legacy record must not 500
        logger.warning(f"Conversation {conversation_id} failed MCP response validation: {e}")
        raise HTTPException(status_code=404, detail="Conversation not found")


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


class McpCreateActionItem(BaseModel):
    description: str
    due_at: Optional[datetime] = None
    completed: bool = False


class McpUpdateActionItem(BaseModel):
    description: Optional[str] = None
    due_at: Optional[datetime] = None


def _action_item_write_error(exc: Exception) -> HTTPException:
    """Map a shared action-item write error to the REST status the memory writes use."""
    if isinstance(exc, mcp_action_items.ActionItemNotFound):
        return HTTPException(status_code=404, detail="Action item not found")
    if isinstance(exc, mcp_action_items.ActionItemLocked):
        return HTTPException(status_code=402, detail="A paid plan is required to modify this action item.")
    return HTTPException(status_code=500, detail="Action item write failed")


@router.get("/v1/mcp/action-items/search", response_model=List[SimpleActionItem], tags=["mcp"])
def search_action_items(
    query: str,
    limit: int = 10,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    logger.info(f"search_action_items {uid} limit={limit}")
    try:
        return mcp_action_items.search_action_items(uid, query, limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/v1/mcp/action-items", response_model=SimpleActionItem, tags=["mcp"])
def create_action_item(
    body: McpCreateActionItem,
    uid: str = Depends(with_rate_limit(get_uid_from_mcp_api_key, "action_items:write")),
):
    logger.info(f"create_action_item {uid} completed={body.completed} has_due={body.due_at is not None}")
    try:
        return mcp_action_items.create_action_item(uid, body.description, due_at=body.due_at, completed=body.completed)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except mcp_action_items.ActionItemError as e:
        raise _action_item_write_error(e)


@router.post("/v1/mcp/action-items/{action_item_id}/complete", response_model=SimpleActionItem, tags=["mcp"])
def complete_action_item(
    action_item_id: str,
    completed: bool = True,
    uid: str = Depends(with_rate_limit(get_uid_from_mcp_api_key, "action_items:write")),
):
    logger.info(f"complete_action_item {uid} id={action_item_id} completed={completed}")
    try:
        return mcp_action_items.set_completed(uid, action_item_id, completed=completed)
    except mcp_action_items.ActionItemError as e:
        raise _action_item_write_error(e)


@router.patch("/v1/mcp/action-items/{action_item_id}", response_model=SimpleActionItem, tags=["mcp"])
def update_action_item(
    action_item_id: str,
    body: McpUpdateActionItem,
    uid: str = Depends(with_rate_limit(get_uid_from_mcp_api_key, "action_items:write")),
):
    logger.info(f"update_action_item {uid} id={action_item_id}")
    try:
        return mcp_action_items.update_action_item(
            uid, action_item_id, description=body.description, due_at=body.due_at
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except mcp_action_items.ActionItemError as e:
        raise _action_item_write_error(e)


@router.delete("/v1/mcp/action-items/{action_item_id}", tags=["mcp"], response_model=McpStatusResponse)
def delete_action_item(
    action_item_id: str,
    uid: str = Depends(with_rate_limit(get_uid_from_mcp_api_key, "action_items:write")),
):
    logger.info(f"delete_action_item {uid} id={action_item_id}")
    try:
        mcp_action_items.delete_action_item(uid, action_item_id)
    except mcp_action_items.ActionItemError as e:
        raise _action_item_write_error(e)
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Goals — the user's stated objectives
# ---------------------------------------------------------------------------


@router.get("/v1/mcp/goals", tags=["mcp"], response_model=List[Dict[str, Any]])
def get_goals(
    include_inactive: bool = False,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
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
def get_chat_messages(
    limit: int = 50,
    offset: int = 0,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
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
# Calendar meetings: the user's synced meetings (title, time, participants)
# ---------------------------------------------------------------------------


class McpMeetingParticipant(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None


class McpMeeting(BaseModel):
    id: Optional[str] = None
    title: Optional[str] = None
    start_time: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    platform: Optional[str] = None
    meeting_link: Optional[str] = None
    participants: List[McpMeetingParticipant] = []
    notes: Optional[str] = None
    calendar_source: Optional[str] = None


@router.get("/v1/mcp/calendar-meetings", response_model=List[McpMeeting], tags=["mcp"])
def get_calendar_meetings(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 50,
    uid: str = Depends(get_uid_from_mcp_api_key),
):
    logger.info(f"get_calendar_meetings {uid} {limit} {start_date} {end_date}")
    limit = max(1, min(limit, 200))
    end_date = inclusive_end_of_day(end_date)
    meetings = calendar_meetings_db.list_meetings(uid, start_date=start_date, end_date=end_date, limit=limit)
    return [clean_meeting(m) for m in meetings]


@router.get("/v1/mcp/calendar-meetings/{meeting_id}", response_model=McpMeeting, tags=["mcp"])
def get_calendar_meeting_by_id(meeting_id: str, uid: str = Depends(get_uid_from_mcp_api_key)):
    meeting = calendar_meetings_db.get_meeting(uid, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return clean_meeting(meeting)


# ---------------------------------------------------------------------------
# Screen activity — desktop Rewind (app, window title, OCR text)
# ---------------------------------------------------------------------------


@router.get(
    "/v1/mcp/screen-activity",
    tags=["mcp"],
    response_model=Union[List[McpScreenActivityRow], McpScreenActivitySummaryResponse],
)
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
    limit = max(1, min(limit, 200))
    rows = screen_activity_db.get_screen_activity(
        uid, start_date=start_date, end_date=end_date, app_filter=app, limit=limit
    )
    return [clean_screen_activity_row(r) for r in rows]


# ---------------------------------------------------------------------------
# Daily summaries — Omi's per-day digest of the user's life
# ---------------------------------------------------------------------------


@router.get("/v1/mcp/daily-summaries", tags=["mcp"], response_model=List[Dict[str, Any]])
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
