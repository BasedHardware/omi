import os
from typing import Optional

from fastapi import APIRouter, UploadFile, Depends, HTTPException
from pydub import AudioSegment

from database.memories import get_memory, update_memory_segments
from database.redis_db import store_user_speech_profile, store_user_speech_profile_duration, get_user_speech_profile
from models.memory import Memory
from models.other import UploadProfile
from utils.other import endpoints as auth
from utils.other.storage import upload_profile_audio, get_profile_audio_if_exists, get_memory_recording_if_exists, \
    upload_additional_profile_audio, delete_additional_profile_audio, get_additional_profile_recordings, \
    upload_user_person_speech_sample, delete_user_person_speech_sample, get_user_person_speech_samples
from utils.stt.vad import apply_vad_for_speech_profile

router = APIRouter()


@router.get('/v3/speech-profile', tags=['v3'])
def has_speech_profile(uid: str = Depends(auth.get_current_user_uid)):
    return {'has_profile': len(get_user_speech_profile(uid)) > 0}


@router.get('/v4/speech-profile', tags=['v3'])
def get_speech_profile(uid: str = Depends(auth.get_current_user_uid)):
    return {'url': get_profile_audio_if_exists(uid, download=False)}


# ******************************************
# ************* UPLOAD SAMPLE **************
# ******************************************

# Consist of bytes (for initiating deepgram)
# and audio itself, which we use on post-processing to use speechbrain model

@router.post('/v3/upload-bytes', tags=['v3'])
def upload_profile(data: UploadProfile, uid: str = Depends(auth.get_current_user_uid)):
    if data.duration < 10:
        raise HTTPException(status_code=400, detail="Audio duration is too short")
    if data.duration > 120:
        raise HTTPException(status_code=400, detail="Audio duration is too long")

    store_user_speech_profile(uid, data.bytes)
    store_user_speech_profile_duration(uid, data.duration)
    return {'status': 'ok'}


@router.post('/v3/upload-audio', tags=['v3'])
def upload_profile(file: UploadFile, uid: str = Depends(auth.get_current_user_uid)):
    os.makedirs(f'_temp/{uid}', exist_ok=True)
    file_path = f"_temp/{uid}/{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())

    aseg = AudioSegment.from_wav(file_path)
    if aseg.frame_rate != 16000:
        raise HTTPException(status_code=400, detail="Invalid codec, must be opus 16khz.")

    if aseg.duration_seconds < 5 or aseg.duration_seconds > 120:
        raise HTTPException(status_code=400, detail="Audio duration is invalid")

    apply_vad_for_speech_profile(file_path)
    return {"url": upload_profile_audio(file_path, uid)}


# ******************************************************
# ************* SPEECH SAMPLES FROM MEMORY *************
# ******************************************************

def _validate(uid, memory_id):
    memory_recording_path = get_memory_recording_if_exists(uid, memory_id)
    if not memory_recording_path:
        raise HTTPException(status_code=404, detail="Memory recording not found")

    memory = get_memory(uid, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    return memory, memory_recording_path


@router.post('/v3/speech-profile/expand', tags=['v3'])
def expand_speech_profile(
        memory_id: str, segment_idx: int, person_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
    print('expand_speech_profile', memory_id, segment_idx, person_id, uid)

    if person_id is None:
        profile_path = get_profile_audio_if_exists(uid)
        if not profile_path:  # TODO: validate this in front
            raise HTTPException(status_code=404, detail="Speech profile not found")
        os.remove(profile_path)

    memory, memory_recording_path = _validate(uid, memory_id)

    memory = Memory(**memory)
    segments = memory.transcript_segments
    if person_id:
        segments[segment_idx].person_id = person_id
    else:
        segments[segment_idx].is_user = True

    update_memory_segments(uid, memory_id, [segment.dict() for segment in segments])

    segment = memory.transcript_segments[segment_idx]
    aseg = AudioSegment.from_wav(memory_recording_path)
    segment_aseg = aseg[segment.start * 1000:segment.end * 1000]
    os.remove(memory_recording_path)

    segment_recording_path = f'_temp/{memory_id}_segment_{segment_idx}.wav'
    segment_aseg.export(segment_recording_path, format='wav')

    apply_vad_for_speech_profile(segment_recording_path)
    if person_id:
        upload_user_person_speech_sample(segment_recording_path, uid, person_id)
    else:
        upload_additional_profile_audio(segment_recording_path, uid)
    return {"status": 'ok'}


@router.delete('/v3/speech-profile/expand', tags=['v3'])
def delete_extra_speech_profile_sample(
        memory_id: str, segment_idx: int, person_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
    file_name = f'{memory_id}_segment_{segment_idx}.wav'

    if person_id:
        delete_user_person_speech_sample(uid, person_id, file_name)
    else:
        delete_additional_profile_audio(uid, file_name)

    return {'status': 'ok'}


@router.get('/v3/speech-profile/expand', tags=['v3'])
def get_extra_speech_profile_samples(person_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)):
    if person_id:
        return get_user_person_speech_samples(uid, person_id)
    return get_additional_profile_recordings(uid)
