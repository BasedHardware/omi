import os
from typing import Optional

import av

from fastapi import APIRouter, UploadFile, Depends, HTTPException
from pydub import AudioSegment

from database.conversations import get_conversation
from database.redis_db import remove_user_soniox_speech_profile, set_speech_profile_duration
from database.users import (
    get_person,
    get_user_profile,
    is_exists_user,
    set_user_speaker_embedding,
    share_speech_profile,
    revoke_speech_profile_share,
    remove_shared_profile_from_me,
    get_profiles_shared_with_user_details,
    get_users_shared_with,
    get_users_shared_with_details,
)
from models.conversation import Conversation
from models.other import ShareSpeechProfileRequest, UploadProfile
from utils.other import endpoints as auth
from utils.other.storage import (
    upload_profile_audio,
    get_profile_audio_if_exists,
    get_conversation_recording_if_exists,
    upload_additional_profile_audio,
    delete_additional_profile_audio,
    get_additional_profile_recordings,
    upload_user_person_speech_sample,
    delete_user_person_speech_sample,
    get_user_person_speech_samples,
    delete_speech_sample_for_people,
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
    remove_user_soniox_speech_profile(uid)

    try:
        embedding = extract_embedding(file_path)
        set_user_speaker_embedding(uid, embedding.flatten().tolist())
    except Exception as e:
        print(f"Failed to extract speaker embedding during profile upload: {e}", uid)

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


# ******************************************************
# ************ SPEECH PROFILE SHARING ******************
# ******************************************************


@router.post('/v1/speech-profile/share', tags=['v1'])
def api_share_speech_profile(data: ShareSpeechProfileRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Share the current user's speech profile with another user"""
    if data.target_uid == uid:
        raise HTTPException(status_code=400, detail="Cannot share with yourself.")
    profile = get_user_profile(uid)
    if not profile or not profile.get('speaker_embedding'):
        raise HTTPException(status_code=400, detail="No speech profile recorded.")
    if not is_exists_user(data.target_uid):
        raise HTTPException(status_code=404, detail="Target user not found.")
    existing = get_users_shared_with(uid)
    if data.target_uid in existing:
        raise HTTPException(status_code=400, detail="Already shared with this user.")
    share_speech_profile(uid, data.target_uid)
    return {"status": "ok"}


@router.post('/v1/speech-profile/revoke', tags=['v1'])
def api_revoke_speech_profile(data: ShareSpeechProfileRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Revoke a previously shared speech profile"""
    if data.target_uid == uid:
        raise HTTPException(status_code=400, detail="Invalid target user ID.")
    result = revoke_speech_profile_share(uid, data.target_uid)
    if not result:
        raise HTTPException(status_code=404, detail="No active share found.")
    return {"status": "ok"}


@router.post('/v1/speech-profile/remove-shared', tags=['v1'])
def api_remove_shared_profile(data: ShareSpeechProfileRequest, uid: str = Depends(auth.get_current_user_uid)):
    """Allow the current user to remove a speech profile that was shared with them"""
    result = remove_shared_profile_from_me(data.target_uid, uid)
    if not result:
        raise HTTPException(status_code=404, detail="No active share found.")
    return {"status": "ok"}


@router.get('/v1/speech-profile/shared-with-me', tags=['v1'])
def api_get_profiles_shared_with_me(uid: str = Depends(auth.get_current_user_uid)):
    """List users who have shared their speech profile with the current user"""
    owners = get_profiles_shared_with_user_details(uid)
    return {"shared_with_me": owners}


@router.get('/v1/speech-profile/i-have-shared', tags=['v1'])
def api_get_users_i_have_shared_with(uid: str = Depends(auth.get_current_user_uid)):
    """List users with whom the current user has shared their speech profile"""
    shared = get_users_shared_with_details(uid)
    return {"i_have_shared_with": shared}
