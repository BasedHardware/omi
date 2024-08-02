import hashlib
import random
import threading
import uuid
from typing import Union

from fastapi import APIRouter, Depends, HTTPException

import database.memories as memories_db
from database.vector import upsert_vector, delete_vector, upsert_vectors
from models.memory import *
from models.plugin import Plugin
from models.transcript_segment import TranscriptSegment
from routers.plugins import get_plugins_data
from utils import auth
from utils.llm import generate_embedding, get_transcript_structure, get_plugin_result
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
    return memory


@router.post("/v1/memories", response_model=CreateMemoryResponse, tags=['memories'])
def create_memory(create_memory: CreateMemory, language_code: str, uid: str = Depends(auth.get_current_user_uid)):
    memory = _process_memory(uid, language_code, create_memory)
    results = trigger_external_integrations(uid, memory)  # TODO: include as part of plugin response
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
    if memory is None or memory.get('deleted', False):
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.delete("/v1/memories/{memory_id}", status_code=204, tags=['memories'])
def delete_memory(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
    memories_db.delete_memory(uid, memory_id)
    delete_vector(memory_id)
    return {"status": "Ok"}


# ************************************************
# ************ Migrate Local Memories ************
# ************************************************


def _get_structured(memory: dict):
    category = memory['structured']['category']
    if category not in CategoryEnum.__members__:
        category = 'other'
    emoji = memory['structured'].get('emoji')
    return Structured(
        title=memory['structured']['title'],
        overview=memory['structured']['overview'],
        emoji=emoji.encode('latin1').decode('utf-8') if emoji else random.choice(['🧠', '🎉']),
        category=CategoryEnum[category],
        action_items=[
            ActionItem(description=description, completed=False) for description in
            memory['structured']['actionItems']
        ],
        events=[
            Event(
                title=event['title'],
                description=event['description'],
                start=datetime.fromisoformat(event['startsAt']),
                duration=event['duration'],
                created=False,
            ) for event in memory['structured']['events']
        ],
    )


def _get_geolocation(memory: dict):
    geolocation = memory.get('geoLocation', {})
    if geolocation and geolocation.get('googlePlaceId'):
        geolocation_obj = Geolocation(
            google_place_id=geolocation['googlePlaceId'],
            latitude=geolocation['latitude'],
            longitude=geolocation['longitude'],
            altitude=geolocation['altitude'],
            accuracy=geolocation['accuracy'],
            address=geolocation['address'],
            location_type=geolocation['locationType'],
        )
    else:
        geolocation_obj = None
    return geolocation_obj


def generate_uuid4_from_seed(seed):
    # Use SHA-256 to hash the seed
    hash_object = hashlib.sha256(seed.encode('utf-8'))
    hash_digest = hash_object.hexdigest()
    return uuid.UUID(hash_digest[:32])


def upload_memory_vectors(uid: str, memories: List[Memory]):
    if not memories:
        return
    vectors = [generate_embedding(str(memory.structured)) for memory in memories]
    upsert_vectors(uid, vectors, memories)


@router.post('/v1/migration/memories', tags=['v1'])
def migrate_local_memories(memories: List[dict], uid: str = Depends(auth.get_current_user_uid)):
    if not memories:
        return {'status': 'ok'}
    memories_vectors = []
    db_batch = memories_db.get_memories_batch_operation()
    for i, memory in enumerate(memories):
        structured_obj = _get_structured(memory)
        # print(structured_obj)
        memory_obj = Memory(
            id=str(generate_uuid4_from_seed(f'{uid}-{memory["createdAt"]}')),
            uid=uid,
            structured=structured_obj,
            created_at=datetime.fromisoformat(memory['createdAt']),
            started_at=datetime.fromisoformat(memory['startedAt']) if memory['startedAt'] else None,
            finished_at=datetime.fromisoformat(memory['finishedAt']) if memory['finishedAt'] else None,
            transcript=memory['transcript'],
            discarded=memory['discarded'],
            transcript_segments=[
                TranscriptSegment(
                    text=segment['text'],
                    start=segment['start'],
                    end=segment['end'],
                    speaker=segment['speaker'],
                    speaker_id=segment['speaker_id'],
                    is_user=segment['is_user'],
                ) for segment in memory['transcriptSegments']
            ],
            plugins_results=[
                PluginResult(plugin_id=result.get('pluginId'), content=result['content'])
                for result in memory['pluginsResponse']
            ],
            photos=[
                # TODO: test migrating photos
                MemoryPhoto(description=photo['description'], base64=photo['base64']) for photo in memory['photos']
            ],
            geolocation=_get_geolocation(memory),
            deleted=False,
        )
        memories_db.add_memory_to_batch(db_batch, uid, memory_obj.dict())

        if not memory_obj.discarded:
            memories_vectors.append(memory_obj)

        if i % 10 == 0:
            threading.Thread(target=upload_memory_vectors, args=(uid, memories_vectors[:])).start()
            memories_vectors = []

        if i % 100 == 0:
            db_batch.commit()
            db_batch = memories_db.get_memories_batch_operation()

    db_batch.commit()
    threading.Thread(target=upload_memory_vectors, args=(uid, memories_vectors[:])).start()
    return {}
