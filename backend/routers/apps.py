import json
import os
import asyncio
from datetime import datetime, timezone
from typing import List
import requests
from ulid import ULID
from fastapi import APIRouter, Depends, Form, UploadFile, File, HTTPException, Header

from database.apps import change_app_approval_status, get_unapproved_public_apps_db, \
    add_app_to_db, update_app_in_db, delete_app_from_db, update_app_visibility_in_db, \
    get_personas_by_username_db, get_persona_by_id_db, delete_persona_db, get_persona_by_twitter_handle_db, \
    get_persona_by_username_db, migrate_app_owner_id_db, get_user_persona_by_uid, get_omi_persona_apps_by_uid_db, \
    create_api_key_db, list_api_keys_db, delete_api_key_db
from database.auth import get_user_from_uid
from database.notifications import get_token_only
from database.redis_db import delete_generic_cache, get_specific_user_review, increase_app_installs_count, \
    decrease_app_installs_count, enable_app, disable_app, delete_app_cache_by_id, is_username_taken, save_username
from utils.apps import get_available_apps, get_available_app_by_id, get_approved_available_apps, \
    get_available_app_by_id_with_reviews, set_app_review, get_app_reviews, add_tester, is_tester, \
    add_app_access_for_tester, remove_app_access_for_tester, upsert_app_payment_link, get_is_user_paid_app, \
    is_permit_payment_plan_get, generate_persona_prompt, generate_persona_desc, get_persona_by_uid, \
    increment_username, generate_api_key

from database.facts import migrate_facts

from utils.llm import generate_description, generate_persona_intro_message

from utils.notifications import send_notification
from utils.other import endpoints as auth
from models.app import App, ActionType
from utils.other.storage import upload_plugin_logo, delete_plugin_logo, upload_app_thumbnail, get_app_thumbnail_url
from utils.social import get_twitter_profile, verify_latest_tweet, \
    upsert_persona_from_twitter_profile, add_twitter_to_persona

router = APIRouter()


# ******************************************************
# ********************* APPS CRUD **********************
# ******************************************************

@router.get('/v1/apps', tags=['v1'], response_model=List[App])
def get_apps(uid: str = Depends(auth.get_current_user_uid), include_reviews: bool = True):
    return get_available_apps(uid, include_reviews=include_reviews)


@router.get('/v1/approved-apps', tags=['v1'], response_model=List[App])
def get_approved_apps(include_reviews: bool = False):
    return get_approved_available_apps(include_reviews=include_reviews)


@router.post('/v1/apps', tags=['v1'])
def create_app(app_data: str = Form(...), file: UploadFile = File(...), uid=Depends(auth.get_current_user_uid)):
    data = json.loads(app_data)
    data['approved'] = False
    data['deleted'] = False
    data['status'] = 'under-review'
    data['name'] = data['name'].strip()
    data['id'] = str(ULID())
    if not data.get('author') and not data.get('email'):
        user = get_user_from_uid(uid)
        data['author'] = user['display_name']
        data['email'] = user['email']
    if not data.get('is_paid'):
        data['is_paid'] = False
    else:
        if data['is_paid'] is True:
            if data.get('price') is None:
                raise HTTPException(status_code=422, detail='App price is required')
            if data.get('price') < 0.0:
                raise HTTPException(status_code=422, detail='Price cannot be a negative value')
            if data.get('payment_plan') is None:
                raise HTTPException(status_code=422, detail='Payment plan is required')

    if external_integration := data.get('external_integration'):
        if external_integration.get('triggers_on') is None and \
                len(external_integration.get('actions', [])) == 0:
            raise HTTPException(status_code=422, detail='Triggers on or actions is required')
        # Trigger on
        if external_integration.get('triggers_on'):
            external_integration['webhook_url'] = external_integration['webhook_url'].strip()
            if external_integration.get('setup_instructions_file_path'):
                external_integration['setup_instructions_file_path'] = external_integration[
                    'setup_instructions_file_path'].strip()
                if external_integration['setup_instructions_file_path'].startswith('http'):
                    external_integration['is_instructions_url'] = True
                else:
                    external_integration['is_instructions_url'] = False

        # Acitons
        if actions := external_integration.get('actions'):
            for action in actions:
                if not action.get('action'):
                    raise HTTPException(status_code=422, detail='Action field is required for each action')
                if action.get('action') not in [action_type.value for action_type in ActionType]:
                    raise HTTPException(status_code=422,
                                        detail=f'Unsupported action type. Supported types: {", ".join([action_type.value for action_type in ActionType])}')
    os.makedirs(f'_temp/plugins', exist_ok=True)
    file_path = f"_temp/plugins/{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())
    img_url = upload_plugin_logo(file_path, data['id'])
    data['image'] = img_url
    data['created_at'] = datetime.now(timezone.utc)

    # Backward compatibility: Set app_home_url from first auth step if not provided
    if 'external_integration' in data:
        ext_int = data['external_integration']
        if (not ext_int.get('app_home_url') and
                ext_int.get('auth_steps') and
                len(ext_int['auth_steps']) == 1):
            ext_int['app_home_url'] = ext_int['auth_steps'][0]['url']

    add_app_to_db(data)

    # payment link
    app = App(**data)
    upsert_app_payment_link(app.id, app.is_paid, app.price, app.payment_plan, app.uid)

    return {'status': 'ok', 'app_id': app.id}


