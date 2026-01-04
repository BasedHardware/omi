import json
import os
import asyncio
from datetime import datetime, timezone
from typing import List
from pydantic import ValidationError
import requests
from ulid import ULID
from fastapi import APIRouter, Depends, Form, UploadFile, File, HTTPException, Header, Query

from utils.apps import fetch_app_chat_tools_from_manifest

from database.apps import (
    change_app_approval_status,
    get_unapproved_public_apps_db,
    add_app_to_db,
    update_app_in_db,
    delete_app_from_db,
    update_app_visibility_in_db,
    get_personas_by_username_db,
    get_persona_by_id_db,
    delete_persona_db,
    get_persona_by_twitter_handle_db,
    get_persona_by_username_db,
    migrate_app_owner_id_db,
    get_user_persona_by_uid,
    get_omi_persona_apps_by_uid_db,
    create_api_key_db,
    list_api_keys_db,
    delete_api_key_db,
    set_app_popular_db,
    search_apps_db,
)
from database.auth import get_user_from_uid
from database.redis_db import (
    delete_generic_cache,
    get_generic_cache,
    set_generic_cache,
    get_specific_user_review,
    increase_app_installs_count,
    decrease_app_installs_count,
    enable_app,
    disable_app,
    delete_app_cache_by_id,
    is_username_taken,
    save_username,
    get_enabled_apps,
    get_conversation_summary_app_ids,
    add_conversation_summary_app_id,
    remove_conversation_summary_app_id,
    get_apps_installs_count,
    get_apps_reviews,
)
from utils.apps import (
    get_available_apps,
    get_available_app_by_id,
    get_approved_available_apps,
    get_available_app_by_id_with_reviews,
    set_app_review,
    get_app_reviews,
    add_tester,
    is_tester,
    add_app_access_for_tester,
    remove_app_access_for_tester,
    upsert_app_payment_link,
    get_is_user_paid_app,
    is_permit_payment_plan_get,
    generate_persona_prompt,
    generate_persona_desc,
    get_persona_by_uid,
    increment_username,
    generate_api_key,
    get_popular_apps,
    paginate_apps,
    build_pagination_metadata,
    get_capabilities_list,
    normalize_app_numeric_fields,
    filter_apps_by_capability,
    sort_apps_by_installs,
    group_apps_by_capability,
    build_capability_groups_response,
    group_capability_apps_by_category,
    build_capability_category_groups_response,
)

from database.memories import migrate_memories

from utils.llm.persona import generate_persona_intro_message
from utils.llm.app_generator import generate_description
from utils.notifications import send_notification, send_app_review_reply_notification, send_new_app_review_notification
from utils.other import endpoints as auth
from models.app import App, ActionType, AppCreate, AppUpdate
from utils.other.storage import upload_app_logo, delete_app_logo, upload_app_thumbnail, get_app_thumbnail_url
from utils.social import (
    get_twitter_profile,
    verify_latest_tweet,
    upsert_persona_from_twitter_profile,
    add_twitter_to_persona,
)

router = APIRouter()


def _get_categories():
    return [
        {'title': 'Popular', 'id': 'popular'},
        {'title': 'Conversation Analysis', 'id': 'conversation-analysis'},
        {'title': 'Personality Clone', 'id': 'personality-emulation'},
        {'title': 'Health', 'id': 'health-and-wellness'},
        {'title': 'Education', 'id': 'education-and-learning'},
        {'title': 'Communication', 'id': 'communication-improvement'},
        {'title': 'Emotional Support', 'id': 'emotional-and-mental-support'},
        {'title': 'Productivity', 'id': 'productivity-and-organization'},
        {'title': 'Entertainment', 'id': 'entertainment-and-fun'},
        {'title': 'Financial', 'id': 'financial'},
        {'title': 'Travel', 'id': 'travel-and-exploration'},
        {'title': 'Safety', 'id': 'safety-and-security'},
        {'title': 'Shopping', 'id': 'shopping-and-commerce'},
        {'title': 'Social', 'id': 'social-and-relationships'},
        {'title': 'News', 'id': 'news-and-information'},
        {'title': 'Utilities', 'id': 'utilities-and-tools'},
        {'title': 'Other', 'id': 'other'},
    ]


# ******************************************************
# ********************* APPS CRUD **********************
# ******************************************************


@router.get('/v1/apps', tags=['v1'], response_model=List[App])
def get_apps(uid: str = Depends(auth.get_current_user_uid), include_reviews: bool = True):
    return get_available_apps(uid, include_reviews=include_reviews)


