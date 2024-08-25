import os

from fastapi import APIRouter, UploadFile, Depends, HTTPException
from fastapi.responses import FileResponse
from pydub import AudioSegment

from database.redis_db import store_user_speech_profile, store_user_speech_profile_duration, get_user_speech_profile
from models.other import UploadProfile
from utils.other import endpoints as auth
from utils.other.storage import upload_profile_audio, get_profile_audio_if_exists
from utils.stt.vad import vad_is_empty

router = APIRouter()


@router.get('/v3/speech-profile', tags=['v3'])
def has_speech_profile(uid: str = Depends(auth.get_current_user_uid)):
    return {'has_profile': len(get_user_speech_profile(uid)) > 0}


@router.get('/v4/speech-profile', tags=['v3'])
def get_speech_profile(uid: str = Depends(auth.get_current_user_uid)):
    file_path = get_profile_audio_if_exists(uid)
    if file_path:
        return FileResponse(path=file_path, filename=file_path.split("/")[-1], media_type='audio/mpeg')
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


def _trim_speech_profile_audio(file_path: str):
    voice_segments = vad_is_empty(file_path, return_segments=True)
    if len(voice_segments) == 0:
        raise HTTPException(status_code=400, detail="Audio is empty")

    joined_segments = []
    for i, segment in enumerate(voice_segments):
        if joined_segments and (segment['start'] - joined_segments[-1]['end']) < 1:
            joined_segments[-1]['end'] = segment['end']
        else:
            joined_segments.append(segment)

    # trim silence out of file_path, but leave 1 sec of silence within chunks
    trimmed_aseg = AudioSegment.empty()
    for i, segment in enumerate(joined_segments):
        start = segment['start'] * 1000
        end = segment['end'] * 1000
        trimmed_aseg += AudioSegment.from_wav(file_path)[start:end]
        if i < len(joined_segments) - 1:  # is .silent better than adding 1 sec from audio, to make it more natural?
            # trimmed_aseg += AudioSegment.silent(duration=1000)
            trimmed_aseg += AudioSegment.from_wav(file_path)[end:end + 1000]

    trimmed_aseg.export(file_path, format="wav")


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

    _trim_speech_profile_audio(file_path)
    return {"url": upload_profile_audio(file_path, uid)}