@router.post('/v1/personas', tags=['v1'])
async def create_persona(persona_data: str = Form(...), file: UploadFile = File(...),
                         uid=Depends(auth.get_current_user_uid)):
    data = json.loads(persona_data)
    data['approved'] = False
    data['deleted'] = False
    data['status'] = 'under-review'
    data['category'] = 'personality-emulation'
    data['name'] = data['name'].strip()
    data['id'] = str(ULID())
    data['uid'] = uid
    data['capabilities'] = ['persona']
    user = get_user_from_uid(uid)
    data['author'] = user['display_name']
    data['email'] = user['email']

    if 'username' not in data or data['username'] == '' or data['username'] is None:
        data['username'] = data['name'].replace(' ', '').lower()
        data['username'] = increment_username(data['username'])
    save_username(data['username'], uid)

    if 'connected_accounts' not in data or data['connected_accounts'] is None:
        data['connected_accounts'] = ['omi']
    data['persona_prompt'] = await generate_persona_prompt(uid, data)
    data['description'] = generate_persona_desc(uid, data['name'])
    os.makedirs(f'_temp/plugins', exist_ok=True)
    file_path = f"_temp/plugins/{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())
    img_url = upload_plugin_logo(file_path, data['id'])
    data['image'] = img_url
    data['created_at'] = datetime.now(timezone.utc)

    add_app_to_db(data)

    return {'status': 'ok', 'app_id': data['id'], 'username': data['username']}


@router.patch('/v1/personas/{persona_id}', tags=['v1'])
async def update_persona(persona_id: str, persona_data: str = Form(...), file: UploadFile = File(None),
                         uid=Depends(auth.get_current_user_uid)):
    data = json.loads(persona_data)
    persona = get_available_app_by_id(persona_id, uid)
    if not persona:
        raise HTTPException(status_code=404, detail='Persona not found')
    if persona['uid'] != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')

    # Image
    if file:
        if 'image' in persona and len(persona['image']) > 0 and \
                persona['image'].startswith('https://storage.googleapis.com/'):
            delete_plugin_logo(persona['image'])
        os.makedirs(f'_temp/plugins', exist_ok=True)
        file_path = f"_temp/plugins/{file.filename}"
        with open(file_path, 'wb') as f:
            f.write(file.file.read())
        img_url = upload_plugin_logo(file_path, persona_id)
        data['image'] = img_url

    save_username(data['username'], uid)
    data['description'] = generate_persona_desc(uid, data['name'])
    data['updated_at'] = datetime.now(timezone.utc)

    # Update 'omi' connected_accounts
    if 'omi' in data.get('connected_accounts', []) and \
            'omi' not in persona.get('connected_accounts', []):
        data['persona_prompt'] = await generate_persona_prompt(uid, persona)

    update_app_in_db(data)

    if persona['approved'] and (persona['private'] is None or persona['private'] is False):
        delete_generic_cache('get_public_approved_apps_data')
    delete_app_cache_by_id(persona_id)
    return {'status': 'ok', 'app_id': persona_id, 'username': data['username']}


