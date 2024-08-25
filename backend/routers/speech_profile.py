import os

from fastapi import APIRouter, UploadFile, Depends, HTTPException
from fastapi.responses import FileResponse
from pydub import AudioSegment

from database.memories import get_memory, update_memory_segments
from database.redis_db import store_user_speech_profile, store_user_speech_profile_duration, get_user_speech_profile
from models.memory import Memory
from models.other import UploadProfile
from utils.other import endpoints as auth
from utils.other.storage import upload_profile_audio, get_profile_audio_if_exists, get_memory_recording_if_exists, \
    upload_additional_profile_audio, delete_additional_profile_audio
from utils.stt.vad import apply_vad_for_speech_profile

router = APIRouter()


@router.get('/v3/speech-profile', tags=['v3'])
def has_speech_profile(uid: str = Depends(auth.get_current_user_uid)):
    return {'has_profile': len(get_user_speech_profile(uid)) > 0}


@router.get('/v4/speech-profile', tags=['v3'])
def get_speech_profile(uid: str = Depends(auth.get_current_user_uid)):
    file_path = get_profile_audio_if_exists(uid)
    if file_path:
        return FileResponse(path=file_path, filename=file_path.split("/")[-1], media_type='audio/wav')
    raise HTTPException(status_code=404, detail="Speech profile not found")


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


@router.post('/v3/speech-profile/expand', tags=['v3'])
def expand_speech_profile(memory_id: str, segment_idx: int, uid: str = Depends(auth.get_current_user_uid)):
    print('expand_speech_profile', memory_id, segment_idx, uid)
    profile_path = get_profile_audio_if_exists(uid)
    if not profile_path:
        raise HTTPException(status_code=404, detail="Speech profile not found")
    os.remove(profile_path)

    memory_recording_path = get_memory_recording_if_exists(uid, memory_id)
    if not memory_recording_path:
        raise HTTPException(status_code=404, detail="Memory recording not found")

    memory = get_memory(uid, memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Memory not found")

    memory = Memory(**memory)
    segments = memory.transcript_segments
    segments[segment_idx].is_user = True
    update_memory_segments(uid, memory_id, [segment.dict() for segment in segments])

    segment = memory.transcript_segments[segment_idx]
    aseg = AudioSegment.from_wav(memory_recording_path)
    segment_aseg = aseg[segment.start * 1000:segment.end * 1000]
    os.remove(memory_recording_path)

    segment_recording_path = f'_temp/{memory_id}_segment_{segment_idx}.wav'
    segment_aseg.export(segment_recording_path, format='wav')

    if aseg.frame_rate != 16000:
        raise HTTPException(status_code=400, detail="Invalid codec, must be opus 16khz.")

    # if aseg.duration_seconds < 5:
    #     raise HTTPException(status_code=400, detail="Audio duration is too short")

    # if aseg.duration_seconds > 30:
    #     raise HTTPException(status_code=400, detail="Sample duration is too long")

    apply_vad_for_speech_profile(segment_recording_path)
    return {"url": upload_additional_profile_audio(segment_recording_path, uid)}


@router.delete('/v3/speech-profile/expand', tags=['v3'])
def delete_extra_speech_profile_sample(memory_id: str, segment_idx: int, uid: str = Depends(auth.get_current_user_uid)):
    delete_additional_profile_audio(uid, f'{memory_id}_segment_{segment_idx}.wav')
    return {'status': 'ok'}

# @router.get()