@router.get('/v2/apps', tags=['v2'])
def get_apps_v2(
    capability: str | None = Query(default=None, description='Filter by capability id'),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=50),
    include_reviews: bool = Query(default=False),
):
    """Public omi apps, paginated by capability groups.

    Notes:
    - Uses approved public apps only (no private/tester apps).
    - Groups: Popular, Integrations, Chat Assistants, Summary Apps, Realtime Notifications.
    - Popular section is shown first.
    - Always excludes persona type apps.
    """

    capabilities = get_capabilities_list()

    if capability:
        cache_key = f"apps:capability:v2:{capability}:offset={offset}:limit={limit}:reviews={int(include_reviews)}"
    else:
        cache_key = f"apps:capability_groups:v2:offset={offset}:limit={limit}:reviews={int(include_reviews)}"

    cached = get_generic_cache(cache_key)
    if cached:
        return cached

    # Fetch and filter approved public apps
    apps = get_approved_available_apps(include_reviews=include_reviews)
    approved_apps = [a for a in apps if a.approved and (a.private is None or not a.private)]
    # Always exclude persona type apps
    approved_apps = [a for a in approved_apps if not a.is_a_persona()]

    # Capability-specific response
    if capability:
        filtered_apps = filter_apps_by_capability(approved_apps, capability)
        sorted_apps = sort_apps_by_installs(filtered_apps)
        page = paginate_apps(sorted_apps, offset, limit)

        res = {
            'data': [normalize_app_numeric_fields(app.model_dump(mode='json')) for app in page],
            'pagination': build_pagination_metadata(len(sorted_apps), offset, limit, capability),
            'capability': {
                'id': capability,
                'title': next(
                    (c['title'] for c in capabilities if c['id'] == capability), capability.title().replace('_', ' ')
                ),
            },
        }
        set_generic_cache(cache_key, res, ttl=60 * 10)
        return res

    # Grouped response by capability
    grouped_apps = group_apps_by_capability(approved_apps, capabilities)
    groups = build_capability_groups_response(grouped_apps, capabilities, offset, limit)

    res = {
        'groups': groups,
        'meta': {
            'capabilities': capabilities,
            'groupCount': len(groups),
            'limit': limit,
            'offset': offset,
        },
    }
    set_generic_cache(cache_key, res, ttl=60 * 10)
    return res


@router.get('/v2/apps/capability/{capability_id}/grouped', tags=['v2'])
def get_capability_apps_grouped_by_category(
    capability_id: str,
    include_reviews: bool = Query(default=True),
):
    """Get all apps for a specific capability, grouped by master category.

    Returns apps grouped into master categories like:
    - For chat: Personality Clones, Productivity & Lifestyle, Social & Entertainment
    - For others: Productivity & Tools, Personal & Lifestyle, Social & Entertainment
    """

    cache_key = f"apps:capability:{capability_id}:grouped:reviews={int(include_reviews)}"

    cached = get_generic_cache(cache_key)
    if cached:
        return cached

    capabilities = get_capabilities_list()

    # Fetch and filter approved public apps
    apps = get_approved_available_apps(include_reviews=include_reviews)
    approved_apps = [a for a in apps if a.approved and (a.private is None or not a.private)]
    # Always exclude persona type apps
    approved_apps = [a for a in approved_apps if not a.is_a_persona()]

    # Filter apps by capability
    filtered_apps = filter_apps_by_capability(approved_apps, capability_id)

    # Group filtered apps by master category
    grouped_apps = group_capability_apps_by_category(filtered_apps, capability_id)
    groups = build_capability_category_groups_response(grouped_apps, capability_id)

    res = {
        'groups': groups,
        'capability': {
            'id': capability_id,
            'title': next(
                (c['title'] for c in capabilities if c['id'] == capability_id),
                capability_id.title().replace('_', ' '),
            ),
        },
        'meta': {
            'totalApps': len(filtered_apps),
            'groupCount': len(groups),
        },
    }
    set_generic_cache(cache_key, res, ttl=60 * 10)
    return res


