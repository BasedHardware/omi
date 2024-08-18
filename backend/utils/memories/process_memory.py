import random
import threading
import uuid
from typing import Union

from fastapi import HTTPException

import database.memories as memories_db
from database.vector_db import upsert_vector
from models.memory import *
from models.plugin import Plugin
from utils.llm import summarize_open_glass, get_transcript_structure, generate_embedding, \
    get_plugin_result, should_discard_memory, summarize_experience_text
from utils.plugins import get_plugins_data


def _get_structured(
        uid: str, language_code: str, memory: Union[Memory, CreateMemory, WorkflowCreateMemory],
        force_process: bool = False, retries: int = 1
) -> Structured:
    try:
        if memory.source == MemorySource.workflow:
            if memory.text_source == WorkflowMemorySource.audio:
                structured = get_transcript_structure(memory.text, memory.started_at, language_code)
                return structured, False

            if memory.text_source == WorkflowMemorySource.other:
                structured = summarize_experience_text(memory.text)
                return structured, False

            # not workflow memory source support
            raise HTTPException(status_code=400, detail='Invalid workflow memory source')

        # from OpenGlass
        if memory.photos:
            return summarize_open_glass(memory.photos), False

        # from Friend
        if force_process:
            # reprocess endpoint
            return get_transcript_structure(memory.get_transcript(False), memory.started_at, language_code), False

        discarded = should_discard_memory(memory.get_transcript(False))
        if discarded:
            return Structured(emoji=random.choice(['🧠', '🎉'])), True

        return get_transcript_structure(memory.get_transcript(False), memory.started_at, language_code), False
    except Exception as e:
        print(e)
        if retries == 2:
            raise HTTPException(status_code=500, detail="Error processing memory, please try again later")
        return _get_structured(uid, language_code, memory, force_process, retries + 1)


def _get_memory_obj(uid: str, structured: Structured, memory: Union[Memory, CreateMemory, WorkflowCreateMemory]):
    discarded = structured.title == ''
    if isinstance(memory, CreateMemory):
        memory = Memory(
            id=str(uuid.uuid4()),
            uid=uid,
            structured=structured,
            **memory.dict(),
            created_at=datetime.utcnow(),
            discarded=discarded,
            deleted=False,
        )
        if memory.photos:
            memories_db.store_memory_photos(uid, memory.id, memory.photos)
    elif isinstance(memory, WorkflowCreateMemory):
        create_memory = memory
        memory = Memory(
            id=str(uuid.uuid4()),
            **memory.dict(),
            created_at=datetime.utcnow(),
            deleted=False,
            structured=structured,
            discarded=discarded,
        )
        memory.external_data = create_memory.dict()
    else:
        memory.structured = structured
        memory.discarded = discarded

    return memory


def _trigger_plugins(uid: str, transcript: str, memory: Memory):
    plugins: List[Plugin] = get_plugins_data(uid, include_reviews=False)
    filtered_plugins = [plugin for plugin in plugins if plugin.works_with_memories() and plugin.enabled]
    threads = []

    def execute_plugin(plugin):
        if result := get_plugin_result(transcript, plugin).strip():
            memory.plugins_results.append(PluginResult(plugin_id=plugin.id, content=result))

    for plugin in filtered_plugins:
        threads.append(threading.Thread(target=execute_plugin, args=(plugin,)))

    [t.start() for t in threads]
    [t.join() for t in threads]


def process_memory(uid: str, language_code: str, memory: Union[Memory, CreateMemory, WorkflowCreateMemory],
                   force_process: bool = False):
    structured, discarded = _get_structured(uid, language_code, memory, force_process)
    memory = _get_memory_obj(uid, structured, memory)

    if not discarded:
        vector = generate_embedding(str(structured))
        upsert_vector(uid, memory, vector)
        _trigger_plugins(uid, memory.get_transcript(False), memory)  # async

    memories_db.upsert_memory(uid, memory.dict())
    print('process_memory memory.id=', memory.id)
    return memory