@router.get('/v1/personas', tags=['v1'])
def get_persona_details(uid: str = Depends(auth.get_current_user_uid)):
    app = get_persona_by_uid(uid)
    print(app)
    app = App(**app) if app else None
    if not app:
        raise HTTPException(status_code=404, detail='Persona not found')
    if app.uid != uid:
        raise HTTPException(status_code=404, detail='Persona not found')
    if app.private is not None:
        if app.private and app.uid != uid:
            raise HTTPException(status_code=403, detail='You are not authorized to view this Persona')

    return app

@router.post('/v1/user/persona', tags=['v1'])
async def get_or_create_user_persona(uid: str = Depends(auth.get_current_user_uid)):
    """Get or create a user persona.

    If the user already has a persona, return it.
    If not, create a new one with default values.
    """
    # Check if user already has a persona
    persona = get_user_persona_by_uid(uid)
    if persona:
        # Return existing persona
        return persona

    # Create a new persona for the user
    user = get_user_from_uid(uid)

    # Generate a unique ID for the persona
    persona_id = str(ULID())

    # Create persona data
    persona_data = {
        'id': persona_id,
        'name': user.get('display_name', 'My Persona'),
        'username': increment_username((user.get('display_name') or 'MyPersona').replace(' ', '').lower()),
        'description': f"This is {user.get('display_name', 'my')} personal AI clone.",
        'image': '',  # Empty image as specified in the task
        'uid': uid,
        'author': user.get('display_name', ''),
        'email': user.get('email', ''),
        'approved': False,
        'deleted': False,
        'status': 'under-review',
        'category': 'personality-emulation',
        'capabilities': ['persona'],
        'connected_accounts': ['omi'],
        'created_at': datetime.now(timezone.utc),
        'private': True
    }

    # Generate persona prompt
    persona_data['persona_prompt'] = await generate_persona_prompt(uid, persona_data)

    # Save username
    save_username(persona_data['username'], uid)

    # Add persona to database
    add_app_to_db(persona_data)

    return persona_data


@router.get('/v1/apps/check-username', tags=['v1'])
def check_username(username: str, uid: str = Depends(auth.get_current_user_uid)):
    is_taken = is_username_taken(username)
    return {'is_taken': is_taken}


@router.get('/v1/personas/generate-username', tags=['v1'])
def generate_username(handle: str, uid: str = Depends(auth.get_current_user_uid)):
    username = handle.replace(' ', '')
    username = increment_username(username)
    return {'username': username}


@router.patch('/v1/apps/{app_id}', tags=['v1'])
def update_app(app_id: str, app_data: str = Form(...), file: UploadFile = File(None),
               uid=Depends(auth.get_current_user_uid)):
    data = json.loads(app_data)
    plugin = get_available_app_by_id(app_id, uid)
    if not plugin:
        raise HTTPException(status_code=404, detail='App not found')
    if plugin['uid'] != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    if file:
        if 'image' in plugin and len(plugin['image']) > 0 and \
                plugin['image'].startswith('https://storage.googleapis.com/'):
            delete_plugin_logo(plugin['image'])
        os.makedirs(f'_temp/plugins', exist_ok=True)
        file_path = f"_temp/plugins/{file.filename}"
        with open(file_path, 'wb') as f:
            f.write(file.file.read())
        img_url = upload_plugin_logo(file_path, app_id)
        data['image'] = img_url
    data['updated_at'] = datetime.now(timezone.utc)

    # Backward compatibility: Set app_home_url from first auth step if not provided
    if 'external_integration' in data:
        ext_int = data['external_integration']
        if (not ext_int.get('app_home_url') and
                ext_int.get('auth_steps') and
                len(ext_int['auth_steps']) == 1):
            ext_int['app_home_url'] = ext_int['auth_steps'][0]['url']

    # Warn: the user can update any fields, e.g. approved.
    update_app_in_db(data)

    # payment link
    upsert_app_payment_link(data.get('id'), data.get('is_paid', False), data.get('price'), data.get('payment_plan'),
                            data.get('uid'),
                            previous_price=plugin.get("price", 0))

    if plugin['approved'] and (plugin['private'] is None or plugin['private'] is False):
        delete_generic_cache('get_public_approved_apps_data')
    delete_app_cache_by_id(app_id)
    return {'status': 'ok'}


