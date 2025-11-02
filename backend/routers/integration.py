import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple, Union

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi import Request
from fastapi.responses import JSONResponse, HTMLResponse

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
    tags=['integration', 'memories'],
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


@router.get(
    '/v2/integrations/{app_id}/memories',
    response_model=integration_models.MemoriesResponse,
    response_model_exclude_none=True,
    tags=['integration', 'memories'],
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
    for memory in memories:
        if memory.get('is_locked', False):
            content = memory.get('content', '')
            memory['content'] = (content[:70] + '...') if len(content) > 70 else content
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
            if len(start_date) == 10:  # YYYY-MM-DD
                dt = datetime.strptime(start_date, '%Y-%m-%d')
                start_date = dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
            else:
                start_date = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid start_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS.sssZ) or YYYY-MM-DD",
            )

    if isinstance(end_date, str) and end_date:
        try:
            if len(end_date) == 10:  # YYYY-MM-DD
                dt = datetime.strptime(end_date, '%Y-%m-%d')
                end_date = dt.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc)
            else:
                end_date = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid end_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS.sssZ) or YYYY-MM-DD",
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
            if conv.get('is_locked', False):
                conv['structured']['action_items'] = []
                conv['structured']['events'] = []
                conv['transcript_segments'] = []
                conv['apps_results'] = []
                conv['plugins_results'] = []
                conv['suggested_summarization_apps'] = []

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
        try:
            start_date_str = search_request.start_date
            if len(start_date_str) == 10:  # YYYY-MM-DD
                dt = datetime.strptime(start_date_str, '%Y-%m-%d')
                start_dt = dt.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)
            else:
                start_dt = datetime.fromisoformat(start_date_str.replace('Z', '+00:00'))
            start_timestamp = int(start_dt.timestamp())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid start_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS.sssZ) or YYYY-MM-DD",
            )

    if search_request.end_date:
        try:
            end_date_str = search_request.end_date
            if len(end_date_str) == 10:  # YYYY-MM-DD
                dt = datetime.strptime(end_date_str, '%Y-%m-%d')
                end_dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999, tzinfo=timezone.utc)
            else:
                end_dt = datetime.fromisoformat(end_date_str.replace('Z', '+00:00'))
            end_timestamp = int(end_dt.timestamp())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid end_date format. Use ISO format (YYYY-MM-DDTHH:MM:SS.sssZ) or YYYY-MM-DD",
            )

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
            if conv.get('is_locked', False):
                conv['structured']['action_items'] = []
                conv['structured']['events'] = []
                conv['transcript_segments'] = []
                conv['apps_results'] = []
                conv['plugins_results'] = []
                conv['suggested_summarization_apps'] = []

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


