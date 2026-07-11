import uuid
from datetime import datetime, timezone, timedelta

from enum import Enum
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator

import database.folders as folders_db
import database.memories as memories_db
import database.conversations as conversations_db
import database.action_items as action_items_db
import database.goals as goals_db
import database.users as users_db
from database._client import db
from database.vector_db import upsert_memory_vectors_batch

from models.folder import Folder
from models.goal import GoalHistoryEntryResponse, GoalMetric
from utils.client_device import resolve_client_device_from_request
from utils.goals_response import normalize_goal_history_entry
from models.memories import MemoryCategory, Memory, MemoryDB
from models.conversation import (
    Conversation as OmiConversation,
    CreateConversation,
    ExternalIntegrationCreateConversation,
)
from models.conversation_enums import (
    CategoryEnum,
    ConversationSource,
    ConversationStatus,
    ExternalIntegrationConversationSource,
)
from models.geolocation import Geolocation
from models.structured import Structured
from utils.conversations.render import populate_speaker_names, populate_folder_names
from models.transcript_segment import TranscriptSegment
from dependencies import (
    ApiKeyAuth,
    check_conversation_transcript_read_limit,
    get_auth_with_conversation_detail_read,
    get_auth_with_conversations_read,
    get_uid_with_conversations_read,
    get_uid_with_conversations_write,
    get_developer_memory_default_memory_batch_write_context,
    get_developer_memory_default_memory_read_context,
    get_developer_memory_default_memory_write_context,
    get_uid_with_action_items_read,
    get_uid_with_action_items_write,
    get_uid_with_goals_read,
    get_uid_with_goals_write,
)
from utils.apps import update_personas_async
from utils.log_sanitizer import sanitize
from utils.other.endpoints import with_rate_limit, get_current_user_uid
from utils.notifications import send_action_item_data_message, sync_action_item_reminder
from utils.conversations.process_conversation import process_conversation
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations.location import get_google_maps_location, resolve_geolocation
from utils.executors import postprocess_executor
from utils.request_validation import HistoryDays
from utils.llm.memories import identify_category_for_memory
from utils.memory.canonical_memory_adapter import _read_canonical_memory_item, memory_item_to_memorydb
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import MemorySystem
from utils.memory.surface_routing import memorydb_list_with_locked_preview, pin_memory_system
from utils.mcp_memories import collect_filtered_memories
from utils.memory.developer_memory_adapter import (
    search_memory_default_developer_memories,
    search_memory_default_developer_memories_vector,
)
from utils.memory.product_authorization import (
    ProductAuthorizationContext,
    authorize_memory_external_default_memory_read,
    authorize_memory_external_default_memory_write,
)
from utils.memory.default_read_rollout import (
    MemoryReadDecision,
    guard_legacy_memory_write,
    read_default_read_rollout,
)
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
FROM_SEGMENTS_CLAIM_STALE_AFTER = timedelta(minutes=15)

_FROM_SEGMENTS_CONVERSATION_NAMESPACE = uuid.UUID('fb2f1f36-3c84-47a4-9c62-b3f6fdb3fd13')


class DeveloperSuccessResponse(BaseModel):
    success: bool


def _developer_request_ip(request: Request) -> Optional[str]:
    client = getattr(request, 'client', None)
    if not client:
        return None
    return client.host


def _audit_developer_read(
    *,
    request: Optional[Request],
    auth: ApiKeyAuth,
    operation: str,
    status: int,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    include_transcript: Optional[bool] = None,
    returned_count: Optional[int] = None,
    resource_id: Optional[str] = None,
):
    if request is None or not hasattr(request, 'url') or not hasattr(request, 'headers'):
        return
    logger.info(
        "developer_api_read operation=%s path=%s status=%s uid=%s app_id=%s key_id=%s remote_ip=%s "
        "user_agent=%s limit=%s offset=%s include_transcript=%s returned_count=%s resource_id=%s",
        operation,
        request.url.path,
        status,
        auth.uid,
        auth.app_id or 'unknown_app',
        auth.key_id or 'unknown_key',
        _developer_request_ip(request),
        sanitize(request.headers.get('user-agent')),
        limit,
        offset,
        include_transcript,
        returned_count,
        sanitize(resource_id) if resource_id else None,
    )


# ******************************************************
# *********************** MEMORIES *********************
# ******************************************************


def _coerce_required_memory_id(value) -> str:
    if not value and value != 0:
        raise ValueError('id is required')
    return str(value)


def _coerce_optional_memory_datetime(value) -> Optional[datetime]:
    if value in [None, '']:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    return None


class DeveloperMemory(BaseModel):
    model_config = ConfigDict(title='DeveloperMemory')

    id: str
    content: str = ''
    category: MemoryCategory = MemoryCategory.interesting
    visibility: Optional[str] = 'private'
    tags: List[str] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    manually_added: bool = False
    reviewed: bool = False
    user_review: Optional[bool] = None
    edited: bool = False
    scoring: Optional[str] = None

    @field_validator('id', mode='before')
    def coerce_id(cls, value):
        return _coerce_required_memory_id(value)

    @field_validator('content', mode='before')
    def coerce_content(cls, value):
        if value is None:
            return ''
        return str(value)

    @field_validator('category', mode='before')
    def coerce_category(cls, value):
        if isinstance(value, MemoryCategory):
            return value
        try:
            return MemoryCategory(value)
        except (TypeError, ValueError):
            return MemoryCategory.interesting

    @field_validator('visibility', mode='before')
    def coerce_visibility(cls, value):
        return value if value in ['public', 'private'] else 'private'

    @field_validator('tags', mode='before')
    def coerce_tags(cls, value):
        if not isinstance(value, list):
            return []
        return [str(tag) for tag in value if tag is not None]

    @field_validator('created_at', 'updated_at', mode='before')
    def coerce_datetime(cls, value):
        return _coerce_optional_memory_datetime(value)

    @field_validator('manually_added', 'reviewed', 'edited', mode='before')
    def coerce_bool(cls, value):
        if isinstance(value, bool):
            return value
        if value in [None, '']:
            return False
        if isinstance(value, str):
            return value.lower() in ['true', '1', 'yes']
        return bool(value)

    @field_validator('user_review', mode='before')
    def coerce_optional_bool(cls, value):
        if value in [None, '']:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ['true', '1', 'yes']
        return bool(value)

    @field_validator('scoring', mode='before')
    def coerce_scoring(cls, value):
        if value is None:
            return None
        return str(value)


class DeveloperMemoryVectorItem(BaseModel):
    model_config = ConfigDict(extra='allow')

    id: str
    content: str = ''
    category: Optional[str] = None
    relevance_score: Optional[float] = None


class DeveloperMemoryVectorPolicy(BaseModel):
    consumer: str
    app_has_default_memory_grant: bool
    archive_capability: bool
    raw_provenance_capability: bool


class DeveloperMemoryVectorSearchResponse(BaseModel):
    items: List[DeveloperMemoryVectorItem] = Field(default_factory=list)
    returned_count: int
    archive_default_visible: bool
    policy: DeveloperMemoryVectorPolicy


# Backward-compatible name used by unit tests and older docs.
CleanerMemory = DeveloperMemory


class CreateMemoryRequest(BaseModel):
    model_config = ConfigDict(title='CreateMemoryRequest')

    content: str = Field(description="The content of the memory", min_length=1, max_length=500)
    category: Optional[MemoryCategory] = Field(
        default=None, description="Memory category: interesting, system, or manual (auto-categorized if not provided)"
    )
    visibility: str = Field(default='private', description="Visibility: public or private")
    tags: List[str] = Field(default=[], description="Tags associated with the memory")


class UpdateMemoryRequest(BaseModel):
    model_config = ConfigDict(title='UpdateMemoryRequest')

    content: Optional[str] = Field(default=None, description="New content for the memory", min_length=1, max_length=500)
    visibility: Optional[str] = Field(default=None, description="New visibility: public or private")
    tags: Optional[List[str]] = Field(default=None, description="New tags for the memory")
    category: Optional[MemoryCategory] = Field(default=None, description="New category for the memory")


class BatchMemoriesRequest(BaseModel):
    model_config = ConfigDict(title='BatchMemoriesRequest')

    memories: List[CreateMemoryRequest] = Field(description="List of memories to create", max_length=25)


class BatchMemoriesResponse(BaseModel):
    model_config = ConfigDict(title='BatchMemoriesResponse')

    memories: List[DeveloperMemory]
    created_count: int


