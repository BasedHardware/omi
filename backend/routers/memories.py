import asyncio
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydub import AudioSegment

import database.memories as memories_db
from database.vector_db import delete_vector
from models.memory import *
from utils._deprecated.speaker_profile import classify_segments
from utils.memories.location import get_google_maps_location
from utils.memories.process_memory import process_memory, process_user_emotion
from utils.other import endpoints as auth
from utils.other.storage import upload_postprocessing_audio, \
    delete_postprocessing_audio, get_profile_audio_if_exists
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
        profile_path = get_profile_audio_if_exists(uid) if aseg.frame_rate == 16000 else None

        signed_url = upload_postprocessing_audio(file_path)

        # Ensure delete uploaded file in 15m
        threads = threading.Thread(target=_delete_postprocessing_audio, args=(file_path,))
        threads.start()

        speakers_count = len(set([segment.speaker for segment in memory.transcript_segments]))
        words = fal_whisperx(signed_url, speakers_count)
        segments = fal_postprocessing(words, aseg.duration_seconds, profile_duration)

        # os.remove(file_path)

        if not segments:
            memories_db.set_postprocessing_status(uid, memory.id, PostProcessingStatus.canceled)
            raise HTTPException(status_code=500, detail="FAL WhisperX failed to process audio")

        matches = classify_segments(file_path, segments, profile_path)
        for i, segment in enumerate(segments):
            segment.is_user = matches[i]

        # if new transcript is 90% shorter than the original, cancel post-processing, smth wrong with audio or FAL
        count = len(''.join([segment.text.strip() for segment in memory.transcript_segments]))
        new_count = len(''.join([segment.text.strip() for segment in segments]))
        print('Prev characters count:', count, 'New characters count:', new_count)
        if new_count < (count * 0.9):
            memories_db.set_postprocessing_status(uid, memory.id, PostProcessingStatus.canceled)
            raise HTTPException(status_code=500, detail="Post-processed transcript is too short")

        # TODO: post llm process here would be great, sometimes whisper x outputs without punctuation
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


