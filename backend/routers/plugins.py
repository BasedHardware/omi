from typing import List

import requests
from fastapi import APIRouter, HTTPException, Depends

from models.plugin import Plugin
from utils.other import endpoints as auth
from utils.plugins import get_plugins_data, get_plugin_by_id
from database.redis_db import set_plugin_review, enable_plugin, disable_plugin

router = APIRouter()


@router.post('/v1/plugins/enable')
def enable_plugin_endpoint(plugin_id: str, uid: str = Depends(auth.get_current_user_uid)):
    plugin = get_plugin_by_id(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail='Plugin not found')
    if plugin.works_externally() and plugin.external_integration.setup_completed_url:
        res = requests.get(plugin.external_integration.setup_completed_url + f'?uid={uid}')
        print('enable_plugin_endpoint', res.status_code, res.content)
        if res.status_code != 200 or not res.json().get('is_setup_completed', False):
            raise HTTPException(status_code=400, detail='Plugin setup is not completed')

    enable_plugin(uid, plugin_id)
    return {'status': 'ok'}


@router.post('/v1/plugins/disable')
def disable_plugin_endpoint(plugin_id: str, uid: str = Depends(auth.get_current_user_uid)):
    plugin = get_plugin_by_id(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail='Plugin not found')
    disable_plugin(uid, plugin_id)
    return {'status': 'ok'}


@router.get('/plugins')  # No auth while migration happens for all.
def get_plugins(uid: str):
    return get_plugins_data(uid, include_reviews=True)


@router.get('/v1/plugins', tags=['v1'])
def get_plugins(uid: str):
    return get_plugins_data(uid, include_reviews=True)


@router.get('/v2/plugins', tags=['v1'], response_model=List[Plugin])
def get_plugins(uid: str = Depends(auth.get_current_user_uid)):
    return get_plugins_data(uid, include_reviews=True)


@router.post('/v1/plugins/review', tags=['v1'])
def review_plugin(plugin_id: str, data: dict, uid: str = Depends(auth.get_current_user_uid)):
    if 'score' not in data:
        raise HTTPException(status_code=422, detail='Score is required')

    plugin = next(filter(lambda x: x.id == plugin_id, get_plugins_data(uid)), None)
    if not plugin:
        raise HTTPException(status_code=404, detail='Plugin not found')

    score = data['score']
    review = data.get('review', '')
    set_plugin_review(plugin_id, uid, score, review)
    return {'status': 'ok'}