@router.get('/v2/apps/search', tags=['v2'])
def search_apps(
    q: str | None = Query(default=None, description='Search query for app name or description'),
    category: str | None = Query(default=None, description='Filter by category id'),
    rating: float | None = Query(default=None, ge=0, le=5, description='Minimum rating filter'),
    capability: str | None = Query(default=None, description='Filter by capability id'),
    sort: str | None = Query(
        default=None, description='Sort order: installs, rating_asc, rating_desc, name_asc, name_desc'
    ),
    my_apps: bool | None = Query(default=None, description='Filter to show only user\'s apps'),
    installed_apps: bool | None = Query(default=None, description='Filter to show only installed/enabled apps'),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    uid: str = Depends(auth.get_current_user_uid),
):
    """Search and filter apps with pagination.

    Returns a flat list of apps matching the search and filter criteria.
    """

    enabled_app_ids = None
    if installed_apps:
        enabled_app_ids = list(get_enabled_apps(uid))

    apps_data = search_apps_db(
        uid=uid,
        category=category,
        capability=capability,
        my_apps=my_apps or False,
        installed_apps=installed_apps or False,
        enabled_app_ids=enabled_app_ids,
    )

    user_enabled = set(get_enabled_apps(uid))

    app_ids = [app['id'] for app in apps_data]
    apps_installs = get_apps_installs_count(app_ids)
    apps_reviews = get_apps_reviews(app_ids)

    apps = []

    for app_dict in apps_data:
        app_dict['enabled'] = app_dict['id'] in user_enabled
        app_dict['rejected'] = app_dict.get('approved') is False
        app_dict['installs'] = apps_installs.get(app_dict['id'], 0)

        # Calculate average from reviews
        reviews = apps_reviews.get(app_dict['id'], {})
        sorted_reviews = list(reviews.values())
        rating_avg = sum([x['score'] for x in sorted_reviews]) / len(sorted_reviews) if reviews else None
        app_dict['rating_avg'] = rating_avg
        app_dict['rating_count'] = len(sorted_reviews)

        apps.append(App(**app_dict))

    # Always exclude persona type apps from results
    filtered_apps = [app for app in apps if not app.is_a_persona()]

    # Apply text search filter
    if q and q.strip():
        search_query = q.strip().lower()
        filtered_apps = [app for app in filtered_apps if search_query in app.name.lower()]

    # Apply rating filter
    if rating is not None:
        filtered_apps = [app for app in filtered_apps if (app.rating_avg or 0) >= rating]

    # Apply sorting
    if sort == 'rating_desc':
        filtered_apps = sorted(filtered_apps, key=lambda a: (a.rating_avg or 0), reverse=True)
    elif sort == 'rating_asc':
        filtered_apps = sorted(filtered_apps, key=lambda a: (a.rating_avg or 0))
    elif sort == 'name_asc':
        filtered_apps = sorted(filtered_apps, key=lambda a: a.name.lower())
    elif sort == 'name_desc':
        filtered_apps = sorted(filtered_apps, key=lambda a: a.name.lower(), reverse=True)
    elif sort == 'installs_desc':
        filtered_apps = sorted(filtered_apps, key=lambda a: (a.installs or 0), reverse=True)
    else:
        # sort by installs when searching, otherwise by name
        if q and q.strip():
            filtered_apps = sorted(filtered_apps, key=lambda a: (a.installs or 0), reverse=True)
        else:
            filtered_apps = sorted(filtered_apps, key=lambda a: a.name.lower())

    # Paginate results
    total = len(filtered_apps)
    page = paginate_apps(filtered_apps, offset, limit)

    return {
        'data': [normalize_app_numeric_fields(app.model_dump()) for app in page],
        'pagination': build_pagination_metadata(total, offset, limit),
        'filters': {
            'query': q,
            'category': category,
            'rating': rating,
            'capability': capability,
            'sort': sort or 'name',
            'my_apps': my_apps,
            'installed_apps': installed_apps,
        },
    }


@router.get('/v1/approved-apps', tags=['v1'], response_model=List[App])
def get_approved_apps(include_reviews: bool = False):
    apps = get_approved_available_apps(include_reviews=include_reviews)
    # Always exclude persona type apps
    return [app for app in apps if not app.is_a_persona()]


@router.get('/v1/apps/popular', tags=['v1'], response_model=List[App])
def get_popular_apps_endpoint(uid: str = Depends(auth.get_current_user_uid)):
    apps = get_popular_apps()
    # Always exclude persona type apps
    return [app for app in apps if not app.is_a_persona()]


