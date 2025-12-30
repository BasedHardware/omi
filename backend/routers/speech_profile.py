import os
import json
from typing import Optional

import av

from fastapi import APIRouter, UploadFile, Depends, HTTPException
from pydub import AudioSegment

from database.conversations import get_conversation
from database.redis_db import remove_user_soniox_speech_profile, set_speech_profile_duration
from database.users import get_person
from models.conversation import Conversation
from models.other import UploadProfile
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
from utils.stt.vad import apply_vad_for_speech_profile
from database.users import add_shared_person_to_user, remove_shared_person_from_user, get_shared_people, get_person
from database import redis_db

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
    return {"url": url}


# ******************************************************
# ********** SPEECH SAMPLES FROM CONVERSATION **********
# ******************************************************


@router.delete('/v3/speech-profile/expand', tags=['v3'])
def delete_extra_speech_profile_sample(
    memory_id: str, segment_idx: int, person_id: Optional[str] = None, uid: str = Depends(auth.get_current_user_uid)
):
    print('delete_extra_speech_profile_sample', memory_id, segment_idx, person_id, uid)
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


@router.post('/v3/speech-profile/share', tags=['v3'])
def share_speech_profile_with_user(target_uid: str, name: str = None, source_person_id: str = None, uid: str = Depends(auth.get_current_user_uid)):
    """Share the caller's speech profile (embedding+metadata) with another user (target_uid).

    - This will read the caller's profile embedding stored under their people or main profile
      and add a shared_people doc under the target user's account keyed by the caller uid.
    - For now we add a minimal record: source_uid, name, speaker_embedding (if exists), profile_url
    """
    # Load specified person embedding if provided, else try to pick a reasonable source
    person_doc = None
    embedding = []
    profile_url = get_profile_audio_if_exists(uid, download=False)

    if source_person_id:
        person_doc = get_person(uid, source_person_id)
    else:
        try:
            from database.users import get_people

            all_people = get_people(uid)
            if all_people:
                person_doc = all_people[0]
        except Exception:
            person_doc = None

    if person_doc and person_doc.get('speaker_embedding'):
        embedding = person_doc.get('speaker_embedding')

    person_name = name or (person_doc.get('name') if person_doc else 'Unknown')
    add_shared_person_to_user(target_uid, uid, person_name, embedding or [], profile_url)

    # Notify target user's active sessions via Redis pubsub
    try:
        channel = f'users:{target_uid}:shared_profiles'
        payload = {'action': 'add', 'source_uid': uid, 'name': person_name}
        redis_db.r.publish(channel, json.dumps(payload))
    except Exception:
        pass

    return {'status': 'ok'}


@router.post('/v3/speech-profile/revoke', tags=['v3'])
def revoke_speech_profile_from_user(target_uid: str, uid: str = Depends(auth.get_current_user_uid)):
    """Revoke a previously shared speech profile from target_uid (remove shared doc)."""
    success = remove_shared_person_from_user(target_uid, uid)
    try:
        channel = f'users:{target_uid}:shared_profiles'
        payload = {'action': 'remove', 'source_uid': uid}
        redis_db.r.publish(channel, json.dumps(payload))
    except Exception:
        pass
    return {'status': 'ok' if success else 'not_found'}


@router.get('/v3/speech-profile/shared', tags=['v3'])
def list_shared_profiles(uid: str = Depends(auth.get_current_user_uid)):
    """List profiles shared with the current user."""
    shared = get_shared_people(uid)
    return {'shared': shared}
