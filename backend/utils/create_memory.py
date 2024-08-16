import threading
import uuid
from typing import Union

from fastapi import HTTPException

import database.memories as memories_db
from database.vector import upsert_vector
from models.memory import *
from models.plugin import Plugin
from utils.llm import summarize_open_glass, discard_memory, get_transcript_structure, generate_embedding, \
    get_plugin_result
from utils.plugins import get_plugins_data
from utils.stt.fal import fal_whisperx


def _get_structured(
        uid: str, language_code: str, memory: Union[Memory, CreateMemory], force_process: bool = False, retries: int = 1
) -> Structured:
    transcript = memory.get_transcript()
    has_audio = isinstance(memory, CreateMemory) and memory.audio_base64_url

    try:
        if memory.photos:
            structured: Structured = summarize_open_glass(memory.photos)
        else:
            if has_audio and not discard_memory(transcript):
                # TODO: test a 1h or 2h recording ~ should this be async ~~ also, how long does it take on frontend to upload that size?
                segments = fal_whisperx(memory.audio_base64_url)
                memory.transcript_segments = segments

            structured: Structured = get_transcript_structure(
                transcript, memory.started_at, language_code, force_process
            )
    except Exception as e:
        print(e)
        if retries == 2:
            raise HTTPException(status_code=500, detail="Error processing memory, please try again later")
        return _get_structured(uid, language_code, memory, force_process, retries + 1)
    return structured


def _get_memory_obj(uid: str, structured: Structured, memory: Union[Memory, CreateMemory], transcript: str):
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
        if memory.photos:
            memories_db.store_memory_photos(uid, memory.id, memory.photos)
    else:
        memory.structured = structured
        memory.discarded = discarded

    return memory


def process_memory(uid: str, language_code: str, memory: Union[Memory, CreateMemory], force_process: bool = False):
    transcript = memory.get_transcript()
    structured: Structured = _get_structured(uid, language_code, memory, force_process)
    memory = _get_memory_obj(uid, structured, memory, transcript)

    discarded = structured.title == ''
    if not discarded:
        structured_str = str(structured)
        vector = generate_embedding(structured_str)
        upsert_vector(uid, memory, vector)

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

    memories_db.upsert_memory(uid, memory.dict())
    print('Memory processed', memory.id)
    return memory