@router.get(
    "/v1/dev/user/memories",
    tags=["Memories"],
    response_model=List[DeveloperMemory],
    operation_id="listMemories",
)
def get_memories(
    auth_context: ProductAuthorizationContext = Depends(get_developer_memory_default_memory_read_context),
    limit: int = 25,
    offset: int = 0,
    categories: Optional[str] = None,
):
    uid = auth_context.uid
    # Clamp pagination so a negative value cannot reach Firestore (which raises -> HTTP 500) and an
    # oversized limit cannot stream the whole collection. Mirrors the GET /v3/memories hardening.
    offset = max(0, offset)
    limit = max(1, min(limit, 1000))
    category_list = []
    if categories:
        try:
            category_list = [MemoryCategory(c.strip()) for c in categories.split(",") if c.strip()]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid category {str(e)}")

    # Grant check must run before the memory-system branch so a canonical-cohort
    # user holding a legacy/read-only Developer key without a persisted default-read
    # grant is denied, instead of listing canonical memories before authorization.
    app_key_grant = authorize_memory_external_default_memory_read(auth_context, db_client=db)
    if not app_key_grant.allowed:
        raise HTTPException(
            status_code=app_key_grant.status_code,
            detail={
                'enabled': False,
                'reason': app_key_grant.reason,
                'consumer': 'developer_api',
                'archive_default_visible': False,
                'archive_capability': False,
                'app_id': auth_context.app_id,
                'key_id': auth_context.key_id,
            },
        )

    memory_system = pin_memory_system(uid, db_client=db)
    if memory_system == MemorySystem.CANONICAL:
        # Over-fetch raw pages and let collect_filtered_memories apply category
        # filtering during the scan, so categories=manual&limit=25 always returns
        # up to 25 matching rows instead of filtering a single unfiltered page.
        filtered = collect_filtered_memories(
            lambda batch_offset, batch_limit: [
                m.model_dump(mode='json')
                for m in memorydb_list_with_locked_preview(
                    MemoryService(db_client=db).read(uid, limit=batch_limit, offset=batch_offset)
                )
            ],
            limit=limit,
            offset=offset,
            categories=[c.value for c in category_list] if category_list else None,
            sort='scoring_desc',
        )
        memories = filtered['memories']
        return [CleanerMemory.model_validate(memory) for memory in memories]
    memory_rollout = read_default_read_rollout(uid=uid, db_client=db, consumer='developer_api')
    memory_result = search_memory_default_developer_memories(
        uid=uid,
        query='',
        limit=limit,
        offset=offset,
        db_client=db,
        rollout_decision=memory_rollout,
        categories=[c.value for c in category_list],
    )

    if memory_result.read_decision == MemoryReadDecision.USE_MEMORY:
        return [CleanerMemory.model_validate(memory) for memory in memory_result.memories]
    if memory_result.read_decision in {MemoryReadDecision.DENY_MEMORY, MemoryReadDecision.SHADOW_ONLY}:
        raise HTTPException(
            status_code=403,
            detail={
                'enabled': False,
                'reason': memory_result.fallback_reason,
                'consumer': 'developer_api',
                'archive_default_visible': False,
                'archive_capability': False,
            },
        )
    if memory_result.should_use_legacy_fallback:
        pass

    memories = memories_db.get_memories(uid, limit, offset, [c.value for c in category_list])
    # Validate each record individually so a single malformed/legacy doc (e.g. missing a required
    # field or an out-of-enum category) doesn't fail the whole page with a 500. Mirrors the
    # hardening already applied to GET /v3/memories.
    valid_memories = []
    for memory in memories:
        if not isinstance(memory, dict) or not memory.get('id'):
            logger.warning('Skipping malformed memory in Developer API memory list')
            continue
        if memory.get('is_locked', False):
            content = str(memory.get('content') or '')
            memory['content'] = (content[:70] + '...') if len(content) > 70 else content
        try:
            valid_memories.append(DeveloperMemory.model_validate(memory))
        except ValidationError as e:
            missing_fields = [err['loc'][0] for err in e.errors() if err.get('loc')]
            logger.warning(
                f"Skipping invalid memory doc {memory.get('id', 'unknown')} for uid {uid}: "
                f"missing/invalid fields {missing_fields}"
            )
            continue
    return valid_memories


@router.get(
    "/v1/dev/user/memories/vector/search",
    tags=["developer"],
    response_model=DeveloperMemoryVectorSearchResponse,
)
def search_memories_vector(
    auth_context: ProductAuthorizationContext = Depends(get_developer_memory_default_memory_read_context),
    query: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=100),
):
    """Search developer-readable default memory memory through hydrated vector candidates.

    This narrow developer API vector endpoint fails closed unless the authenticated
    Developer API app/key has a verified memories.read scope, a persisted app/key
    default-read grant, and the server-owned rollout state enables developer_api
    memory default-memory reads. Vector hits are hydrated from authoritative
    `users/{uid}/memory_items` before returning results, so stale Short-term and
    Archive remain unavailable by default.
    """

    uid = auth_context.uid

    # Grant check must run before the memory-system branch so a canonical-cohort
    # user holding a legacy/read-only Developer key without a persisted default-read
    # grant is denied, instead of searching canonical memories before authorization.
    app_key_grant = authorize_memory_external_default_memory_read(auth_context, db_client=db)
    if not app_key_grant.allowed:
        raise HTTPException(
            status_code=app_key_grant.status_code,
            detail={
                'enabled': False,
                'reason': app_key_grant.reason,
                'consumer': 'developer_api',
                'archive_default_visible': False,
                'archive_capability': False,
                'app_id': auth_context.app_id,
                'key_id': auth_context.key_id,
            },
        )

    memory_system = pin_memory_system(uid, db_client=db)
    if memory_system == MemorySystem.CANONICAL:
        matches = MemoryService(db_client=db).search(uid, query, limit=min(limit, 20))
        items = []
        for match in matches:
            memory = match.memory
            items.append(
                {
                    'id': memory.id,
                    'content': memory.content,
                    'category': memory.category.value if hasattr(memory.category, 'value') else memory.category,
                    'relevance_score': round(match.score, 4),
                }
            )
        return {
            'items': items,
            'returned_count': len(items),
            'archive_default_visible': False,
            'policy': {
                'consumer': 'developer_api',
                'app_has_default_memory_grant': True,
                'archive_capability': False,
                'raw_provenance_capability': False,
            },
        }

    memory_rollout = read_default_read_rollout(uid=uid, db_client=db, consumer='developer_api')
    memory_result = search_memory_default_developer_memories_vector(
        uid=uid,
        query=query,
        limit=limit,
        db_client=db,
        rollout_decision=memory_rollout,
    )
    if memory_result.read_decision in {MemoryReadDecision.DENY_MEMORY, MemoryReadDecision.SHADOW_ONLY}:
        raise HTTPException(
            status_code=403,
            detail={
                'enabled': False,
                'reason': memory_result.fallback_reason,
                'consumer': 'developer_api',
                'archive_default_visible': False,
                'archive_capability': False,
            },
        )
    if memory_result.should_use_legacy_fallback:
        raise HTTPException(
            status_code=403,
            detail={
                'enabled': False,
                'reason': memory_result.fallback_reason,
                'consumer': 'developer_api',
                'archive_default_visible': False,
                'archive_capability': False,
            },
        )
    return {
        'items': memory_result.memories,
        'returned_count': len(memory_result.memories),
        'archive_default_visible': False,
        'policy': {
            'consumer': 'developer_api',
            'app_has_default_memory_grant': True,
            'archive_capability': False,
            'raw_provenance_capability': False,
        },
    }


