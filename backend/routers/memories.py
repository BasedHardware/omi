import hashlib
import os
import random
import threading
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile

import database.memories as memories_db
from database.vector import delete_vector, upsert_vectors
from models.memory import *
from models.transcript_segment import TranscriptSegment
from utils import auth
from utils.llm import generate_embedding, transcript_user_speech_fix
from utils.location import get_google_maps_location
from utils.plugins import trigger_external_integrations
from utils.process_memory import process_memory
from utils.storage import upload_postprocessing_audio, delete_postprocessing_audio
from utils.stt.fal import fal_whisperx

router = APIRouter()


@router.post("/v1/memories", response_model=CreateMemoryResponse, tags=['memories'])
def create_memory(
        create_memory: CreateMemory, trigger_integrations: bool, language_code: Optional[str] = None,
        uid: str = Depends(auth.get_current_user_uid)
):
    if not create_memory.transcript_segments and not create_memory.photos:
        raise HTTPException(status_code=400, detail="Transcript segments or photos are required")

    geolocation = create_memory.geolocation
    if geolocation and not geolocation.google_place_id:
        create_memory.geolocation = get_google_maps_location(geolocation.latitude, geolocation.longitude)

    if not language_code:
        language_code = create_memory.language
    else:
        create_memory.language = language_code

    memory = process_memory(uid, language_code, create_memory)
    if not trigger_integrations:
        return CreateMemoryResponse(memory=memory, messages=[])

    messages = trigger_external_integrations(uid, memory)
    return CreateMemoryResponse(memory=memory, messages=messages)


@router.post("/v1/memories/{memory_id}/post-processing", response_model=Memory, tags=['memories'])
async def postprocess_memory(
        memory_id: str, file: Optional[UploadFile], uid: str = Depends(auth.get_current_user_uid)
):
    """
    The objective of this endpoint, is to get the best possible transcript from the audio file.
    Instead of storing the initial deepgram result, doing a full post-processing with whisper-x.
    This increases the quality of transcript by at least 20%.
    Which also includes a better summarization.
    Which helps us create better vectors for the memory.
    And improves the overall experience of the user.

    TODO: Try Nvidia Nemo ASR as suggested by @jhonnycombs
    https://huggingface.co/spaces/hf-audio/open_asr_leaderboard

    TODO: do soniox here? with speech profile and stuff?
    """

    memory_data = _get_memory_by_id(uid, memory_id)
    # TODO: if transcript too large ignore? or if discarded?

    # TODO: can do VAD and still keep segments?

    file_path = f"_temp/{memory_id}_{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())

    # Upload to GCP + remove file locally and cloud storage
    url = upload_postprocessing_audio(file_path)
    os.remove(file_path)
    segments = fal_whisperx(url)
    delete_postprocessing_audio(file_path)

    memory = Memory(**memory_data)

    # Fix user speaker_id matching
    if any(segment.is_user for segment in memory.transcript_segments):
        prev = TranscriptSegment.segments_as_string(memory.transcript_segments, False)
        new = TranscriptSegment.segments_as_string(segments, False)
        speaker_id: int = transcript_user_speech_fix(prev, new)
        for segment in segments:
            if segment.speaker_id == speaker_id:
                segment.is_user = True

    memory.transcript_segments = segments
    # TODO: post-processing flag or smth in memory
    # TODO: store unprocessed and compare?
    return process_memory(uid, memory.language, memory, force_process=True)


@router.post('/v1/memories/{memory_id}/reprocess', response_model=Memory, tags=['memories'])
def reprocess_memory(
        memory_id: str, language_code: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
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


def _get_memory_by_id(uid: str, memory_id: str):
    memory = memories_db.get_memory(uid, memory_id)
    if memory is None or memory.get('deleted', False):
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.get("/v1/memories/{memory_id}", response_model=Memory, tags=['memories'])
def get_memory_by_id(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
    return _get_memory_by_id(uid, memory_id)


@router.get("/v1/memories/{memory_id}/photos", response_model=List[MemoryPhoto], tags=['memories'])
def get_memory_photos(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
    _get_memory_by_id(uid, memory_id)
    return memories_db.get_memory_photos(uid, memory_id)


@router.delete("/v1/memories/{memory_id}", status_code=204, tags=['memories'])
def delete_memory(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
    memories_db.delete_memory(uid, memory_id)
    delete_vector(memory_id)
    return {"status": "Ok"}
