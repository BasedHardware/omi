# async-blockers: no-import-scope
# async-blockers: no-changed-range-scope  # pre-existing patterns surfaced by type-annotation import changes
import asyncio
import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import ValidationError
from pydantic import BaseModel as PydanticBaseModel
from ulid import ULID

from utils.apps import fetch_app_chat_tools_from_manifest
from utils.executors import db_executor, llm_executor, run_blocking, storage_executor
from utils.http_client import get_webhook_client
from utils.llm.app_generator import (
    generate_app_from_prompt,
    generate_app_icon,
    generate_description,
    generate_description_and_emoji,
)
from utils.llm.clients import get_llm
from utils.llm.persona import generate_persona_intro_message
from utils.llm.usage_tracker import Features, track_usage
from utils.mcp_client import (
    build_authorization_url,
    discover_mcp_tools,
    discover_oauth_metadata,
    exchange_oauth_code,
    fetch_brandfetch_logo,
    generate_pkce_pair,
    generate_state_token,
    parse_state_token,
    refresh_oauth_token,
    register_oauth_client,
)
from utils.notifications import (
    send_app_review_reply_notification,
    send_new_app_review_notification,
    send_notification,
)
from utils.other import endpoints as auth
from utils.other.storage import delete_app_logo, get_app_thumbnail_url, upload_app_logo, upload_app_thumbnail
from utils.request_validation import (
    backfill_app_home_url_from_auth_steps,
    normalize_required_webhook_url,
    parse_form_json,
)
from utils.social import (
    add_twitter_to_persona,
    get_twitter_profile,
    upsert_persona_from_twitter_profile,
    verify_latest_tweet,
)

from database.apps import (
    add_app_to_db,
    change_app_approval_status,
    create_api_key_db,
    delete_api_key_db,
    delete_app_from_db,
    delete_persona_db,
    get_app_by_id_db,
    get_omi_persona_apps_by_uid_db,
    get_persona_by_id_db,
    get_persona_by_twitter_handle_db,
    get_persona_by_username_db,
    get_personas_by_username_db,
    get_unapproved_public_apps_db,
    get_user_persona_by_uid,
    list_api_keys_db,
    migrate_app_owner_id_db,
    search_apps_db,
    set_app_popular_db,
    update_app_in_db,
    update_app_visibility_in_db,
)
from database.auth import get_user_from_uid
from database.memories import migrate_memories
from database.redis_db import (
    add_conversation_summary_app_id,
    decrease_app_installs_count,
    delete_app_cache_by_id,
    disable_app,
    enable_app,
    get_apps_installs_count,
    get_apps_reviews,
    get_conversation_summary_app_ids,
    get_enabled_apps,
    get_generic_cache,
    get_specific_user_review,
    increase_app_installs_count,
    is_app_enabled,
    remove_conversation_summary_app_id,
    save_username,
    set_generic_cache,
)
from database.webhook_health import clear_app_webhook_health
from utils.apps import (
    add_app_access_for_tester,
    add_tester,
    build_capability_category_groups_response,
    build_capability_groups_response,
    build_pagination_metadata,
    filter_apps_by_capability,
    generate_api_key,
    generate_persona_desc,
    generate_persona_prompt,
    get_app_reviews,
    get_approved_available_apps,
    get_available_app_by_id,
    get_available_app_by_id_with_reviews,
    get_available_apps,
    get_capabilities_list,
    get_is_user_paid_app,
    get_persona_by_uid,
    get_popular_apps,
    increment_username,
    invalidate_approved_apps_cache,
    invalidate_popular_apps_cache,
    is_permit_payment_plan_get,
    is_tester,
    normalize_app_numeric_fields,
    paginate_apps,
    remove_app_access_for_tester,
    set_app_review,
    sort_apps_by_installs,
    group_apps_by_capability,
    group_capability_apps_by_category,
    upsert_app_payment_link,
    validate_app_endpoints_for_reenable,
)

from models.app import ActionType, App, AppBaseModel, AppCreate, AppUpdate, ChatTool

logger = logging.getLogger(__name__)

router = APIRouter()


def _write_file(path: str, data: bytes) -> None:
    """Write bytes to file — offloaded to storage_executor."""
    with open(path, 'wb') as f:
        f.write(data)


def _get_app_by_id(app_id: str, uid: Optional[str]) -> Optional[Dict[str, Any]]:
    """Typed wrapper for get_available_app_by_id."""
    return get_available_app_by_id(app_id, uid)


def _get_app_by_id_with_reviews(app_id: str, uid: Optional[str]) -> Optional[Dict[str, Any]]:
    """Typed wrapper for get_available_app_by_id_with_reviews."""
    return get_available_app_by_id_with_reviews(app_id, uid)