@router.post("/v1/dev/user/memories", response_model=DeveloperMemory, tags=["Memories"], operation_id="createMemory")
def create_memory(
    request: CreateMemoryRequest,
    auth_context: ProductAuthorizationContext = Depends(get_developer_memory_default_memory_write_context),
):
    """
    Create a new memory for the authenticated user.

    - **content**: The content of the memory (1-500 characters)
    - **category**: Memory category (auto-categorized if not provided)
    - **visibility**: Visibility: public or private (default: private)
    - **tags**: List of tags associated with the memory
    """
    if not request.content or len(request.content.strip()) == 0:
        raise HTTPException(status_code=422, detail="content cannot be empty")

    # Fail closed: a legacy/read-only Developer key (no persisted memories.write
    # grant) must not mutate canonical memories. The canonical branch skips the
    # legacy write guard inside create_external_memory(), so the grant check must
    # run first for both canonical and legacy paths.
    write_grant = authorize_memory_external_default_memory_write(auth_context, db_client=db)
    if not write_grant.allowed:
        raise HTTPException(
            status_code=write_grant.status_code,
            detail=write_grant.observability,
        )
    uid = auth_context.uid

    category = request.category if request.category else identify_category_for_memory(request.content.strip())

    memory_system = pin_memory_system(uid, db_client=db)
    if memory_system == MemorySystem.CANONICAL:
        memory = Memory(
            content=request.content.strip(),
            category=category,
            visibility=request.visibility,
            tags=request.tags,
        )
        memory_db = MemoryDB.from_memory(memory, uid, None, True)
        memory_db = MemoryService(db_client=db).create_external_memory(
            uid,
            memory_db,
            memory_system=memory_system,
            consumer='developer_api',
            operation='create_memory',
            upsert_vector=False,
            require_canonical_promotion=True,
        )
        if memory.visibility == 'public':
            postprocess_executor.submit(update_personas_async, uid)
        return DeveloperMemory(
            id=memory_db.id,
            content=memory_db.content,
            category=memory_db.category,
            visibility=memory_db.visibility,
            tags=memory_db.tags,
            created_at=memory_db.created_at,
            updated_at=memory_db.updated_at,
            manually_added=memory_db.manually_added,
            scoring=memory_db.scoring,
        )

    memory = Memory(
        content=request.content.strip(),
        category=category,
        visibility=request.visibility,
        tags=request.tags,
    )
    memory_db = MemoryDB.from_memory(memory, uid, None, True)
    memory_db = MemoryService(db_client=db).create_external_memory(
        uid,
        memory_db,
        memory_system=memory_system,
        consumer='developer_api',
        operation='create_memory',
        upsert_vector=False,
        require_canonical_promotion=True,
    )
    if memory.visibility == 'public':
        postprocess_executor.submit(update_personas_async, uid)
    return DeveloperMemory(
        id=memory_db.id,
        content=memory_db.content,
        category=memory_db.category,
        visibility=memory_db.visibility,
        tags=memory_db.tags,
        created_at=memory_db.created_at,
        updated_at=memory_db.updated_at,
        manually_added=memory_db.manually_added,
    )


@router.post(
    "/v1/dev/user/memories/batch",
    response_model=BatchMemoriesResponse,
    tags=["Memories"],
    operation_id="createMemoriesBatch",
)
def create_memories_batch(
    request: BatchMemoriesRequest,
    auth_context: ProductAuthorizationContext = Depends(get_developer_memory_default_memory_batch_write_context),
):
    """
    Create multiple memories in a batch.

    - **memories**: List of memories to create (max 25)
    """
    # Fail closed: a legacy/read-only Developer key (no persisted memories.write
    # grant) must not mutate canonical memories. Gated before any memory
    # construction so rejected requests build no side effects.
    write_grant = authorize_memory_external_default_memory_write(auth_context, db_client=db)
    if not write_grant.allowed:
        raise HTTPException(
            status_code=write_grant.status_code,
            detail=write_grant.observability,
        )
    uid = auth_context.uid

    if not request.memories:
        return BatchMemoriesResponse(memories=[], created_count=0)

    if len(request.memories) > 25:
        raise HTTPException(status_code=422, detail="Maximum 25 memories per batch request")

    memory_dbs = []
    has_public = False

    for mem_req in request.memories:
        if not mem_req.content or len(mem_req.content.strip()) == 0:
            raise HTTPException(status_code=422, detail="All memories must have non-empty content")
        category = mem_req.category if mem_req.category else identify_category_for_memory(mem_req.content.strip())
        memory = Memory(
            content=mem_req.content.strip(),
            category=category,
            visibility=mem_req.visibility,
            tags=mem_req.tags,
        )
        memory_db = MemoryDB.from_memory(memory, uid, None, True)
        memory_dbs.append(memory_db)
        if memory.visibility == 'public':
            has_public = True

    memory_system = pin_memory_system(uid, db_client=db)
    created_dbs = MemoryService(db_client=db).create_external_memory_batch(
        uid,
        memory_dbs,
        memory_system=memory_system,
        consumer='developer_api',
        operation='batch_create_memories',
        upsert_vectors=memory_system != MemorySystem.CANONICAL,
        require_canonical_promotion=True,
    )
    if has_public:
        postprocess_executor.submit(update_personas_async, uid)

    created_memories = [
        DeveloperMemory(
            id=mem.id,
            content=mem.content,
            category=mem.category,
            visibility=mem.visibility,
            tags=mem.tags,
            created_at=mem.created_at,
            updated_at=mem.updated_at,
            manually_added=mem.manually_added,
        )
        for mem in created_dbs
    ]
    return BatchMemoriesResponse(memories=created_memories, created_count=len(created_memories))


@router.delete(
    "/v1/dev/user/memories/{memory_id}",
    tags=["Memories"],
    operation_id="deleteMemory",
    response_model=DeveloperSuccessResponse,
)
def delete_memory(
    memory_id: str,
    auth_context: ProductAuthorizationContext = Depends(get_developer_memory_default_memory_write_context),
):
    """
    Delete a memory by ID.

    - **memory_id**: The ID of the memory to delete
    """
    # Fail closed: a legacy/read-only Developer key (no persisted memories.write
    # grant) must not mutate canonical memories.
    write_grant = authorize_memory_external_default_memory_write(auth_context, db_client=db)
    if not write_grant.allowed:
        raise HTTPException(
            status_code=write_grant.status_code,
            detail=write_grant.observability,
        )
    uid = auth_context.uid

    memory_system = pin_memory_system(uid, db_client=db)
    MemoryService(db_client=db).delete_external_memory(
        uid,
        memory_id,
        memory_system=memory_system,
        consumer='developer_api',
        operation='delete_memory',
        delete_vector=False,
    )
    return {"success": True}