@router.delete('/v1/apps/{app_id}', tags=['v1'])
def delete_app(app_id: str, uid: str = Depends(auth.get_current_user_uid)):
    plugin = get_available_app_by_id(app_id, uid)
    if not plugin:
        raise HTTPException(status_code=404, detail='App not found')
    if plugin['uid'] != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    delete_app_from_db(app_id)
    if plugin['approved']:
        delete_generic_cache('get_public_approved_apps_data')
    delete_app_cache_by_id(app_id)
    return {'status': 'ok'}


@router.get('/v1/apps/{app_id}', tags=['v1'])
def get_app_details(app_id: str, uid: str = Depends(auth.get_current_user_uid)):
    app = get_available_app_by_id_with_reviews(app_id, uid)
    app = App(**app) if app else None
    if not app:
        raise HTTPException(status_code=404, detail='App not found')
    if not app.approved and app.uid != uid:
        raise HTTPException(status_code=404, detail='App not found')
    if app.private is not None:
        if app.private and app.uid != uid:
            raise HTTPException(status_code=403, detail='You are not authorized to view this app')

    # is user paid
    app.is_user_paid = get_is_user_paid_app(app.id, uid)

    # payment link
    if app.payment_link:
        app.payment_link = f'{app.payment_link}?client_reference_id=uid_{uid}'

    # Generate thumbnail URLs if thumbnails exist
    if app.thumbnails:
        app.thumbnail_urls = [
            get_app_thumbnail_url(thumbnail_id)
            for thumbnail_id in app.thumbnails
        ]

    return app


@router.post('/v1/apps/review', tags=['v1'])
def review_app(app_id: str, data: dict, uid: str = Depends(auth.get_current_user_uid)):
    if 'score' not in data:
        raise HTTPException(status_code=422, detail='Score is required')

    app = get_available_app_by_id(app_id, uid)
    app = App(**app) if app else None
    if not app:
        raise HTTPException(status_code=404, detail='App not found')

    if app.uid == uid:
        raise HTTPException(status_code=403, detail='You are not authorized to review your own app')

    if app.private and app.uid != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to review this app')

    review_data = {
        'score': data['score'],
        'review': data.get('review', ''),
        'username': data.get('username', ''),
        'response': data.get('response', ''),
        'rated_at': datetime.now(timezone.utc).isoformat(),
        'uid': uid
    }
    set_app_review(app_id, uid, review_data)
    return {'status': 'ok'}


@router.patch('/v1/apps/{app_id}/review', tags=['v1'])
def update_app_review(app_id: str, data: dict, uid: str = Depends(auth.get_current_user_uid)):
    if 'score' not in data:
        raise HTTPException(status_code=422, detail='Score is required')

    app = get_available_app_by_id(app_id, uid)
    app = App(**app) if app else None
    if not app:
        raise HTTPException(status_code=404, detail='App not found')

    if app.uid == uid:
        raise HTTPException(status_code=403, detail='You are not authorized to review your own app')

    if app.private and app.uid != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to review this app')
    old_review = get_specific_user_review(app_id, uid)
    if not old_review:
        raise HTTPException(status_code=404, detail='Review not found')
    review_data = {
        'score': data['score'],
        'review': data.get('review', ''),
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'rated_at': old_review['rated_at'],
        'username': old_review.get('username', ''),
        'response': old_review.get('response', ''),
        'uid': uid
    }
    set_app_review(app_id, uid, review_data)
    return {'status': 'ok'}