@router.post('/v1/apps', tags=['v1'])
def create_app(app_data: str = Form(...), file: UploadFile = File(...), uid=Depends(auth.get_current_user_uid)):
    data = json.loads(app_data)
    data['approved'] = False
    data['status'] = 'under-review'
    data['name'] = (data.get('name') or '').strip()
    data['id'] = str(ULID())
    if not data.get('author') and not data.get('email'):
        user = get_user_from_uid(uid)
        data['author'] = user.get('display_name', '')
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
        if external_integration.get('triggers_on') is None and len(external_integration.get('actions', [])) == 0:
            raise HTTPException(status_code=422, detail='Triggers on or actions is required')
        # Trigger on
        if external_integration.get('triggers_on'):
            external_integration['webhook_url'] = external_integration['webhook_url'].strip()
            if external_integration.get('setup_instructions_file_path'):
                external_integration['setup_instructions_file_path'] = external_integration[
                    'setup_instructions_file_path'
                ].strip()
                if external_integration['setup_instructions_file_path'].startswith('http'):
                    external_integration['is_instructions_url'] = True
                else:
                    external_integration['is_instructions_url'] = False

        # Actions
        if actions := external_integration.get('actions'):
            for action in actions:
                if not action.get('action'):
                    raise HTTPException(status_code=422, detail='Action field is required for each action')
                if action.get('action') not in [action_type.value for action_type in ActionType]:
                    raise HTTPException(
                        status_code=422,
                        detail=f'Unsupported action type. Supported types: {", ".join([action_type.value for action_type in ActionType])}',
                    )
    os.makedirs(f'_temp/apps', exist_ok=True)
    file_path = f"_temp/apps/{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())
    img_url = upload_app_logo(file_path, data['id'])
    data['image'] = img_url
    data['created_at'] = datetime.now(timezone.utc)
    # Backward compatibility: Set app_home_url from first auth step if not provided
    if 'external_integration' in data:
        ext_int = data['external_integration']
        if not ext_int.get('app_home_url') and ext_int.get('auth_steps') and len(ext_int['auth_steps']) == 1:
            ext_int['app_home_url'] = ext_int['auth_steps'][0]['url']

    try:
        app = AppCreate.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Build app dict
    app_dict = app.model_dump(exclude_unset=True)

    # Fetch chat tools from manifest URL (only way to add chat tools)
    if external_integration := data.get('external_integration'):
        manifest_url = external_integration.get('chat_tools_manifest_url')
        if manifest_url:
            fetched_tools = fetch_app_chat_tools_from_manifest(manifest_url)
            if fetched_tools:
                # Resolve relative endpoints to absolute URLs
                base_url = external_integration.get('app_home_url', '').rstrip('/')
                if base_url:
                    for tool in fetched_tools:
                        endpoint = tool.get('endpoint', '')
                        if endpoint.startswith('/') and not endpoint.startswith('//'):
                            tool['endpoint'] = f"{base_url}{endpoint}"
                app_dict['chat_tools'] = fetched_tools

    add_app_to_db(app_dict)

    # payment link
    upsert_app_payment_link(app.id, app.is_paid, app.price, app.payment_plan, app.uid)

    return {'status': 'ok', 'app_id': app.id}


@router.post('/v1/personas', tags=['v1'])
async def create_persona(
    persona_data: str = Form(...), file: UploadFile = File(...), uid=Depends(auth.get_current_user_uid)
):
    data = json.loads(persona_data)
    data['approved'] = False
    data['status'] = 'under-review'
    data['category'] = 'personality-emulation'
    data['name'] = (data.get('name') or '').strip()
    data['id'] = str(ULID())
    data['uid'] = uid
    data['capabilities'] = ['persona']
    user = get_user_from_uid(uid)
    data['author'] = user.get('display_name', '')
    data['email'] = user['email']

    if 'username' not in data or data['username'] == '' or data['username'] is None:
        data['username'] = data['name'].replace(' ', '').lower()
        data['username'] = increment_username(data['username'])
    save_username(data['username'], uid)

    if 'connected_accounts' not in data or data['connected_accounts'] is None:
        data['connected_accounts'] = ['omi']
    data['persona_prompt'] = await generate_persona_prompt(uid, data)
    data['description'] = generate_persona_desc(uid, data['name'])
    os.makedirs(f'_temp/apps', exist_ok=True)
    file_path = f"_temp/apps/{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())
    img_url = upload_app_logo(file_path, data['id'])
    data['image'] = img_url
    data['created_at'] = datetime.now(timezone.utc)

    try:
        app_create = AppCreate.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    add_app_to_db(app_create.model_dump(exclude_unset=True))

    return {'status': 'ok', 'app_id': data['id'], 'username': data['username']}


