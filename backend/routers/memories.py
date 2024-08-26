import asyncio
import os
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydub import AudioSegment

import database.memories as memories_db
from database.users import get_user_store_recording_permission
from database.vector_db import delete_vector
from models.memory import *
from utils.memories.location import get_google_maps_location
from utils.memories.process_memory import process_memory, process_user_emotion
from utils.other import endpoints as auth
from utils.other.storage import upload_postprocessing_audio, \
    delete_postprocessing_audio, upload_memory_recording, delete_additional_profile_audio
from utils.plugins import trigger_external_integrations
from utils.stt.pre_recorded import fal_whisperx, fal_postprocessing
from utils.stt.speech_profile import get_speech_profile_matching_predictions, get_speech_profile_expanded
from utils.stt.vad import vad_is_empty

router = APIRouter()


def _get_memory_by_id(uid: str, memory_id: str):
    memory = memories_db.get_memory(uid, memory_id)
    if memory is None or memory.get('deleted', False):
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory


@router.post("/v1/memories", response_model=CreateMemoryResponse, tags=['memories'])
def create_memory(
        create_memory: CreateMemory, trigger_integrations: bool, language_code: Optional[str] = None,
        uid: str = Depends(auth.get_current_user_uid)
):
    """
    Create Memory endpoint.
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

    memory = process_memory(uid, language_code, create_memory)
    if not trigger_integrations:
        return CreateMemoryResponse(memory=memory, messages=[])

    messages = trigger_external_integrations(uid, memory)
    return CreateMemoryResponse(memory=memory, messages=messages)


@router.post("/v1/memories/{memory_id}/post-processing", response_model=Memory, tags=['memories'])
def postprocess_memory(
        memory_id: str, file: Optional[UploadFile], emotional_feedback: Optional[bool] = False,
        uid: str = Depends(auth.get_current_user_uid)
):
    """
    The objective of this endpoint, is to get the best possible transcript from the audio file.
    Instead of storing the initial deepgram result, doing a full post-processing with whisper-x.
    This increases the quality of transcript by at least 20%.
    Which also includes a better summarization.
    Which helps us create better vectors for the memory.
    And improves the overall experience of the user.

    TODO: Try Nvidia Nemo ASR as suggested by @jhonnycombs https://huggingface.co/spaces/hf-audio/open_asr_leaderboard
    That + pyannote diarization 3.1, is as good as it gets. Then is only hardware improvements.
    TODO: should consider storing non beautified segments, and beautify on read?
    TODO: post llm process here would be great, sometimes whisper x outputs without punctuation
    """
    memory_data = _get_memory_by_id(uid, memory_id)
    memory = Memory(**memory_data)
    if memory.discarded:
        raise HTTPException(status_code=400, detail="Memory is discarded")

    if memory.postprocessing is not None:
        raise HTTPException(status_code=400, detail="Memory can't be post-processed again")

    file_path = f"_temp/{memory_id}_{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())

    memories_db.set_postprocessing_status(uid, memory.id, PostProcessingStatus.in_progress)

    try:
        # Calling VAD to avoid processing empty parts and getting hallucinations from whisper.
        vad_segments = vad_is_empty(file_path, return_segments=True)
        if vad_segments:
            start = vad_segments[0]['start']
            end = vad_segments[-1]['end']
            aseg = AudioSegment.from_wav(file_path)
            aseg = aseg[max(0, (start - 1) * 1000):min((end + 1) * 1000, aseg.duration_seconds * 1000)]
            aseg.export(file_path, format="wav")
    except Exception as e:
        print(e)

    try:
        aseg = AudioSegment.from_wav(file_path)
        signed_url = upload_postprocessing_audio(file_path)
        threading.Thread(target=_delete_postprocessing_audio, args=(file_path,)).start()

        if get_user_store_recording_permission(uid):
            upload_memory_recording(file_path, uid, memory_id)

        speakers_count = len(set([segment.speaker for segment in memory.transcript_segments]))
        words = fal_whisperx(signed_url, speakers_count)
        segments = fal_postprocessing(words, aseg.duration_seconds)

        if not segments:
            memories_db.set_postprocessing_status(uid, memory.id, PostProcessingStatus.canceled)
            raise HTTPException(status_code=500, detail="FAL WhisperX failed to process audio")

        # if new transcript is 90% shorter than the original, cancel post-processing, smth wrong with audio or FAL
        count = len(''.join([segment.text.strip() for segment in memory.transcript_segments]))
        new_count = len(''.join([segment.text.strip() for segment in segments]))
        print('Prev characters count:', count, 'New characters count:', new_count)
        if new_count < (count * 0.9):
            memories_db.set_postprocessing_status(uid, memory.id, PostProcessingStatus.canceled)
            raise HTTPException(status_code=500, detail="Post-processed transcript is too short")

        # Speech profile matching using speechbrain
        profile_path = get_speech_profile_expanded(uid) if aseg.frame_rate == 16000 else None
        matches = get_speech_profile_matching_predictions(file_path, profile_path, [s.dict() for s in segments])
        for i, segment in enumerate(segments):
            segment.is_user = matches[i]

        # Store previous and new segments in DB as collection.
        memories_db.store_model_segments_result(uid, memory.id, 'deepgram_streaming', memory.transcript_segments)
        memories_db.store_model_segments_result(uid, memory.id, 'fal_whisperx', segments)
        memory.transcript_segments = segments
        memories_db.upsert_memory(uid, memory.dict())  # Store transcript segments at least if smth fails later

        # Reprocess memory with improved transcription
        result = process_memory(uid, memory.language, memory, force_process=True)

        # Process users emotion, async
        if emotional_feedback:
            asyncio.run(_process_user_emotion(uid, memory.language, memory, [signed_url]))
    except Exception as e:
        print(e)
        memories_db.set_postprocessing_status(uid, memory.id, PostProcessingStatus.failed)
        raise HTTPException(status_code=500, detail=str(e))

    memories_db.set_postprocessing_status(uid, memory.id, PostProcessingStatus.completed)
    return result


def _delete_postprocessing_audio(file_path):
    time.sleep(300)  # 5 min
    delete_postprocessing_audio(file_path)
    os.remove(file_path)


async def _process_user_emotion(uid: str, language_code: str, memory: Memory, urls: [str]):
    if not any(segment.is_user for segment in memory.transcript_segments):
        print(f"Users transcript segments is emty. uid: {uid}. memory: {memory.id}")
        return

    process_user_emotion(uid, language_code, memory, urls)


@router.post('/v1/memories/{memory_id}/reprocess', response_model=Memory, tags=['memories'])
def reprocess_memory(
        memory_id: str, language_code: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
    """
    Whenever a user wants to reprocess a memory, or wants to force process a discarded one
    :return: The updated memory after reprocessing.
    """
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


@router.delete("/v1/memories/{memory_id}", status_code=204, tags=['memories'])
def delete_memory(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
    memories_db.delete_memory(uid, memory_id)
    delete_vector(memory_id)
    return {"status": "Ok"}


@router.patch('/v1/memories/{memory_id}/segments/{segment_idx}/is_user', response_model=Memory, tags=['memories'])
def update_memory_segment_is_user(
        memory_id: str, segment_idx: int, value: bool, uid: str = Depends(auth.get_current_user_uid)
):
    memory = _get_memory_by_id(uid, memory_id)
    memory = Memory(**memory)
    memory.transcript_segments[segment_idx].is_user = value
    memories_db.update_memory_segments(uid, memory_id, [segment.dict() for segment in memory.transcript_segments])
    # in case the user selected this as post training.
    delete_additional_profile_audio(uid, f'{memory_id}_segment_{segment_idx}.wav')
    return memory