@router.patch('/v1/apps/{app_id}/review/reply', tags=['v1'])
def reply_to_review(app_id: str, data: dict, uid: str = Depends(auth.get_current_user_uid)):
    app = get_available_app_by_id(app_id, uid)
    app = App(**app) if app else None
    if not app:
        raise HTTPException(status_code=404, detail='App not found')

    if app.uid != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to reply to this app review')

    if app.private and app.uid != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to reply to this app review')

    review = get_specific_user_review(app_id, uid)
    if not review:
        raise HTTPException(status_code=404, detail='Review not found')

    review['response'] = data['response']
    review['responded_at'] = datetime.now(timezone.utc).isoformat()
    set_app_review(app_id, uid, review)
    return {'status': 'ok'}


@router.get('/v1/apps/{app_id}/reviews', tags=['v1'])
def app_reviews(app_id: str):
    reviews = get_app_reviews(app_id)
    reviews = [
        details for details in reviews.values() if details['review']
    ]
    return reviews


@router.patch('/v1/apps/{app_id}/change-visibility', tags=['v1'])
def change_app_visibility(app_id: str, private: bool, uid: str = Depends(auth.get_current_user_uid)):
    app = get_available_app_by_id(app_id, uid)
    app = App(**app) if app else None
    if not app:
        raise HTTPException(status_code=404, detail='App not found')
    if app.uid != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    update_app_visibility_in_db(app_id, private)
    delete_app_cache_by_id(app_id)
    return {'status': 'ok'}


@router.get('/v1/app/proactive-notification-scopes', tags=['v1'])
def get_notification_scopes():
    return [
        {'title': 'User Name', 'id': 'user_name'},
        {'title': 'User Facts', 'id': 'user_facts'},
        {'title': 'User Memories', 'id': 'user_context'},
        {'title': 'User Chat', 'id': 'user_chat'}
    ]


@router.get('/v1/app-capabilities', tags=['v1'])
def get_plugin_capabilities():
    return [
        {'title': 'Chat', 'id': 'chat'},
        {'title': 'Memories', 'id': 'memories'},
        {'title': 'External Integration', 'id': 'external_integration', 'triggers': [
            {'title': 'Audio Bytes', 'id': 'audio_bytes'},
            {'title': 'Memory Creation', 'id': 'memory_creation'},
            {'title': 'Transcript Processed', 'id': 'transcript_processed'},
        ], 'actions': [
            {'title': 'Create conversations', 'id': 'create_conversation', 'doc_url': 'https://docs.omi.me/docs/developer/apps/IntegrationActions'},
            {'title': 'Create facts', 'id': 'create_facts', 'doc_url': 'https://docs.omi.me/docs/developer/apps/IntegrationActions'}
        ]},
        {'title': 'Notification', 'id': 'proactive_notification', 'scopes': [
            {'title': 'User Name', 'id': 'user_name'},
            {'title': 'User Facts', 'id': 'user_facts'},
            {'title': 'User Memories', 'id': 'user_context'},
            {'title': 'User Chat', 'id': 'user_chat'}
        ]}
    ]


# @deprecated
@router.get('/v1/app/payment-plans', tags=['v1'])
def get_payment_plans_v1():
    return [
        {'title': 'Monthly Recurring', 'id': 'monthly_recurring'},
    ]


@router.get('/v1/app/plans', tags=['v1'])
def get_payment_plans(uid: str = Depends(auth.get_current_user_uid)):
    if not uid or len(uid) == 0 or not is_permit_payment_plan_get(uid):
        return []
    return [
        {'title': 'Monthly Recurring', 'id': 'monthly_recurring'},
    ]


