import os
from typing import Annotated
from datetime import datetime, timedelta
from fastapi import APIRouter, Header
from fastapi import Request, HTTPException
import models.memory as memory_models
import models.integrations as integration_models

from utils.memories.location import get_google_maps_location
from routers.app.memories import process_memory, trigger_external_integrations

router = APIRouter()


@router.post('/v1/integrations/workflow/memories', response_model=integration_models.EmptyResponse)
def create_memory(request: Request, uid: str, api_key: Annotated[str | None, Header()], create_memory: memory_models.WorkflowCreateMemory):
    if api_key != os.getenv('WORKFLOW_API_KEY'):
        raise HTTPException(status_code=401, detail="Invalid API Key")

    # Time
    started_at = create_memory.started_at if create_memory.started_at is not None else datetime.utcnow()
    finished_at = create_memory.finished_at if create_memory.finished_at is not None else started_at + \
        timedelta(seconds=300)  # 5 minutes
    create_memory.started_at = started_at
    create_memory.finished_at = finished_at

    # Geo
    geolocation = create_memory.geolocation
    if geolocation and not geolocation.google_place_id:
        create_memory.geolocation = get_google_maps_location(
            geolocation.latitude, geolocation.longitude)
    create_memory.geolocation = geolocation

    # Language
    language_code = create_memory.language
    if not language_code:  # not breaking change
        language_code = create_memory.language
    else:
        create_memory.language = language_code

    # Process
    memory = process_memory(uid, language_code, create_memory)

    # Always trigger integration
    trigger_external_integrations(uid, memory)

    # Empty response
    return {}