@router.patch(
    "/v1/dev/user/memories/{memory_id}",
    response_model=DeveloperMemory,
    tags=["Memories"],
    operation_id="updateMemory",
)
def update_memory(
    memory_id: str,
    request: UpdateMemoryRequest,
    auth_context: ProductAuthorizationContext = Depends(get_developer_memory_default_memory_write_context),
):
    """
    Update a memory's content, visibility, tags, or category.

    - **memory_id**: The ID of the memory to update
    - **content**: New content for the memory (optional)
    - **visibility**: New visibility: public or private (optional)
    - **tags**: New tags for the memory (optional)
    - **category**: New category for the memory (optional)
    """
    # Fail closed: a legacy/read-only Developer key (no persisted memories.write
    # grant) must not mutate canonical memories.
    write_grant = authorize_memory_external_default_memory_write(auth_context, db_client=db)
    if not write_grant.allowed:
        raise HTTPException(
            status_code=write_grant.status_code,
            detail=write_grant.observability,
        )
    uid = auth_context.uid

    if request.content is None and request.visibility is None and request.tags is None and request.category is None:
        raise HTTPException(
            status_code=422, detail="At least one field (content, visibility, tags, or category) must be provided"
        )

    memory_service = MemoryService(db_client=db)
    memory_system = pin_memory_system(uid, db_client=db)
    if memory_system == MemorySystem.CANONICAL:
        # Validate existence before mutations so a missing memory returns 404
        # (matching legacy) rather than letting the update helpers raise
        # ValueError, which FastAPI surfaces as a 500.
        if _read_canonical_memory_item(uid, memory_id, db_client=db) is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        if request.content is not None and not request.content.strip():
            raise HTTPException(status_code=422, detail="content must not be empty")
        if request.content is not None:
            memory_service.update_content(uid, memory_id, request.content.strip())
        if request.visibility is not None:
            if request.visibility not in ['public', 'private']:
                raise HTTPException(status_code=422, detail="visibility must be 'public' or 'private'")
            memory_service.update_visibility(uid, memory_id, request.visibility)
        if request.tags is not None or request.category is not None:
            memory_service.update_product_fields(
                uid,
                memory_id,
                tags=request.tags,
                category=request.category.value if request.category is not None else None,
            )
        item = _read_canonical_memory_item(uid, memory_id, db_client=db)
        if item is None:
            raise HTTPException(status_code=404, detail="Memory not found")
        return memory_item_to_memorydb(item).model_dump()

    write_guard = guard_legacy_memory_write(uid, db, consumer='developer_api', operation='update_memory')
    if not write_guard.allowed:
        raise HTTPException(status_code=write_guard.status_code, detail=write_guard.detail)

    memory = memories_db.get_memory(uid, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")
    if memory.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this memory.")

    old_visibility = memory.get('visibility')

    if request.content is not None:
        memories_db.edit_memory(uid, memory_id, request.content.strip())

    if request.visibility is not None:
        if request.visibility not in ['public', 'private']:
            raise HTTPException(status_code=422, detail="visibility must be 'public' or 'private'")
        memories_db.change_memory_visibility(uid, memory_id, request.visibility)

    update_data = {}
    if request.tags is not None:
        update_data['tags'] = request.tags
    if request.category is not None:
        update_data['category'] = request.category.value

    if update_data:
        memories_db.update_memory_fields(uid, memory_id, update_data)

    return memories_db.get_memory(uid, memory_id)


# ******************************************************
# ******************* ACTION ITEMS *********************
# ******************************************************


class ActionItemResponse(BaseModel):
    model_config = ConfigDict(title='DeveloperActionItem')

    id: str
    description: str
    completed: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    conversation_id: Optional[str] = None


class CreateActionItemRequest(BaseModel):
    model_config = ConfigDict(title='CreateActionItemRequest')

    description: str = Field(description="The action item description", min_length=1, max_length=500)
    completed: bool = Field(default=False, description="Whether the action item is completed")
    due_at: Optional[datetime] = Field(
        default=None, description="When the action item is due (ISO format with timezone)"
    )


class UpdateActionItemRequest(BaseModel):
    model_config = ConfigDict(title='UpdateActionItemRequest')

    description: Optional[str] = Field(default=None, description="New description", min_length=1, max_length=500)
    completed: Optional[bool] = Field(default=None, description="New completion status")
    due_at: Optional[datetime] = Field(default=None, description="New due date (ISO format with timezone)")


class BatchActionItemsRequest(BaseModel):
    model_config = ConfigDict(title='BatchActionItemsRequest')

    action_items: List[CreateActionItemRequest] = Field(description="List of action items to create", max_length=50)


class BatchActionItemsResponse(BaseModel):
    model_config = ConfigDict(title='BatchActionItemsResponse')

    action_items: List[ActionItemResponse]
    created_count: int


@router.get(
    "/v1/dev/user/action-items",
    tags=["Action Items"],
    response_model=List[ActionItemResponse],
    operation_id="listActionItems",
)
def get_action_items(
    uid: str = Depends(get_uid_with_action_items_read),
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
    # Clamp pagination so a negative value cannot reach Firestore (which raises -> HTTP 500) and an
    # oversized limit cannot stream the whole collection. Mirrors the GET /v3/memories hardening.
    offset = max(0, offset)
    limit = max(1, min(limit, 1000))
    action_items = action_items_db.get_action_items(
        uid=uid,
        conversation_id=conversation_id,
        completed=completed,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
        offset=offset,
    )

    # Validate each record individually so a single malformed/legacy doc (e.g. missing a required
    # field like description/completed) doesn't fail the whole page with a 500. Mirrors the hardening
    # already applied to GET /v1/dev/user/memories.
    valid_action_items = []
    for item in action_items:
        if not isinstance(item, dict) or not item.get('id'):
            logger.warning('Skipping malformed action item in Developer API action-item list')
            continue
        if item.get('is_locked', False):
            continue
        try:
            valid_action_items.append(ActionItemResponse.model_validate(item))
        except ValidationError as e:
            invalid_fields = [err['loc'][0] for err in e.errors() if err.get('loc')]
            logger.warning(
                f"Skipping invalid action item doc {item.get('id', 'unknown')} for uid {uid}: "
                f"missing/invalid fields {invalid_fields}"
            )
            continue
    return valid_action_items


@router.post(
    "/v1/dev/user/action-items",
    response_model=ActionItemResponse,
    tags=["Action Items"],
    operation_id="createActionItem",
)
def create_action_item(
    request: CreateActionItemRequest,
    uid: str = Depends(get_uid_with_action_items_write),
):
    """
    Create a new action item for the authenticated user.

    - **description**: The action item description (1-500 characters)
    - **completed**: Whether the action item is completed (default: False)
    - **due_at**: Optional due date in ISO 8601 format with timezone
    """
    if not request.description or len(request.description.strip()) == 0:
        raise HTTPException(status_code=422, detail="description cannot be empty")

    action_item_data = {
        'description': request.description.strip(),
        'completed': request.completed,
        'due_at': request.due_at,
        'conversation_id': None,
    }

    action_item_id = action_items_db.create_action_item(uid, action_item_data)
    action_item = action_items_db.get_action_item(uid, action_item_id)

    if not action_item:
        raise HTTPException(status_code=500, detail="Failed to create action item")

    # Send FCM data message if action item has a due date
    if request.due_at:
        send_action_item_data_message(
            user_id=uid,
            action_item_id=action_item_id,
            description=request.description.strip(),
            due_at=request.due_at.isoformat(),
        )

    return ActionItemResponse(**action_item)


@router.post(
    "/v1/dev/user/action-items/batch",
    response_model=BatchActionItemsResponse,
    tags=["Action Items"],
    operation_id="createActionItemsBatch",
)
def create_action_items_batch(
    request: BatchActionItemsRequest,
    uid: str = Depends(get_uid_with_action_items_write),
):
    """
    Create multiple action items in a batch.

    - **action_items**: List of action items to create (max 50)
    """
    if not request.action_items:
        return BatchActionItemsResponse(action_items=[], created_count=0)

    if len(request.action_items) > 50:
        raise HTTPException(status_code=422, detail="Maximum 50 action items per batch request")

    # Prepare action items data
    action_items_data = []
    for item in request.action_items:
        if not item.description or len(item.description.strip()) == 0:
            raise HTTPException(status_code=422, detail="All action items must have non-empty descriptions")

        action_item_data = {
            'description': item.description.strip(),
            'completed': item.completed,
            'due_at': item.due_at,
            'conversation_id': None,
        }
        action_items_data.append(action_item_data)

    # Create batch
    created_ids = action_items_db.create_action_items_batch(uid, action_items_data)

    # Fetch all created items in a single batch query
    created_items_list = action_items_db.get_action_items_by_ids(uid, created_ids)

    # Send FCM messages for items with due dates
    for idx, item in enumerate(created_items_list):
        if idx < len(request.action_items) and request.action_items[idx].due_at:
            send_action_item_data_message(
                user_id=uid,
                action_item_id=item['id'],
                description=request.action_items[idx].description.strip(),
                due_at=request.action_items[idx].due_at.isoformat(),
            )

    # Convert to response objects
    created_items = [ActionItemResponse(**item) for item in created_items_list]

    return BatchActionItemsResponse(action_items=created_items, created_count=len(created_items))


@router.delete(
    "/v1/dev/user/action-items/{action_item_id}",
    tags=["Action Items"],
    operation_id="deleteActionItem",
    response_model=DeveloperSuccessResponse,
)
def delete_action_item(
    action_item_id: str,
    uid: str = Depends(get_uid_with_action_items_write),
):
    """
    Delete an action item by ID.

    - **action_item_id**: The ID of the action item to delete
    """
    action_item = action_items_db.get_action_item(uid, action_item_id)
    if not action_item:
        raise HTTPException(status_code=404, detail="Action item not found")
    if action_item.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this action item.")

    action_items_db.delete_action_item(uid, action_item_id)
    return {"success": True}


@router.patch(
    "/v1/dev/user/action-items/{action_item_id}",
    response_model=ActionItemResponse,
    tags=["Action Items"],
    operation_id="updateActionItem",
)
def update_action_item(
    action_item_id: str,
    request: UpdateActionItemRequest,
    uid: str = Depends(get_uid_with_action_items_write),
):
    """
    Update an action item.

    - **action_item_id**: The ID of the action item to update
    - **description**: New description (optional)
    - **completed**: New completion status (optional)
    - **due_at**: New due date (optional, set to null to remove)
    """
    # Check if action item exists
    action_item = action_items_db.get_action_item(uid, action_item_id)
    if not action_item:
        raise HTTPException(status_code=404, detail="Action item not found")
    if action_item.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this action item.")

    # Build update data from non-None fields
    update_data = {}
    if request.description is not None:
        update_data['description'] = request.description.strip()
    if request.completed is not None:
        update_data['completed'] = request.completed
        # Set or clear completed_at based on completion status
        if request.completed:
            update_data['completed_at'] = datetime.now(timezone.utc)
        else:
            update_data['completed_at'] = None
    if request.due_at is not None:
        update_data['due_at'] = request.due_at

    if not update_data:
        raise HTTPException(status_code=422, detail="At least one field must be provided")

    if not action_items_db.update_action_item(uid, action_item_id, update_data):
        raise HTTPException(status_code=500, detail="Failed to update action item")

    # Reconcile the client-scheduled reminder when completion or due date changed, using the final
    # state: cancel if completed or no due date, (re)schedule only for an open task with a due date
    # (#5085).
    if 'completed' in update_data or 'due_at' in update_data:
        description = request.description.strip() if request.description else action_item.get('description', '')
        sync_action_item_reminder(
            user_id=uid,
            action_item_id=action_item_id,
            description=description,
            completed=bool(update_data.get('completed', action_item.get('completed'))),
            due_at=update_data.get('due_at', action_item.get('due_at')),
        )

    return action_items_db.get_action_item(uid, action_item_id)


# ******************************************************
# ******************* CONVERSATIONS ********************
# ******************************************************


class ActionItem(BaseModel):
    model_config = ConfigDict(title='DeveloperConversationActionItem')

    description: str
    completed: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    conversation_id: Optional[str] = None


class Event(BaseModel):
    model_config = ConfigDict(title='DeveloperConversationEvent')

    title: str
    description: str = ''
    start: datetime
    duration: int = 30
    created: bool = False


class SimpleStructured(BaseModel):
    model_config = ConfigDict(title='DeveloperConversationStructured')

    title: str
    overview: str
    emoji: str = '🧠'
    category: CategoryEnum
    action_items: List[ActionItem] = []
    events: List[Event] = []


class SimpleTranscriptSegment(BaseModel):
    model_config = ConfigDict(title='DeveloperTranscriptSegment')

    id: Optional[str] = None
    text: str
    speaker_id: Optional[int] = None
    speaker_name: Optional[str] = None
    start: float
    end: float


class Conversation(BaseModel):
    model_config = ConfigDict(title='DeveloperConversation')

    id: str
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    structured: SimpleStructured
    language: Optional[str] = None
    source: Optional[str] = None
    transcript_segments: Optional[List[SimpleTranscriptSegment]] = None
    geolocation: Optional[Geolocation] = None
    folder_id: Optional[str] = None
    folder_name: Optional[str] = None


class CreateConversationRequest(BaseModel):
    model_config = ConfigDict(title='CreateConversationRequest')

    text: str = Field(description="The conversation text/transcript", min_length=1, max_length=100000)
    text_source: ExternalIntegrationConversationSource = Field(
        default=ExternalIntegrationConversationSource.other,
        description="Source type: audio_transcript, message, or other_text",
    )
    text_source_spec: Optional[str] = Field(
        default=None, description="Additional source specification (e.g., 'email', 'slack', 'whatsapp')"
    )
    started_at: Optional[datetime] = Field(default=None, description="When the conversation started (defaults to now)")
    finished_at: Optional[datetime] = Field(
        default=None, description="When the conversation finished (defaults to started_at + 5 minutes)"
    )
    language: Optional[str] = Field(default='en', description="Language code (ISO 639-1, e.g., 'en', 'es', 'fr')")
    geolocation: Optional[Geolocation] = Field(default=None, description="Geolocation where conversation occurred")


class ConversationResponse(BaseModel):
    model_config = ConfigDict(title='ConversationCreateResponse')

    id: str
    status: str
    discarded: bool


class UpdateConversationRequest(BaseModel):
    model_config = ConfigDict(title='UpdateConversationRequest')

    title: Optional[str] = Field(
        default=None, description="New title for the conversation", min_length=1, max_length=500
    )
    discarded: Optional[bool] = Field(default=None, description="Whether the conversation is discarded")


class DevTranscriptSegment(BaseModel):
    model_config = ConfigDict(title='CreateConversationTranscriptSegment')

    text: str = Field(description="The text spoken in this segment")
    speaker: Optional[str] = Field(
        default='SPEAKER_00', description="Speaker identifier (e.g., 'SPEAKER_00', 'SPEAKER_01')"
    )
    speaker_id: Optional[int] = Field(default=None, description="Numeric speaker ID")
    is_user: bool = Field(default=False, description="Whether this segment is from the user")
    person_id: Optional[str] = Field(default=None, description="ID of person speaking (if known)")
    start: float = Field(description="Start time in seconds (e.g., 0.0, 1.5, 60.2)")
    end: float = Field(description="End time in seconds (e.g., 1.5, 3.0, 65.8)")


class CreateConversationFromTranscriptRequest(BaseModel):
    model_config = ConfigDict(title='CreateConversationFromTranscriptRequest')

    transcript_segments: List[DevTranscriptSegment] = Field(
        description="List of transcript segments with speaker and timing info", min_length=1, max_length=500
    )
    client_session_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices('client_session_id', 'client_conversation_id', 'session_id', 'client_id'),
        min_length=1,
        max_length=200,
        description="Stable client-generated session ID. When provided, retries return the same conversation ID.",
    )
    source: Optional[ConversationSource] = Field(
        default=ConversationSource.phone,
        description="Source of the conversation (e.g., omi, friend, openglass, phone, external_integration)",
    )
    started_at: Optional[datetime] = Field(default=None, description="When conversation started (defaults to now)")
    finished_at: Optional[datetime] = Field(
        default=None, description="When conversation finished (calculated from segments duration if not provided)"
    )
    language: Optional[str] = Field(default='en', description="Language code (ISO 639-1, e.g., 'en', 'es', 'fr')")
    geolocation: Optional[Geolocation] = Field(default=None, description="Geolocation where conversation occurred")
    client_device_id: Optional[str] = Field(default=None, description="Capture device id ({platform}_{hash})")
    client_platform: Optional[str] = Field(default=None, description="Client platform (ios/android/macos)")

    @field_validator('client_session_id')
    @classmethod
    def normalize_client_session_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError('client_session_id cannot be empty')
        return value


class DeveloperFolder(BaseModel):
    model_config = ConfigDict(title='DeveloperFolder')

    id: str
    name: str
    description: Optional[str] = None
    color: str
    icon: str
    created_at: datetime
    updated_at: datetime
    order: int = 0
    is_default: bool = False
    is_system: bool = False
    conversation_count: int = 0


@router.get("/v1/dev/user/folders", response_model=List[DeveloperFolder], tags=["Folders"], operation_id="listFolders")
def get_user_folders(uid: str = Depends(get_uid_with_conversations_read)):
    """
    Get all folders for the authenticated user.

    This endpoint is strictly read-only and returns an empty list if the user has no folders.
    Unlike the internal `/v1/folders` endpoint, it does NOT call `initialize_system_folders`,
    because doing so under a `conversations:read` scope would silently write to Firestore
    (violating the read-only contract) and opens a TOCTOU window where concurrent first
    requests can race past the outer empty-check and create duplicate system folders.

    System folders (Work, Personal, Social) are still initialized lazily through other paths:
    - The mobile app calls the internal `GET /v1/folders` whenever the conversations screen
      is rendered (`app/lib/pages/conversations/conversations_page.dart`), which triggers
      `initialize_system_folders` on first access.
    - The conversation post-processing pipeline calls `initialize_system_folders` whenever
      a new conversation is created (`backend/utils/conversations/process_conversation.py`).

    In practice, any user who can issue a Developer API key has already gone through one of
    those paths, so the empty-list case here only affects users who have never opened the
    conversations tab nor created a single conversation.
    """
    return folders_db.get_folders(uid)


@router.get(
    "/v1/dev/user/conversations",
    response_model=List[Conversation],
    tags=["Conversations"],
    operation_id="listConversations",
)
def get_conversations(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    categories: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
    include_transcript: bool = False,
    folder_id: Optional[str] = Query(default=None, min_length=1),
    starred: Optional[bool] = None,
    uid: ApiKeyAuth = Depends(get_auth_with_conversations_read),
    request: Request = None,
):
    """
    Get conversations with optional transcript inclusion.

    - **include_transcript**: If True, includes full transcript_segments in the response
    - **folder_id**: Filter by folder ID (must be a non-empty string if provided)
    - **starred**: Filter by starred status (true/false)
    """
    auth = uid
    uid = auth.uid
    status = 500
    returned_count = None
    try:
        if include_transcript:
            check_conversation_transcript_read_limit(auth, request=request)

        # Clamp pagination so a negative value cannot reach Firestore (which raises -> HTTP 500) and an
        # oversized limit cannot stream the whole collection. Mirrors the GET /v3/memories hardening.
        offset = max(0, offset)
        limit = max(1, min(limit, 25 if include_transcript else 100))
        try:
            category_list = [CategoryEnum(c.strip()) for c in categories.split(",") if c.strip()] if categories else []
        except ValueError as e:
            status = 400
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
            folder_id=folder_id,
            starred=starred,
        )

        # Filter out locked conversations completely
        unlocked_conversations = [conv for conv in conversations if not conv.get('is_locked', False)]

        # Remove transcript_segments if not requested
        if not include_transcript:
            for conv in unlocked_conversations:
                conv.pop('transcript_segments', None)
        else:
            populate_speaker_names(uid, unlocked_conversations)

        populate_folder_names(uid, unlocked_conversations)

        # Validate each record individually so a single malformed/legacy doc doesn't fail the whole page
        # with a 500. Mirrors the hardening already applied to GET /v1/dev/user/memories.
        valid_conversations = []
        for conv in unlocked_conversations:
            if not isinstance(conv, dict) or not conv.get('id'):
                logger.warning('Skipping malformed conversation in Developer API conversation list')
                continue
            try:
                valid_conversations.append(Conversation.model_validate(conv))
            except ValidationError as e:
                invalid_fields = [err['loc'][0] for err in e.errors() if err.get('loc')]
                logger.warning(
                    f"Skipping invalid conversation doc {conv.get('id', 'unknown')} for uid {uid}: "
                    f"missing/invalid fields {invalid_fields}"
                )
                continue
        status = 200
        returned_count = len(valid_conversations)
        return valid_conversations
    except HTTPException as e:
        status = e.status_code
        returned_count = 0 if returned_count is None else returned_count
        raise
    finally:
        _audit_developer_read(
            request=request,
            auth=auth,
            operation='list_conversations',
            status=status,
            limit=limit,
            offset=offset,
            include_transcript=include_transcript,
            returned_count=returned_count,
        )


