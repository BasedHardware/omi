import os

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydub import AudioSegment

import database.memories as memories_db
from database.vector_db import delete_vector
from models.memory import *
from utils.llm import transcript_user_speech_fix
from utils.memories.location import get_google_maps_location
from utils.memories.process_memory import process_memory
from utils.other import endpoints as auth
from utils.other.storage import upload_postprocessing_audio, delete_postprocessing_audio
from utils.plugins import trigger_external_integrations
from utils.stt.pre_recorded import fal_whisperx, fal_postprocessing
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
        memory_id: str, file: Optional[UploadFile], uid: str = Depends(auth.get_current_user_uid)
):
    """
    The objective of this endpoint, is to get the best possible transcript from the audio file.
    Instead of storing the initial deepgram result, doing a full post-processing with whisper-x.
    This increases the quality of transcript by at least 20%.
    Which also includes a better summarization.
    Which helps us create better vectors for the memory.
    And improves the overall experience of the user.

    TODO: Try Nvidia Nemo ASR as suggested by @jhonnycombs https://huggingface.co/spaces/hf-audio/open_asr_leaderboard
    TODO: USE soniox here? with speech profile and stuff?
    TODO: either do speech profile embeddings or use the profile audio as prefix
    TODO: should consider storing non beautified segments, and beautify on read?
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
        profile_duration = 0

        # if aseg.frame_rate == 16000:  # do not allow pcm8 DOESN'T PERFORM BETTER
        #     if profile_path := get_profile_audio_if_exists(uid):
        #         print('Processing audio with profile')
        #         # join (file_path + profile_path)
        #         profile_aseg = AudioSegment.from_wav(profile_path)
        #         separate_seconds = 30
        #         final = profile_aseg + AudioSegment.silent(duration=separate_seconds * 1000) + aseg
        #         final.export(file_path, format="wav")
        #         profile_duration = profile_aseg.duration_seconds + separate_seconds

        url = upload_postprocessing_audio(file_path)
        speakers_count = len(set([segment.speaker for segment in memory.transcript_segments]))
        words = fal_whisperx(url, speakers_count, aseg.duration_seconds)
        segments = fal_postprocessing(words, aseg.duration_seconds, profile_duration)
        delete_postprocessing_audio(file_path)
        os.remove(file_path)

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

        if any(segment.is_user for segment in memory.transcript_segments):
            prev = TranscriptSegment.segments_as_string(memory.transcript_segments, False)
            new = TranscriptSegment.segments_as_string(segments, False)
            speaker_id: int = transcript_user_speech_fix(prev, new)  # COULD BE TERRIBLE, use with caution
            print('matched speaker_id:', speaker_id)
            # good enough for now

            for segment in segments:
                if segment.speaker_id == speaker_id:
                    segment.is_user = True

        # TODO: post llm process here would be great, sometimes whisper x outputs without punctuation
        # Store previous and new segments in DB as collection.
        memories_db.store_model_segments_result(uid, memory.id, 'deepgram_streaming', memory.transcript_segments)
        memories_db.store_model_segments_result(uid, memory.id, 'fal_whisperx', segments)
        memory.transcript_segments = segments
        memories_db.upsert_memory(uid, memory.dict())  # Store transcript segments at least if smth fails later

        # Reprocess memory with improved transcription
        result = process_memory(uid, memory.language, memory, force_process=True)
    except Exception as e:
        print(e)
        memories_db.set_postprocessing_status(uid, memory.id, PostProcessingStatus.failed)
        raise HTTPException(status_code=500, detail=str(e))

    memories_db.set_postprocessing_status(uid, memory.id, PostProcessingStatus.completed)
    return result


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
