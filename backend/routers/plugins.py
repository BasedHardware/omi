import json
import os
import random
from collections import defaultdict
from typing import List

import requests
from fastapi import APIRouter, HTTPException, Depends, UploadFile
from fastapi.params import File, Form, Header

from database.notifications import get_token_only
from database.plugins import get_plugin_usage_history, add_public_plugin, add_private_plugin, \
    change_plugin_approval_status, \
    get_plugin_by_id_db, change_plugin_visibility_db, get_unapproved_public_plugins_db, public_plugin_id_exists_db, \
    private_plugin_id_exists_db, delete_private_plugin, \
    delete_public_plugin, update_private_plugin, update_public_plugin
from database.redis_db import set_plugin_review, enable_plugin, disable_plugin, increase_plugin_installs_count, \
    decrease_plugin_installs_count
from models.plugin import Plugin, UsageHistoryItem, UsageHistoryType
from utils.notifications import send_notification
from utils.other import endpoints as auth
from utils.other.storage import upload_plugin_logo, delete_plugin_logo
from utils.plugins import get_plugins_data, get_plugin_by_id, get_plugins_data_from_db

router = APIRouter()


@router.post('/v1/plugins/enable')
def enable_plugin_endpoint(plugin_id: str, uid: str = Depends(auth.get_current_user_uid)):
    plugin = get_plugin_by_id_db(plugin_id, uid)
    plugin = Plugin(**plugin)
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
    plugin = get_plugin_by_id_db(plugin_id, uid)
    plugin = Plugin(**plugin)
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
    data['id'] = data['name'].replace(' ', '-').lower()
    data['uid'] = uid
    if 'private' in data and data['private']:
        data['id'] = data['id'] + '-private'
        if private_plugin_id_exists_db(data['id'], uid):
            data['id'] = data['id'] + '-' + ''.join([str(random.randint(0, 9)) for _ in range(5)])
    else:
        if public_plugin_id_exists_db(data['id']):
            data['id'] = data['id'] + '-' + ''.join([str(random.randint(0, 9)) for _ in range(5)])
    os.makedirs(f'_temp/plugins', exist_ok=True)
    file_path = f"_temp/plugins/{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())
    imgUrl = upload_plugin_logo(file_path, data['id'])
    data['image'] = imgUrl
    if data.get('private', True):
        print("Adding private plugin")
        add_private_plugin(data, data['uid'])
    else:
        add_public_plugin(data)
    # delete_generic_cache('get_public_plugins_data')
    return {'status': 'ok'}


@router.patch('/v1/plugins/{plugin_id}', tags=['v1'])
def update_plugin(plugin_id: str, plugin_data: str = Form(...), file: UploadFile = File(None),
                  uid=Depends(auth.get_current_user_uid)):
    data = json.loads(plugin_data)
    plugin = get_plugin_by_id_db(plugin_id, uid)
    if not plugin:
        raise HTTPException(status_code=404, detail='Plugin not found')
    if plugin['uid'] != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    if file:
        delete_plugin_logo(plugin['image'])
        os.makedirs(f'_temp/plugins', exist_ok=True)
        file_path = f"_temp/plugins/{file.filename}"
        with open(file_path, 'wb') as f:
            f.write(file.file.read())
        imgUrl = upload_plugin_logo(file_path, plugin_id)
        data['image'] = imgUrl
    if data.get('private', True):
        update_private_plugin(data, uid)
    else:
        update_public_plugin(data)
    return {'status': 'ok'}


@router.get('/v3/plugins', tags=['v3'], response_model=List[Plugin])
def get_plugins(uid: str = Depends(auth.get_current_user_uid), include_reviews: bool = True):
    return get_plugins_data_from_db(uid, include_reviews=include_reviews)


@router.patch('/v1/plugins/{plugin_id}/change-visibility', tags=['v1'])
def change_plugin_visibility(plugin_id: str, private: bool, uid: str = Depends(auth.get_current_user_uid)):
    plugin = get_plugin_by_id_db(plugin_id, uid)
    if not plugin:
        raise HTTPException(status_code=404, detail='Plugin not found')
    was_public = not plugin['deleted'] and not plugin['private']
    change_plugin_visibility_db(plugin_id, private, was_public, uid)
    return {'status': 'ok'}


@router.get('/v1/plugins/public/unapproved', tags=['v1'])
def get_unapproved_public_plugins(secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    plugins = get_unapproved_public_plugins_db()
    return plugins


@router.get('/v1/plugins/{plugin_id}', tags=['v1'])
def get_plugin_details(plugin_id: str, uid: str = Depends(auth.get_current_user_uid)):
    plugin = get_plugin_by_id_db(plugin_id, uid)
    if not plugin:
        raise HTTPException(status_code=404, detail='Plugin not found')
    return plugin


@router.get('/v1/plugin-capabilities', tags=['v1'])
def get_plugin_capabilities():
    return [
        {'title': 'Chat', 'id': 'chat'},
        {'title': 'Memories', 'id': 'memories'},
        {'title': 'External Integration', 'id': 'external_integration', 'triggers': [
            {'title': 'Memory Creation', 'id': 'memory_creation'},
            {'title': 'Transcript Processed', 'id': 'transcript_processed'},
        ]},
        {'title': 'Proactive Notification', 'id': 'proactive_notification', 'scopes': [
            {'title': 'User Name', 'id': 'user_name'},
            {'title': 'User Facts', 'id': 'user_facts'}
        ]}
    ]

@router.get('/v1/plugin-triggers', tags=['v1'])
def get_plugin_triggers():
    # TODO: Include audio_bytes trigger when the code for it triggering through plugin is ready
    return [
        {'title': 'Memory Creation', 'id': 'memory_creation'},
        {'title': 'Transcript Processed', 'id': 'transcript_processed'},
        {'title': 'Proactive Notification', 'id': 'proactive_notification'}
    ]


@router.get('/v1/notification-scopes', tags=['v1'])
def get_notification_scopes():
    return [
        {'title': 'User Name', 'id': 'user_name'},
        {'title': 'User Facts', 'id': 'user_facts'}
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