@router.post(
    "/v1/dev/user/conversations",
    response_model=ConversationResponse,
    tags=["Conversations"],
    operation_id="createConversation",
)
def create_conversation(
    request: CreateConversationRequest,
    uid: str = Depends(get_uid_with_conversations_write),
):
    """
    Create a new conversation from text for the authenticated user.

    This endpoint processes the provided text through the full conversation pipeline:
    - Generates structured data (title, overview, category, emoji)
    - Extracts action items (with deduplication)
    - Extracts memories (with quality filtering)
    - Determines if conversation should be discarded
    - Triggers app integrations
    - Triggers webhooks

    **Request Parameters:**
    - **text**: The conversation text/transcript (1-100,000 characters)
    - **text_source**: Source type - audio_transcript, message, or other_text (default: other_text)
    - **text_source_spec**: Additional source info (e.g., 'email', 'slack')
    - **started_at**: When conversation started (defaults to now)
    - **finished_at**: When conversation finished (defaults to started_at + 5 minutes)
    - **language**: Language code (default: 'en')
    - **geolocation**: Optional geolocation data

    **Response:**
    - Returns the created conversation ID and status
    - Use GET /v1/dev/user/conversations/{id} to retrieve full details
    """
    if not request.text or len(request.text.strip()) == 0:
        raise HTTPException(status_code=422, detail="text cannot be empty")

    if len(request.text) > 100000:
        raise HTTPException(status_code=422, detail="text cannot exceed 100,000 characters")

    # Set default timestamps
    started_at = request.started_at if request.started_at is not None else datetime.now(timezone.utc)
    finished_at = request.finished_at if request.finished_at is not None else started_at + timedelta(seconds=300)

    # Validate finished_at is after started_at
    if finished_at < started_at:
        raise HTTPException(status_code=422, detail="finished_at must be after started_at")

    # Process geolocation if provided (keeps the raw coordinates when the geocode lookup misses)
    geolocation = resolve_geolocation(request.geolocation)

    # Language defaults
    language_code = request.language or 'en'

    # Create conversation object
    create_conversation_obj = ExternalIntegrationCreateConversation(
        text=request.text.strip(),
        text_source=request.text_source,
        text_source_spec=request.text_source_spec,
        started_at=started_at,
        finished_at=finished_at,
        language=language_code,
        geolocation=geolocation,
        source=ConversationSource.external_integration,
        app_id=None,  # Not from a specific app, from developer API
    )

    # Process conversation
    conversation = process_conversation(uid, language_code, create_conversation_obj)

    return ConversationResponse(
        id=conversation.id,
        status=conversation.status.value if conversation.status else 'completed',
        discarded=conversation.discarded,
    )


