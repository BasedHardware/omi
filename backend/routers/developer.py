import threading
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

import database.memories as memories_db
import database.conversations as conversations_db
import database.dev_api_key as dev_api_key_db
import database.action_items as action_items_db

from models.memories import MemoryCategory, Memory, MemoryDB
from models.conversation import (
    CategoryEnum,
    ExternalIntegrationCreateConversation,
    ExternalIntegrationConversationSource,
    Geolocation,
    ConversationSource,
    CreateConversation,
)
from models.conversation import Conversation as ConversationModel
from models.transcript_segment import TranscriptSegment
from dependencies import (
    get_uid_from_dev_api_key,
    get_current_user_id,
    get_uid_with_conversations_read,
    get_uid_with_conversations_write,
    get_uid_with_memories_read,
    get_uid_with_memories_write,
    get_uid_with_action_items_read,
    get_uid_with_action_items_write,
)
from models.dev_api_key import DevApiKey, DevApiKeyCreate, DevApiKeyCreated
from utils.scopes import AVAILABLE_SCOPES, validate_scopes
from utils.llm.memories import identify_category_for_memory
from utils.apps import update_personas_async
from utils.notifications import send_action_item_data_message
from utils.conversations.process_conversation import process_conversation
from utils.conversations.location import get_google_maps_location

router = APIRouter()


# ******************************************************
# ****************** API KEY MANAGEMENT ****************
# ******************************************************


@router.get("/v1/dev/keys", response_model=List[DevApiKey], tags=["developer"])
def get_keys(uid: str = Depends(get_current_user_id)):
    return dev_api_key_db.get_dev_keys_for_user(uid)


@router.post("/v1/dev/keys", response_model=DevApiKeyCreated, tags=["developer"])
def create_key(key_data: DevApiKeyCreate, uid: str = Depends(get_current_user_id)):
    """
    Create a new Developer API key with optional scopes.

    - **name**: Descriptive name for the key
    - **scopes**: Optional list of scopes. If not provided, defaults to read-only access.
      Available scopes:
      - conversations:read
      - conversations:write
      - memories:read
      - memories:write
      - action_items:read
      - action_items:write
    """
    if not key_data.name or len(key_data.name.strip()) == 0:
        raise HTTPException(status_code=422, detail="Key name cannot be empty")

    # Validate scopes if provided
    if key_data.scopes is not None:
        if not validate_scopes(key_data.scopes):
            raise HTTPException(status_code=400, detail=f"Invalid scopes. Available: {AVAILABLE_SCOPES}")

    raw_key, api_key_data = dev_api_key_db.create_dev_key(uid, key_data.name.strip(), scopes=key_data.scopes)
    return DevApiKeyCreated(**api_key_data.model_dump(), key=raw_key)


@router.delete("/v1/dev/keys/{key_id}", status_code=204, tags=["developer"])
def delete_key(key_id: str, uid: str = Depends(get_current_user_id)):
    dev_api_key_db.delete_dev_key(uid, key_id)
    return


# ******************************************************
# *********************** MEMORIES *********************
# ******************************************************


class CleanerMemory(BaseModel):
    # Core fields (aligned with MemoryResponse)
    id: str
    content: str
    category: MemoryCategory
    visibility: Optional[str] = 'private'
    tags: List[str] = []
    created_at: datetime
    updated_at: datetime
    manually_added: bool
    scoring: Optional[str] = None
    reviewed: bool
    user_review: Optional[bool] = None
    edited: bool


class CreateMemoryRequest(BaseModel):
    content: str = Field(description="The content of the memory", min_length=1, max_length=500)
    category: Optional[MemoryCategory] = Field(
        default=None, description="Memory category: interesting, system, or manual (auto-categorized if not provided)"
    )
    visibility: str = Field(default='private', description="Visibility: public or private")
    tags: List[str] = Field(default=[], description="Tags associated with the memory")


class MemoryResponse(BaseModel):
    id: str
    content: str
    category: MemoryCategory
    visibility: str
    tags: List[str]
    created_at: datetime
    updated_at: datetime
    manually_added: bool
    scoring: str


class BatchMemoriesRequest(BaseModel):
    memories: List[CreateMemoryRequest] = Field(description="List of memories to create", max_length=25)


class BatchMemoriesResponse(BaseModel):
    memories: List[MemoryResponse]
    created_count: int


