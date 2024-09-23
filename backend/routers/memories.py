from fastapi import APIRouter, Depends, HTTPException

import database.memories as memories_db
import database.redis_db as redis_db
from database.vector_db import delete_vector
from models.memory import *
from routers.speech_profile import expand_speech_profile
from utils.memories.location import get_google_maps_location
from utils.memories.process_memory import process_memory
from utils.other import endpoints as auth
from utils.other.storage import get_memory_recording_if_exists, \
    delete_additional_profile_audio, delete_speech_sample_for_people
from utils.plugins import trigger_external_integrations

router = APIRouter()


def _get_memory_by_id(uid: str, memory_id: str) -> dict:
    memory = memories_db.get_memory(uid, memory_id)
    if memory is None or memory.get('deleted', False):
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.post("/v1/memories", response_model=CreateMemoryResponse, tags=['memories'])
def create_memory(
        create_memory: CreateMemory, trigger_integrations: bool, language_code: Optional[str] = None,
        source: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
    """
    Create Memory endpoint.
    :param source:
    :param create_memory: data to create memory
    :param trigger_integrations: determine if triggering the on_memory_created plugins webhooks.
    :param language_code: language.
    :param uid: user id.
    :return: The new memory created + any messages triggered by on_memory_created integrations.

    TODO: Should receive raw segments by deepgram, instead of the beautified ones? and get beautified on read?
    """
    if not create_memory.transcript_segments and not create_memory.photos:
        raise HTTPException(status_code=400, detail="Transcript segments or photos are required")

    geolocation = create_memory.geolocation
    if geolocation and not geolocation.google_place_id:
        create_memory.geolocation = get_google_maps_location(geolocation.latitude, geolocation.longitude)

    if not language_code:
        language_code = create_memory.language
    else:
        create_memory.language = language_code

    if create_memory.processing_memory_id:
        print(
            f"warn: split-brain in memory (maybe) by forcing new memory creation during processing. uid: {uid}, processing_memory_id: {create_memory.processing_memory_id}")

    memory = process_memory(uid, language_code, create_memory, force_process=source == 'speech_profile_onboarding')
    if not trigger_integrations:
        return CreateMemoryResponse(memory=memory, messages=[])

    if not memory.discarded:
        memories_db.set_postprocessing_status(uid, memory.id, PostProcessingStatus.not_started)
        memory.postprocessing = MemoryPostProcessing(status=PostProcessingStatus.not_started,
                                                     model=PostProcessingModel.fal_whisperx)

    messages = trigger_external_integrations(uid, memory)
    return CreateMemoryResponse(memory=memory, messages=messages)


@router.post('/v1/memories/{memory_id}/reprocess', response_model=Memory, tags=['memories'])
def reprocess_memory(
        memory_id: str, language_code: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
    """
    Whenever a user wants to reprocess a memory, or wants to force process a discarded one
    :return: The updated memory after reprocessing.
    """
    print('')
    memory = memories_db.get_memory(uid, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    memory = Memory(**memory)
    if not language_code:
        language_code = memory.language or 'en'

    return process_memory(uid, language_code, memory, force_process=True)


@router.get('/v1/memories', response_model=List[Memory], tags=['memories'])
def get_memories(limit: int = 100, offset: int = 0, uid: str = Depends(auth.get_current_user_uid)):
    print('get_memories', uid, limit, offset)
    return memories_db.get_memories(uid, limit, offset, include_discarded=True)


@router.get("/v1/memories/{memory_id}", response_model=Memory, tags=['memories'])
def get_memory_by_id(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
    return _get_memory_by_id(uid, memory_id)


@router.get("/v1/memories/{memory_id}/photos", response_model=List[MemoryPhoto], tags=['memories'])
def get_memory_photos(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
    _get_memory_by_id(uid, memory_id)
    return memories_db.get_memory_photos(uid, memory_id)


@router.get(
    "/v1/memories/{memory_id}/transcripts", response_model=Dict[str, List[TranscriptSegment]], tags=['memories']
)
def get_memory_transcripts_by_models(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
    _get_memory_by_id(uid, memory_id)
    return memories_db.get_memory_transcripts_by_model(uid, memory_id)


@router.delete("/v1/memories/{memory_id}", status_code=204, tags=['memories'])
def delete_memory(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
    print('delete_memory', memory_id, uid)
    memories_db.delete_memory(uid, memory_id)
    delete_vector(memory_id)
    return {"status": "Ok"}


@router.get("/v1/memories/{memory_id}/recording", response_model=dict, tags=['memories'])
def memory_has_audio_recording(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
    _get_memory_by_id(uid, memory_id)
    return {'has_recording': get_memory_recording_if_exists(uid, memory_id) is not None}


@router.patch("/v1/memories/{memory_id}/events", response_model=dict, tags=['memories'])
def set_memory_events_state(
        memory_id: str, data: SetMemoryEventsStateRequest, uid: str = Depends(auth.get_current_user_uid)
):
    memory = _get_memory_by_id(uid, memory_id)
    memory = Memory(**memory)
    events = memory.structured.events
    for i, event_idx in enumerate(data.events_idx):
        if event_idx >= len(events):
            continue
        events[event_idx].created = data.values[i]

    memories_db.update_memory_events(uid, memory_id, [event.dict() for event in events])
    return {"status": "Ok"}


@router.patch('/v1/memories/{memory_id}/segments/{segment_idx}/assign', response_model=Memory, tags=['memories'])
def set_assignee_memory_segment(
        memory_id: str, segment_idx: int, assign_type: str, value: Optional[str] = None,
        use_for_speech_training: bool = True, uid: str = Depends(auth.get_current_user_uid)
):
    """
    Another complex endpoint.

    Modify the assignee of a segment in the transcript of a memory.
    But,
    if `use_for_speech_training` is True, the corresponding audio segment will be used for speech training.

    Speech training of whom?

    If `assign_type` is 'is_user', the segment will be used for the user speech training.
    If `assign_type` is 'person_id', the segment will be used for the person with the given id speech training.

    What is required for a segment to be used for speech training?
    1. The segment must have more than 5 words.
    2. The memory audio file shuold be already stored in the user's bucket.

    :return: The updated memory.
    """
    print('set_assignee_memory_segment', memory_id, segment_idx, assign_type, value, use_for_speech_training, uid)
    memory = _get_memory_by_id(uid, memory_id)
    memory = Memory(**memory)

    if value == 'null':
        value = None

    is_unassigning = value is None or value is False

    if assign_type == 'is_user':
        memory.transcript_segments[segment_idx].is_user = bool(value) if value is not None else False
        memory.transcript_segments[segment_idx].person_id = None
    elif assign_type == 'person_id':
        memory.transcript_segments[segment_idx].is_user = False
        memory.transcript_segments[segment_idx].person_id = value
    else:
        print(assign_type)
        raise HTTPException(status_code=400, detail="Invalid assign type")

    memories_db.update_memory_segments(uid, memory_id, [segment.dict() for segment in memory.transcript_segments])
    segment_words = len(memory.transcript_segments[segment_idx].text.split(' '))

    # TODO: can do this async
    if use_for_speech_training and not is_unassigning and segment_words > 5:  # some decent sample at least
        person_id = value if assign_type == 'person_id' else None
        expand_speech_profile(memory_id, uid, segment_idx, assign_type, person_id)
    else:
        path = f'{memory_id}_segment_{segment_idx}.wav'
        delete_additional_profile_audio(uid, path)
        delete_speech_sample_for_people(uid, path)

    return memory


# *********************************************
# ************* SHARING MEMORIES **************
# *********************************************

@router.patch('/v1/memories/{memory_id}/visibility', tags=['memories'])
def set_memory_visibility(
        memory_id: str, value: MemoryVisibility, uid: str = Depends(auth.get_current_user_uid)
):
    print('update_memory_visibility', memory_id, value, uid)
    _get_memory_by_id(uid, memory_id)
    memories_db.set_memory_visibility(uid, memory_id, value)
    if value == MemoryVisibility.private:
        redis_db.remove_memory_to_uid(memory_id)
        redis_db.remove_public_memory(memory_id)
    else:
        redis_db.store_memory_to_uid(memory_id, uid)
        redis_db.add_public_memory(memory_id)

    return {"status": "Ok"}


@router.get("/v1/memories/{memory_id}/shared", response_model=Memory, tags=['memories'])
def get_shared_memory_by_id(memory_id: str):
    uid = redis_db.get_memory_uid(memory_id)
    if not uid:
        raise HTTPException(status_code=404, detail="Memory is private")

    # TODO: include speakers and people matched?
    # TODO: other fields that  shouldn't be included?
    memory = _get_memory_by_id(uid, memory_id)
    visibility = memory.get('visibility', MemoryVisibility.private)
    if not visibility or visibility == MemoryVisibility.private:
        raise HTTPException(status_code=404, detail="Memory is private")
    memory = Memory(**memory)
    memory.geolocation = None
    return memory


@router.get("/v1/public-memories", response_model=List[Memory], tags=['memories'])
def get_public_memories(offset: int = 0, limit: int = 1000):
    memories = redis_db.get_public_memories()
    data = []
    for memory_id in memories:
        uid = redis_db.get_memory_uid(memory_id)
        if not uid:
            continue
        data.append([uid, memory_id])
    # TODO: sort in some way to have proper pagination

    memories = memories_db.run_get_public_memories(data[offset:offset + limit])
    for memory in memories:
        memory['geolocation'] = None
    return memories