@router.get(
    "/v1/dev/user/conversations/{conversation_id}",
    response_model=Conversation,
    tags=["Conversations"],
    operation_id="getConversation",
)
def get_conversation_endpoint(
    conversation_id: str,
    include_transcript: bool = False,
    uid: ApiKeyAuth = Depends(get_auth_with_conversation_detail_read),
    request: Request = None,
):
    """
    Get a single conversation by ID.

    - **conversation_id**: The ID of the conversation to retrieve
    - **include_transcript**: If True, includes full transcript_segments in the response
    """
    auth = uid
    uid = auth.uid
    status = 500
    returned_count = None
    try:
        if include_transcript:
            check_conversation_transcript_read_limit(auth, request=request)

        conversation = conversations_db.get_conversation(uid, conversation_id)
        if not conversation:
            status = 404
            returned_count = 0
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Filter out locked conversations
        if conversation.get('is_locked', False):
            status = 404
            returned_count = 0
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Remove transcript_segments if not requested
        if not include_transcript:
            conversation.pop('transcript_segments', None)
        else:
            populate_speaker_names(uid, [conversation])

        populate_folder_names(uid, [conversation])

        status = 200
        returned_count = 1
        return conversation
    except HTTPException as e:
        status = e.status_code
        returned_count = 0 if returned_count is None else returned_count
        raise
    finally:
        _audit_developer_read(
            request=request,
            auth=auth,
            operation='get_conversation',
            status=status,
            include_transcript=include_transcript,
            returned_count=returned_count,
            resource_id=conversation_id,
        )


def _from_segments_conversation_id(uid: str, client_session_id: str) -> str:
    return str(uuid.uuid5(_FROM_SEGMENTS_CONVERSATION_NAMESPACE, f'{uid}\0{client_session_id}'))


def _is_stale_from_segments_claim(conversation: dict, client_session_id: str, now: datetime) -> bool:
    external_data = conversation.get('external_data') or {}
    if external_data.get('from_segments_client_session_id') != client_session_id:
        return False
    if conversation.get('status') != ConversationStatus.processing.value:
        return False
    claimed_at = external_data.get('from_segments_claimed_at')
    if not isinstance(claimed_at, datetime):
        return False
    if claimed_at.tzinfo is None:
        claimed_at = claimed_at.replace(tzinfo=timezone.utc)
    return now - claimed_at > FROM_SEGMENTS_CLAIM_STALE_AFTER


def _conversation_response_from_data(conversation: dict) -> ConversationResponse:
    status = conversation.get('status') or 'completed'
    if hasattr(status, 'value'):
        status = status.value
    return ConversationResponse(
        id=conversation['id'],
        status=status,
        discarded=bool(conversation.get('discarded', False)),
    )