@router.post('/v1/app/generate-description', tags=['v1'])
def generate_description_endpoint(data: dict, uid: str = Depends(auth.get_current_user_uid)):
    if data['name'] == '':
        raise HTTPException(status_code=422, detail='App Name is required')
    if data['description'] == '':
        raise HTTPException(status_code=422, detail='App Description is required')
    desc = generate_description(data['name'], data['description'])
    return {
        'description': desc,
    }


# ******************************************************
# ********************** SOCIAL ************************
# ******************************************************

@router.get('/v1/personas/twitter/profile', tags=['v1'])
async def get_twitter_profile_data(handle: str, uid: str = Depends(auth.get_current_user_uid)):
    if handle.startswith('@'):
        handle = handle[1:]
    profile = await get_twitter_profile(handle)

    # Convert TwitterProfile to dict for response
    res = {
        "name": profile.name,
        "profile": profile.profile,
        "rest_id": profile.rest_id,
        "avatar": profile.avatar,
        "desc": profile.desc,
        "friends": profile.friends,
        "sub_count": profile.sub_count,
        "id": profile.id,
        "status": profile.status,
    }

    # By user persona first
    persona = get_user_persona_by_uid(uid)

    # Get matching persona if exists
    if not persona:
        persona = get_persona_by_twitter_handle_db(handle)

    if persona:
        res['persona_id'] = persona['id']
        res['persona_username'] = persona['username']

    return res


@router.get('/v1/personas/twitter/verify-ownership', tags=['v1'])
async def verify_twitter_ownership_tweet(
        username: str,
        handle: str,
        uid: str = Depends(auth.get_current_user_uid),
        persona_id: str | None = None
):
    # Get user info to check auth provider
    user = get_user_from_uid(uid)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get provider info from Firebase
    user_info = auth.get_user(uid)
    provider_data = [p.provider_id for p in user_info.provider_data]

    # Verify handle
    if handle.startswith('@'):
        handle = handle[1:]
    if username.startswith('@'):
        username = username[1:]
    persona = None
    res = await verify_latest_tweet(username, handle)
    if res['verified']:
        if not ('google.com' in provider_data or 'apple.com' in provider_data):
            persona = await upsert_persona_from_twitter_profile(username, handle, uid)
        else:
            if persona_id:
                persona = await add_twitter_to_persona(handle, persona_id)

    if persona:
        res['persona_id'] = persona['id']

    return res


@router.get('/v1/personas/twitter/initial-message', tags=['v1'])
async def get_twitter_initial_message(username: str, uid: str = Depends(auth.get_current_user_uid)):
    persona = get_persona_by_username_db(username)
    if persona:
        message = generate_persona_intro_message(persona['persona_prompt'], persona['name'])
        return {'message': message}
    return {'message': ''}


@router.post('/v1/apps/migrate-owner', tags=['v1'])
async def migrate_app_owner(old_id, uid: str = Depends(auth.get_current_user_uid)):
    # Migrate app ownership in the database
    migrate_app_owner_id_db(uid, old_id)

    # Start async tasks to migrate facts and update persona connected accounts
    asyncio.create_task(migrate_facts(old_id, uid))
    asyncio.create_task(update_omi_persona_connected_accounts(uid))

    return {"status": "ok", "message": "Migration started"}

async def update_omi_persona_connected_accounts(uid: str):
    try:
        # Get all personas owned by the user
        personas = get_omi_persona_apps_by_uid_db(uid)

        # Update each persona to add 'omi' to connected_accounts
        for persona in personas:
            connected_accounts = persona.get('connected_accounts', [])
            if 'omi' not in connected_accounts:
                connected_accounts.append('omi')

                # Update the persona with the new connected_accounts
                update_data = persona
                update_data['connected_accounts'] = connected_accounts
                update_data['updated_at'] = datetime.now(timezone.utc)
                update_data['persona_prompt'] = await generate_persona_prompt(uid, update_data)
                update_data['description'] = generate_persona_desc(uid, update_data['name'])

                update_app_in_db(update_data)
                delete_app_cache_by_id(persona['id'])
    except Exception as e:
        print(f"Error updating persona connected accounts: {e}")


