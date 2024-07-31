import threading
import uuid
from datetime import datetime
from typing import List, Union

from fastapi import APIRouter, Depends, HTTPException

import database.memories as memories_db
from database.vector import upsert_vector, delete_vector
from models.memory import Memory, CreateMemory, PluginResponse, CreateMemoryResponse
from models.plugin import Plugin
from routers.plugins import get_plugins_data
from utils import auth
from utils.llm import generate_embedding, get_transcript_structure, get_plugin_result, advise_post_memory_creation
from utils.plugins import trigger_external_integrations

router = APIRouter()


def _process_memory(uid: str, language_code: str, memory: Union[Memory, CreateMemory], force_process: bool = False):
    transcript = memory.get_transcript()

    structured = get_transcript_structure(transcript, memory.started_at, language_code, force_process)
    discarded = structured.title == ''

    if isinstance(memory, CreateMemory):
        memory = Memory(
            id=str(uuid.uuid4()),
            uid=uid,
            structured=structured,
            **memory.dict(),
            created_at=datetime.utcnow(),
            transcript=transcript,
            discarded=discarded,
            deleted=False,
        )
    else:
        memory.structured = structured
        memory.discarded = discarded
        memory.transcript = transcript

    if not discarded:
        structured_str = str(structured)
        vector = generate_embedding(structured_str)
        upsert_vector(memory.id, vector, uid, structured_str)

        plugins: List[Plugin] = get_plugins_data(uid, include_reviews=False)
        filtered_plugins = [plugin for plugin in plugins if plugin.works_with_memories() and plugin.enabled]
        threads = []

        def execute_plugin(plugin):
            if result := get_plugin_result(transcript, plugin).strip():
                memory.plugins_response.append(PluginResponse(plugin_id=plugin.id, content=result))

        for plugin in filtered_plugins:
            threads.append(threading.Thread(target=execute_plugin, args=(plugin,)))

        [t.start() for t in threads]
        [t.join() for t in threads]

    memories_db.upsert_memory(uid, memory.dict())
    return memory


@router.post("/v1/memories", response_model=CreateMemoryResponse, tags=['memories'])
def create_memory(create_memory: CreateMemory, language_code: str, uid: str = Depends(auth.get_current_user_uid)):
    memory = _process_memory(uid, language_code, create_memory)
    results = trigger_external_integrations(uid, memory)
    if message := advise_post_memory_creation(memory):  # TODO: this should be a plugin
        results['memory-feedback-advisor'] = message
    return CreateMemoryResponse(memory=memory, messages=results)


@router.post('/v1/memories/{memory_id}/reprocess', response_model=Memory, tags=['memories'])
def reprocess_memory(memory_id: str, language_code: str, uid: str = Depends(auth.get_current_user_uid)):
    memory = memories_db.get_memory(uid, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    memory = Memory(**memory)
    return _process_memory(uid, language_code, memory, force_process=True)


@router.get('/v1/memories', response_model=List[Memory], tags=['memories'])
def get_memories(limit: int = 100, offset: int = 0, uid: str = Depends(auth.get_current_user_uid)):
    print('get_memories', uid, limit, offset)
    return memories_db.get_memories(uid, limit, offset, include_discarded=True)


@router.get("/v1/memories/{memory_id}", response_model=Memory, tags=['memories'])
def get_memory_by_id(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
    memory = memories_db.get_memory(uid, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.delete("/v1/memories/{memory_id}", status_code=204, tags=['memories'])
def delete_memory(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
    memories_db.delete_memory(uid, memory_id)
    delete_vector(memory_id)
    return {"status": "Ok"}