def _create_conversation_from_segments(
    uid: str,
    request: CreateConversationFromTranscriptRequest,
    *,
    client_device_id: Optional[str] = None,
    client_platform: Optional[str] = None,
) -> ConversationResponse:
    """Shared impl: validate already-transcribed segments, build a CreateConversation, run the full
    processing pipeline (title, memories, action items, sync), and return the result. Used by both
    the developer-API-key endpoint and the Firebase-authed user endpoint (on-device transcription)."""
    if not request.transcript_segments or len(request.transcript_segments) == 0:
        raise HTTPException(status_code=422, detail="transcript_segments cannot be empty")

    if len(request.transcript_segments) > 500:
        raise HTTPException(status_code=422, detail="Maximum 500 transcript segments allowed")

    # Validate segments
    for idx, segment in enumerate(request.transcript_segments):
        if segment.end <= segment.start:
            raise HTTPException(status_code=422, detail=f"Segment {idx}: end time must be after start time")
        if segment.start < 0:
            raise HTTPException(status_code=422, detail=f"Segment {idx}: start time cannot be negative")
        if not segment.text or len(segment.text.strip()) == 0:
            raise HTTPException(status_code=422, detail=f"Segment {idx}: text cannot be empty")

    # Convert DevTranscriptSegment to TranscriptSegment
    transcript_segments = []
    for seg in request.transcript_segments:
        transcript_segments.append(
            TranscriptSegment(
                text=seg.text.strip(),
                speaker=seg.speaker or 'SPEAKER_00',
                speaker_id=seg.speaker_id,
                is_user=seg.is_user,
                person_id=seg.person_id,
                start=seg.start,
                end=seg.end,
            )
        )

    # Calculate started_at and finished_at
    # started_at defaults to now
    started_at = request.started_at if request.started_at is not None else datetime.now(timezone.utc)

    # finished_at: if not provided, calculate from last segment's end time
    if request.finished_at is not None:
        finished_at = request.finished_at
    else:
        # Calculate total duration from segments
        last_segment = request.transcript_segments[-1]
        total_duration_seconds = last_segment.end
        finished_at = started_at + timedelta(seconds=total_duration_seconds)

    # Validate finished_at is after started_at
    if finished_at <= started_at:
        raise HTTPException(status_code=422, detail="finished_at must be after started_at")

    # Process geolocation if provided (keeps the raw coordinates when the geocode lookup misses)
    geolocation = resolve_geolocation(request.geolocation)

    # Language defaults
    language_code = request.language or 'en'

    # Segment uploads are transcript-shaped; default to phone so process_conversation uses
    # the transcript path (CreateConversation has no text_source field).
    source = request.source or ConversationSource.phone

    conversation_id = None
    if request.client_session_id:
        conversation_id = _from_segments_conversation_id(uid, request.client_session_id)
        existing_conversation = conversations_db.get_conversation(uid, conversation_id)
        if existing_conversation:
            if _is_stale_from_segments_claim(
                existing_conversation, request.client_session_id, datetime.now(timezone.utc)
            ):
                logger.warning(
                    "from-segments idempotency stale claim for uid=%s client_session_id=%s conversation_id=%s; retrying",
                    uid,
                    request.client_session_id,
                    conversation_id,
                )
                conversations_db.delete_conversation(uid, conversation_id)
            else:
                logger.info(
                    "from-segments idempotency hit for uid=%s client_session_id=%s conversation_id=%s",
                    uid,
                    request.client_session_id,
                    conversation_id,
                )
                return _conversation_response_from_data(existing_conversation)

    resolved_client_device_id = client_device_id or request.client_device_id
    resolved_client_platform = client_platform or request.client_platform

    # Create conversation object with transcript segments
    if conversation_id:
        create_conversation_obj = OmiConversation(
            id=conversation_id,
            created_at=started_at,
            transcript_segments=transcript_segments,
            started_at=started_at,
            finished_at=finished_at,
            language=language_code,
            geolocation=geolocation,
            source=source,
            client_device_id=resolved_client_device_id,
            client_platform=resolved_client_platform,
            structured=Structured(),
            external_data={
                'from_segments_client_session_id': request.client_session_id,
                'from_segments_claimed_at': datetime.now(timezone.utc),
            },
            status=ConversationStatus.processing,
        )
        if not lifecycle_service.create_processing_conversation(
            uid, create_conversation_obj.model_dump(), idempotent=True
        ):
            existing_conversation = conversations_db.get_conversation(uid, conversation_id)
            if existing_conversation:
                logger.info(
                    "from-segments idempotency concurrent hit for uid=%s client_session_id=%s conversation_id=%s",
                    uid,
                    request.client_session_id,
                    conversation_id,
                )
                return _conversation_response_from_data(existing_conversation)
            raise HTTPException(status_code=409, detail="Conversation creation already in progress")
    else:
        create_conversation_obj = CreateConversation(
            transcript_segments=transcript_segments,
            started_at=started_at,
            finished_at=finished_at,
            language=language_code,
            geolocation=geolocation,
            source=source,
            client_device_id=resolved_client_device_id,
            client_platform=resolved_client_platform,
        )

    # Process conversation
    try:
        conversation = process_conversation(uid, language_code, create_conversation_obj)
    except Exception:
        if request.client_session_id and conversation_id:
            conversations_db.delete_conversation(uid, conversation_id)
        raise
    if request.client_session_id:
        logger.info(
            "from-segments idempotency persisted returned conversation uid=%s client_session_id=%s conversation_id=%s",
            uid,
            request.client_session_id,
            conversation.id,
        )
        lifecycle_service.persist_processed_conversation(uid, conversation.model_dump())

    return ConversationResponse(
        id=conversation.id,
        status=conversation.status.value if conversation.status else 'completed',
        discarded=conversation.discarded,
    )


@router.post("/v1/conversations/from-segments", response_model=ConversationResponse, tags=["conversations"])
def create_conversation_from_segments_user(
    request: CreateConversationFromTranscriptRequest,
    http_request: Request,
    uid: str = Depends(with_rate_limit(get_current_user_uid, "conversations:from-segments")),
):
    """Create a conversation from already-transcribed segments (Firebase-authed).

    Used by clients that transcribe ON-DEVICE (e.g. the macOS desktop app with Parakeet) and need
    the conversation persisted, processed (memories/summaries), and synced across devices — exactly
    like a cloud-transcribed conversation, but without the live `/v4/listen` websocket."""
    device_ctx = resolve_client_device_from_request(http_request)
    return _create_conversation_from_segments(
        uid,
        request,
        client_device_id=device_ctx.client_device_id,
        client_platform=device_ctx.platform,
    )


@router.post(
    "/v1/dev/user/conversations/from-segments",
    response_model=ConversationResponse,
    tags=["Conversations"],
    operation_id="createConversationFromSegments",
)
def create_conversation_from_segments(
    request: CreateConversationFromTranscriptRequest,
    http_request: Request,
    uid: str = Depends(get_uid_with_conversations_write),
):
    """
    Create a new conversation from structured transcript segments.

    This endpoint is for advanced integrations that have speaker diarization and timing information.
    It processes the transcript segments through the full conversation pipeline.

    **Transcript Segments:**
    - **text**: The text spoken (required)
    - **speaker**: Speaker identifier like 'SPEAKER_00', 'SPEAKER_01' (default: 'SPEAKER_00')
    - **speaker_id**: Numeric speaker ID (auto-calculated from speaker if not provided)
    - **is_user**: Whether this segment is from the user (default: False)
    - **person_id**: ID of known person speaking (optional)
    - **start**: Start time in seconds, e.g., 0.0, 1.5, 60.2 (required)
    - **end**: End time in seconds, e.g., 1.5, 3.0, 65.8 (required)

    **Other Parameters:**
    - **source**: Source of conversation (default: external_integration). Options:
      - omi, friend, openglass, phone, desktop, apple_watch, bee, plaud, frame, etc.
    - **started_at**: When conversation started (defaults to now)
    - **finished_at**: When conversation finished (calculated from last segment if not provided)
    - **language**: Language code (default: 'en')
    - **geolocation**: Optional geolocation data

    **Example:**
    ```json
    {
      "transcript_segments": [
        {
          "text": "Hey, how are you doing?",
          "speaker": "SPEAKER_00",
          "is_user": true,
          "start": 0.0,
          "end": 2.5
        },
        {
          "text": "I'm doing great, thanks!",
          "speaker": "SPEAKER_01",
          "is_user": false,
          "start": 2.8,
          "end": 5.2
        }
      ],
      "source": "phone",
      "language": "en"
    }
    ```
    """
    device_ctx = resolve_client_device_from_request(http_request)
    return _create_conversation_from_segments(
        uid,
        request,
        client_device_id=device_ctx.client_device_id,
        client_platform=device_ctx.platform,
    )


@router.delete(
    "/v1/dev/user/conversations/{conversation_id}",
    tags=["Conversations"],
    operation_id="deleteConversation",
    response_model=DeveloperSuccessResponse,
)
def delete_conversation_endpoint(
    conversation_id: str,
    uid: str = Depends(get_uid_with_conversations_write),
):
    """
    Delete a conversation by ID.

    This also deletes any associated photos in the conversation's subcollection.

    - **conversation_id**: The ID of the conversation to delete
    """
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this conversation.")

    conversations_db.delete_conversation(uid, conversation_id)
    return {"success": True}