@router.get(
    '/v2/integrations/todoist/callback',
    response_class=HTMLResponse,
    tags=['integration', 'oauth'],
)
async def todoist_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """
    OAuth callback endpoint for Todoist integration.
    Exchanges the authorization code for tokens and redirects back to the app with tokens.
    """
    if not code:
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Todoist Auth Error - Omi</title>
                <meta charset="UTF-8">
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #E44332 0%, #DB4035 100%);
                        color: white;
                    }
                    .container {
                        text-align: center;
                        padding: 2rem;
                        background: rgba(255, 255, 255, 0.1);
                        border-radius: 20px;
                        backdrop-filter: blur(10px);
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>❌ Authentication Error</h2>
                    <p>No authorization code received from Todoist.</p>
                </div>
            </body>
            </html>
            """,
            status_code=400,
        )

    # Exchange code for tokens using backend credentials
    import requests
    import os

    client_id = os.getenv('TODOIST_CLIENT_ID')
    client_secret = os.getenv('TODOIST_CLIENT_SECRET')

    if not all([client_id, client_secret]):
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Todoist Auth Error - Omi</title>
                <meta charset="UTF-8">
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #E44332 0%, #DB4035 100%);
                        color: white;
                    }
                    .container {
                        text-align: center;
                        padding: 2rem;
                        background: rgba(255, 255, 255, 0.1);
                        border-radius: 20px;
                        backdrop-filter: blur(10px);
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>❌ Configuration Error</h2>
                    <p>Todoist OAuth not properly configured.</p>
                </div>
            </body>
            </html>
            """,
            status_code=500,
        )

    try:
        # Exchange code for tokens
        token_response = requests.post(
            'https://todoist.com/oauth/access_token',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'code': code,
            },
        )

        if token_response.status_code == 200:
            token_data = token_response.json()
            access_token = token_data.get('access_token', '')

            # Create deep link with token
            from urllib.parse import quote

            deep_link = f'omi://todoist/callback?access_token={quote(access_token)}&state={state or ""}'
        else:
            # Failed to exchange, return error
            deep_link = f'omi://todoist/callback?error=token_exchange_failed&state={state or ""}'
    except Exception as e:
        print(f'Error exchanging Todoist code: {e}')
        deep_link = f'omi://todoist/callback?error=server_error&state={state or ""}'

    # Return HTML that redirects to the app
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Todoist Auth - Omi</title>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="1;url={deep_link}">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #E44332 0%, #DB4035 100%);
                color: white;
            }}
            .container {{
                text-align: center;
                padding: 2rem;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 20px;
                backdrop-filter: blur(10px);
            }}
            h2 {{ margin: 0 0 1rem 0; }}
            .spinner {{
                border: 3px solid rgba(255, 255, 255, 0.3);
                border-radius: 50%;
                border-top: 3px solid white;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 20px auto;
            }}
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            a {{
                color: white;
                text-decoration: underline;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>✓ Authentication Successful!</h2>
            <div class="spinner"></div>
            <p>Redirecting back to Omi...</p>
            <p style="font-size: 0.9em; margin-top: 20px;">
                If you're not redirected automatically, 
                <a href="{deep_link}">click here</a>
            </p>
        </div>
        <script>
            setTimeout(function() {{
                window.location.href = '{deep_link}';
            }}, 1000);
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content)


@router.get(
    '/v2/integrations/asana/callback',
    response_class=HTMLResponse,
    tags=['integration', 'oauth'],
)
async def asana_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """
    OAuth callback endpoint for Asana integration.
    Exchanges the authorization code for tokens and redirects back to the app with tokens.
    """
    if not code:
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Asana Auth Error - Omi</title>
                <meta charset="UTF-8">
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                    }
                    .container {
                        text-align: center;
                        padding: 2rem;
                        background: rgba(255, 255, 255, 0.1);
                        border-radius: 20px;
                        backdrop-filter: blur(10px);
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>❌ Authentication Error</h2>
                    <p>No authorization code received from Asana.</p>
                </div>
            </body>
            </html>
            """,
            status_code=400,
        )

    # Exchange code for tokens using backend credentials
    import requests
    import os

    client_id = os.getenv('ASANA_CLIENT_ID')
    client_secret = os.getenv('ASANA_CLIENT_SECRET')
    base_url = os.getenv('BASE_API_URL')

    if not all([client_id, client_secret, base_url]):
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Asana Auth Error - Omi</title>
                <meta charset="UTF-8">
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        color: white;
                    }
                    .container {
                        text-align: center;
                        padding: 2rem;
                        background: rgba(255, 255, 255, 0.1);
                        border-radius: 20px;
                        backdrop-filter: blur(10px);
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>❌ Configuration Error</h2>
                    <p>Asana OAuth not properly configured.</p>
                </div>
            </body>
            </html>
            """,
            status_code=500,
        )

    redirect_uri = f'{base_url}v2/integrations/asana/callback'

    try:
        # Exchange code for tokens
        token_response = requests.post(
            'https://app.asana.com/-/oauth_token',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'grant_type': 'authorization_code',
                'client_id': client_id,
                'client_secret': client_secret,
                'redirect_uri': redirect_uri,
                'code': code,
            },
        )

        if token_response.status_code == 200:
            token_data = token_response.json()
            access_token = token_data.get('access_token', '')
            refresh_token = token_data.get('refresh_token', '')

            # Create deep link with tokens
            from urllib.parse import quote

            deep_link = f'omi://asana/callback?access_token={quote(access_token)}&refresh_token={quote(refresh_token)}&state={state or ""}'
        else:
            # Failed to exchange, return error
            deep_link = f'omi://asana/callback?error=token_exchange_failed&state={state or ""}'
    except Exception as e:
        print(f'Error exchanging Asana code: {e}')
        deep_link = f'omi://asana/callback?error=server_error&state={state or ""}'

    # Return HTML that redirects to the app
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Asana Auth - Omi</title>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="1;url={deep_link}">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }}
            .container {{
                text-align: center;
                padding: 2rem;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 20px;
                backdrop-filter: blur(10px);
            }}
            h2 {{ margin: 0 0 1rem 0; }}
            .spinner {{
                border: 3px solid rgba(255, 255, 255, 0.3);
                border-radius: 50%;
                border-top: 3px solid white;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 20px auto;
            }}
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            a {{
                color: white;
                text-decoration: underline;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>✓ Authentication Successful!</h2>
            <div class="spinner"></div>
            <p>Redirecting back to Omi...</p>
            <p style="font-size: 0.9em; margin-top: 20px;">
                If you're not redirected automatically, 
                <a href="{deep_link}">click here</a>
            </p>
        </div>
        <script>
            setTimeout(function() {{
                window.location.href = '{deep_link}';
            }}, 1000);
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content)


@router.get(
    '/v2/integrations/clickup/callback',
    response_class=HTMLResponse,
    tags=['integration', 'oauth'],
)
async def clickup_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """
    OAuth callback endpoint for ClickUp integration.
    Exchanges the authorization code for tokens and redirects back to the app with tokens.
    """
    if not code:
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>ClickUp Auth Error - Omi</title>
                <meta charset="UTF-8">
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #7B68EE 0%, #9B59B6 100%);
                        color: white;
                    }
                    .container {
                        text-align: center;
                        padding: 2rem;
                        background: rgba(255, 255, 255, 0.1);
                        border-radius: 20px;
                        backdrop-filter: blur(10px);
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>❌ Authentication Error</h2>
                    <p>No authorization code received from ClickUp.</p>
                </div>
            </body>
            </html>
            """,
            status_code=400,
        )

    # Exchange code for tokens using backend credentials
    import requests
    import os
    import json as json_module

    client_id = os.getenv('CLICKUP_CLIENT_ID')
    client_secret = os.getenv('CLICKUP_CLIENT_SECRET')

    if not all([client_id, client_secret]):
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>ClickUp Auth Error - Omi</title>
                <meta charset="UTF-8">
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #7B68EE 0%, #9B59B6 100%);
                        color: white;
                    }
                    .container {
                        text-align: center;
                        padding: 2rem;
                        background: rgba(255, 255, 255, 0.1);
                        border-radius: 20px;
                        backdrop-filter: blur(10px);
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>❌ Configuration Error</h2>
                    <p>ClickUp OAuth not properly configured.</p>
                </div>
            </body>
            </html>
            """,
            status_code=500,
        )

    try:
        # Exchange code for tokens
        token_response = requests.post(
            'https://api.clickup.com/api/v2/oauth/token',
            headers={'Content-Type': 'application/json'},
            data=json_module.dumps(
                {
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'code': code,
                }
            ),
        )

        if token_response.status_code == 200:
            token_data = token_response.json()
            access_token = token_data.get('access_token', '')

            # Create deep link with token
            from urllib.parse import quote

            deep_link = f'omi://clickup/callback?access_token={quote(access_token)}&state={state or ""}'
        else:
            # Failed to exchange, return error
            deep_link = f'omi://clickup/callback?error=token_exchange_failed&state={state or ""}'
    except Exception as e:
        print(f'Error exchanging ClickUp code: {e}')
        deep_link = f'omi://clickup/callback?error=server_error&state={state or ""}'

    # Return HTML that redirects to the app
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>ClickUp Auth - Omi</title>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="1;url={deep_link}">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #7B68EE 0%, #9B59B6 100%);
                color: white;
            }}
            .container {{
                text-align: center;
                padding: 2rem;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 20px;
                backdrop-filter: blur(10px);
            }}
            h2 {{ margin: 0 0 1rem 0; }}
            .spinner {{
                border: 3px solid rgba(255, 255, 255, 0.3);
                border-radius: 50%;
                border-top: 3px solid white;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 20px auto;
            }}
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            a {{
                color: white;
                text-decoration: underline;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>✓ Authentication Successful!</h2>
            <div class="spinner"></div>
            <p>Redirecting back to Omi...</p>
            <p style="font-size: 0.9em; margin-top: 20px;">
                If you're not redirected automatically, 
                <a href="{deep_link}">click here</a>
            </p>
        </div>
        <script>
            setTimeout(function() {{
                window.location.href = '{deep_link}';
            }}, 1000);
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content)


@router.get(
    '/v2/integrations/google-tasks/callback',
    response_class=HTMLResponse,
    tags=['integration', 'oauth'],
)
async def google_tasks_oauth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
):
    """
    OAuth callback endpoint for Google Tasks integration.
    Exchanges the authorization code for tokens and redirects back to the app with tokens.
    """
    if not code:
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Google Tasks Auth Error - Omi</title>
                <meta charset="UTF-8">
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #4285F4 0%, #34A853 100%);
                        color: white;
                    }
                    .container {
                        text-align: center;
                        padding: 2rem;
                        background: rgba(255, 255, 255, 0.1);
                        border-radius: 20px;
                        backdrop-filter: blur(10px);
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>❌ Authentication Error</h2>
                    <p>No authorization code received from Google.</p>
                </div>
            </body>
            </html>
            """,
            status_code=400,
        )

    # Exchange code for tokens using backend credentials
    import requests
    import os

    client_id = os.getenv('GOOGLE_TASKS_CLIENT_ID')
    client_secret = os.getenv('GOOGLE_TASKS_CLIENT_SECRET')
    base_url = os.getenv('BASE_API_URL')

    if not all([client_id, client_secret, base_url]):
        return HTMLResponse(
            content="""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Google Tasks Auth Error - Omi</title>
                <meta charset="UTF-8">
                <style>
                    body {
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                        background: linear-gradient(135deg, #4285F4 0%, #34A853 100%);
                        color: white;
                    }
                    .container {
                        text-align: center;
                        padding: 2rem;
                        background: rgba(255, 255, 255, 0.1);
                        border-radius: 20px;
                        backdrop-filter: blur(10px);
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h2>❌ Configuration Error</h2>
                    <p>Google Tasks OAuth not properly configured.</p>
                </div>
            </body>
            </html>
            """,
            status_code=500,
        )

    redirect_uri = f'{base_url}v2/integrations/google-tasks/callback'

    try:
        # Exchange code for tokens
        token_response = requests.post(
            'https://oauth2.googleapis.com/token',
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            data={
                'code': code,
                'client_id': client_id,
                'client_secret': client_secret,
                'redirect_uri': redirect_uri,
                'grant_type': 'authorization_code',
            },
        )

        if token_response.status_code == 200:
            token_data = token_response.json()
            access_token = token_data.get('access_token', '')
            refresh_token = token_data.get('refresh_token', '')

            # Create deep link with tokens
            from urllib.parse import quote

            deep_link = f'omi://google-tasks/callback?access_token={quote(access_token)}&refresh_token={quote(refresh_token)}&state={state or ""}'
        else:
            # Failed to exchange, return error
            deep_link = f'omi://google-tasks/callback?error=token_exchange_failed&state={state or ""}'
    except Exception as e:
        print(f'Error exchanging Google Tasks code: {e}')
        deep_link = f'omi://google-tasks/callback?error=server_error&state={state or ""}'

    # Return HTML that redirects to the app
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Google Tasks Auth - Omi</title>
        <meta charset="UTF-8">
        <meta http-equiv="refresh" content="1;url={deep_link}">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #4285F4 0%, #34A853 100%);
                color: white;
            }}
            .container {{
                text-align: center;
                padding: 2rem;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 20px;
                backdrop-filter: blur(10px);
            }}
            h2 {{ margin: 0 0 1rem 0; }}
            .spinner {{
                border: 3px solid rgba(255, 255, 255, 0.3);
                border-radius: 50%;
                border-top: 3px solid white;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 20px auto;
            }}
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            a {{
                color: white;
                text-decoration: underline;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>✓ Authentication Successful!</h2>
            <div class="spinner"></div>
            <p>Redirecting back to Omi...</p>
            <p style="font-size: 0.9em; margin-top: 20px;">
                If you're not redirected automatically, 
                <a href="{deep_link}">click here</a>
            </p>
        </div>
        <script>
            setTimeout(function() {{
                window.location.href = '{deep_link}';
            }}, 1000);
        </script>
    </body>
    </html>
    """

    return HTMLResponse(content=html_content)