# ******************************************************
# **************** ENABLE/DISABLE APPS *****************
# ******************************************************

@router.post('/v1/apps/enable')
def enable_app_endpoint(app_id: str, uid: str = Depends(auth.get_current_user_uid)):
    app = get_available_app_by_id(app_id, uid)
    app = App(**app) if app else None
    if not app:
        raise HTTPException(status_code=404, detail='App not found')
    if app.private is not None:
        if app.private and app.uid != uid and not is_tester(uid):
            raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    if app.works_externally() and app.external_integration.setup_completed_url:
        res = requests.get(app.external_integration.setup_completed_url + f'?uid={uid}')
        print('enable_app_endpoint', res.status_code, res.content)
        if res.status_code != 200 or not res.json().get('is_setup_completed', False):
            raise HTTPException(status_code=400, detail='App setup is not completed')

    # Check payment status
    if app.is_paid and get_is_user_paid_app(app.id, uid) == False:
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')

    enable_app(uid, app_id)
    if (app.private is None or not app.private) and (app.uid is None or app.uid != uid) and not is_tester(uid):
        increase_app_installs_count(app_id)
    return {'status': 'ok'}


@router.post('/v1/apps/disable')
def disable_app_endpoint(app_id: str, uid: str = Depends(auth.get_current_user_uid)):
    app = get_available_app_by_id(app_id, uid)
    app = App(**app) if app else None
    if not app:
        raise HTTPException(status_code=404, detail='App not found')
    if app.private is None:
        if app.private and app.uid != uid and not is_tester(uid):
            raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    disable_app(uid, app_id)
    if (app.private is None or not app.private) and (app.uid is None or app.uid != uid) and not is_tester(uid):
        decrease_app_installs_count(app_id)
    return {'status': 'ok'}


# ******************************************************
# ******************* TEAM ENDPOINTS *******************
# ******************************************************

