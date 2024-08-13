import os
from typing import Annotated
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Header
from fastapi import Request, HTTPException

from database.memories import upsert_memory
from models.integrations import WorkflowCreateMemory, WorkflowMemorySource
from models.memory import Memory
from models.memory import MemorySource
from utils.llm import get_transcript_structure, summarize_experience_text
from utils.location import get_google_maps_location

router = APIRouter()


@router.post('/v1/integrations/workflow/memories', response_model=Memory)
def create_memory(request: Request, uid: str, api_key: Annotated[str | None, Header()],  create_memory: WorkflowCreateMemory):
    if api_key != os.getenv('WORKFLOW_API_KEY'):
        raise HTTPException(status_code=401, detail="Invalid API Key")

    # Time
    started_at = create_memory.started_at if create_memory.started_at is not None else datetime.utcnow()
    finished_at = create_memory.finished_at if create_memory.finished_at is not None else started_at + \
        timedelta(seconds=300)  # 5 minutes

    # Summarize
    if create_memory.source == WorkflowMemorySource.audio:
        structured = get_transcript_structure(
            create_memory.text, started_at, create_memory.language, True)
    elif create_memory.source == WorkflowMemorySource.other:
        structured = summarize_experience_text(create_memory.text)
    else:
        raise HTTPException(status_code=400, detail='Invalid memory source')

    # Geo
    geolocation = create_memory.geolocation
    if geolocation and not geolocation.google_place_id:
        create_memory.geolocation = get_google_maps_location(
            geolocation.latitude, geolocation.longitude)

    memory = Memory(
        id=str(uuid.uuid4()),
        uid=uid,
        structured=structured,
        started_at=started_at,
        finished_at=finished_at,
        created_at=datetime.utcnow(),
        discarded=False,
        deleted=False,
        source=MemorySource.workflow,
        geolocation=geolocation,
    )

    output = memory.dict()
    output['external_data'] = create_memory.dict()
    upsert_memory(uid, output)
    return output
