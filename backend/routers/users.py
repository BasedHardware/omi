import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException

import database.facts as facts_db
from database.redis_db import cache_user_name
from database.users import *
from models.other import Person, CreatePerson
from utils.other import endpoints as auth
from utils.other.storage import delete_all_memory_recordings, get_user_person_speech_samples, \
    delete_user_person_speech_samples

router = APIRouter()


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


# **********************************
# ************* OTHER **************
# **********************************

@router.patch('/v1/users/name', tags=['users'])  # TODO: shouldn't need params, instead should retrieve auth values
def edit_user_name_in_facts(prev: str, new: str, uid: str = Depends(auth.get_current_user_uid)):
    if len(new.split(' ')) > 1:
        raise HTTPException(status_code=400, detail='Name must be a single word')
    if len(new) < 2 or len(new) > 40:
        raise HTTPException(status_code=400, detail='Name must be between 3 and 40 characters')

    cache_user_name(uid, new.capitalize())
    facts = facts_db.get_facts(uid, 1000, 0)
    for fact in facts:
        text = fact['content']
        fact['content'] = text.replace(f'{prev.capitalize()}', f'{new.capitalize()}')
        fact['content'] = text.replace(f'The User', f'{new.capitalize()}').replace(f'User', f'{new.capitalize()}')

    facts_db.save_facts(uid, facts)
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
        'created_at': datetime.utcnow(),
        'updated_at': datetime.utcnow(),
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
def get_all_people(include_speech_samples: bool = False, uid: str = Depends(auth.get_current_user_uid)):
    people = get_people(uid)
    if include_speech_samples:
        for person in people:
            person['speech_samples'] = get_user_person_speech_samples(uid, person['id'])
    return people


@router.patch('/v1/users/people/{person_id}/name', tags=['v1'])
def update_person_name(person_id: str, value: str, uid: str = Depends(auth.get_current_user_uid)):
    update_person(uid, person_id, value)
    return {'status': 'ok'}


@router.delete('/v1/users/people/{person_id}', tags=['v1'], status_code=204)
def delete_person_endpoint(person_id: str, uid: str = Depends(auth.get_current_user_uid)):
    delete_person(uid, person_id)
    delete_user_person_speech_samples(uid, person_id)
    return {'status': 'ok'}
