import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple, Union

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi import Request
from fastapi.responses import JSONResponse

import database.apps as apps_db
import database.conversations as conversations_db
import utils.apps as apps_utils
from utils.apps import verify_api_key
import database.redis_db as redis_db
import database.memories as memory_db
from database.redis_db import get_enabled_apps, r as redis_client
import database.notifications as notification_db
import models.integrations as integration_models
import models.conversation as conversation_models
from models.conversation import SearchRequest
from models.app import App
from routers.conversations import process_conversation, trigger_external_integrations
from utils.conversations.location import get_google_maps_location
from utils.conversations.memories import process_external_integration_memory
from utils.conversations.search import search_conversations
from utils.app_integrations import send_app_notification

# Rate limit settings - more conservative limits to prevent notification fatigue
RATE_LIMIT_PERIOD = 3600  # 1 hour in seconds
MAX_NOTIFICATIONS_PER_HOUR = 10  # Maximum notifications per hour per app per user

router = APIRouter()


def check_rate_limit(app_id: str, user_id: str) -> Tuple[bool, int, int, int]:
    """
    Check if the app has exceeded its rate limit for a specific user
    Returns: (allowed, remaining, reset_time, retry_after)
    """
    now = datetime.utcnow()
    hour_key = f"notification_rate_limit:{app_id}:{user_id}:{now.strftime('%Y-%m-%d-%H')}"

    # Check hourly limit
    hour_count = redis_client.get(hour_key)
    if hour_count is None:
        redis_client.setex(hour_key, RATE_LIMIT_PERIOD, 1)
        hour_count = 1
    else:
        hour_count = int(hour_count)

    # Calculate reset time
    hour_reset = RATE_LIMIT_PERIOD - (int(now.timestamp()) % RATE_LIMIT_PERIOD)
    reset_time = hour_reset

    # Check if hourly limit is exceeded
    if hour_count >= MAX_NOTIFICATIONS_PER_HOUR:
        return False, MAX_NOTIFICATIONS_PER_HOUR - hour_count, hour_reset, hour_reset

    # Increment counter
    redis_client.incr(hour_key)

    remaining = MAX_NOTIFICATIONS_PER_HOUR - hour_count - 1

    return True, remaining, reset_time, 0


