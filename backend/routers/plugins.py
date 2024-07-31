from fastapi import APIRouter, HTTPException, Depends

from utils import auth
from utils.plugins import get_plugins_data
from utils.redis_utils import set_plugin_review, enable_plugin, disable_plugin

router = APIRouter()


@router.get('/plugins', tags=['plugins'])
def get_plugins(uid: str):
    return get_plugins_data(uid, include_reviews=True)


@router.post('/plugins/review')
def review_plugin(plugin_id: str, uid: str, data: dict):
    if 'score' not in data:
        raise HTTPException(status_code=422, detail='Score is required')

    plugin = next(filter(lambda x: x['id'] == plugin_id, get_plugins_data(uid)), None)
    if not plugin:
        raise HTTPException(status_code=404, detail='Plugin not found')

    score = data['score']
    review = data.get('review', '')
    set_plugin_review(plugin_id, uid, score, review)
    return {'status': 'ok'}


# AUTH

@router.post('/v1/plugins/enable')
def enable_plugin_db(plugin_id: str, uid: str = Depends(auth.get_current_user_uid)):
    enable_plugin(uid, plugin_id)
    return {'status': 'ok'}


@router.post('/v1/plugins/disable')
def disable_plugin_db(plugin_id: str, uid: str = Depends(auth.get_current_user_uid)):
    disable_plugin(uid, plugin_id)
    return {'status': 'ok'}


@router.get('/v1/plugins', tags=['v1'])
def get_plugins(uid: str):
    return get_plugins_data(uid, include_reviews=True)


@router.post('/v1/plugins/review', tags=['v1'])
def review_plugin(plugin_id: str, data: dict, uid: str):
    if 'score' not in data:
        raise HTTPException(status_code=422, detail='Score is required')

    plugin = next(filter(lambda x: x['id'] == plugin_id, get_plugins_data(uid)), None)
    if not plugin:
        raise HTTPException(status_code=404, detail='Plugin not found')

    score = data['score']
    review = data.get('review', '')
    set_plugin_review(plugin_id, uid, score, review)
    return {'status': 'ok'}
