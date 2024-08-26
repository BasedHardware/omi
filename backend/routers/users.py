from fastapi import APIRouter, Depends, HTTPException

import database.facts as facts_db
from database.redis_db import cache_user_name
from database.users import set_user_store_recording_permission, get_user_store_recording_permission
from utils.other import endpoints as auth
from utils.other.storage import delete_all_memory_recordings

router = APIRouter()


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


@router.patch('/v1/users/name', tags=['users'])  # TODO: shouldn't need params, instead shuold retrieve auth values
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