@router.patch('/v1/personas/{persona_id}', tags=['v1'])
async def update_persona(
    persona_id: str,
    persona_data: str = Form(...),
    file: UploadFile = File(None),
    uid=Depends(auth.get_current_user_uid),
):
    data = json.loads(persona_data)
    persona = get_available_app_by_id(persona_id, uid)
    if not persona:
        raise HTTPException(status_code=404, detail='Persona not found')
    if persona['uid'] != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')

    # Image
    if file:
        if (
            'image' in persona
            and len(persona['image']) > 0
            and persona['image'].startswith('https://storage.googleapis.com/')
        ):
            delete_app_logo(persona['image'])
        os.makedirs(f'_temp/apps', exist_ok=True)
        file_path = f"_temp/apps/{file.filename}"
        with open(file_path, 'wb') as f:
            f.write(file.file.read())
        img_url = upload_app_logo(file_path, persona_id)
        data['image'] = img_url

    save_username(data['username'], uid)
    data['description'] = generate_persona_desc(uid, data['name'])
    data['updated_at'] = datetime.now(timezone.utc)

    # Update 'omi' connected_accounts
    if 'omi' in data.get('connected_accounts', []) and 'omi' not in persona.get('connected_accounts', []):
        data['persona_prompt'] = await generate_persona_prompt(uid, persona)

    try:
        update_app = AppUpdate.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    update_app_in_db(update_app.model_dump(exclude_unset=True))

    if persona['approved'] and (persona['private'] is None or persona['private'] is False):
        delete_generic_cache('get_public_approved_apps_data')
    delete_app_cache_by_id(persona_id)
    return {'status': 'ok', 'app_id': persona_id, 'username': data['username']}


@router.get('/v1/personas', tags=['v1'])
def get_persona_details(uid: str = Depends(auth.get_current_user_uid)):
    app = get_persona_by_uid(uid)
    # print(app)
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
        'status': 'under-review',
        'category': 'personality-emulation',
        'capabilities': ['persona'],
        'connected_accounts': ['omi'],
        'created_at': datetime.now(timezone.utc),
        'private': True,
    }

    # Generate persona prompt
    persona_data['persona_prompt'] = await generate_persona_prompt(uid, persona_data)

    try:
        persona_create = AppCreate.model_validate(persona_data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Save username
    save_username(persona_data['username'], uid)

    # Add persona to database
    add_app_to_db(persona_create.model_dump(exclude_unset=True))

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
def update_app(
    app_id: str, app_data: str = Form(...), file: UploadFile = File(None), uid=Depends(auth.get_current_user_uid)
):
    data = json.loads(app_data)
    app = get_available_app_by_id(app_id, uid)
    if not app:
        raise HTTPException(status_code=404, detail='App not found')
    if app['uid'] != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    if file:
        if 'image' in app and len(app['image']) > 0 and app['image'].startswith('https://storage.googleapis.com/'):
            delete_app_logo(app['image'])
        os.makedirs(f'_temp/apps', exist_ok=True)
        file_path = f"_temp/apps/{file.filename}"
        with open(file_path, 'wb') as f:
            f.write(file.file.read())
        img_url = upload_app_logo(file_path, app_id)
        data['image'] = img_url
    data['updated_at'] = datetime.now(timezone.utc)

    # Backward compatibility: Set app_home_url from first auth step if not provided
    if 'external_integration' in data:
        ext_int = data['external_integration']
        if not ext_int.get('app_home_url') and ext_int.get('auth_steps') and len(ext_int['auth_steps']) == 1:
            ext_int['app_home_url'] = ext_int['auth_steps'][0]['url']

    try:
        update_app = AppUpdate.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Build update dict
    update_dict = update_app.model_dump(exclude_unset=True)

    # Fetch chat tools from manifest URL (only way to add/update chat tools)
    if external_integration := data.get('external_integration'):
        manifest_url = external_integration.get('chat_tools_manifest_url')
        if manifest_url:
            fetched_tools = fetch_app_chat_tools_from_manifest(manifest_url)
            if fetched_tools:
                # Resolve relative endpoints to absolute URLs
                base_url = external_integration.get('app_home_url', '').rstrip('/')
                if base_url:
                    for tool in fetched_tools:
                        endpoint = tool.get('endpoint', '')
                        if endpoint.startswith('/') and not endpoint.startswith('//'):
                            tool['endpoint'] = f"{base_url}{endpoint}"
                update_dict['chat_tools'] = fetched_tools

    update_app_in_db(update_dict)

    # payment link
    upsert_app_payment_link(
        data.get('id'),
        data.get('is_paid', False),
        data.get('price'),
        data.get('payment_plan'),
        data.get('uid'),
        previous_price=app.get("price", 0),
    )

    if app['approved'] and (app['private'] is None or app['private'] is False):
        delete_generic_cache('get_public_approved_apps_data')
    delete_app_cache_by_id(app_id)
    return {'status': 'ok'}


@router.delete('/v1/apps/{app_id}', tags=['v1'])
def delete_app(app_id: str, uid: str = Depends(auth.get_current_user_uid)):
    app = get_available_app_by_id(app_id, uid)
    if not app:
        raise HTTPException(status_code=404, detail='App not found')
    if app['uid'] != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    delete_app_from_db(app_id)
    if app['approved']:
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
        app.thumbnail_urls = [get_app_thumbnail_url(thumbnail_id) for thumbnail_id in app.thumbnails]

    return app


@router.get('/v1/app-categories', tags=['v1'])
def get_app_categories():
    return [
        {'title': 'Conversation Analysis', 'id': 'conversation-analysis'},
        {'title': 'Personality Clone', 'id': 'personality-emulation'},
        {'title': 'Health', 'id': 'health-and-wellness'},
        {'title': 'Education', 'id': 'education-and-learning'},
        {'title': 'Communication', 'id': 'communication-improvement'},
        {'title': 'Emotional Support', 'id': 'emotional-and-mental-support'},
        {'title': 'Productivity', 'id': 'productivity-and-organization'},
        {'title': 'Entertainment', 'id': 'entertainment-and-fun'},
        {'title': 'Financial', 'id': 'financial'},
        {'title': 'Travel', 'id': 'travel-and-exploration'},
        {'title': 'Safety', 'id': 'safety-and-security'},
        {'title': 'Shopping', 'id': 'shopping-and-commerce'},
        {'title': 'Social', 'id': 'social-and-relationships'},
        {'title': 'News', 'id': 'news-and-information'},
        {'title': 'Utilities', 'id': 'utilities-and-tools'},
        {'title': 'Other', 'id': 'other'},
    ]


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
        'uid': uid,
    }
    set_app_review(app_id, uid, review_data)

    # Send notification to app owner
    if review_body := data.get('review', ''):
        send_new_app_review_notification(
            app_owner_uid=app.uid,
            reviewer_uid=uid,
            app_id=app_id,
            app_name=app.name,
            review_body=review_body,
        )

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
        'uid': uid,
    }
    set_app_review(app_id, uid, review_data)

    # Send notification to app owner
    if review_body := data.get('review', ''):
        send_new_app_review_notification(
            app_owner_uid=app.uid,
            reviewer_uid=uid,
            app_id=app_id,
            app_name=app.name,
            review_body=review_body,
        )

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

    reviewer_uid = data.get('reviewer_uid')
    if not reviewer_uid:
        raise HTTPException(status_code=422, detail='Reviewer UID is required')

    review = get_specific_user_review(app_id, reviewer_uid)
    if not review:
        raise HTTPException(status_code=404, detail='Review not found')

    review['response'] = data['response']
    review['responded_at'] = datetime.now(timezone.utc).isoformat()
    set_app_review(app_id, reviewer_uid, review)

    # Send notification to reviewer
    send_app_review_reply_notification(
        reviewer_uid,
        app.uid,
        data['response'],
        app_id,
        app.name,
    )

    return {'status': 'ok'}


