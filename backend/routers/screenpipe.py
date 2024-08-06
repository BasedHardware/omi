import os
import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException

from database.memories import upsert_memory
from models.integrations import ScreenPipeCreateMemory
from models.memory import Memory
from utils.llm import get_transcript_structure, summarize_screen_pipe
from fastapi import Request, HTTPException

router = APIRouter()


@router.post('/v1/integrations/screenpipe', response_model=Memory)
def create_memory(request: Request, uid: str, data: ScreenPipeCreateMemory):
    if request.headers.get('api_key') != os.getenv('SCREENPIPE_API_KEY'):
        raise HTTPException(status_code=401, detail="Invalid API Key")

    if data.memory_source == 'screen':
        structured = summarize_screen_pipe(data.memory_text)
    elif data.memory_source == 'audio':
        structured = get_transcript_structure(data.memory_text, datetime.now(), 'en', True)
    else:
        raise HTTPException(status_code=400, detail='Invalid memory source')

    memory = Memory(
        id=str(uuid.uuid4()),
        uid=uid,
        structured=structured,
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        transcript=data.memory_text,
        discarded=False,
        deleted=False,
        source='screenpipe',
    )

    upsert_memory(uid, memory.dict())
    return memory