def _process_chat_tools_manifest(external_integration: Dict[str, Any], app_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch and process chat tools manifest, updating and returning app_dict.

    Fetches the manifest from chat_tools_manifest_url, resolves relative endpoints
    to absolute URLs using app_home_url, and stores chat_messages config.

    Args:
        external_integration: The external_integration dict from app data
        app_dict: The app dict to update with chat_tools and chat_messages config

    Returns:
        The updated app_dict
    """
    manifest_url = external_integration.get('chat_tools_manifest_url')
    if not manifest_url:
        return app_dict

    manifest_result = fetch_app_chat_tools_from_manifest(manifest_url)
    if not manifest_result:
        return app_dict

    fetched_tools_raw = manifest_result.get('tools')
    fetched_tools: List[Dict[str, Any]] = (
        [cast(Dict[str, Any], t) for t in cast(List[Any], fetched_tools_raw) if isinstance(t, dict)]
        if isinstance(fetched_tools_raw, list)
        else []
    )
    if fetched_tools:
        # Resolve relative endpoints to absolute URLs
        base_url = str(external_integration.get('app_home_url', '') or '').rstrip('/')
        if base_url:
            for tool in fetched_tools:
                endpoint = str(tool.get('endpoint', '') or '')
                if endpoint.startswith('/') and not endpoint.startswith('//'):
                    tool['endpoint'] = f"{base_url}{endpoint}"
        app_dict['chat_tools'] = fetched_tools

    # Store chat_messages config in external_integration
    chat_messages = manifest_result.get('chat_messages')
    if 'external_integration' not in app_dict:
        app_dict['external_integration'] = {}
    if chat_messages:
        app_dict['external_integration']['chat_messages_enabled'] = chat_messages.get('enabled', False)
        app_dict['external_integration']['chat_messages_target'] = chat_messages.get('target', 'app')
        app_dict['external_integration']['chat_messages_notify'] = chat_messages.get('notify', False)
    else:
        # Reset all chat_messages fields to defaults when not in manifest
        app_dict['external_integration']['chat_messages_enabled'] = False
        app_dict['external_integration']['chat_messages_target'] = 'app'
        app_dict['external_integration']['chat_messages_notify'] = False

    return app_dict


# ******************************************************
# ********************* APPS CRUD **********************
# ******************************************************


@router.get('/v1/apps', tags=['v1'], response_model=List[AppBaseModel])
def get_apps(uid: str = Depends(auth.get_current_user_uid), include_reviews: bool = True) -> List[Dict[str, Any]]:
    apps = get_available_apps(uid, include_reviews=include_reviews)
    return [normalize_app_numeric_fields(app.to_reduced_dict()) for app in apps]


@router.get('/v1/apps/enabled', tags=['v1'])
def get_user_enabled_apps(uid: str = Depends(auth.get_current_user_uid)) -> List[str]:
    """Returns the list of app IDs the user has enabled/installed."""
    return get_enabled_apps(uid)


@router.get('/v2/apps', tags=['v2'])
def get_apps_v2(
    capability: str | None = Query(default=None, description='Filter by capability id'),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    include_reviews: bool = Query(default=False),
) -> Any:
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
    approved_apps = [a for a in apps if a.approved and (cast(Optional[bool], a.private) is None or not a.private)]
    # Always exclude persona type apps
    approved_apps = [a for a in approved_apps if not a.is_a_persona()]

    # Capability-specific response
    if capability:
        filtered_apps = filter_apps_by_capability(approved_apps, capability)
        sorted_apps = sort_apps_by_installs(filtered_apps)
        page = paginate_apps(sorted_apps, offset, limit)

        res: Dict[str, Any] = {
            'data': [normalize_app_numeric_fields(app.to_reduced_dict()) for app in page],
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
) -> Any:
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
    approved_apps = [a for a in apps if a.approved and (cast(Optional[bool], a.private) is None or not a.private)]
    # Always exclude persona type apps
    approved_apps = [a for a in approved_apps if not a.is_a_persona()]

    # Filter apps by capability
    filtered_apps = filter_apps_by_capability(approved_apps, capability_id)

    # Group filtered apps by master category
    grouped_apps = group_capability_apps_by_category(filtered_apps, capability_id)
    groups = build_capability_category_groups_response(grouped_apps, capability_id)

    res: Dict[str, Any] = {
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
) -> Dict[str, Any]:
    """Search and filter apps with pagination.

    Returns a flat list of apps matching the search and filter criteria.
    """

    enabled_app_ids: Optional[List[str]] = None
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

    # Drop any malformed record missing an id before enrichment: id drives the installs/reviews/
    # enabled lookups below and the pre-loop app_ids list, so a missing id would KeyError before the
    # per-record ValidationError guard can catch it.
    valid_apps_data = [a for a in apps_data if a.get('id')]
    skipped_no_id = len(apps_data) - len(valid_apps_data)
    if skipped_no_id:
        logger.warning("Skipping %d malformed app record(s) without an id in search results", skipped_no_id)
    apps_data = valid_apps_data

    app_ids = [app['id'] for app in apps_data]
    apps_installs = get_apps_installs_count(app_ids)
    apps_reviews = get_apps_reviews(app_ids)

    apps: List[App] = []

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

        # Skip a malformed/legacy app document rather than 500 the whole search page.
        try:
            apps.append(App(**app_dict))
        except ValidationError as e:
            logger.warning(
                "Skipping malformed app %s in search results: %s",
                app_dict.get('id'),
                [err['loc'][0] for err in e.errors() if err.get('loc')],
            )

    # Always exclude persona type apps from results
    filtered_apps: List[App] = [app for app in apps if not app.is_a_persona()]

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
        'data': [normalize_app_numeric_fields(app.to_reduced_dict()) for app in page],
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


@router.get('/v1/approved-apps', tags=['v1'], response_model=List[AppBaseModel])
def get_approved_apps(include_reviews: bool = False) -> List[Dict[str, Any]]:
    apps = get_approved_available_apps(include_reviews=include_reviews)
    # Always exclude persona type apps
    filtered_apps = [app for app in apps if not app.is_a_persona()]
    return [normalize_app_numeric_fields(app.to_reduced_dict()) for app in filtered_apps]


@router.get('/v1/apps/popular', tags=['v1'], response_model=List[AppBaseModel])
def get_popular_apps_endpoint(uid: str = Depends(auth.get_current_user_uid)) -> List[Dict[str, Any]]:
    apps = get_popular_apps()
    # Always exclude persona type apps
    filtered_apps = [app for app in apps if not app.is_a_persona()]
    return [normalize_app_numeric_fields(app.to_reduced_dict()) for app in filtered_apps]


@router.post('/v1/apps', tags=['v1'])
def create_app(
    app_data: str = Form(...), file: UploadFile = File(...), uid: str = Depends(auth.get_current_user_uid)
) -> Dict[str, str]:
    data: Dict[str, Any] = parse_form_json(dict, app_data, 'app_data')
    data['approved'] = False
    data['status'] = 'under-review'
    data['name'] = (data.get('name') or '').strip()
    data['id'] = str(ULID())
    data['uid'] = uid
    if not data.get('author') and not data.get('email'):
        user = get_user_from_uid(uid) or {}
        email = user.get('email')
        # author is required + non-null on AppCreate; display_name/email can both be null.
        data['author'] = user.get('display_name') or (email.split('@')[0] if email else None) or 'Anonymous'
        data['email'] = email
    if not data.get('is_paid'):
        data['is_paid'] = False
    else:
        if data['is_paid'] is True:
            if data.get('price') is None:
                raise HTTPException(status_code=422, detail='App price is required')
            if cast(float, data.get('price')) < 0.0:
                raise HTTPException(status_code=422, detail='Price cannot be a negative value')
            if data.get('payment_plan') is None:
                raise HTTPException(status_code=422, detail='Payment plan is required')

    if external_integration := data.get('external_integration'):
        ext_int = cast(Dict[str, Any], external_integration) if isinstance(external_integration, dict) else {}
        if ext_int.get('triggers_on') is None and len(ext_int.get('actions', [])) == 0:
            raise HTTPException(status_code=422, detail='Triggers on or actions is required')
        # Trigger on
        if ext_int.get('triggers_on'):
            normalize_required_webhook_url(ext_int)
            if ext_int.get('setup_instructions_file_path'):
                ext_int['setup_instructions_file_path'] = cast(str, ext_int['setup_instructions_file_path']).strip()
                if ext_int['setup_instructions_file_path'].startswith('http'):
                    ext_int['is_instructions_url'] = True
                else:
                    ext_int['is_instructions_url'] = False

        # Actions
        if actions := ext_int.get('actions'):
            for action in actions:
                action_dict = cast(Dict[str, Any], action) if isinstance(action, dict) else {}
                if not action_dict.get('action'):
                    raise HTTPException(status_code=422, detail='Action field is required for each action')
                if action_dict.get('action') not in [action_type.value for action_type in ActionType]:
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
        backfill_app_home_url_from_auth_steps(data['external_integration'])

    try:
        app = AppCreate.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Build app dict
    app_dict = app.model_dump(exclude_unset=True)

    # Fetch chat tools from manifest URL (only way to add chat tools)
    if external_integration := data.get('external_integration'):
        app_dict = _process_chat_tools_manifest(
            cast(Dict[str, Any], external_integration) if isinstance(external_integration, dict) else {},
            app_dict,
        )

    add_app_to_db(app_dict)

    # payment link
    upsert_app_payment_link(
        app.id,
        cast(bool, app.is_paid),
        cast(float, app.price),
        cast(str, app.payment_plan),
        cast(str, app.uid),
    )

    return {'status': 'ok', 'app_id': app.id}


@router.post('/v1/personas', tags=['v1'])
async def create_persona(
    persona_data: str = Form(...), file: UploadFile = File(...), uid: str = Depends(auth.get_current_user_uid)
) -> Dict[str, str]:
    data: Dict[str, Any] = parse_form_json(dict, persona_data, 'persona_data')
    data['approved'] = False
    data['status'] = 'under-review'
    data['category'] = 'personality-emulation'
    data['name'] = (data.get('name') or '').strip()
    data['id'] = str(ULID())
    data['uid'] = uid
    data['capabilities'] = ['persona']
    user_raw = await run_blocking(db_executor, get_user_from_uid, uid)
    user: Dict[str, Any] = user_raw if isinstance(user_raw, dict) else {}
    data['author'] = user.get('display_name', '')
    data['email'] = user.get('email')

    if 'username' not in data or data['username'] == '' or data['username'] is None:
        data['username'] = data['name'].replace(' ', '').lower()
        data['username'] = await run_blocking(db_executor, increment_username, data['username'])
    await run_blocking(db_executor, save_username, data['username'], uid)

    if 'connected_accounts' not in data or data['connected_accounts'] is None:
        data['connected_accounts'] = ['omi']
    data['persona_prompt'] = await generate_persona_prompt(uid, data)
    data['description'] = await run_blocking(llm_executor, generate_persona_desc, uid, data['name'])
    os.makedirs(f'_temp/apps', exist_ok=True)
    file_path = f"_temp/apps/{file.filename}"
    contents = await file.read()
    await run_blocking(storage_executor, _write_file, file_path, contents)
    img_url = await run_blocking(storage_executor, upload_app_logo, file_path, data['id'])
    data['image'] = img_url
    data['created_at'] = datetime.now(timezone.utc)

    try:
        app_create = AppCreate.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    await run_blocking(db_executor, add_app_to_db, app_create.model_dump(exclude_unset=True))

    return {'status': 'ok', 'app_id': data['id'], 'username': data['username']}


@router.patch('/v1/personas/{persona_id}', tags=['v1'])
async def update_persona(
    persona_id: str,
    persona_data: str = Form(...),
    file: UploadFile = File(None),
    uid: str = Depends(auth.get_current_user_uid),
) -> Dict[str, str]:
    data: Dict[str, Any] = parse_form_json(dict, persona_data, 'persona_data')
    persona_raw = await run_blocking(db_executor, _get_app_by_id, persona_id, uid)
    persona: Optional[Dict[str, Any]] = persona_raw if isinstance(persona_raw, dict) else None
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
            await run_blocking(storage_executor, delete_app_logo, persona['image'])
        os.makedirs(f'_temp/apps', exist_ok=True)
        file_path = f"_temp/apps/{file.filename}"
        contents = await file.read()
        await run_blocking(storage_executor, _write_file, file_path, contents)
        img_url = await run_blocking(storage_executor, upload_app_logo, file_path, persona_id)
        data['image'] = img_url

    await run_blocking(db_executor, save_username, data['username'], uid)
    data['description'] = await run_blocking(llm_executor, generate_persona_desc, uid, data['name'])
    data['updated_at'] = datetime.now(timezone.utc)

    # Update 'omi' connected_accounts
    if 'omi' in data.get('connected_accounts', []) and 'omi' not in persona.get('connected_accounts', []):
        data['persona_prompt'] = await generate_persona_prompt(uid, persona)

    try:
        update_app = AppUpdate.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    await run_blocking(db_executor, update_app_in_db, update_app.model_dump(exclude_unset=True))

    if persona['approved'] and (
        cast(Optional[bool], persona['private']) is None or cast(Optional[bool], persona['private']) is False
    ):
        await run_blocking(db_executor, invalidate_approved_apps_cache)
    await run_blocking(db_executor, delete_app_cache_by_id, persona_id)
    return {'status': 'ok', 'app_id': persona_id, 'username': data['username']}


@router.get('/v1/personas', tags=['v1'])
def get_persona_details(uid: str = Depends(auth.get_current_user_uid)) -> App:
    app_raw = get_persona_by_uid(uid)
    app = App(**app_raw) if app_raw else None
    if not app:
        raise HTTPException(status_code=404, detail='Persona not found')
    if app.uid != uid:
        raise HTTPException(status_code=404, detail='Persona not found')
    if cast(Optional[bool], app.private) is not None:
        if app.private and app.uid != uid:
            raise HTTPException(status_code=403, detail='You are not authorized to view this Persona')

    return app


@router.post('/v1/user/persona', tags=['v1'])
async def get_or_create_user_persona(uid: str = Depends(auth.get_current_user_uid)) -> Any:
    """Get or create a user persona.

    If the user already has a persona, return it.
    If not, create a new one with default values.
    """
    # Check if user already has a persona
    persona = await run_blocking(db_executor, get_user_persona_by_uid, uid)
    if persona:
        # Return existing persona
        return persona

    # Create a new persona for the user
    user_raw = await run_blocking(db_executor, get_user_from_uid, uid)
    user: Dict[str, Any] = user_raw if isinstance(user_raw, dict) else {}

    # Generate a unique ID for the persona
    persona_id = str(ULID())

    # Create persona data
    persona_data: Dict[str, Any] = {
        'id': persona_id,
        'name': user.get('display_name', 'My Persona'),
        'username': await run_blocking(
            db_executor, increment_username, (user.get('display_name') or 'MyPersona').replace(' ', '').lower()
        ),
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
    await run_blocking(db_executor, save_username, persona_data['username'], uid)

    # Add persona to database
    await run_blocking(db_executor, add_app_to_db, persona_create.model_dump(exclude_unset=True))

    return persona_data


@router.patch('/v1/apps/{app_id}', tags=['v1'])
def update_app(
    app_id: str,
    app_data: str = Form(...),
    file: UploadFile = File(None),
    uid: str = Depends(auth.get_current_user_uid),
) -> Dict[str, str]:
    data: Dict[str, Any] = parse_form_json(dict, app_data, 'app_data')
    app_raw = _get_app_by_id(app_id, uid)
    app: Optional[Dict[str, Any]] = app_raw if isinstance(app_raw, dict) else None
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
        ext_int_data = data['external_integration']
        backfill_app_home_url_from_auth_steps(
            cast(Dict[str, Any], ext_int_data) if isinstance(ext_int_data, dict) else {}
        )

    try:
        update_app = AppUpdate.model_validate(data)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Build update dict
    update_dict: Dict[str, Any] = update_app.model_dump(exclude_unset=True)

    # Fetch chat tools from manifest URL (only way to add/update chat tools)
    if external_integration := data.get('external_integration'):
        update_dict = _process_chat_tools_manifest(
            cast(Dict[str, Any], external_integration) if isinstance(external_integration, dict) else {},
            update_dict,
        )

    if update_dict.get('disabled') is False and app.get('disabled'):
        validate_app_endpoints_for_reenable(app, update_dict, app_id)
        clear_app_webhook_health(app_id)
        update_dict.setdefault('disabled_reason', '')
        update_dict.setdefault('disabled_error', '')
        update_dict.setdefault('disabled_at', '')
        update_dict.setdefault('disabled_failure_duration_hours', 0)

    update_app_in_db(update_dict)

    # payment link
    upsert_app_payment_link(
        cast(str, data.get('id')),
        cast(bool, data.get('is_paid', False)),
        cast(float, data.get('price')),
        cast(str, data.get('payment_plan')),
        cast(str, data.get('uid')),
        previous_price=cast(float, app.get("price", 0)),
    )

    if app['approved'] and (
        cast(Optional[bool], app['private']) is None or cast(Optional[bool], app['private']) is False
    ):
        invalidate_approved_apps_cache()
    delete_app_cache_by_id(app_id)
    return {'status': 'ok'}


@router.post('/v1/apps/{app_id}/refresh-manifest', tags=['v1'])
def refresh_app_manifest(app_id: str, uid: str = Depends(auth.get_current_user_uid)) -> Dict[str, Any]:
    """
    Refresh chat tools manifest for an app.

    Forces a fresh fetch of the manifest from the external URL, bypassing cache.
    Only the app owner can refresh their app's manifest.
    """
    app_raw = _get_app_by_id(app_id, uid)
    app: Optional[Dict[str, Any]] = app_raw if isinstance(app_raw, dict) else None
    if not app:
        raise HTTPException(status_code=404, detail='App not found')
    if app['uid'] != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')

    external_integration_raw = app.get('external_integration')
    external_integration: Dict[str, Any] = (
        cast(Dict[str, Any], external_integration_raw) if isinstance(external_integration_raw, dict) else {}
    )
    if not external_integration_raw:
        raise HTTPException(status_code=400, detail='App does not have external integration')

    manifest_url_raw: object = external_integration.get('chat_tools_manifest_url')
    manifest_url = manifest_url_raw if isinstance(manifest_url_raw, str) else None
    if not manifest_url:
        raise HTTPException(status_code=400, detail='App does not have a chat tools manifest URL')

    manifest_result_raw: object = fetch_app_chat_tools_from_manifest(manifest_url, force_refresh=True)
    manifest_result: Dict[str, Any] = manifest_result_raw if isinstance(manifest_result_raw, dict) else {}
    if not manifest_result:
        raise HTTPException(status_code=502, detail='Failed to fetch manifest from external URL')

    update_dict: Dict[str, Any] = {'id': app_id, 'updated_at': datetime.now(timezone.utc)}

    fetched_tools_raw: object = manifest_result.get('tools')
    fetched_tools: List[Dict[str, Any]] = (
        [cast(Dict[str, Any], t) for t in cast(List[Any], fetched_tools_raw) if isinstance(t, dict)]
        if isinstance(fetched_tools_raw, list)
        else []
    )
    if fetched_tools:
        base_url_raw: object = external_integration.get('app_home_url', '')
        base_url = base_url_raw.rstrip('/') if isinstance(base_url_raw, str) else ''
        if base_url:
            for tool in fetched_tools:
                endpoint_raw: object = tool.get('endpoint', '')
                endpoint = endpoint_raw if isinstance(endpoint_raw, str) else ''
                if endpoint.startswith('/') and not endpoint.startswith('//'):
                    tool['endpoint'] = f"{base_url}{endpoint}"
        update_dict['chat_tools'] = fetched_tools

    chat_messages_raw: object = manifest_result.get('chat_messages')
    chat_messages: Dict[str, Any] = (
        cast(Dict[str, Any], chat_messages_raw) if isinstance(chat_messages_raw, dict) else {}
    )
    ext_int_update: Dict[str, Any] = {}
    if chat_messages:
        ext_int_update['chat_messages_enabled'] = chat_messages.get('enabled', False)
        ext_int_update['chat_messages_target'] = chat_messages.get('target', 'app')
        ext_int_update['chat_messages_notify'] = chat_messages.get('notify', False)
    else:
        ext_int_update['chat_messages_enabled'] = False
        ext_int_update['chat_messages_target'] = 'app'
        ext_int_update['chat_messages_notify'] = False
    update_dict['external_integration'] = ext_int_update

    update_app_in_db(update_dict)

    if app['approved'] and (
        cast(Optional[bool], app['private']) is None or cast(Optional[bool], app['private']) is False
    ):
        invalidate_approved_apps_cache()
    delete_app_cache_by_id(app_id)

    tools_count = len(fetched_tools) if fetched_tools else 0
    return {'status': 'ok', 'tools_count': tools_count}


@router.delete('/v1/apps/{app_id}', tags=['v1'])
def delete_app(app_id: str, uid: str = Depends(auth.get_current_user_uid)) -> Dict[str, str]:
    app: Optional[Dict[str, Any]] = _get_app_by_id(app_id, uid)
    if not app:
        raise HTTPException(status_code=404, detail='App not found')
    if app['uid'] != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    delete_app_from_db(app_id)
    if app['approved']:
        invalidate_approved_apps_cache()
    delete_app_cache_by_id(app_id)
    return {'status': 'ok'}


@router.get('/v1/apps/{app_id}', tags=['v1'])
def get_app_details(app_id: str, uid: str = Depends(auth.get_current_user_uid)) -> App:
    app_raw = _get_app_by_id_with_reviews(app_id, uid)
    app = App(**app_raw) if app_raw else None
    if not app:
        raise HTTPException(status_code=404, detail='App not found')
    if not app.approved and app.uid != uid:
        raise HTTPException(status_code=404, detail='App not found')
    if cast(Optional[bool], app.private) is not None:
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
def get_app_categories() -> List[Dict[str, str]]:
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
def review_app(app_id: str, data: Dict[str, Any], uid: str = Depends(auth.get_current_user_uid)) -> Dict[str, str]:
    if 'score' not in data:
        raise HTTPException(status_code=422, detail='Score is required')

    app_raw = _get_app_by_id(app_id, uid)
    app = App(**app_raw) if app_raw else None
    if not app:
        raise HTTPException(status_code=404, detail='App not found')

    if app.uid == uid:
        raise HTTPException(status_code=403, detail='You are not authorized to review your own app')

    if app.private and app.uid != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to review this app')

    review_data: Dict[str, Any] = {
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
            app_owner_uid=cast(str, app.uid),
            reviewer_uid=uid,
            app_id=app_id,
            app_name=app.name,
            review_body=review_body,
        )

    return {'status': 'ok'}


@router.patch('/v1/apps/{app_id}/review', tags=['v1'])
def update_app_review(
    app_id: str, data: Dict[str, Any], uid: str = Depends(auth.get_current_user_uid)
) -> Dict[str, str]:
    if 'score' not in data:
        raise HTTPException(status_code=422, detail='Score is required')

    app_raw = _get_app_by_id(app_id, uid)
    app = App(**app_raw) if app_raw else None
    if not app:
        raise HTTPException(status_code=404, detail='App not found')

    if app.uid == uid:
        raise HTTPException(status_code=403, detail='You are not authorized to review your own app')

    if app.private and app.uid != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to review this app')
    old_review = get_specific_user_review(app_id, uid)
    if not old_review:
        raise HTTPException(status_code=404, detail='Review not found')
    review_data: Dict[str, Any] = {
        'score': data['score'],
        'review': data.get('review', ''),
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'rated_at': old_review['rated_at'],
        'username': data.get('username', old_review.get('username', '')),
        'response': old_review.get('response', ''),
        'uid': uid,
    }
    set_app_review(app_id, uid, review_data)

    # Send notification to app owner
    if review_body := data.get('review', ''):
        send_new_app_review_notification(
            app_owner_uid=cast(str, app.uid),
            reviewer_uid=uid,
            app_id=app_id,
            app_name=app.name,
            review_body=review_body,
        )

    return {'status': 'ok'}


@router.patch('/v1/apps/{app_id}/review/reply', tags=['v1'])
def reply_to_review(app_id: str, data: Dict[str, Any], uid: str = Depends(auth.get_current_user_uid)) -> Dict[str, str]:
    app_raw = _get_app_by_id(app_id, uid)
    app = App(**app_raw) if app_raw else None
    if not app:
        raise HTTPException(status_code=404, detail='App not found')

    if app.uid != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to reply to this app review')

    if app.private and app.uid != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to reply to this app review')

    reviewer_uid = data.get('reviewer_uid')
    if not reviewer_uid:
        raise HTTPException(status_code=422, detail='Reviewer UID is required')

    response = data.get('response')
    if not isinstance(response, str) or not response.strip():
        raise HTTPException(status_code=422, detail='Response is required')

    review = get_specific_user_review(app_id, cast(str, reviewer_uid))
    if not review:
        raise HTTPException(status_code=404, detail='Review not found')

    review['response'] = response
    review['responded_at'] = datetime.now(timezone.utc).isoformat()
    set_app_review(app_id, cast(str, reviewer_uid), review)

    # Send notification to reviewer
    send_app_review_reply_notification(
        cast(str, reviewer_uid),
        cast(str, app.uid),
        response,
        app_id,
        app.name,
    )

    return {'status': 'ok'}


@router.get('/v1/apps/{app_id}/reviews', tags=['v1'])
def app_reviews(app_id: str) -> List[Dict[str, Any]]:
    reviews = get_app_reviews(app_id)
    reviews = [details for details in reviews.values() if details['review']]
    return reviews


@router.patch('/v1/apps/{app_id}/change-visibility', tags=['v1'])
def change_app_visibility(app_id: str, private: bool, uid: str = Depends(auth.get_current_user_uid)) -> Dict[str, str]:
    app_raw = _get_app_by_id(app_id, uid)
    app = App(**app_raw) if app_raw else None
    if not app:
        raise HTTPException(status_code=404, detail='App not found')
    if app.uid != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    update_app_visibility_in_db(app_id, private)
    # Toggling visibility of an approved app changes whether it appears in the public marketplace
    # list, so invalidate that cache too (mirrors approve/reject/delete). Otherwise a newly public
    # app does not show, and a newly private one keeps showing, until the list cache TTL expires
    # (issue #3783).
    if app.approved:
        invalidate_approved_apps_cache()
    delete_app_cache_by_id(app_id)
    return {'status': 'ok'}


@router.get('/v1/app/proactive-notification-scopes', tags=['v1'])
def get_notification_scopes() -> List[Dict[str, str]]:
    return [
        {'title': 'User Name', 'id': 'user_name'},
        {'title': 'User Memories', 'id': 'user_facts'},
        {'title': 'User Conversations', 'id': 'user_context'},
        {'title': 'User Chat', 'id': 'user_chat'},
    ]


@router.get('/v1/app-capabilities', tags=['v1'])
def get_app_capabilities() -> List[Dict[str, Any]]:
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
def get_payment_plans_v1() -> List[Dict[str, str]]:
    return [
        {'title': 'Monthly Recurring', 'id': 'monthly_recurring'},
    ]


@router.get('/v1/app/plans', tags=['v1'])
def get_payment_plans(uid: str = Depends(auth.get_current_user_uid)) -> List[Dict[str, str]]:
    if not uid or len(uid) == 0 or not is_permit_payment_plan_get(uid):
        return []
    return [
        {'title': 'Monthly Recurring', 'id': 'monthly_recurring'},
    ]


@router.post('/v1/app/generate-description', tags=['v1'])
def generate_description_endpoint(
    data: Dict[str, Any], uid: str = Depends(auth.get_current_user_uid)
) -> Dict[str, str]:
    if data['name'] == '':
        raise HTTPException(status_code=422, detail='App Name is required')
    if data['description'] == '':
        raise HTTPException(status_code=422, detail='App Description is required')
    with track_usage(uid, Features.APP_GENERATOR):
        desc = generate_description(data['name'], data['description'])
    return {
        'description': desc,
    }


@router.post('/v1/app/generate-description-emoji', tags=['v1'])
def generate_description_and_emoji_endpoint(
    data: Dict[str, Any], uid: str = Depends(auth.get_current_user_uid)
) -> Dict[str, Any]:
    """
    Generate an app description and representative emoji.
    Used by the quick template creator feature.
    """
    if not data.get('name'):
        raise HTTPException(status_code=422, detail='App Name is required')
    if not data.get('prompt'):
        raise HTTPException(status_code=422, detail='App Prompt is required')

    with track_usage(uid, Features.APP_GENERATOR):
        result: Dict[str, Any] = cast(
            Dict[str, Any], generate_description_and_emoji(str(data['name']), str(data['prompt']))
        )
    return result


# ******************************************************
# ****************** AI APP GENERATOR ******************
# ******************************************************


@router.get('/v1/app/generate-prompts', tags=['v1'])
async def generate_sample_prompts_endpoint(
    uid: str = Depends(auth.with_rate_limit(auth.get_current_user_uid, "apps:generate_prompts")),
) -> Dict[str, Any]:
    """
    Generate sample app prompts for the AI app generator.
    Uses a fast model to generate creative suggestions.
    """
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
        with track_usage(uid, Features.APP_GENERATOR):
            response = await get_llm('app_integration').ainvoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content="Generate 5 creative app ideas now"),
                ]
            )

        content_raw: Any = response.content  # type: ignore[reportUnknownMemberType]  # langchain BaseMessage.content partially typed
        content = content_raw if isinstance(content_raw, str) else ''
        content = content.strip()

        # Parse JSON from response
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        loaded: object = json.loads(content)

        if isinstance(loaded, list) and len(cast(List[Any], loaded)) >= 5:
            prompts = cast(List[Any], loaded)
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
        logger.error(f"Error generating prompts: {e}")
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
async def generate_app_endpoint(data: Dict[str, Any], uid: str = Depends(auth.get_current_user_uid)) -> Dict[str, Any]:
    """
    Generate an app configuration from a natural language prompt.
    This is an experimental feature that uses AI to create app configurations.
    """
    prompt = str(data.get('prompt', '') or '').strip()
    if not prompt:
        raise HTTPException(status_code=422, detail='Prompt is required')

    if len(prompt) < 10:
        raise HTTPException(status_code=422, detail='Prompt is too short. Please provide more details.')

    if len(prompt) > 2000:
        raise HTTPException(status_code=422, detail='Prompt is too long. Please keep it under 2000 characters.')

    try:
        # Generate app configuration using LLM
        with track_usage(uid, Features.APP_GENERATOR):
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
        logger.error(f"Error generating app: {e}")
        raise HTTPException(status_code=500, detail=f'Failed to generate app: {str(e)}')


@router.post('/v1/app/generate-icon', tags=['v1'])
async def generate_app_icon_endpoint(
    data: Dict[str, Any], uid: str = Depends(auth.get_current_user_uid)
) -> Dict[str, str]:
    """
    Generate an app icon using AI (DALL-E).
    Returns the icon as a base64 encoded PNG image.
    """
    app_name = str(data.get('name', '') or '').strip()
    app_description = str(data.get('description', '') or '').strip()
    category = str(data.get('category', 'other') or '').strip()

    if not app_name:
        raise HTTPException(status_code=422, detail='App name is required')

    if not app_description:
        raise HTTPException(status_code=422, detail='App description is required')

    try:
        # Generate icon using DALL-E
        with track_usage(uid, Features.APP_GENERATOR):
            icon_bytes = await generate_app_icon(app_name, app_description, category)

        # Return as base64
        icon_base64 = base64.b64encode(icon_bytes).decode('utf-8')

        return {'status': 'ok', 'icon_base64': icon_base64, 'mime_type': 'image/png'}
    except Exception as e:
        logger.error(f"Error generating icon: {e}")
        raise HTTPException(status_code=500, detail=f'Failed to generate icon: {str(e)}')


# ******************************************************
# ********************** SOCIAL ************************
# ******************************************************


@router.get('/v1/personas/twitter/profile', tags=['v1'])
async def get_twitter_profile_data(handle: str, uid: str = Depends(auth.get_current_user_uid)) -> Dict[str, Any]:
    if handle.startswith('@'):
        handle = handle[1:]
    profile = await get_twitter_profile(handle)

    # Convert TwitterProfile to dict for response
    res: Dict[str, Any] = {
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
    persona = await run_blocking(db_executor, get_user_persona_by_uid, uid)

    # Get matching persona if exists
    if not persona:
        persona = await run_blocking(db_executor, get_persona_by_twitter_handle_db, handle)

    if persona:
        res['persona_id'] = persona['id']
        res['persona_username'] = persona['username']

    return res


@router.get('/v1/personas/twitter/verify-ownership', tags=['v1'])
async def verify_twitter_ownership_tweet(
    username: str,
    handle: str,
    uid: str = Depends(auth.get_current_user_uid),
    persona_id: Optional[str] = None,
) -> Dict[str, Any]:
    # Get user info to check auth provider
    user = await run_blocking(db_executor, get_user_from_uid, uid)
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
def get_twitter_initial_message(username: str, uid: str = Depends(auth.get_current_user_uid)) -> Dict[str, str]:
    persona = get_persona_by_username_db(username)
    if persona:
        with track_usage(uid, Features.PERSONA):
            message = generate_persona_intro_message(persona['persona_prompt'], persona['name'])
        return {'message': message}
    return {'message': ''}


@router.post('/v1/apps/migrate-owner', tags=['v1'])
async def migrate_app_owner(old_id: str, uid: str = Depends(auth.get_current_user_uid)) -> Dict[str, str]:
    await run_blocking(db_executor, migrate_app_owner_id_db, uid, old_id)

    # Start async tasks to migrate memories and update persona connected accounts
    asyncio.create_task(run_blocking(db_executor, migrate_memories, old_id, uid))
    asyncio.create_task(update_omi_persona_connected_accounts(uid))

    return {"status": "ok", "message": "Migration started"}


async def update_omi_persona_connected_accounts(uid: str) -> None:
    try:
        personas = await run_blocking(db_executor, get_omi_persona_apps_by_uid_db, uid)

        for persona in personas:
            connected_accounts = list(persona.get('connected_accounts', []) or [])
            if 'omi' not in connected_accounts:
                connected_accounts.append('omi')

                update_data: Dict[str, Any] = persona
                update_data['connected_accounts'] = connected_accounts
                update_data['updated_at'] = datetime.now(timezone.utc)
                update_data['persona_prompt'] = await generate_persona_prompt(uid, update_data)
                update_data['description'] = await run_blocking(
                    llm_executor, generate_persona_desc, uid, update_data['name']
                )

                await run_blocking(db_executor, update_app_in_db, update_data)
                await run_blocking(db_executor, delete_app_cache_by_id, persona['id'])
    except Exception as e:
        logger.error(f"Error updating persona connected accounts: {e}")


# ******************************************************
# ******************* MCP SERVERS **********************
# ******************************************************


class McpServerRequest(PydanticBaseModel):
    name: str
    mcp_server_url: str
    description: Optional[str] = None


def _serialize_chat_tools_for_firestore(tools: List[ChatTool]) -> List[Dict[str, Any]]:
    """Serialize ChatTool objects for Firestore, converting parameters dict to JSON string.

    Firestore has nesting depth limits that MCP tool schemas can exceed,
    so we store the parameters field as a JSON string.
    """
    result: List[Dict[str, Any]] = []
    for t in tools:
        d = t.dict()
        if d.get('parameters') is not None:
            d['parameters'] = json.dumps(d['parameters'])
        result.append(d)
    return result


@router.post('/v1/apps/mcp', tags=['v1'])
async def add_mcp_server(data: McpServerRequest, uid: str = Depends(auth.get_current_user_uid)) -> Dict[str, Any]:
    """Add a remote MCP server as a private app with chat tools.

    1. Extracts domain from URL and fetches logo via Brandfetch / logo.dev
    2. Checks for OAuth metadata at /.well-known/oauth-authorization-server
    3. If OAuth required: registers client, returns auth URL for the user
    4. If no OAuth: discovers tools directly, creates app immediately
    """
    server_url = data.mcp_server_url.strip().rstrip('/')
    app_name = data.name.strip()
    app_description = data.description.strip() if data.description else f"MCP server tools from {app_name}"

    if not app_name:
        raise HTTPException(status_code=422, detail='App name is required')
    if not server_url:
        raise HTTPException(status_code=422, detail='MCP server URL is required')

    # Extract domain for logo
    parsed = urlparse(server_url)
    domain = parsed.netloc
    logo_url = await fetch_brandfetch_logo(domain) or ''

    app_id = str(ULID())
    user_raw = await run_blocking(db_executor, get_user_from_uid, uid)
    user: Dict[str, Any] = user_raw if isinstance(user_raw, dict) else {}

    # Check for OAuth metadata
    oauth_meta = await discover_oauth_metadata(server_url)

    if oauth_meta and oauth_meta.get('authorization_endpoint'):
        # OAuth required — register client and return auth URL
        base_url = os.getenv('BASE_API_URL', '').rstrip('/')
        if not base_url:
            raise HTTPException(status_code=500, detail='BASE_API_URL not configured')

        redirect_uri = f"{base_url}/v1/apps/mcp/callback"

        client_info: Dict[str, Any] = {}
        if oauth_meta.get('registration_endpoint'):
            try:
                client_info = await register_oauth_client(
                    oauth_meta['registration_endpoint'], redirect_uri, scopes=oauth_meta.get('scopes_supported')
                )
            except Exception as e:
                raise HTTPException(status_code=502, detail=f'OAuth client registration failed: {str(e)}')
        else:
            raise HTTPException(
                status_code=422,
                detail='MCP server requires OAuth but does not support dynamic client registration',
            )

        state = generate_state_token(app_id, uid)

        # Generate PKCE pair (required by MCP OAuth 2.1 spec)
        code_verifier, code_challenge = generate_pkce_pair()

        auth_url = build_authorization_url(
            oauth_meta['authorization_endpoint'],
            client_info['client_id'],
            redirect_uri,
            state,
            scopes=oauth_meta.get('scopes_supported'),
            code_challenge=code_challenge,
        )
        logger.info(f"[MCP OAuth] client_id={client_info['client_id']}, redirect_uri={redirect_uri}")
        logger.info(f"[MCP OAuth] auth_url={auth_url}")

        # Create app in pending state (no tools yet)
        app_dict: Dict[str, Any] = {
            'id': app_id,
            'name': app_name,
            'description': app_description,
            'image': logo_url,
            'uid': uid,
            'author': user.get('display_name', ''),
            'email': user.get('email', ''),
            'private': True,
            'approved': True,
            'status': 'pending_mcp_auth',
            'category': 'utilities-and-tools',
            'capabilities': ['chat'],
            'created_at': datetime.now(timezone.utc),
            'external_integration': {
                'mcp_server_url': server_url,
                'mcp_oauth_tokens': {
                    'client_id': client_info['client_id'],
                    'client_secret': client_info.get('client_secret'),
                    'token_endpoint': oauth_meta['token_endpoint'],
                    'redirect_uri': redirect_uri,
                    'code_verifier': code_verifier,
                },
            },
            'chat_tools': [],
        }
        await run_blocking(db_executor, add_app_to_db, app_dict)

        return {
            'app_id': app_id,
            'requires_oauth': True,
            'auth_url': auth_url,
        }

    else:
        # No OAuth — discover tools directly
        try:
            tools = await discover_mcp_tools(server_url)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f'Failed to discover MCP tools: {str(e)}')

        if not tools:
            raise HTTPException(status_code=422, detail='No tools found on the MCP server')

        # Use the resolved URL from discovery (may differ from user input if /http or /sse was needed)
        resolved_url = tools[0].endpoint if tools else server_url

        app_dict = {
            'id': app_id,
            'name': app_name,
            'description': app_description,
            'image': logo_url,
            'uid': uid,
            'author': user.get('display_name', ''),
            'email': user.get('email', ''),
            'private': True,
            'approved': True,
            'status': 'approved',
            'category': 'utilities-and-tools',
            'capabilities': ['chat'],
            'created_at': datetime.now(timezone.utc),
            'external_integration': {
                'mcp_server_url': resolved_url,
            },
            'chat_tools': _serialize_chat_tools_for_firestore(tools),
        }
        await run_blocking(db_executor, add_app_to_db, app_dict)

        return {
            'app_id': app_id,
            'requires_oauth': False,
            'tools_count': len(tools),
            'tool_names': [t.name for t in tools],
        }


@router.get('/v1/apps/mcp/callback', tags=['v1'])
async def mcp_oauth_callback(code: str, state: str) -> HTMLResponse:
    """OAuth callback for MCP server authorization.

    Exchanges the authorization code for tokens, discovers tools, updates the app.
    Returns an HTML success/failure page.
    """
    try:
        app_id, uid = parse_state_token(state)
    except ValueError:
        return HTMLResponse('<html><body><h1>Invalid state parameter</h1></body></html>', status_code=400)

    app_data = await run_blocking(db_executor, get_app_by_id_db, app_id)
    if not app_data:
        return HTMLResponse('<html><body><h1>App not found</h1></body></html>', status_code=404)

    ext_raw = app_data.get('external_integration', {})
    ext: Dict[str, Any] = cast(Dict[str, Any], ext_raw) if isinstance(ext_raw, dict) else {}
    oauth_tokens_raw = ext.get('mcp_oauth_tokens', {})
    oauth_tokens: Dict[str, Any] = cast(Dict[str, Any], oauth_tokens_raw) if isinstance(oauth_tokens_raw, dict) else {}
    server_url = ext.get('mcp_server_url', '')

    if not oauth_tokens or not oauth_tokens.get('token_endpoint'):
        return HTMLResponse('<html><body><h1>OAuth configuration missing</h1></body></html>', status_code=400)

    # Exchange code for tokens (include PKCE code_verifier)
    try:
        token_data = await exchange_oauth_code(
            oauth_tokens['token_endpoint'],
            code,
            oauth_tokens.get('redirect_uri', ''),
            oauth_tokens['client_id'],
            oauth_tokens.get('client_secret'),
            code_verifier=oauth_tokens.get('code_verifier'),
        )
    except Exception as e:
        return HTMLResponse(f'<html><body><h1>Token exchange failed</h1><p>{str(e)}</p></body></html>', status_code=502)

    # Update stored tokens
    oauth_tokens['access_token'] = token_data['access_token']
    oauth_tokens['refresh_token'] = token_data.get('refresh_token')
    if token_data.get('expires_in'):
        oauth_tokens['expires_at'] = time.time() + token_data['expires_in']

    # Discover tools with the new access token
    try:
        tools = await discover_mcp_tools(server_url, token_data['access_token'])
    except Exception as e:
        return HTMLResponse(f'<html><body><h1>Tool discovery failed</h1><p>{str(e)}</p></body></html>', status_code=502)

    # Use the resolved URL from the first tool (discover_mcp_tools stores the working URL)
    resolved_url = tools[0].endpoint if tools else server_url

    # Update app with tokens and tools
    update_dict: Dict[str, Any] = {
        'id': app_id,
        'status': 'approved',
        'external_integration': {
            'mcp_server_url': resolved_url,
            'mcp_oauth_tokens': oauth_tokens,
        },
        'chat_tools': _serialize_chat_tools_for_firestore(tools),
    }
    await run_blocking(db_executor, update_app_in_db, update_dict)
    await run_blocking(db_executor, delete_app_cache_by_id, app_id)

    # Auto-enable the app for the user
    await run_blocking(db_executor, enable_app, uid, app_id)

    tool_count = len(tools)
    tool_names = ', '.join(t.name for t in tools)

    return HTMLResponse(f"""
    <html>
    <head><meta name="viewport" content="width=device-width,initial-scale=1">
    <style>
        body {{ font-family: -apple-system, system-ui, sans-serif; background: #111; color: #fff;
               display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }}
        .card {{ background: #1a1a1a; border-radius: 16px; padding: 40px; text-align: center; max-width: 400px; }}
        h1 {{ color: #4ade80; margin-bottom: 8px; }}
        p {{ color: #aaa; }}
        .count {{ font-size: 2em; font-weight: bold; color: #fff; }}
    </style></head>
    <body><div class="card">
        <h1>Connected!</h1>
        <p class="count">{tool_count} tools</p>
        <p>{tool_names}</p>
        <p style="margin-top:24px;color:#666;">You can close this window and return to the app.</p>
    </div></body></html>
    """)


@router.post('/v1/apps/{app_id}/mcp/refresh', tags=['v1'])
async def refresh_mcp_tools(app_id: str, uid: str = Depends(auth.get_current_user_uid)) -> Dict[str, Any]:
    """Re-discover tools from an MCP server and update the app."""
    app_data = await run_blocking(db_executor, get_app_by_id_db, app_id)
    if not app_data:
        raise HTTPException(status_code=404, detail='App not found')
    if app_data.get('uid') != uid:
        raise HTTPException(status_code=403, detail='Not authorized')

    ext_raw = app_data.get('external_integration', {})
    ext: Dict[str, Any] = cast(Dict[str, Any], ext_raw) if isinstance(ext_raw, dict) else {}
    server_url = ext.get('mcp_server_url')
    if not server_url:
        raise HTTPException(status_code=422, detail='App is not an MCP server app')

    oauth_tokens_raw = ext.get('mcp_oauth_tokens')
    oauth_tokens: Optional[Dict[str, Any]] = (
        cast(Dict[str, Any], oauth_tokens_raw) if isinstance(oauth_tokens_raw, dict) else None
    )
    access_token = oauth_tokens.get('access_token') if oauth_tokens else None

    try:
        tools = await discover_mcp_tools(server_url, access_token)
    except PermissionError:
        # Try token refresh
        if oauth_tokens and oauth_tokens.get('refresh_token'):
            new_tokens = await refresh_oauth_token(
                oauth_tokens['token_endpoint'],
                oauth_tokens['refresh_token'],
                oauth_tokens['client_id'],
                oauth_tokens.get('client_secret'),
            )
            oauth_tokens['access_token'] = new_tokens['access_token']
            if new_tokens.get('refresh_token'):
                oauth_tokens['refresh_token'] = new_tokens['refresh_token']

            tools = await discover_mcp_tools(server_url, new_tokens['access_token'])

            update_dict: Dict[str, Any] = {
                'id': app_id,
                'external_integration': {
                    'mcp_server_url': server_url,
                    'mcp_oauth_tokens': oauth_tokens,
                },
                'chat_tools': _serialize_chat_tools_for_firestore(tools),
            }
            await run_blocking(db_executor, update_app_in_db, update_dict)
            await run_blocking(db_executor, delete_app_cache_by_id, app_id)

            return {'tools_count': len(tools), 'tool_names': [t.name for t in tools]}
        raise HTTPException(status_code=401, detail='MCP server requires re-authorization')
    except Exception as e:
        raise HTTPException(status_code=502, detail=f'Failed to discover tools: {str(e)}')

    update_dict = {
        'id': app_id,
        'chat_tools': _serialize_chat_tools_for_firestore(tools),
    }
    await run_blocking(db_executor, update_app_in_db, update_dict)
    await run_blocking(db_executor, delete_app_cache_by_id, app_id)

    return {'tools_count': len(tools), 'tool_names': [t.name for t in tools]}


# ******************************************************
# **************** ENABLE/DISABLE APPS *****************
# ******************************************************


@router.post('/v1/apps/enable')
async def enable_app_endpoint(app_id: str, uid: str = Depends(auth.get_current_user_uid)) -> Dict[str, str]:
    app_raw = await run_blocking(db_executor, _get_app_by_id, app_id, uid)
    app = App(**app_raw) if app_raw else None
    if not app:
        raise HTTPException(status_code=404, detail='App not found')
    if app.disabled:
        raise HTTPException(
            status_code=400,
            detail='This app is currently unavailable due to connectivity issues. The developer has been notified.',
        )
    if cast(Optional[bool], app.private) is not None:
        if app.private and app.uid != uid and not await run_blocking(db_executor, is_tester, uid):
            raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    if app.works_externally() and app.external_integration and app.external_integration.setup_completed_url:
        client = get_webhook_client()
        res = await client.get(app.external_integration.setup_completed_url + f'?uid={uid}')
        logger.info(f'enable_app_endpoint {res.status_code} {res.content}')
        if res.status_code != 200 or not res.json().get('is_setup_completed', False):
            raise HTTPException(status_code=400, detail='App setup is not completed')

    # Check payment status
    if app.is_paid and await run_blocking(db_executor, get_is_user_paid_app, app.id, uid) == False:
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')

    await run_blocking(db_executor, enable_app, uid, app_id)
    if (
        (cast(Optional[bool], app.private) is None or not app.private)
        and (app.uid is None or app.uid != uid)
        and not await run_blocking(db_executor, is_tester, uid)
    ):
        await run_blocking(db_executor, increase_app_installs_count, app_id)
    return {'status': 'ok'}


@router.post('/v1/apps/disable')
def disable_app_endpoint(app_id: str, uid: str = Depends(auth.get_current_user_uid)) -> Dict[str, str]:
    # Allow users to always disable apps they have installed, even if the app
    # was made private after installation (see issue #4886).
    if is_app_enabled(uid, app_id):
        disable_app(uid, app_id)
        app_raw = _get_app_by_id(app_id, uid)
        if app_raw:
            app = App(**app_raw)
            if (
                (cast(Optional[bool], app.private) is None or not app.private)
                and (app.uid is None or app.uid != uid)
                and not is_tester(uid)
            ):
                decrease_app_installs_count(app_id)
        return {'status': 'ok'}

    raise HTTPException(status_code=404, detail='App not found')


# ******************************************************
# ******************* TEAM ENDPOINTS *******************
# ******************************************************


@router.post('/v1/apps/tester', tags=['v1'])
def add_new_tester(data: Dict[str, Any], secret_key: str = Header(...)):
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
def add_app_access_tester(data: Dict[str, Any], secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    if not data.get('uid'):
        raise HTTPException(status_code=422, detail='uid is required')
    if not data.get('app_id'):
        raise HTTPException(status_code=422, detail='app_id is required')
    add_app_access_for_tester(data['app_id'], data['uid'])
    return {'status': 'ok'}


@router.delete('/v1/apps/tester/access', tags=['v1'])
def remove_app_access_tester(data: Dict[str, Any], secret_key: str = Header(...)):
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
    invalidate_popular_apps_cache()
    return {'status': 'ok'}


@router.post('/v1/apps/{app_id}/approve', tags=['v1'])
def approve_app(app_id: str, uid: str, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    change_app_approval_status(app_id, True)
    invalidate_approved_apps_cache()  # App is now public, invalidate cache
    delete_app_cache_by_id(app_id)
    app_raw = _get_app_by_id(app_id, uid)
    app: Dict[str, Any] = cast(Dict[str, Any], app_raw)
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
    invalidate_approved_apps_cache()  # App removed from public list, invalidate cache
    app_raw = _get_app_by_id(app_id, uid)
    app: Dict[str, Any] = cast(Dict[str, Any], app_raw)
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
        contents = await file.read()
        await run_blocking(storage_executor, _write_file, temp_path, contents)

        # Upload to cloud storage
        url = await run_blocking(storage_executor, upload_app_thumbnail, temp_path, thumbnail_id)

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
    logger.info(persona)
    return persona


@router.post('/v1/apps/{app_id}/keys', tags=['v1'])
def create_api_key_for_app(app_id: str, uid: str = Depends(auth.get_current_user_uid)):
    app = _get_app_by_id(app_id, uid)
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
    app = _get_app_by_id(app_id, uid)
    if not app:
        raise HTTPException(status_code=404, detail='App not found')

    if app.get('uid') != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to view API keys for this app')

    keys = list_api_keys_db(app_id)
    return keys


@router.delete('/v1/apps/{app_id}/keys/{key_id}', tags=['v1'])
def delete_api_key(app_id: str, key_id: str, uid: str = Depends(auth.get_current_user_uid)):
    app = _get_app_by_id(app_id, uid)
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
    logger.info(app_ids)
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