@router.get('/v1/apps/{app_id}/reviews', tags=['v1'])
def app_reviews(app_id: str):
    reviews = get_app_reviews(app_id)
    reviews = [details for details in reviews.values() if details['review']]
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
        {'title': 'User Memories', 'id': 'user_facts'},
        {'title': 'User Conversations', 'id': 'user_context'},
        {'title': 'User Chat', 'id': 'user_chat'},
    ]


@router.get('/v1/app-capabilities', tags=['v1'])
def get_app_capabilities():
    return [
        {'title': 'Chat', 'id': 'chat'},
        {'title': 'Conversations', 'id': 'memories'},
        {
            'title': 'External Integration',
            'id': 'external_integration',
            'triggers': [
                {'title': 'Audio Bytes', 'id': 'audio_bytes'},
                {'title': 'Conversation Creation', 'id': 'memory_creation'},
                {'title': 'Transcript Processed', 'id': 'transcript_processed'},
            ],
            'actions': [
                {
                    'title': 'Create conversations',
                    'id': 'create_conversation',
                    'doc_url': 'https://docs.omi.me/doc/developer/apps/Import',
                    'description': 'Extend user conversations by making a POST request to the OMI System.',
                },
                {
                    'title': 'Create memories',
                    'id': 'create_facts',
                    'doc_url': 'https://docs.omi.me/doc/developer/apps/Import',
                    'description': 'Create new memories for the user through the OMI System.',
                },
                {
                    'title': 'Read conversations',
                    'id': 'read_conversations',
                    'doc_url': 'https://docs.omi.me/doc/developer/apps/Import',
                    'description': 'Access and read all user conversations through the OMI System. This gives the app access to all conversation history.',
                },
                {
                    'title': 'Read memories',
                    'id': 'read_memories',
                    'doc_url': 'https://docs.omi.me/doc/developer/apps/Import',
                    'description': 'Access and read all user memories through the OMI System. This gives the app access to all stored memories.',
                },
                {
                    'title': 'Read tasks',
                    'id': 'read_tasks',
                    'doc_url': 'https://docs.omi.me/doc/developer/apps/Import',
                    'description': 'Access and read all user tasks (to-dos) through the OMI System. This gives the app access to all stored tasks.',
                },
            ],
        },
        {
            'title': 'Notification',
            'id': 'proactive_notification',
            'scopes': [
                {'title': 'User Name', 'id': 'user_name'},
                {'title': 'User Facts', 'id': 'user_facts'},
                {'title': 'User Conversations', 'id': 'user_context'},
                {'title': 'User Chat', 'id': 'user_chat'},
            ],
        },
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


@router.post('/v1/app/generate-description-emoji', tags=['v1'])
def generate_description_and_emoji_endpoint(data: dict, uid: str = Depends(auth.get_current_user_uid)):
    """
    Generate an app description and representative emoji.
    Used by the quick template creator feature.
    """
    from utils.llm.app_generator import generate_description_and_emoji

    if not data.get('name'):
        raise HTTPException(status_code=422, detail='App Name is required')
    if not data.get('prompt'):
        raise HTTPException(status_code=422, detail='App Prompt is required')

    result = generate_description_and_emoji(data['name'], data['prompt'])
    return result


# ******************************************************
# ****************** AI APP GENERATOR ******************
# ******************************************************


@router.get('/v1/app/generate-prompts', tags=['v1'])
async def generate_sample_prompts_endpoint(uid: str = Depends(auth.get_current_user_uid)):
    """
    Generate sample app prompts for the AI app generator.
    Uses a fast model to generate creative suggestions.
    """
    from utils.llm.clients import llm_mini
    import json

    system_prompt = """Generate 5 creative and diverse ideas for apps that are either:
1. Conversation summary based apps - analyze user's recorded conversations and extract/organize information
2. Chat assistant based apps - AI personas or assistants users can chat with

Generate exactly 3 conversation-based and 2 chat-based app ideas.

Examples:
- Conversation based: "Mind map generator from my conversations", "Jokes and funny moments extractor", "Meeting action items tracker"
- Chat based: "Elon Musk personality clone", "Strict accountability mentor", "Socratic philosophy tutor"

Return ONLY a JSON array of 5 strings, each being a short app description (max 50 characters).
Format: ["idea 1", "idea 2", "idea 3", "idea 4", "idea 5"]

First 3 should be conversation-based, last 2 should be chat-based.
Be creative, fun, and varied. No generic ideas."""

    try:
        response = await llm_mini.ainvoke(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Generate 5 creative app ideas now"},
            ]
        )

        content = response.content.strip()

        # Parse JSON from response
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        prompts = json.loads(content)

        if isinstance(prompts, list) and len(prompts) >= 5:
            return {"prompts": prompts[:5]}
        else:
            # Fallback
            return {
                "prompts": [
                    "Mind map generator from conversations",
                    "Jokes and funny moments extractor",
                    "Key decisions and commitments tracker",
                    "Elon Musk startup advisor clone",
                    "Strict accountability coach",
                ]
            }
    except Exception as e:
        print(f"Error generating prompts: {e}")
        return {
            "prompts": [
                "Mind map generator from conversations",
                "Jokes and funny moments extractor",
                "Key decisions and commitments tracker",
                "Elon Musk startup advisor clone",
                "Strict accountability coach",
            ]
        }