@router.get("/v1/dev/user/memories", tags=["developer"], response_model=List[CleanerMemory])
def get_memories(
    uid: str = Depends(get_uid_with_memories_read),
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


@router.post("/v1/dev/user/memories", response_model=MemoryResponse, tags=["developer"])
def create_memory(
    request: CreateMemoryRequest,
    uid: str = Depends(get_uid_with_memories_write),
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

    # Create Memory object
    memory = Memory(
        content=request.content.strip(),
        category=request.category if request.category else MemoryCategory.manual,
        visibility=request.visibility,
        tags=request.tags,
    )

    # Auto-categorize if category not manually set
    if request.category is None:
        categories = [MemoryCategory.interesting.value, MemoryCategory.system.value]
        category_str = identify_category_for_memory(memory.content, categories)
        memory.category = MemoryCategory(category_str)

    # Convert to MemoryDB object
    memory_db = MemoryDB.from_memory(memory, uid, None, True)

    # Save to database
    memories_db.create_memory(uid, memory_db.dict())

    # Update personas asynchronously if visibility is public
    if memory.visibility == 'public':
        threading.Thread(target=update_personas_async, args=(uid,)).start()

    return MemoryResponse(
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


@router.post("/v1/dev/user/memories/batch", response_model=BatchMemoriesResponse, tags=["developer"])
def create_memories_batch(
    request: BatchMemoriesRequest,
    uid: str = Depends(get_uid_with_memories_write),
):
    """
    Create multiple memories in a batch.

    - **memories**: List of memories to create (max 25)
    """
    if not request.memories:
        return BatchMemoriesResponse(memories=[], created_count=0)

    if len(request.memories) > 25:
        raise HTTPException(status_code=422, detail="Maximum 25 memories per batch request")

    # Prepare memories
    memory_dbs = []
    has_public = False

    for mem_req in request.memories:
        if not mem_req.content or len(mem_req.content.strip()) == 0:
            raise HTTPException(status_code=422, detail="All memories must have non-empty content")

        # Create Memory object
        memory = Memory(
            content=mem_req.content.strip(),
            category=mem_req.category if mem_req.category else MemoryCategory.manual,
            visibility=mem_req.visibility,
            tags=mem_req.tags,
        )

        # Auto-categorize if category not manually set
        if mem_req.category is None:
            categories = [MemoryCategory.interesting.value, MemoryCategory.system.value]
            category_str = identify_category_for_memory(memory.content, categories)
            memory.category = MemoryCategory(category_str)

        # Convert to MemoryDB object
        memory_db = MemoryDB.from_memory(memory, uid, None, True)
        memory_dbs.append(memory_db)

        if memory.visibility == 'public':
            has_public = True

    # Save all memories to database
    memories_db.save_memories(uid, [mem.dict() for mem in memory_dbs])

    # Update personas if any memory is public
    if has_public:
        threading.Thread(target=update_personas_async, args=(uid,)).start()

    # Prepare response
    created_memories = [
        MemoryResponse(
            id=mem.id,
            content=mem.content,
            category=mem.category,
            visibility=mem.visibility,
            tags=mem.tags,
            created_at=mem.created_at,
            updated_at=mem.updated_at,
            manually_added=mem.manually_added,
            scoring=mem.scoring,
        )
        for mem in memory_dbs
    ]

    return BatchMemoriesResponse(memories=created_memories, created_count=len(created_memories))


# ******************************************************
# ******************* ACTION ITEMS *********************
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


class CreateActionItemRequest(BaseModel):
    description: str = Field(description="The action item description", min_length=1, max_length=500)
    completed: bool = Field(default=False, description="Whether the action item is completed")
    due_at: Optional[datetime] = Field(
        default=None, description="When the action item is due (ISO format with timezone)"
    )


class BatchActionItemsRequest(BaseModel):
    action_items: List[CreateActionItemRequest] = Field(description="List of action items to create", max_length=50)


class BatchActionItemsResponse(BaseModel):
    action_items: List[ActionItemResponse]
    created_count: int


@router.get("/v1/dev/user/action-items", tags=["developer"], response_model=List[ActionItemResponse])
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


@router.post("/v1/dev/user/action-items", response_model=ActionItemResponse, tags=["developer"])
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


@router.post("/v1/dev/user/action-items/batch", response_model=BatchActionItemsResponse, tags=["developer"])
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


# ******************************************************
# ******************* CONVERSATIONS ********************
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


class CreateConversationRequest(BaseModel):
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
    id: str
    status: str
    discarded: bool


class DevTranscriptSegment(BaseModel):
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
    transcript_segments: List[DevTranscriptSegment] = Field(
        description="List of transcript segments with speaker and timing info", min_length=1, max_length=500
    )
    source: Optional[ConversationSource] = Field(
        default=ConversationSource.external_integration,
        description="Source of the conversation (e.g., omi, friend, openglass, phone, external_integration)",
    )
    started_at: Optional[datetime] = Field(default=None, description="When conversation started (defaults to now)")
    finished_at: Optional[datetime] = Field(
        default=None, description="When conversation finished (calculated from segments duration if not provided)"
    )
    language: Optional[str] = Field(default='en', description="Language code (ISO 639-1, e.g., 'en', 'es', 'fr')")
    geolocation: Optional[Geolocation] = Field(default=None, description="Geolocation where conversation occurred")


@router.get("/v1/dev/user/conversations", response_model=List[Conversation], tags=["developer"])
def get_conversations(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    categories: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
    include_transcript: bool = False,
    uid: str = Depends(get_uid_with_conversations_read),
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


@router.post("/v1/dev/user/conversations", response_model=ConversationResponse, tags=["developer"])
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

    # Process geolocation if provided
    geolocation = request.geolocation
    if geolocation and not geolocation.google_place_id:
        try:
            geolocation = get_google_maps_location(geolocation.latitude, geolocation.longitude)
        except Exception as e:
            print(f"Error enriching geolocation: {e}")
            # Continue with original geolocation if enrichment fails

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


@router.post("/v1/dev/user/conversations/from-segments", response_model=ConversationResponse, tags=["developer"])
def create_conversation_from_segments(
    request: CreateConversationFromTranscriptRequest,
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

    # Process geolocation if provided
    geolocation = request.geolocation
    if geolocation and not geolocation.google_place_id:
        try:
            geolocation = get_google_maps_location(geolocation.latitude, geolocation.longitude)
        except Exception as e:
            print(f"Error enriching geolocation: {e}")
            # Continue with original geolocation if enrichment fails

    # Language defaults
    language_code = request.language or 'en'

    # Source defaults
    source = request.source or ConversationSource.external_integration

    # Create conversation object with transcript segments
    create_conversation_obj = CreateConversation(
        transcript_segments=transcript_segments,
        started_at=started_at,
        finished_at=finished_at,
        language=language_code,
        geolocation=geolocation,
        source=source,
    )

    # Process conversation
    conversation = process_conversation(uid, language_code, create_conversation_obj)

    return ConversationResponse(
        id=conversation.id,
        status=conversation.status.value if conversation.status else 'completed',
        discarded=conversation.discarded,
    )
