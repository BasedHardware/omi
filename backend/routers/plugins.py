import json
import os
import random
from datetime import datetime, timezone
from collections import defaultdict
from typing import List

import requests
from fastapi import APIRouter, HTTPException, Depends, UploadFile
from fastapi.params import File, Form
from slugify import slugify
from ulid import ULID

from database.apps import add_app_to_db
from database.redis_db import set_plugin_review, enable_plugin, disable_plugin, increase_plugin_installs_count, \
    decrease_plugin_installs_count
from models.app import App
from models.plugin import Plugin
from utils.apps import get_available_app_by_id, get_app_usage_history, get_app_money_made
from utils.other import endpoints as auth
from utils.other.storage import upload_plugin_logo
from utils.plugins import get_plugins_data, get_plugins_data_from_db

router = APIRouter()


@router.post('/v1/plugins/enable')
def enable_plugin_endpoint(plugin_id: str, uid: str = Depends(auth.get_current_user_uid)):
    plugin = get_available_app_by_id(plugin_id, uid)
    plugin = App(**plugin) if plugin else None
    if not plugin:
        raise HTTPException(status_code=404, detail='Plugin not found')
    if plugin.works_externally() and plugin.external_integration.setup_completed_url:
        res = requests.get(plugin.external_integration.setup_completed_url + f'?uid={uid}')
        print('enable_plugin_endpoint', res.status_code, res.content)
        if res.status_code != 200 or not res.json().get('is_setup_completed', False):
            raise HTTPException(status_code=400, detail='Plugin setup is not completed')
    if plugin.private is not None and plugin.private is False:
        increase_plugin_installs_count(plugin_id)
    enable_plugin(uid, plugin_id)
    return {'status': 'ok'}


@router.post('/v1/plugins/disable')
def disable_plugin_endpoint(plugin_id: str, uid: str = Depends(auth.get_current_user_uid)):
    plugin = get_available_app_by_id(plugin_id, uid)
    plugin = App(**plugin) if plugin else None
    if not plugin:
        raise HTTPException(status_code=404, detail='App not found')
    disable_plugin(uid, plugin_id)
    if plugin.private is not None and plugin.private is False:
        decrease_plugin_installs_count(plugin_id)
    return {'status': 'ok'}


@router.get('/plugins')  # No auth while migration happens for all.
def get_plugins(uid: str):
    return get_plugins_data(uid, include_reviews=True)


@router.get('/v1/plugins', tags=['v1'])
def get_plugins_v1(uid: str):
    return get_plugins_data(uid, include_reviews=True)


@router.get('/v2/plugins', tags=['v1'], response_model=List[Plugin])
def get_plugins_v2(uid: str = Depends(auth.get_current_user_uid)):
    return get_plugins_data(uid, include_reviews=True)


@router.post('/v1/plugins/review', tags=['v1'])
def review_plugin(plugin_id: str, data: dict, uid: str = Depends(auth.get_current_user_uid)):
    if 'score' not in data:
        raise HTTPException(status_code=422, detail='Score is required')

    plugin = get_available_app_by_id(plugin_id, uid)
    if not plugin:
        raise HTTPException(status_code=404, detail='Plugin not found')

    score = data['score']
    review = data.get('review', '')
    set_plugin_review(plugin_id, uid, {'score': score, 'review': review})
    return {'status': 'ok'}


@router.get('/v1/plugins/{plugin_id}/usage', tags=['v1'])
def get_plugin_usage(plugin_id: str):
    app = get_available_app_by_id(plugin_id, None)
    if not app:
        raise HTTPException(status_code=404, detail='Plugin not found')
    data = get_app_usage_history(plugin_id)
    return data


@router.get('/v1/plugins/{plugin_id}/money', tags=['v1'])
def get_plugin_money_made(plugin_id: str):
    app = get_available_app_by_id(plugin_id, None)
    if not app:
        raise HTTPException(status_code=404, detail='App not found')
    money = get_app_money_made(plugin_id)
    return money


# @router.get('/v1/migrate-plugins', tags=['v1'])
# def migrate_plugins():
#     response = requests.get('https://raw.githubusercontent.com/BasedHardware/Omi/main/community-plugins.json')
#     if response.status_code != 200:
#         return []
#     data = response.json()
#     for plugin in data:
#         add_plugin_from_community_json(plugin)


@router.post('/v3/plugins', tags=['v1'])
def add_plugin(plugin_data: str = Form(...), file: UploadFile = File(...), uid=Depends(auth.get_current_user_uid)):
    data = json.loads(plugin_data)
    data['approved'] = False
    data['name'] = data['name'].strip()
    new_app_id = slugify(data['name']) + '-' + str(ULID())
    data['id'] = new_app_id
    os.makedirs(f'_temp/plugins', exist_ok=True)
    file_path = f"_temp/plugins/{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())
    imgUrl = upload_plugin_logo(file_path, data['id'])
    data['image'] = imgUrl
    data['created_at'] = datetime.now(timezone.utc)
    add_app_to_db(data)
    return {'status': 'ok'}


@router.get('/v3/plugins', tags=['v3'], response_model=List[Plugin])
def get_plugins(uid: str = Depends(auth.get_current_user_uid), include_reviews: bool = True):
    return get_plugins_data_from_db(uid, include_reviews=include_reviews)


@router.get('/v1/plugin-triggers', tags=['v1'])
def get_plugin_triggers():
    # TODO: Include audio_bytes trigger when the code for it triggering through plugin is ready
    return [
        {'title': 'Memory Creation', 'id': 'memory_creation'},
        {'title': 'Transcript Processed', 'id': 'transcript_processed'},
        {'title': 'Proactive Notification', 'id': 'proactive_notification'}
    ]


@router.get('/v1/plugin-categories', tags=['v1'])
def get_plugin_categories():
    return [
        {'title': 'Conversation Analysis', 'id': 'conversation-analysis'},
        {'title': 'Personality Emulation', 'id': 'personality-emulation'},
        {'title': 'Health and Wellness', 'id': 'health-and-wellness'},
        {'title': 'Education and Learning', 'id': 'education-and-learning'},
        {'title': 'Communication Improvement', 'id': 'communication-improvement'},
        {'title': 'Emotional and Mental Support', 'id': 'emotional-and-mental-support'},
        {'title': 'Productivity and Organization', 'id': 'productivity-and-organization'},
        {'title': 'Entertainment and Fun', 'id': 'entertainment-and-fun'},
        {'title': 'Financial', 'id': 'financial'},
        {'title': 'Travel and Exploration', 'id': 'travel-and-exploration'},
        {'title': 'Safety and Security', 'id': 'safety-and-security'},
        {'title': 'Shopping and Commerce', 'id': 'shopping-and-commerce'},
        {'title': 'Social and Relationships', 'id': 'social-and-relationships'},
        {'title': 'News and Information', 'id': 'news-and-information'},
        {'title': 'Utilities and Tools', 'id': 'utilities-and-tools'},
        {'title': 'Other', 'id': 'other'}
    ]