@router.post('/v1/app/generate', tags=['v1'])
async def generate_app_endpoint(data: dict, uid: str = Depends(auth.get_current_user_uid)):
    """
    Generate an app configuration from a natural language prompt.
    This is an experimental feature that uses AI to create app configurations.
    """
    from utils.llm.app_generator import generate_app_from_prompt, generate_app_icon

    prompt = data.get('prompt', '').strip()
    if not prompt:
        raise HTTPException(status_code=422, detail='Prompt is required')

    if len(prompt) < 10:
        raise HTTPException(status_code=422, detail='Prompt is too short. Please provide more details.')

    if len(prompt) > 2000:
        raise HTTPException(status_code=422, detail='Prompt is too long. Please keep it under 2000 characters.')

    try:
        # Generate app configuration using LLM
        generated_app = await generate_app_from_prompt(prompt)

        return {
            'status': 'ok',
            'app': {
                'name': generated_app.name,
                'description': generated_app.description,
                'category': generated_app.category,
                'capabilities': generated_app.capabilities,
                'chat_prompt': generated_app.chat_prompt,
                'memory_prompt': generated_app.memory_prompt,
            },
        }
    except Exception as e:
        print(f"Error generating app: {e}")
        raise HTTPException(status_code=500, detail=f'Failed to generate app: {str(e)}')


