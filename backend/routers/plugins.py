import json
import os
from collections import defaultdict
from typing import List

import requests
from fastapi import APIRouter, HTTPException, Depends, UploadFile
from fastapi.params import File, Form

from database.plugins import get_plugin_usage_history, add_plugin_script, add_public_plugin, add_private_plugin, \
    get_plugins_db
from database.redis_db import set_plugin_review, enable_plugin, disable_plugin, increase_plugin_installs_count, \
    decrease_plugin_installs_count, get_generic_cache, set_generic_cache, get_enabled_plugins, \
    get_plugin_installs_count, get_plugin_reviews
from models.plugin import Plugin, UsageHistoryItem, UsageHistoryType, AuthStep
from utils.other import endpoints as auth
from utils.other.storage import upload_plugin_logo
from utils.plugins import get_plugins_data, get_plugin_by_id, weighted_rating

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
    increase_plugin_installs_count(plugin_id)
    enable_plugin(uid, plugin_id)
    return {'status': 'ok'}


@router.post('/v1/plugins/disable')
def disable_plugin_endpoint(plugin_id: str, uid: str = Depends(auth.get_current_user_uid)):
    plugin = get_plugin_by_id(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail='Plugin not found')
    disable_plugin(uid, plugin_id)
    decrease_plugin_installs_count(plugin_id)
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


@router.get('/v1/plugins/{plugin_id}/usage', tags=['v1'])
def get_plugin_usage(plugin_id: str):
    plugin = get_plugin_by_id(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail='Plugin not found')
    usage = get_plugin_usage_history(plugin_id)
    usage = [UsageHistoryItem(**x) for x in usage]
    # return usage by date grouped count
    by_date = defaultdict(int)
    for item in usage:
        date = item.timestamp.date()
        by_date[date] += 1

    data = [{'date': k, 'count': v} for k, v in by_date.items()]
    data = sorted(data, key=lambda x: x['date'])
    return data


@router.get('/v1/plugins/{plugin_id}/money', tags=['v1'])
def get_plugin_money_made(plugin_id: str):
    plugin = get_plugin_by_id(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail='Plugin not found')
    usage = get_plugin_usage_history(plugin_id)
    usage = [UsageHistoryItem(**x) for x in usage]
    type1 = len(list(filter(lambda x: x.type == UsageHistoryType.memory_created_external_integration, usage)))
    type2 = len(list(filter(lambda x: x.type == UsageHistoryType.memory_created_prompt, usage)))
    type3 = len(list(filter(lambda x: x.type == UsageHistoryType.chat_message_sent, usage)))

    # tbd based on current prod stats
    t1multiplier = 0.5
    t2multiplier = 0.01
    t3multiplier = 0.005

    return {
        'money': round((type1 * t1multiplier) + (type2 * t2multiplier) + (type3 * t3multiplier), 2),
        'type1': type1,
        'type2': type2,
        'type3': type3
    }



@router.get('/v3/plugins', tags=['v1'], response_model=List[Plugin])
def get_plugins(uid: str = Depends(auth.get_current_user_uid), include_reviews: bool = False):
    if data := get_generic_cache('get_plugins_data'):
        print('get_plugins_data from cache')
        pass
    else:
        # get all plugins from the database
        data = get_plugins_db(uid)
    user_enabled = set(get_enabled_plugins(uid))
    plugins = []
    for plugin in data:
        plugin_dict = plugin
        plugin_dict['enabled'] = plugin['id'] in user_enabled
        plugin_dict['installs'] = get_plugin_installs_count(plugin['id'])
        if include_reviews:
            reviews = get_plugin_reviews(plugin['id'])
            sorted_reviews = reviews.values()
            rating_avg = sum([x['score'] for x in sorted_reviews]) / len(sorted_reviews) if reviews else None
            plugin_dict['reviews'] = []
            plugin_dict['user_review'] = reviews.get(uid)
            plugin_dict['rating_avg'] = rating_avg
            plugin_dict['rating_count'] = len(sorted_reviews)
        plugins.append(Plugin(**plugin_dict))
    if include_reviews:
        plugins = sorted(plugins, key=weighted_rating, reverse=True)

    return plugins



@router.get('/v1/migrate-plugins', tags=['v1'])
def migrate_plugins():
    response = requests.get('https://raw.githubusercontent.com/BasedHardware/Omi/main/community-plugins.json')
    if response.status_code != 200:
        return []
    data = response.json()
    for plugin in data:
        add_plugin_script(plugin)



@router.post('/v1/plugins/add', tags=['v1'])
def add_plugin(plugin_data: str = Form(...), file: UploadFile = File(...), ):
    data = json.loads(plugin_data)
    os.makedirs(f'_temp/plugins', exist_ok=True)
    file_path = f"_temp/plugins/{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())
    imgUrl = upload_plugin_logo(file_path,data['id'])
    data['image'] = imgUrl
    if data.get('private', True):
        print("Adding private plugin")
        add_private_plugin(data, data['uid'])
    else:
        add_public_plugin(data)
    return {'status': 'ok'}
