import os
from typing import Optional

import av

from fastapi import APIRouter, UploadFile, Depends, HTTPException
from pydub import AudioSegment

from database.redis_db import set_speech_profile_duration
from database.users import set_user_speaker_embedding
from utils.other import endpoints as auth
from utils.other.storage import (
    upload_profile_audio,
    get_profile_audio_if_exists,
    delete_additional_profile_audio,
    get_additional_profile_recordings,
    delete_user_person_speech_sample,
    get_user_person_speech_samples,
    get_user_has_speech_profile,
)
from utils.stt.speaker_embedding import extract_embedding
from utils.stt.vad import apply_vad_for_speech_profile
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get('/v3/speech-profile', tags=['v3'])
def has_speech_profile(uid: str = Depends(auth.get_current_user_uid)):
    return {'has_profile': get_user_has_speech_profile(uid, max_age_days=90)}


@router.get('/v4/speech-profile', tags=['v3'])
def get_speech_profile(uid: str = Depends(auth.get_current_user_uid)):
    return {'url': get_profile_audio_if_exists(uid, download=False)}


# ******************************************
# ************* UPLOAD SAMPLE **************
# ******************************************

# Consist of bytes (for initiating deepgram)
# and audio itself, which we use on post-processing to use speechbrain model


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
        raise HTTPException(status_code=400, detail="Audio duration is invalid (must be 5-120 seconds)")

    apply_vad_for_speech_profile(file_path)

    # Write-ahead: Cache exact duration after VAD processing (use av for fast header-only read)
    with av.open(file_path) as container:
        duration = (float(container.duration) / av.time_base) + 5 if container.duration else 0
    set_speech_profile_duration(uid, duration)

    url = upload_profile_audio(file_path, uid)

    # Extract and store speaker embedding for user identification in listen sessions
    try:
        embedding = extract_embedding(file_path)
        set_user_speaker_embedding(uid, embedding.flatten().tolist())
        logger.info(f"Speech profile: stored speaker embedding for {uid}")
    except Exception as e:
        logger.error(f"Speech profile: failed to extract/store speaker embedding for {uid}: {e}")

    return {"url": url}


# ******************************************************
# ********** SPEECH SAMPLES FROM CONVERSATION **********
# ******************************************************


@router.delete('/v3/speech-profile/expand', tags=['v3'])
def delete_extra_speech_profile_sample(
    memory_id: str, segment_idx: int, person_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
    logger.info(f'delete_extra_speech_profile_sample {memory_id} {segment_idx} {person_id} {uid}')
    file_name = f'{memory_id}_segment_{segment_idx}.wav'
    if person_id == 'null':
        person_id = None

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
