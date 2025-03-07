import os
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Header, HTTPException, Depends
from fastapi import Request

import database.apps as apps_db
import utils.apps as apps_utils
from utils.apps import verify_api_key
import database.memories as memories_db
import database.redis_db as redis_db
import models.integrations as integration_models
import models.memory as memory_models
from routers.memories import process_memory, trigger_external_integrations
from utils.memories.location import get_google_maps_location

router = APIRouter()


@router.post('/v2/integrations/{app_id}/user/memories', response_model=integration_models.EmptyResponse,
             tags=['integration', 'memories'])
async def create_memory_via_integration(
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

    # Check if the app has the capability external_integration > action > create_memory
    if not apps_utils.app_has_action(app, 'create_memory'):
        raise HTTPException(status_code=403, detail="App does not have the capability to create memories")

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
