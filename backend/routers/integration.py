import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional, List, Tuple

from fastapi import APIRouter, Header, HTTPException, Depends
from fastapi import Request
from fastapi.responses import JSONResponse

import database.apps as apps_db
import utils.apps as apps_utils
from utils.apps import verify_api_key
import database.memories as memories_db
import database.redis_db as redis_db
from database.redis_db import get_enabled_plugins, r as redis_client
import database.notifications as notification_db
import models.integrations as integration_models
import models.memory as memory_models
from models.app import App
from routers.memories import process_memory, trigger_external_integrations
from utils.memories.location import get_google_maps_location
from utils.memories.facts import process_external_integration_fact
from utils.plugins import send_plugin_notification

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


@router.post('/v2/integrations/{app_id}/user/conversations', response_model=integration_models.EmptyResponse,
             tags=['integration', 'conversations'])
async def create_conversation_via_integration(
    request: Request,
    app_id: str,
    create_memory: memory_models.ExternalIntegrationCreateMemory,
    uid: str,
    authorization: Optional[str] = Header(None)
):
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
    enabled_plugins = redis_db.get_enabled_plugins(uid)
    if app_id not in enabled_plugins:
        raise HTTPException(status_code=403, detail="App is not enabled for this user")

    # Check if the app has the capability external_integration > action > create_conversation
    if not apps_utils.app_has_action(app, 'create_conversation'):
        raise HTTPException(status_code=403, detail="App does not have the capability to create conversations")

    # Time
    started_at = create_memory.started_at if create_memory.started_at is not None else datetime.now(timezone.utc)
    finished_at = create_memory.finished_at if create_memory.finished_at is not None else started_at + \
        timedelta(seconds=300)  # 5 minutes
    create_memory.started_at = started_at
    create_memory.finished_at = finished_at

    # Geo
    geolocation = create_memory.geolocation
    if geolocation and not geolocation.google_place_id:
        create_memory.geolocation = get_google_maps_location(geolocation.latitude, geolocation.longitude)
    create_memory.geolocation = geolocation

    # Language
    language_code = create_memory.language
    if not language_code:
        language_code = 'en'  # Default to English
        create_memory.language = language_code

    # Set source to external_integration
    create_memory.source = memory_models.MemorySource.external_integration

    # Set app_id
    create_memory.app_id = app_id

    # Process
    memory = process_memory(uid, language_code, create_memory)

    # Always trigger integration
    trigger_external_integrations(uid, memory)

    # Empty response
    return {}


@router.post('/v2/integrations/{app_id}/user/memories', response_model=integration_models.EmptyResponse,
             tags=['integration', 'facts'])
async def create_memories_via_integration(
    request: Request,
    app_id: str,
    fact_data: integration_models.ExternalIntegrationCreateFact,
    uid: str,
    authorization: Optional[str] = Header(None)
):
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
    enabled_plugins = redis_db.get_enabled_plugins(uid)
    if app_id not in enabled_plugins:
        raise HTTPException(status_code=403, detail="App is not enabled for this user")

    # Check if the app has the capability external_integration > action > create_facts
    if not apps_utils.app_has_action(app, 'create_facts'):
        raise HTTPException(status_code=403, detail="App does not have the capability to create facts")

    # Validate that text is provided or explicit facts are provided
    if (not fact_data.text or len(fact_data.text.strip()) == 0) and \
            (not fact_data.memories or len(fact_data.memories) == 0):
        raise HTTPException(status_code=422, detail="Either text or explicit memories(facts) are required and cannot be empty")

    # Process and save the fact using the utility function
    process_external_integration_fact(uid, fact_data, app_id)

    # Empty response
    return {}


@router.post('/v2/integrations/{app_id}/user/facts', response_model=integration_models.EmptyResponse,
             tags=['integration', 'facts'])
async def create_facts_via_integration(
    request: Request,
    app_id: str,
    fact_data: integration_models.ExternalIntegrationCreateFact,
    uid: str,
    authorization: Optional[str] = Header(None)
):
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
    enabled_plugins = redis_db.get_enabled_plugins(uid)
    if app_id not in enabled_plugins:
        raise HTTPException(status_code=403, detail="App is not enabled for this user")

    # Check if the app has the capability external_integration > action > create_facts
    if not apps_utils.app_has_action(app, 'create_facts'):
        raise HTTPException(status_code=403, detail="App does not have the capability to create facts")

    # Validate that text is provided or explicit facts are provided
    if (not fact_data.text or len(fact_data.text.strip()) == 0) and \
            (not fact_data.memories or len(fact_data.memories) == 0):
        raise HTTPException(status_code=422, detail="Either text or explicit memories(facts) are required and cannot be empty")

    # Process and save the fact using the utility function
    process_external_integration_fact(uid, fact_data, app_id)

    # Empty response
    return {}


@router.post('/v2/integrations/{app_id}/notification', response_model=integration_models.EmptyResponse,
             tags=['integration', 'notifications'])
async def send_notification_via_integration(
    request: Request,
    app_id: str,
    message: str,
    uid: str,
    authorization: Optional[str] = Header(None)
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
    user_enabled = set(get_enabled_plugins(uid))
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
            content={
                'detail': f'Rate limit exceeded. Maximum {MAX_NOTIFICATIONS_PER_HOUR} notifications per hour.'
            }
        )

    token = notification_db.get_token_only(uid)
    send_plugin_notification(token, app.name, app.id, message)
    return JSONResponse(
        status_code=200,
        headers=headers,
        content={'status': 'Ok'}
    )