@router.post(
    '/v2/integrations/{app_id}/user/conversations',
    response_model=integration_models.EmptyResponse,
    tags=['integration', 'conversations'],
)
async def create_conversation_via_integration(
    request: Request,
    app_id: str,
    create_conversation: conversation_models.ExternalIntegrationCreateConversation,
    uid: str,
    authorization: Optional[str] = Header(None),
):
    # Verify API key from Authorization header
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header. Must be 'Bearer API_KEY'")

    api_key = authorization.replace('Bearer ', '')
    if not verify_api_key(app_id, api_key):
        raise HTTPException(status_code=403, detail="Invalid integration API key")

    # Verify if the app exists
    app = apps_db.get_app_by_id_db(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    # Verify if the uid has enabled the app
    enabled_plugins = redis_db.get_enabled_apps(uid)
    if app_id not in enabled_plugins:
        raise HTTPException(status_code=403, detail="App is not enabled for this user")

    # Check if the app has the capability external_integration > action > create_conversation
    if not apps_utils.app_can_create_conversation(app):
        raise HTTPException(status_code=403, detail="App does not have the capability to create conversations")

    # Time
    started_at = (
        create_conversation.started_at if create_conversation.started_at is not None else datetime.now(timezone.utc)
    )
    finished_at = (
        create_conversation.finished_at
        if create_conversation.finished_at is not None
        else started_at + timedelta(seconds=300)
    )  # 5 minutes
    create_conversation.started_at = started_at
    create_conversation.finished_at = finished_at

    # Geo
    geolocation = create_conversation.geolocation
    if geolocation and not geolocation.google_place_id:
        create_conversation.geolocation = get_google_maps_location(geolocation.latitude, geolocation.longitude)
    create_conversation.geolocation = geolocation

    # Language
    language_code = create_conversation.language
    if not language_code:
        language_code = 'en'  # Default to English
        create_conversation.language = language_code

    # Set source to external_integration
    create_conversation.source = conversation_models.ConversationSource.external_integration

    # Set app_id
    create_conversation.app_id = app_id

    # Process
    conversation = process_conversation(uid, language_code, create_conversation)

    # Always trigger integration
    trigger_external_integrations(uid, conversation)

    # TODO: Empty for now, replace with ConversationCreateResponse once we don't have to wait for process_conversation
    # to finish for the conversation id
    return {}


@router.post(
    '/v2/integrations/{app_id}/user/memories',
    response_model=integration_models.EmptyResponse,
    tags=['integration', 'facts'],
)
async def create_memories_via_integration(
    request: Request,
    app_id: str,
    fact_data: integration_models.ExternalIntegrationCreateMemory,
    uid: str,
    authorization: Optional[str] = Header(None),
):
    # Verify API key from Authorization header
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header. Must be 'Bearer API_KEY'")

    api_key = authorization.replace('Bearer ', '')
    if not verify_api_key(app_id, api_key):
        raise HTTPException(status_code=403, detail="Invalid integrationAPI key")

    # Verify if the app exists
    app = apps_db.get_app_by_id_db(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    # Verify if the uid has enabled the app
    enabled_plugins = redis_db.get_enabled_apps(uid)
    if app_id not in enabled_plugins:
        raise HTTPException(status_code=403, detail="App is not enabled for this user")

    # Check if the app has the capability external_integration > action > create_memories / create_facts
    if not apps_utils.app_can_create_memories(app):
        raise HTTPException(status_code=403, detail="App does not have the capability to create memories")

    # Validate that text is provided or explicit facts are provided
    if (not fact_data.text or len(fact_data.text.strip()) == 0) and (
        not fact_data.memories or len(fact_data.memories) == 0
    ):
        raise HTTPException(
            status_code=422, detail="Either text or explicit memories(facts) are required and cannot be empty"
        )

    # Process and save the memory using the utility function
    process_external_integration_memory(uid, fact_data, app_id)

    # Empty response
    return {}


@router.post(
    '/v2/integrations/{app_id}/user/facts',
    response_model=integration_models.EmptyResponse,
    tags=['integration', 'facts'],
)
async def create_facts_via_integration(
    request: Request,
    app_id: str,
    fact_data: integration_models.ExternalIntegrationCreateMemory,
    uid: str,
    authorization: Optional[str] = Header(None),
):
    # Verify API key from Authorization header
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header. Must be 'Bearer API_KEY'")

    api_key = authorization.replace('Bearer ', '')
    if not verify_api_key(app_id, api_key):
        raise HTTPException(status_code=403, detail="Invalid integrationAPI key")

    # Verify if the app exists
    app = apps_db.get_app_by_id_db(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    # Verify if the uid has enabled the app
    enabled_plugins = redis_db.get_enabled_apps(uid)
    if app_id not in enabled_plugins:
        raise HTTPException(status_code=403, detail="App is not enabled for this user")

    # Check if the app has the capability external_integration > action > create_facts / create_memories
    if not apps_utils.app_can_create_memories(app):
        raise HTTPException(status_code=403, detail="App does not have the capability to create memories")

    # Validate that text is provided or explicit facts are provided
    if (not fact_data.text or len(fact_data.text.strip()) == 0) and (
        not fact_data.memories or len(fact_data.memories) == 0
    ):
        raise HTTPException(
            status_code=422, detail="Either text or explicit memories(facts) are required and cannot be empty"
        )

    # Process and save the memory using the utility function
    process_external_integration_memory(uid, fact_data, app_id)

    # Empty response
    return {}


@router.get(
    '/v2/integrations/{app_id}/memories',
    response_model=integration_models.MemoriesResponse,
    response_model_exclude_none=True,
    tags=['integration', 'facts'],
)
async def get_memories_via_integration(
    request: Request,
    app_id: str,
    uid: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    authorization: Optional[str] = Header(None),
):
    """
    Get all memories (facts) for a user via integration API.
    Authentication is required via API key in the Authorization header.
    """
    # Verify API key from Authorization header
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header. Must be 'Bearer API_KEY'")

    api_key = authorization.replace('Bearer ', '')
    if not verify_api_key(app_id, api_key):
        raise HTTPException(status_code=403, detail="Invalid integrationAPI key")

    # Verify if the app exists
    app = apps_db.get_app_by_id_db(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    # Verify if the uid has enabled the app
    enabled_plugins = redis_db.get_enabled_apps(uid)
    if app_id not in enabled_plugins:
        raise HTTPException(status_code=403, detail="App is not enabled for this user")

    # Check if the app has the capability to read memories
    if not apps_utils.app_can_read_memories(app):
        raise HTTPException(status_code=403, detail="App does not have the capability to read memories")

    memories = memory_db.get_memories(uid, limit=limit, offset=offset)
    memory_items = [integration_models.MemoryItem(**fact) for fact in memories]

    return {"memories": memory_items}


@router.get(
    '/v2/integrations/{app_id}/conversations',
    response_model=integration_models.ConversationsResponse,
    response_model_exclude_none=True,
    tags=['integration', 'conversations'],
)
async def get_conversations_via_integration(
    request: Request,
    app_id: str,
    uid: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    include_discarded: bool = Query(False),
    statuses: List[str] = Query([]),
    start_date: Optional[Union[datetime, str]] = Query(
        None, description="Filter conversations after this date (ISO format)"
    ),
    end_date: Optional[Union[datetime, str]] = Query(
        None, description="Filter conversations before this date (ISO format)"
    ),
    max_transcript_segments: int = Query(
        100,
        ge=-1,
        le=1000,
        description="Maximum number of transcript segments to include per conversation. Use -1 for no limit.",
    ),
    authorization: Optional[str] = Header(None),
):
    """
    Get all conversations for a user via integration API.
    Authentication is required via API key in the Authorization header.

    Optional date range filtering:
    - start_date: Filter conversations after this date (ISO format)
    - end_date: Filter conversations before this date (ISO format)
    """
    # Verify API key from Authorization header
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header. Must be 'Bearer API_KEY'")

    api_key = authorization.replace('Bearer ', '')
    if not verify_api_key(app_id, api_key):
        raise HTTPException(status_code=403, detail="Invalid API key")

    # Verify if the app exists
    app = apps_db.get_app_by_id_db(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    # Verify if the uid has enabled the app
    enabled_plugins = redis_db.get_enabled_apps(uid)
    if app_id not in enabled_plugins:
        raise HTTPException(status_code=403, detail="App is not enabled for this user")

    # Check if the app has the capability to read conversations
    if not apps_utils.app_can_read_conversations(app):
        raise HTTPException(status_code=403, detail="App does not have the capability to read conversations")

    # Convert string dates to datetime objects if needed
    if isinstance(start_date, str) and start_date:
        try:
            start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid start_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS.sssZ)"
            )

    if isinstance(end_date, str) and end_date:
        try:
            end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid end_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS.sssZ)"
            )

    conversations_data = conversations_db.get_conversations(
        uid,
        limit=limit,
        offset=offset,
        include_discarded=include_discarded,
        statuses=statuses,
        start_date=start_date,
        end_date=end_date,
    )

    # Convert database conversations
    conversation_items = []
    for conv in conversations_data:
        try:
            item = integration_models.ConversationItem.parse_obj(conv)

            # Limit transcript segments
            if (
                max_transcript_segments != -1
                and item.transcript_segments
                and len(item.transcript_segments) > max_transcript_segments
            ):
                item.transcript_segments = item.transcript_segments[:max_transcript_segments]

            # Convert to dict with exclude_none=True to remove null values
            conversation_items.append(item)
        except Exception as e:
            print(f"Error parsing conversation {conv.get('id')}: {str(e)}")
            continue

    # Create response with exclude_none=True
    response = integration_models.ConversationsResponse(conversations=conversation_items)
    return response.dict(exclude_none=True)


@router.post(
    '/v2/integrations/{app_id}/search/conversations',
    response_model=integration_models.SearchConversationsResponse,
    response_model_exclude_none=True,
    tags=['integration', 'conversations'],
)
async def search_conversations_via_integration(
    request: Request,
    app_id: str,
    uid: str,
    search_request: SearchRequest,
    max_transcript_segments: int = Query(
        100,
        ge=-1,
        le=1000,
        description="Maximum number of transcript segments to include per conversation. Use -1 for no limit.",
    ),
    authorization: Optional[str] = Header(None),
):
    """
    Search conversations for a user via integration API.
    Authentication is required via API key in the Authorization header.
    """
    # Verify API key from Authorization header
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header. Must be 'Bearer API_KEY'")

    api_key = authorization.replace('Bearer ', '')
    if not verify_api_key(app_id, api_key):
        raise HTTPException(status_code=403, detail="Invalid API key")

    # Verify if the app exists
    app = apps_db.get_app_by_id_db(app_id)
    if not app:
        raise HTTPException(status_code=404, detail="App not found")

    # Verify if the uid has enabled the app
    enabled_plugins = redis_db.get_enabled_apps(uid)
    if app_id not in enabled_plugins:
        raise HTTPException(status_code=403, detail="App is not enabled for this user")

    # Check if the app has the capability to read conversations
    if not apps_utils.app_can_read_conversations(app):
        raise HTTPException(status_code=403, detail="App does not have the capability to read conversations")

    # Convert ISO datetime strings to Unix timestamps if provided
    start_timestamp = None
    end_timestamp = None

    if search_request.start_date:
        start_timestamp = int(datetime.fromisoformat(search_request.start_date).timestamp())

    if search_request.end_date:
        end_timestamp = int(datetime.fromisoformat(search_request.end_date).timestamp())

    # Search conversations
    search_results = search_conversations(
        query=search_request.query,
        page=search_request.page,
        per_page=search_request.per_page,
        uid=uid,
        include_discarded=search_request.include_discarded,
        start_date=start_timestamp,
        end_date=end_timestamp,
    )

    # Extract conversation IDs from search results
    conversation_ids = [conv.get('id') for conv in search_results['items']]

    # Get full conversation data using the IDs
    full_conversations = []
    if conversation_ids:
        full_conversations = conversations_db.get_conversations_by_id(uid, conversation_ids)

    # Convert database conversations to integration model
    conversation_items = []
    for conv in full_conversations:
        try:
            item = integration_models.ConversationItem.parse_obj(conv)

            # Limit transcript segments
            if (
                max_transcript_segments != -1
                and item.transcript_segments
                and len(item.transcript_segments) > max_transcript_segments
            ):
                item.transcript_segments = item.transcript_segments[:max_transcript_segments]

            conversation_items.append(item)
        except Exception as e:
            print(f"Error parsing conversation {conv.get('id')}: {str(e)}")
            continue

    # Create response with pagination info
    response = integration_models.SearchConversationsResponse(
        conversations=conversation_items,
        total_pages=search_results['total_pages'],
        current_page=search_results['current_page'],
        per_page=search_results['per_page'],
    )

    return response.dict(exclude_none=True)


@router.post(
    '/v2/integrations/{app_id}/notification',
    response_model=integration_models.EmptyResponse,
    tags=['integration', 'notifications'],
)
async def send_notification_via_integration(
    request: Request, app_id: str, message: str, uid: str, authorization: Optional[str] = Header(None)
):
    # Verify API key from Authorization header
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header. Must be 'Bearer API_KEY'")

    api_key = authorization.replace('Bearer ', '')
    if not verify_api_key(app_id, api_key):
        raise HTTPException(status_code=403, detail="Invalid API key")

    # Verify if the app exists
    app_data = apps_utils.get_available_app_by_id(app_id, uid)
    if not app_data:
        raise HTTPException(status_code=404, detail='App not found')

    app = App(**app_data)

    # Check if user has app installed
    user_enabled = set(get_enabled_apps(uid))
    if app_id not in user_enabled:
        raise HTTPException(status_code=403, detail='User does not have this app installed')

    # Check rate limit
    allowed, remaining, reset_time, retry_after = check_rate_limit(app.id, uid)

    # Add rate limit headers to response
    headers = {
        'X-RateLimit-Limit': str(MAX_NOTIFICATIONS_PER_HOUR),
        'X-RateLimit-Remaining': str(remaining),
        'X-RateLimit-Reset': str(reset_time),
    }

    if not allowed:
        headers['Retry-After'] = str(retry_after)
        return JSONResponse(
            status_code=429,
            headers=headers,
            content={'detail': f'Rate limit exceeded. Maximum {MAX_NOTIFICATIONS_PER_HOUR} notifications per hour.'},
        )

    token = notification_db.get_token_only(uid)
    send_app_notification(token, app.name, app.id, message)
    return JSONResponse(status_code=200, headers=headers, content={'status': 'Ok'})