@router.post('/v1/app/generate-icon', tags=['v1'])
async def generate_app_icon_endpoint(data: dict, uid: str = Depends(auth.get_current_user_uid)):
    """
    Generate an app icon using AI (DALL-E).
    Returns the icon as a base64 encoded PNG image.
    """
    from utils.llm.app_generator import generate_app_icon
    import base64

    app_name = data.get('name', '').strip()
    app_description = data.get('description', '').strip()
    category = data.get('category', 'other').strip()

    if not app_name:
        raise HTTPException(status_code=422, detail='App name is required')

    if not app_description:
        raise HTTPException(status_code=422, detail='App description is required')

    try:
        # Generate icon using DALL-E
        icon_bytes = await generate_app_icon(app_name, app_description, category)

        # Return as base64
        icon_base64 = base64.b64encode(icon_bytes).decode('utf-8')

        return {'status': 'ok', 'icon_base64': icon_base64, 'mime_type': 'image/png'}
    except Exception as e:
        print(f"Error generating icon: {e}")
        raise HTTPException(status_code=500, detail=f'Failed to generate icon: {str(e)}')


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
    username: str, handle: str, uid: str = Depends(auth.get_current_user_uid), persona_id: str | None = None
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

    # Start async tasks to migrate memories and update persona connected accounts
    asyncio.create_task(migrate_memories(old_id, uid))
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


@router.patch('/v1/apps/{app_id}/popular', tags=['v1'])
def set_app_popular(app_id: str, value: bool = Query(...), secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    set_app_popular_db(app_id, value)
    delete_app_cache_by_id(app_id)
    delete_generic_cache('get_popular_apps_data')
    return {'status': 'ok'}


@router.post('/v1/apps/{app_id}/approve', tags=['v1'])
def approve_app(app_id: str, uid: str, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    change_app_approval_status(app_id, True)
    delete_app_cache_by_id(app_id)
    app = get_available_app_by_id(app_id, uid)
    send_notification(
        uid,
        'App Approved 🎉',
        f'Your app {app["name"]} has been approved and is now available for everyone to use 🥳',
    )
    return {'status': 'ok'}


@router.post('/v1/apps/{app_id}/reject', tags=['v1'])
def reject_app(app_id: str, uid: str, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    change_app_approval_status(app_id, False)
    delete_app_cache_by_id(app_id)
    app = get_available_app_by_id(app_id, uid)
    # TODO: Add reason for rejection in payload and also redirect to the app page
    send_notification(
        uid,
        'App Rejected 😔',
        f'Your app {app["name"]} has been rejected. Please make the necessary changes and resubmit for approval.',
    )
    return {'status': 'ok'}


@router.delete('/v1/personas/{persona_id}', tags=['v1'])
@router.post('/v1/app/thumbnails', tags=['v1'])
async def upload_app_thumbnail_endpoint(file: UploadFile = File(...), uid: str = Depends(auth.get_current_user_uid)):
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

        return {'thumbnail_url': url, 'thumbnail_id': thumbnail_id}

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

    data = {'id': str(ULID()), 'hashed': hashed_key, 'label': label, 'created_at': datetime.now(timezone.utc)}
    create_api_key_db(app_id, data)

    # Return both the raw key (for one-time display to user) and the stored data
    return {'id': data['id'], 'secret': key, 'label': label, 'created_at': data['created_at']}  # with sk_


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


# ******************************************************
# ******** CONVERSATION SUMMARY APP IDS ****************
# ******************************************************


@router.get('/v1/summary-app-ids', tags=['v1'])
def get_summary_app_ids(secret_key: str = Header(...)):
    """Get all conversation summary app IDs from Redis"""
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='Forbidden')

    app_ids = get_conversation_summary_app_ids()
    print(app_ids)
    return {'app_ids': app_ids or []}


@router.post('/v1/summary-app-ids/{app_id}', tags=['v1'])
def add_summary_app_id(app_id: str, secret_key: str = Header(...)):
    """Add an app ID to the conversation summary apps list"""
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='Forbidden')

    success = add_conversation_summary_app_id(app_id)
    if success:
        return {'status': 'ok', 'message': f'App {app_id} added to conversation summary apps'}
    else:
        return {'status': 'ok', 'message': f'App {app_id} already exists in conversation summary apps'}


@router.delete('/v1/summary-app-ids/{app_id}', tags=['v1'])
def delete_summary_app_id(app_id: str, secret_key: str = Header(...)):
    """Remove an app ID from the conversation summary apps list"""
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='Forbidden')

    success = remove_conversation_summary_app_id(app_id)
    if success:
        return {'status': 'ok', 'message': f'App {app_id} removed from conversation summary apps'}
    else:
        raise HTTPException(status_code=404, detail=f'App {app_id} not found in conversation summary apps')
