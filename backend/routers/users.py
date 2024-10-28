import threading
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException

from database.memories import get_in_progress_memory, get_memory
from database.redis_db import cache_user_geolocation, set_user_webhook_db, get_user_webhook_db, disable_user_webhook_db, \
    enable_user_webhook_db, user_webhook_status_db
from database.users import *
from models.memory import Geolocation, Memory
from models.other import Person, CreatePerson
from models.users import WebhookType
from utils.llm import followup_question_prompt
from utils.other import endpoints as auth
from utils.other.storage import delete_all_memory_recordings, get_user_person_speech_samples, \
    delete_user_person_speech_samples
from utils.webhooks import webhook_first_time_setup

router = APIRouter()


# TODO: url should be /v1/users
@router.delete('/v1/users/delete-account', tags=['v1'])
def delete_account(uid: str = Depends(auth.get_current_user_uid)):
    try:
        delete_user_data(uid)
        # delete user from firebase auth
        auth.delete_account(uid)
        return {'status': 'ok', 'message': 'Account deleted successfully'}
    except Exception as e:
        print('delete_account', str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.patch('/v1/users/geolocation', tags=['v1'])
def set_user_geolocation(geolocation: Geolocation, uid: str = Depends(auth.get_current_user_uid)):
    cache_user_geolocation(uid, geolocation.dict())
    return {'status': 'ok'}


# ***********************************************
# ************* DEVELOPER WEBHOOKS **************
# ***********************************************


@router.post('/v1/users/developer/webhook/{wtype}', tags=['v1'])
def set_user_webhook_endpoint(wtype: WebhookType, data: dict, uid: str = Depends(auth.get_current_user_uid)):
    url = data['url']
    if url == '' or url == ',':
        disable_user_webhook_db(uid, wtype)
    set_user_webhook_db(uid, wtype, url)
    return {'status': 'ok'}


@router.get('/v1/users/developer/webhook/{wtype}', tags=['v1'])
def get_user_webhook_endpoint(wtype: WebhookType, uid: str = Depends(auth.get_current_user_uid)):
    return {'url': get_user_webhook_db(uid, wtype)}

@router.post('/v1/users/developer/webhook/{wtype}/disable', tags=['v1'])
def disable_user_webhook_endpoint(wtype: WebhookType, uid: str = Depends(auth.get_current_user_uid)):
    disable_user_webhook_db(uid, wtype)
    return {'status': 'ok'}


@router.post('/v1/users/developer/webhook/{wtype}/enable', tags=['v1'])
def enable_user_webhook_endpoint(wtype: WebhookType, uid: str = Depends(auth.get_current_user_uid)):
    enable_user_webhook_db(uid, wtype)
    return {'status': 'ok'}


@router.get('/v1/users/developer/webhooks/status', tags=['v1'])
def get_user_webhooks_status(uid: str = Depends(auth.get_current_user_uid)):
    # This only happens the first time because the user_webhook_status_db function will return None for existing users
    audioBytes = user_webhook_status_db(uid, WebhookType.audio_bytes)
    if audioBytes is None:
        audioBytes = webhook_first_time_setup(uid, WebhookType.audio_bytes)
    memoryCreated = user_webhook_status_db(uid, WebhookType.memory_created)
    if memoryCreated is None:
        memoryCreated = webhook_first_time_setup(uid, WebhookType.memory_created)
    realtimeTranscript = user_webhook_status_db(uid, WebhookType.realtime_transcript)
    if realtimeTranscript is None:
        realtimeTranscript = webhook_first_time_setup(uid, WebhookType.realtime_transcript)
    daySummary = user_webhook_status_db(uid, WebhookType.day_summary)
    if daySummary is None:
        daySummary = webhook_first_time_setup(uid, WebhookType.day_summary)
    return {
        'audio_bytes': audioBytes,
        'memory_created': memoryCreated,
        'realtime_transcript': realtimeTranscript,
        'day_summary': daySummary
    }


# *************************************************
# ************* RECORDING PERMISSION **************
# *************************************************

@router.post('/v1/users/store-recording-permission', tags=['v1'])
def store_recording_permission(value: bool, uid: str = Depends(auth.get_current_user_uid)):
    set_user_store_recording_permission(uid, value)
    return {'status': 'ok'}


@router.get('/v1/users/store-recording-permission', tags=['v1'])
def get_store_recording_permission(uid: str = Depends(auth.get_current_user_uid)):
    return {'store_recording_permission': get_user_store_recording_permission(uid)}


@router.delete('/v1/users/store-recording-permission', tags=['v1'])
def delete_permission_and_recordings(uid: str = Depends(auth.get_current_user_uid)):
    set_user_store_recording_permission(uid, False)
    delete_all_memory_recordings(uid)
    return {'status': 'ok'}


# ****************************************
# ************* PEOPLE CRUD **************
# ****************************************

# TODO: consider adding person photo.
@router.post('/v1/users/people', tags=['v1'], response_model=Person)
def create_new_person(data: CreatePerson, uid: str = Depends(auth.get_current_user_uid)):
    data = {
        'id': str(uuid.uuid4()),
        'name': data.name,
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
        'deleted': False,
    }
    result = create_person(uid, data)
    return result


@router.get('/v1/users/people/{person_id}', tags=['v1'], response_model=Person)
def get_single_person(
        person_id: str, include_speech_samples: bool = False, uid: str = Depends(auth.get_current_user_uid)
):
    person = get_person(uid, person_id)
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    if include_speech_samples:
        person['speech_samples'] = get_user_person_speech_samples(uid, person['id'])
    return person


@router.get('/v1/users/people', tags=['v1'], response_model=List[Person])
def get_all_people(include_speech_samples: bool = True, uid: str = Depends(auth.get_current_user_uid)):
    print('get_all_people', include_speech_samples)
    people = get_people(uid)
    if include_speech_samples:
        def single(person):
            person['speech_samples'] = get_user_person_speech_samples(uid, person['id'])

        threads = [threading.Thread(target=single, args=(person,)) for person in people]
        [t.start() for t in threads]
        [t.join() for t in threads]
    return people


@router.patch('/v1/users/people/{person_id}/name', tags=['v1'])
def update_person_name(
        person_id: str,
        value: str,  # = Field(min_length=2, max_length=40),
        uid: str = Depends(auth.get_current_user_uid),
):
    update_person(uid, person_id, value)
    return {'status': 'ok'}


@router.delete('/v1/users/people/{person_id}', tags=['v1'], status_code=204)
def delete_person_endpoint(person_id: str, uid: str = Depends(auth.get_current_user_uid)):
    delete_person(uid, person_id)
    delete_user_person_speech_samples(uid, person_id)
    return {'status': 'ok'}


# **********************************************************
# ************* RANDOM JOAN SPECIFIC FEATURES **************
# **********************************************************


@router.delete('/v1/joan/{memory_id}/followup-question', tags=['v1'], status_code=204)
def delete_person_endpoint(memory_id: str, uid: str = Depends(auth.get_current_user_uid)):
    if memory_id == '0':
        memory = get_in_progress_memory(uid)
        if not memory:
            raise HTTPException(status_code=400, detail='No memory in progres')
    else:
        memory = get_memory(uid, memory_id)
    memory = Memory(**memory)
    return {'result': followup_question_prompt(memory.transcript_segments)}