@router.patch(
    "/v1/dev/user/conversations/{conversation_id}",
    response_model=Conversation,
    tags=["Conversations"],
    operation_id="updateConversation",
)
def update_conversation_endpoint(
    conversation_id: str,
    request: UpdateConversationRequest,
    uid: str = Depends(get_uid_with_conversations_write),
):
    """
    Update a conversation's title or discard status.

    - **conversation_id**: The ID of the conversation to update
    - **title**: New title for the conversation (optional)
    - **discarded**: Whether the conversation is discarded (optional)
    """
    conversation = conversations_db.get_conversation(uid, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation.get('is_locked', False):
        raise HTTPException(status_code=402, detail="A paid plan is required to access this conversation.")

    if request.title is None and request.discarded is None:
        raise HTTPException(status_code=422, detail="At least one field (title or discarded) must be provided")

    if request.title is not None:
        conversations_db.update_conversation_title(uid, conversation_id, request.title.strip())

    if request.discarded is not None:
        if request.discarded:
            lifecycle_service.discard(uid, conversation_id)
        else:
            lifecycle_service.restore_discarded(uid, conversation_id)

    conversation = conversations_db.get_conversation(uid, conversation_id)
    if conversation:
        populate_folder_names(uid, [conversation])
    return conversation


# ******************************************************
# *********************** GOALS ************************
# ******************************************************


class GoalType(str, Enum):
    boolean = "boolean"
    scale = "scale"
    numeric = "numeric"


class GoalResponse(BaseModel):
    model_config = ConfigDict(title='DeveloperGoal')

    id: str
    goal_id: str
    title: str
    desired_outcome: str
    why_it_matters: Optional[str] = None
    success_criteria: List[str] = Field(default_factory=list)
    horizon_at: Optional[datetime] = None
    status: str
    focus_rank: Optional[int] = None
    metric: Optional[GoalMetric] = None
    source: str
    goal_type: str
    target_value: float
    current_value: float
    min_value: float
    max_value: float
    unit: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CreateGoalRequest(BaseModel):
    model_config = ConfigDict(title='CreateGoalRequest')

    title: str = Field(description="The goal title/description", min_length=1, max_length=500)
    desired_outcome: Optional[str] = Field(default=None, max_length=2000)
    why_it_matters: Optional[str] = Field(default=None, max_length=2000)
    success_criteria: List[str] = Field(default_factory=list, max_length=20)
    horizon_at: Optional[datetime] = None
    goal_type: Optional[GoalType] = Field(default=None, description="Optional metric type")
    target_value: Optional[float] = Field(default=None, description="Optional target value")
    current_value: Optional[float] = Field(default=None, description="Optional current progress")
    min_value: Optional[float] = Field(default=None, description="Optional minimum scale value")
    max_value: Optional[float] = Field(default=None, description="Optional maximum scale value")
    unit: Optional[str] = Field(default=None, description="Unit label (e.g., 'users', 'points')")


class UpdateGoalRequest(BaseModel):
    model_config = ConfigDict(title='UpdateGoalRequest')

    title: Optional[str] = Field(default=None, description="New title", min_length=1, max_length=500)
    desired_outcome: Optional[str] = Field(default=None, max_length=2000)
    why_it_matters: Optional[str] = Field(default=None, max_length=2000)
    success_criteria: Optional[List[str]] = Field(default=None, max_length=20)
    horizon_at: Optional[datetime] = None
    target_value: Optional[float] = Field(default=None, description="New target value")
    current_value: Optional[float] = Field(default=None, description="New progress value")
    min_value: Optional[float] = Field(default=None, description="New minimum value")
    max_value: Optional[float] = Field(default=None, description="New maximum value")
    unit: Optional[str] = Field(default=None, description="New unit label")

    @field_validator('title', 'desired_outcome')
    @classmethod
    def required_text_cannot_be_null_or_blank(cls, value: Optional[str]) -> str:
        if value is None or not value.strip():
            raise ValueError('required goal text cannot be null or blank')
        return value.strip()

    @field_validator('success_criteria')
    @classmethod
    def success_criteria_cannot_be_null(cls, value: Optional[List[str]]) -> List[str]:
        if value is None:
            raise ValueError('success_criteria cannot be null; use an empty list to clear it')
        return value

    @field_validator('target_value', 'current_value')
    @classmethod
    def required_metric_values_cannot_be_null(cls, value: Optional[float]) -> float:
        if value is None:
            raise ValueError('metric value cannot be null')
        return value


def _serialize_goal_datetimes(goal: dict) -> dict:
    """Convert datetime objects to ISO strings for JSON serialization."""
    if 'created_at' in goal and hasattr(goal['created_at'], 'isoformat'):
        goal['created_at'] = goal['created_at'].isoformat()
    if 'updated_at' in goal and hasattr(goal['updated_at'], 'isoformat'):
        goal['updated_at'] = goal['updated_at'].isoformat()
    return goal


@router.get("/v1/dev/user/goals", tags=["Goals"], response_model=List[GoalResponse], operation_id="listGoals")
def get_goals(
    uid: str = Depends(get_uid_with_goals_read),
    limit: int = 10,
    include_inactive: bool = False,
):
    """
    Get user goals.

    - **limit**: Maximum number of goals to return
    - **include_inactive**: If True, includes inactive/completed goals
    """
    # Clamp pagination so a negative value cannot reach Firestore (which raises -> HTTP 500) and an
    # oversized limit cannot stream the whole collection. Mirrors the GET /v3/memories hardening.
    limit = max(1, min(limit, 1000))
    if include_inactive:
        goals = goals_db.get_all_goals(uid, include_inactive=True)
    else:
        goals = goals_db.get_user_goals(uid, limit=limit)

    return [_serialize_goal_datetimes(g) for g in goals]


@router.get("/v1/dev/user/goals/{goal_id}", tags=["Goals"], response_model=GoalResponse, operation_id="getGoal")
def get_goal(
    goal_id: str,
    uid: str = Depends(get_uid_with_goals_read),
):
    """
    Get a single goal by ID.

    - **goal_id**: The ID of the goal to retrieve
    """
    goals = goals_db.get_all_goals(uid, include_inactive=True)
    goal = next((g for g in goals if g.get('id') == goal_id), None)

    if not goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    return _serialize_goal_datetimes(goal)


@router.post("/v1/dev/user/goals", tags=["Goals"], response_model=GoalResponse, operation_id="createGoal")
def create_goal(
    request: CreateGoalRequest,
    uid: str = Depends(get_uid_with_goals_write),
):
    """
    Create a durable goal. Metrics are optional and other goals are never changed implicitly.

    - **title**: The goal title/description (1-500 characters)
    - **goal_type**: Optional metric type: boolean, scale, or numeric
    - **target_value**: Optional target value
    - **current_value**: Optional current progress
    - **min_value**: Optional minimum scale value
    - **max_value**: Optional maximum scale value
    - **unit**: Optional unit label (e.g., 'users', 'points')

    Omit all metric fields to create a qualitative goal.
    """
    if not request.title or len(request.title.strip()) == 0:
        raise HTTPException(status_code=422, detail="title cannot be empty")

    goal_data = {
        'id': f"goal_{uuid.uuid4().hex[:12]}",
        'title': request.title.strip(),
        'desired_outcome': request.desired_outcome or request.title.strip(),
        'why_it_matters': request.why_it_matters,
        'success_criteria': request.success_criteria,
        'horizon_at': request.horizon_at,
        'goal_type': request.goal_type.value if request.goal_type is not None else None,
        'target_value': request.target_value,
        'current_value': request.current_value,
        'min_value': request.min_value,
        'max_value': request.max_value,
        'unit': request.unit,
    }

    created_goal = goals_db.create_goal(uid, goal_data)
    return _serialize_goal_datetimes(created_goal)


@router.patch("/v1/dev/user/goals/{goal_id}", tags=["Goals"], response_model=GoalResponse, operation_id="updateGoal")
def update_goal(
    goal_id: str,
    request: UpdateGoalRequest,
    uid: str = Depends(get_uid_with_goals_write),
):
    """
    Update a goal.

    - **goal_id**: The ID of the goal to update
    - **title**: New title (optional)
    - **target_value**: New target value (optional)
    - **current_value**: New progress value (optional)
    - **min_value**: New minimum value (optional)
    - **max_value**: New maximum value (optional)
    - **unit**: New unit label (optional)
    """
    update_data = request.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=422, detail="At least one field must be provided")

    if 'title' in update_data and update_data['title']:
        update_data['title'] = update_data['title'].strip()

    updated_goal = goals_db.update_goal(uid, goal_id, update_data)

    if not updated_goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    return _serialize_goal_datetimes(updated_goal)


@router.patch(
    "/v1/dev/user/goals/{goal_id}/progress",
    tags=["Goals"],
    response_model=GoalResponse,
    operation_id="updateGoalProgress",
)
def update_goal_progress(
    goal_id: str,
    current_value: float = Query(..., description="New progress value"),
    uid: str = Depends(get_uid_with_goals_write),
):
    """
    Update the progress value of a goal.

    - **goal_id**: The ID of the goal to update
    - **current_value**: New progress value (query parameter)
    """
    updated_goal = goals_db.update_goal_progress(uid, goal_id, current_value)

    if not updated_goal:
        raise HTTPException(status_code=404, detail="Goal not found")

    return _serialize_goal_datetimes(updated_goal)


@router.get(
    "/v1/dev/user/goals/{goal_id}/history",
    tags=["Goals"],
    operation_id="listGoalHistory",
    response_model=List[GoalHistoryEntryResponse],
)
def get_goal_history(
    goal_id: str,
    days: HistoryDays = 30,
    uid: str = Depends(get_uid_with_goals_read),
) -> List[dict]:
    """
    Get progress history for a goal.

    - **goal_id**: The ID of the goal
    - **days**: Number of days of history to return (max 365, default 30)
    """
    history = goals_db.get_goal_history(uid, goal_id, days)
    return [normalize_goal_history_entry(entry) for entry in history]


@router.delete(
    "/v1/dev/user/goals/{goal_id}",
    tags=["Goals"],
    operation_id="deleteGoal",
    response_model=DeveloperSuccessResponse,
)
def delete_goal(
    goal_id: str,
    uid: str = Depends(get_uid_with_goals_write),
):
    """
    Delete a goal by ID.

    - **goal_id**: The ID of the goal to delete
    """
    if not goals_db.delete_goal(uid, goal_id):
        raise HTTPException(status_code=404, detail="Goal not found")
    return {"success": True}