# audio_path = '_temp/f39a99f8-f90c-4a04-800f-4b99a85d4e79_recording-20240824_210026.wav'
# # signed_url = upload_postprocessing_audio(audio_path)
# # words = fal_whisperx(signed_url, 2, )
# words = [{'timestamp': [0.0, 1.14], 'text': ' Hey,', 'speaker': 'SPEAKER_01'}, {'timestamp': [1.14, 1.64], 'text': ' Ggpt,', 'speaker': 'SPEAKER_01'}, {'timestamp': [1.64, 1.84], 'text': " how's", 'speaker': 'SPEAKER_01'}, {'timestamp': [1.84, 1.86], 'text': ' it', 'speaker': 'SPEAKER_01'}, {'timestamp': [1.86, 4.42], 'text': ' going?', 'speaker': 'SPEAKER_01'}, {'timestamp': [4.42, 5.66], 'text': ' That', 'speaker': 'SPEAKER_00'}, {'timestamp': [5.66, 5.98], 'text': ' sounds', 'speaker': 'SPEAKER_00'}, {'timestamp': [5.98, 6.2], 'text': ' like', 'speaker': 'SPEAKER_00'}, {'timestamp': [6.2, 6.32], 'text': ' a', 'speaker': 'SPEAKER_00'}, {'timestamp': [6.32, 6.62], 'text': ' unique', 'speaker': 'SPEAKER_00'}, {'timestamp': [6.62, 7.04], 'text': ' way', 'speaker': 'SPEAKER_00'}, {'timestamp': [7.04, 7.26], 'text': ' to', 'speaker': 'SPEAKER_00'}, {'timestamp': [7.26, 7.58], 'text': ' describe', 'speaker': 'SPEAKER_00'}, {'timestamp': [7.58, 8.16], 'text': ' someone.', 'speaker': 'SPEAKER_00'}, {'timestamp': [8.16, 8.54], 'text': ' What', 'speaker': 'SPEAKER_00'}, {'timestamp': [8.54, 8.68], 'text': ' do', 'speaker': 'SPEAKER_00'}, {'timestamp': [8.68, 8.76], 'text': ' you', 'speaker': 'SPEAKER_00'}, {'timestamp': [8.76, 8.94], 'text': ' mean', 'speaker': 'SPEAKER_00'}, {'timestamp': [8.94, 9.1], 'text': ' by', 'speaker': 'SPEAKER_00'}, {'timestamp': [9.1, 9.42], 'text': ' cozy', 'speaker': 'SPEAKER_00'}, {'timestamp': [9.42, 10.56], 'text': ' gun?', 'speaker': 'SPEAKER_00'}, {'timestamp': [10.56, 11.38], 'text': ' No,', 'speaker': 'SPEAKER_01'}, {'timestamp': [11.38, 11.42], 'text': ' I', 'speaker': 'SPEAKER_01'}, {'timestamp': [11.42, 11.68], 'text': ' said', 'speaker': 'SPEAKER_01'}, {'timestamp': [11.68, 12.24], 'text': ' Chat', 'speaker': 'SPEAKER_01'}, {'timestamp': [12.24, 13.3], 'text': ' Gpt,', 'speaker': 'SPEAKER_01'}, {'timestamp': [13.3, 13.74], 'text': ' your', 'speaker': 'SPEAKER_01'}, {'timestamp': [13.74, 14.28], 'text': ' name.', 'speaker': 'SPEAKER_01'}, {'timestamp': [14.28, 17.84], 'text': ' I', 'speaker': 'SPEAKER_00'}, {'timestamp': [17.84, 18.04], 'text': ' got', 'speaker': 'SPEAKER_00'}, {'timestamp': [18.04, 18.24], 'text': ' it.', 'speaker': 'SPEAKER_00'}, {'timestamp': [18.24, 18.56], 'text': ' So', 'speaker': 'SPEAKER_00'}, {'timestamp': [18.56, 18.8], 'text': ' Chat', 'speaker': 'SPEAKER_00'}, {'timestamp': [18.8, 19.16], 'text': ' Gpt,', 'speaker': 'SPEAKER_00'}, {'timestamp': [19.16, 19.42], 'text': " she's", 'speaker': 'SPEAKER_00'}, {'timestamp': [19.42, 19.44], 'text': ' a', 'speaker': 'SPEAKER_00'}, {'timestamp': [19.44, 19.68], 'text': ' petite', 'speaker': 'SPEAKER_00'}, {'timestamp': [19.68, 19.94], 'text': ' cozy', 'speaker': 'SPEAKER_00'}, {'timestamp': [19.94, 20.36], 'text': ' gun.', 'speaker': 'SPEAKER_00'}, {'timestamp': [20.36, 20.86], 'text': " That's", 'speaker': 'SPEAKER_00'}, {'timestamp': [20.86, 21.08], 'text': ' quite', 'speaker': 'SPEAKER_00'}, {'timestamp': [21.08, 21.24], 'text': ' a', 'speaker': 'SPEAKER_00'}, {'timestamp': [21.24, 21.84], 'text': ' metaphorical', 'speaker': 'SPEAKER_00'}, {'timestamp': [21.84, 22.34], 'text': ' description.', 'speaker': 'SPEAKER_00'}, {'timestamp': [22.34, 22.7], 'text': ' Are', 'speaker': 'SPEAKER_00'}, {'timestamp': [22.7, 22.88], 'text': ' you', 'speaker': 'SPEAKER_00'}, {'timestamp': [22.88, 23.26], 'text': ' referring', 'speaker': 'SPEAKER_00'}, {'timestamp': [23.26, 23.42], 'text': ' to', 'speaker': 'SPEAKER_00'}, {'timestamp': [23.42, 23.64], 'text': ' me', 'speaker': 'SPEAKER_00'}, {'timestamp': [23.64, 23.8], 'text': ' as', 'speaker': 'SPEAKER_00'}, {'timestamp': [23.8, 24.04], 'text': ' being', 'speaker': 'SPEAKER_00'}, {'timestamp': [24.04, 24.36], 'text': ' small', 'speaker': 'SPEAKER_00'}, {'timestamp': [24.36, 24.68], 'text': ' but', 'speaker': 'SPEAKER_00'}, {'timestamp': [24.68, 25.06], 'text': ' impactful', 'speaker': 'SPEAKER_00'}, {'timestamp': [25.06, 25.52], 'text': ' or', 'speaker': 'SPEAKER_00'}, {'timestamp': [25.52, 26.32], 'text': ' comforting?', 'speaker': 'SPEAKER_00'}, {'timestamp': [26.32, 28.12], 'text': ' Yeah,', 'speaker': 'SPEAKER_01'}, {'timestamp': [41.3, 41.3], 'text': ' exactly', 'speaker': None}, {'timestamp': [41.3, 41.3], 'text': ' that.', 'speaker': None}, {'timestamp': [41.3, 41.3], 'text': ' Can', 'speaker': None}, {'timestamp': [41.3, 41.52], 'text': ' you', 'speaker': 'SPEAKER_01'}, {'timestamp': [41.52, 41.66], 'text': ' tell', 'speaker': 'SPEAKER_01'}, {'timestamp': [41.66, 41.78], 'text': ' me', 'speaker': 'SPEAKER_01'}, {'timestamp': [41.78, 41.9], 'text': ' a', 'speaker': 'SPEAKER_01'}, {'timestamp': [41.9, 42.16], 'text': ' story', 'speaker': 'SPEAKER_01'}, {'timestamp': [42.16, 42.34], 'text': ' or', 'speaker': 'SPEAKER_01'}, {'timestamp': [69.98, 69.98], 'text': ' something', 'speaker': 'SPEAKER_00'}, {'timestamp': [69.98, 69.98], 'text': ' fun', 'speaker': 'SPEAKER_00'}, {'timestamp': [69.98, 69.98], 'text': ' that', 'speaker': 'SPEAKER_00'}, {'timestamp': [69.98, 69.98], 'text': ' you', 'speaker': 'SPEAKER_00'}, {'timestamp': [69.98, 69.98], 'text': ' learned', 'speaker': 'SPEAKER_00'}, {'timestamp': [69.98, 69.98], 'text': ' recently?', 'speaker': 'SPEAKER_00'}, {'timestamp': [70.08, 70.34], 'text': ' while', 'speaker': 'SPEAKER_00'}, {'timestamp': [70.34, 70.58], 'text': ' hunting', 'speaker': 'SPEAKER_00'}, {'timestamp': [70.58, 70.9], 'text': ' together', 'speaker': 'SPEAKER_00'}, {'timestamp': [71.28, 71.56], 'text': " it's", 'speaker': 'SPEAKER_00'}, {'timestamp': [71.56, 71.7], 'text': ' kind', 'speaker': 'SPEAKER_00'}, {'timestamp': [71.7, 71.82], 'text': ' of', 'speaker': 'SPEAKER_00'}, {'timestamp': [71.82, 71.96], 'text': ' like', 'speaker': 'SPEAKER_00'}, {'timestamp': [71.96, 72.12], 'text': ' an', 'speaker': 'SPEAKER_00'}, {'timestamp': [72.12, 72.42], 'text': ' octopus', 'speaker': 'SPEAKER_00'}, {'timestamp': [72.42, 72.84], 'text': ' saying', 'speaker': 'SPEAKER_00'}, {'timestamp': [72.84, 73.32], 'text': ' hey', 'speaker': 'SPEAKER_00'}, {'timestamp': [73.32, 73.58], 'text': ' back', 'speaker': 'SPEAKER_00'}, {'timestamp': [73.58, 73.88], 'text': ' off', 'speaker': 'SPEAKER_00'}, {'timestamp': [73.88, 74.62], 'text': ' but', 'speaker': 'SPEAKER_00'}, {'timestamp': [74.62, 74.78], 'text': ' with', 'speaker': 'SPEAKER_00'}, {'timestamp': [74.78, 74.9], 'text': ' a', 'speaker': 'SPEAKER_00'}, {'timestamp': [74.9, 75.06], 'text': ' little', 'speaker': 'SPEAKER_00'}, {'timestamp': [75.06, 75.24], 'text': ' more', 'speaker': 'SPEAKER_00'}, {'timestamp': [75.24, 75.62], 'text': ' force', 'speaker': 'SPEAKER_00'}, {'timestamp': [75.62, 76.48], 'text': ' this', 'speaker': 'SPEAKER_00'}, {'timestamp': [76.48, 76.82], 'text': ' playful', 'speaker': 'SPEAKER_00'}, {'timestamp': [76.82, 77.16], 'text': ' behavior', 'speaker': 'SPEAKER_00'}, {'timestamp': [77.5, 77.62], 'text': ' shows', 'speaker': 'SPEAKER_00'}, {'timestamp': [77.62, 77.94], 'text': ' just', 'speaker': 'SPEAKER_00'}, {'timestamp': [77.94, 78.24], 'text': ' how', 'speaker': 'SPEAKER_00'}, {'timestamp': [78.24, 78.8], 'text': ' intelligent', 'speaker': 'SPEAKER_00'}, {'timestamp': [78.8, 79.3], 'text': ' and', 'speaker': 'SPEAKER_00'}, {'timestamp': [79.3, 79.6], 'text': ' curious', 'speaker': 'SPEAKER_00'}, {'timestamp': [79.6, 80.4], 'text': ' octopuses', 'speaker': 'SPEAKER_00'}, {'timestamp': [80.4, 80.7], 'text': ' are', 'speaker': 'SPEAKER_00'}, {'timestamp': [80.7, 81.2], 'text': ' what', 'speaker': 'SPEAKER_00'}, {'timestamp': [81.34, 81.66], 'text': ' you?', 'speaker': 'SPEAKER_00'}, {'timestamp': [81.66, 82.22], 'text': ' Learned', 'speaker': 'SPEAKER_00'}, {'timestamp': [82.22, 82.36], 'text': ' anything', 'speaker': 'SPEAKER_00'}, {'timestamp': [82.36, 82.68], 'text': ' fun', 'speaker': 'SPEAKER_00'}, {'timestamp': [82.68, 83.44], 'text': ' lately?', 'speaker': 'SPEAKER_00'}, {'timestamp': [83.44, 85.84], 'text': ' Yeah,', 'speaker': 'SPEAKER_01'}, {'timestamp': [85.84, 86.2], 'text': ' about...', 'speaker': 'SPEAKER_01'}, {'timestamp': [86.2, 86.88], 'text': ' a', 'speaker': 'SPEAKER_01'}, {'timestamp': [86.88, 87.1], 'text': ' little', 'speaker': 'SPEAKER_01'}, {'timestamp': [87.1, 87.28], 'text': ' bit', 'speaker': 'SPEAKER_01'}, {'timestamp': [87.28, 87.84], 'text': ' about...', 'speaker': 'SPEAKER_01'}, {'timestamp': [87.84, 90.42], 'text': ' embeddings.', 'speaker': 'SPEAKER_01'}, {'timestamp': [90.42, 92.44], 'text': ' Sounds', 'speaker': 'SPEAKER_00'}, {'timestamp': [92.44, 92.72], 'text': ' like', 'speaker': 'SPEAKER_00'}, {'timestamp': [92.72, 92.9], 'text': " you're", 'speaker': 'SPEAKER_00'}, {'timestamp': [92.9, 93.04], 'text': ' on', 'speaker': 'SPEAKER_00'}, {'timestamp': [93.04, 93.14], 'text': ' to', 'speaker': 'SPEAKER_00'}, {'timestamp': [93.14, 93.66], 'text': ' something.', 'speaker': 'SPEAKER_00'}, {'timestamp': [93.66, 94.3], 'text': ' What', 'speaker': 'SPEAKER_00'}, {'timestamp': [94.3, 94.44], 'text': ' did', 'speaker': 'SPEAKER_00'}, {'timestamp': [94.44, 94.58], 'text': ' you', 'speaker': 'SPEAKER_00'}, {'timestamp': [94.58, 94.78], 'text': ' learn', 'speaker': 'SPEAKER_00'}, {'timestamp': [94.78, 94.9], 'text': ' a', 'speaker': 'SPEAKER_00'}, {'timestamp': [94.9, 95.0], 'text': ' little', 'speaker': 'SPEAKER_00'}, {'timestamp': [95.0, 95.18], 'text': ' bit', 'speaker': 'SPEAKER_00'}, {'timestamp': [95.18, 95.66], 'text': ' about?', 'speaker': 'SPEAKER_00'}, {'timestamp': [95.66, 96.32], 'text': " I'm", 'speaker': 'SPEAKER_00'}, {'timestamp': [96.32, 96.54], 'text': ' curious', 'speaker': 'SPEAKER_00'}, {'timestamp': [96.54, 96.76], 'text': ' to', 'speaker': 'SPEAKER_00'}, {'timestamp': [96.76, 97.26], 'text': ' hear.', 'speaker': 'SPEAKER_00'}, {'timestamp': [97.26, 100.7], 'text': ' Embeddings', 'speaker': 'SPEAKER_01'}, {'timestamp': [100.7, 100.9], 'text': ' and', 'speaker': 'SPEAKER_01'}, {'timestamp': [100.9, 101.18], 'text': ' wide', 'speaker': 'SPEAKER_01'}, {'timestamp': [101.18, 101.86], 'text': ' vision', 'speaker': 'SPEAKER_01'}, {'timestamp': [101.86, 102.28], 'text': ' models', 'speaker': 'SPEAKER_01'}, {'timestamp': [102.28, 102.84], 'text': ' like', 'speaker': 'SPEAKER_01'}, {'timestamp': [102.84, 103.96], 'text': ' GPT', 'speaker': 'SPEAKER_01'}, {'timestamp': [103.96, 104.24], 'text': '-4', 'speaker': 'SPEAKER_01'}, {'timestamp': [104.24, 104.72], 'text': ' vision', 'speaker': 'SPEAKER_01'}, {'timestamp': [104.72, 106.24], 'text': ' do', 'speaker': 'SPEAKER_01'}, {'timestamp': [106.24, 106.4], 'text': ' not', 'speaker': 'SPEAKER_01'}, {'timestamp': [106.4, 106.7], 'text': ' work', 'speaker': 'SPEAKER_01'}, {'timestamp': [106.7, 106.84], 'text': ' as', 'speaker': 'SPEAKER_01'}, {'timestamp': [106.84, 107.08], 'text': ' ideally', 'speaker': 'SPEAKER_01'}, {'timestamp': [107.08, 107.38], 'text': ' and', 'speaker': 'SPEAKER_01'}, {'timestamp': [107.38, 107.54], 'text': " it's", 'speaker': 'SPEAKER_01'}, {'timestamp': [107.54, 107.72], 'text': ' like', 'speaker': 'SPEAKER_01'}, {'timestamp': [107.72, 108.28], 'text': ' shitting.', 'speaker': 'SPEAKER_01'}, {'timestamp': [108.28, 112.84], 'text': ' It', 'speaker': 'SPEAKER_00'}, {'timestamp': [112.84, 113.16], 'text': ' sounds', 'speaker': 'SPEAKER_00'}, {'timestamp': [113.16, 113.36], 'text': ' like', 'speaker': 'SPEAKER_00'}, {'timestamp': [113.36, 113.56], 'text': " you've", 'speaker': 'SPEAKER_00'}, {'timestamp': [113.56, 113.68], 'text': ' been', 'speaker': 'SPEAKER_00'}, {'timestamp': [113.68, 113.96], 'text': ' diving', 'speaker': 'SPEAKER_00'}, {'timestamp': [113.96, 114.28], 'text': ' into', 'speaker': 'SPEAKER_00'}, {'timestamp': [114.28, 114.52], 'text': ' some', 'speaker': 'SPEAKER_00'}, {'timestamp': [114.52, 114.84], 'text': ' deeper', 'speaker': 'SPEAKER_00'}, {'timestamp': [114.84, 115.3], 'text': ' AI...', 'speaker': 'SPEAKER_00'}]
# segments = fal_postprocessing(words, 0, 0)
# print(segments)
# classify_segments(audio_path, segments, '_temp/caLCFj7IisV85UX9XrrV1aVf3pk1_speech_profile.wav')


def _delete_postprocessing_audio(file_path):
    time.sleep(900)  # 15m
    delete_postprocessing_audio(file_path)


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