@router.post('/v1/apps/tester', tags=['v1'])
def add_new_tester(data: dict, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    if not data.get('uid'):
        raise HTTPException(status_code=422, detail='uid is required')
    if not data.get('apps'):
        raise HTTPException(status_code=422, detail='apps is required')
    data['added_at'] = datetime.now(timezone.utc).isoformat()
    add_tester(data)
    return {'status': 'ok'}


@router.post('/v1/apps/tester/access', tags=['v1'])
def add_app_access_tester(data: dict, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    if not data.get('uid'):
        raise HTTPException(status_code=422, detail='uid is required')
    if not data.get('app_id'):
        raise HTTPException(status_code=422, detail='app_id is required')
    add_app_access_for_tester(data['app_id'], data['uid'])
    return {'status': 'ok'}


@router.delete('/v1/apps/tester/access', tags=['v1'])
def remove_app_access_tester(data: dict, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    if not data.get('uid'):
        raise HTTPException(status_code=422, detail='uid is required')
    if not data.get('app_id'):
        raise HTTPException(status_code=422, detail='app_id is required')
    remove_app_access_for_tester(data['app_id'], data['uid'])
    return {'status': 'ok'}


@router.get('/v1/apps/tester/check', tags=['v1'])
def check_is_tester(uid: str = Depends(auth.get_current_user_uid)):
    if is_tester(uid):
        return {'is_tester': True}
    return {'is_tester': False}


@router.get('/v1/apps/public/unapproved', tags=['v1'])
def get_unapproved_public_apps(secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    apps = get_unapproved_public_apps_db()
    return apps


@router.post('/v1/apps/{app_id}/approve', tags=['v1'])
def approve_app(app_id: str, uid: str, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    change_app_approval_status(app_id, True)
    delete_app_cache_by_id(app_id)
    app = get_available_app_by_id(app_id, uid)
    token = get_token_only(uid)
    if token:
        send_notification(token, 'App Approved 🎉',
                          f'Your app {app["name"]} has been approved and is now available for everyone to use 🥳')
    return {'status': 'ok'}


@router.post('/v1/apps/{app_id}/reject', tags=['v1'])
def reject_app(app_id: str, uid: str, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    change_app_approval_status(app_id, False)
    delete_app_cache_by_id(app_id)
    app = get_available_app_by_id(app_id, uid)
    token = get_token_only(uid)
    if token:
        # TODO: Add reason for rejection in payload and also redirect to the plugin page
        send_notification(token, 'App Rejected 😔',
                          f'Your app {app["name"]} has been rejected. Please make the necessary changes and resubmit for approval.')
    return {'status': 'ok'}


@router.delete('/v1/personas/{persona_id}', tags=['v1'])
@router.post('/v1/app/thumbnails', tags=['v1'])
async def upload_app_thumbnail_endpoint(
        file: UploadFile = File(...),
        uid: str = Depends(auth.get_current_user_uid)
):
    """Upload a thumbnail image for an app.

    Args:
        file: The thumbnail image file
        app_id: ID of the app to add thumbnail for
        uid: User ID from auth

    Returns:
        Dict with thumbnail URL
    """
    # Save uploaded file temporarily
    thumbnail_id = str(ULID())
    os.makedirs('_temp/thumbnails', exist_ok=True)
    temp_path = f'_temp/thumbnails/{thumbnail_id}.jpg'

    try:
        with open(temp_path, 'wb') as f:
            f.write(await file.read())

        # Upload to cloud storage
        url = upload_app_thumbnail(temp_path, thumbnail_id)

        return {
            'thumbnail_url': url,
            'thumbnail_id': thumbnail_id
        }

    finally:
        # Cleanup temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)


def delete_persona(persona_id: str, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    personas = get_persona_by_id_db(persona_id)
    if not personas:
        raise HTTPException(status_code=404, detail='Persona not found')
    delete_persona_db(persona_id)
    return {'status': 'ok'}


@router.get('/v1/personas/{persona_id}', tags=['v1'])
def get_personas(persona_id: str, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    persona = get_personas_by_username_db(persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail='Persona not found')
    print(persona)
    return persona


@router.post('/v1/apps/{app_id}/keys', tags=['v1'])
def create_api_key_for_app(app_id: str, uid: str = Depends(auth.get_current_user_uid)):
    app = get_available_app_by_id(app_id, uid)
    if not app:
        raise HTTPException(status_code=404, detail='App not found')

    if app.get('uid') != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to create API keys for this app')

    key, hashed_key, label = generate_api_key()

    data = {
        'id': str(ULID()),
        'hashed': hashed_key,
        'label': label,
        'created_at': datetime.now(timezone.utc)
    }
    create_api_key_db(app_id, data)

    # Return both the raw key (for one-time display to user) and the stored data
    return {
        'id': data['id'],
        'secret': key,  # with sk_
        'label': label,
        'created_at': data['created_at']
    }


@router.get('/v1/apps/{app_id}/keys', tags=['v1'])
def list_api_keys(app_id: str, uid: str = Depends(auth.get_current_user_uid)):
    app = get_available_app_by_id(app_id, uid)
    if not app:
        raise HTTPException(status_code=404, detail='App not found')

    if app.get('uid') != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to view API keys for this app')

    keys = list_api_keys_db(app_id)
    return keys


@router.delete('/v1/apps/{app_id}/keys/{key_id}', tags=['v1'])
def delete_api_key(app_id: str, key_id: str, uid: str = Depends(auth.get_current_user_uid)):
    app = get_available_app_by_id(app_id, uid)
    if not app:
        raise HTTPException(status_code=404, detail='App not found')

    if app.get('uid') != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to delete API keys for this app')

    delete_api_key_db(app_id, key_id)

    return {'status': 'ok', 'message': 'API key deleted'}
