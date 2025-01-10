import json
import os
from datetime import datetime, timezone
from typing import List
import requests
from ulid import ULID
from fastapi import APIRouter, Depends, Form, UploadFile, File, HTTPException, Header

from database.apps import change_app_approval_status, get_unapproved_public_apps_db, \
    add_app_to_db, update_app_in_db, delete_app_from_db, update_app_visibility_in_db, \
    get_personas_by_username_db, get_persona_by_id_db, delete_persona_db
from database.notifications import get_token_only
from database.redis_db import delete_generic_cache, get_specific_user_review, increase_app_installs_count, \
    decrease_app_installs_count, enable_app, disable_app, delete_app_cache_by_id
from utils.apps import get_available_apps, get_available_app_by_id, get_approved_available_apps, \
    get_available_app_by_id_with_reviews, set_app_review, get_app_reviews, add_tester, is_tester, \
    add_app_access_for_tester, remove_app_access_for_tester, upsert_app_payment_link, get_is_user_paid_app, \
    is_permit_payment_plan_get
from utils.llm import generate_description

from utils.notifications import send_notification
from utils.other import endpoints as auth
from models.app import App
from utils.other.storage import upload_plugin_logo, delete_plugin_logo

v1_router = APIRouter(prefix="/v1", tags=['apps'])


# ******************************************************
# ********************* APPS CRUD **********************
# ******************************************************

@v1_router.get('/apps', response_model=List[App])
def get_apps(uid: str = Depends(auth.get_current_user_uid), include_reviews: bool = True):
    return get_available_apps(uid, include_reviews=include_reviews)


@v1_router.get('/approved-apps', response_model=List[App])
def get_approved_apps(include_reviews: bool = False):
    return get_approved_available_apps(include_reviews=include_reviews)


@v1_router.post('/apps')
def create_app(app_data: str = Form(...), file: UploadFile = File(...), uid=Depends(auth.get_current_user_uid)):
    data = json.loads(app_data)
    data['approved'] = False
    data['deleted'] = False
    data['status'] = 'under-review'
    data['name'] = data['name'].strip()
    data['id'] = str(ULID())
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
        external_integration['webhook_url'] = external_integration['webhook_url'].strip()
        if external_integration.get('triggers_on') is None:
            raise HTTPException(status_code=422, detail='Triggers on is required')
        # check if setup_instructions_file_path is a single url or a just a string of text
        if external_integration.get('setup_instructions_file_path'):
            external_integration['setup_instructions_file_path'] = external_integration[
                'setup_instructions_file_path'].strip()
            if external_integration['setup_instructions_file_path'].startswith('http'):
                external_integration['is_instructions_url'] = True
            else:
                external_integration['is_instructions_url'] = False
    os.makedirs(f'_temp/plugins', exist_ok=True)
    file_path = f"_temp/plugins/{file.filename}"
    with open(file_path, 'wb') as f:
        f.write(file.file.read())
    imgUrl = upload_plugin_logo(file_path, data['id'])
    data['image'] = imgUrl
    data['created_at'] = datetime.now(timezone.utc)

    add_app_to_db(data)

    # payment link
    app = App(**data)
    upsert_app_payment_link(app.id, app.is_paid, app.price, app.payment_plan)

    return {'status': 'ok'}


@v1_router.patch('/apps/{app_id}')
def update_app(app_id: str, app_data: str = Form(...), file: UploadFile = File(None),
               uid=Depends(auth.get_current_user_uid)):
    data = json.loads(app_data)
    plugin = get_available_app_by_id(app_id, uid)
    if not plugin:
        raise HTTPException(status_code=404, detail='App not found')
    if plugin['uid'] != uid:
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    if file:
        delete_plugin_logo(plugin['image'])
        os.makedirs(f'_temp/plugins', exist_ok=True)
        file_path = f"_temp/plugins/{file.filename}"
        with open(file_path, 'wb') as f:
            f.write(file.file.read())
        img_url = upload_plugin_logo(file_path, app_id)
        data['image'] = img_url
    data['updated_at'] = datetime.now(timezone.utc)
    # Warn: the user can update any fields, e.g. approved.
    update_app_in_db(data)

    # payment link
    upsert_app_payment_link(data.get('id'), data.get('is_paid', False), data.get('price'), data.get('payment_plan'),
                            previous_price=plugin.get("price", 0))

    if plugin['approved'] and (plugin['private'] is None or plugin['private'] is False):
        delete_generic_cache('get_public_approved_apps_data')
    delete_app_cache_by_id(app_id)
    return {'status': 'ok'}


@v1_router.delete('/apps/{app_id}')
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


@v1_router.get('/apps/{app_id}')
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

    return app


@v1_router.post('/apps/review')
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


@v1_router.patch('/apps/{app_id}/review')
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


@v1_router.patch('/apps/{app_id}/review/reply')
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


@v1_router.get('/apps/{app_id}/reviews')
def app_reviews(app_id: str):
    reviews = get_app_reviews(app_id)
    reviews = [
        details for details in reviews.values() if details['review']
    ]
    return reviews


@v1_router.patch('/apps/{app_id}/change-visibility')
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


@v1_router.get('/app/proactive-notification-scopes')
def get_notification_scopes():
    return [
        {'title': 'User Name', 'id': 'user_name'},
        {'title': 'User Facts', 'id': 'user_facts'},
        {'title': 'User Memories', 'id': 'user_context'},
        {'title': 'User Chat', 'id': 'user_chat'}
    ]


@v1_router.get('/app-capabilities')
def get_plugin_capabilities():
    return [
        {'title': 'Chat', 'id': 'chat'},
        {'title': 'Memories', 'id': 'memories'},
        {'title': 'External Integration', 'id': 'external_integration', 'triggers': [
            {'title': 'Memory Creation', 'id': 'memory_creation'},
            {'title': 'Transcript Processed', 'id': 'transcript_processed'},
        ]},
        {'title': 'Notification', 'id': 'proactive_notification', 'scopes': [
            {'title': 'User Name', 'id': 'user_name'},
            {'title': 'User Facts', 'id': 'user_facts'},
            {'title': 'User Memories', 'id': 'user_context'},
            {'title': 'User Chat', 'id': 'user_chat'}
        ]}
    ]


# @deprecated
@v1_router.get('/app/payment-plans')
def get_payment_plans_v1():
    return [
        {'title': 'Monthly Recurring', 'id': 'monthly_recurring'},
    ]


@v1_router.get('/app/plans')
def get_payment_plans(uid: str = Depends(auth.get_current_user_uid)):
    if not uid or len(uid) == 0 or not is_permit_payment_plan_get(uid):
        return []
    return [
        {'title': 'Monthly Recurring', 'id': 'monthly_recurring'},
    ]


@v1_router.post('/app/generate-description')
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
# **************** ENABLE/DISABLE APPS *****************
# ******************************************************

@v1_router.post('/apps/enable')
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


@v1_router.post('/apps/disable')
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

@v1_router.post('/apps/tester')
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


@v1_router.post('/apps/tester/access')
def add_app_access_tester(data: dict, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    if not data.get('uid'):
        raise HTTPException(status_code=422, detail='uid is required')
    if not data.get('app_id'):
        raise HTTPException(status_code=422, detail='app_id is required')
    add_app_access_for_tester(data['app_id'], data['uid'])
    return {'status': 'ok'}


@v1_router.delete('/apps/tester/access')
def remove_app_access_tester(data: dict, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    if not data.get('uid'):
        raise HTTPException(status_code=422, detail='uid is required')
    if not data.get('app_id'):
        raise HTTPException(status_code=422, detail='app_id is required')
    remove_app_access_for_tester(data['app_id'], data['uid'])
    return {'status': 'ok'}


@v1_router.get('/apps/tester/check')
def check_is_tester(uid: str = Depends(auth.get_current_user_uid)):
    if is_tester(uid):
        return {'is_tester': True}
    return {'is_tester': False}


@v1_router.get('/apps/public/unapproved')
def get_unapproved_public_apps(secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    apps = get_unapproved_public_apps_db()
    return apps


@v1_router.post('/apps/{app_id}/approve')
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


@v1_router.post('/apps/{app_id}/reject')
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


@v1_router.delete('/personas/{persona_id}')
def delete_persona(persona_id: str, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    personas = get_persona_by_id_db(persona_id)
    if not personas:
        raise HTTPException(status_code=404, detail='Persona not found')
    delete_persona_db(persona_id)
    return {'status': 'ok'}


@v1_router.get('/personas/{persona_id}')
def get_personas(persona_id: str, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    persona = get_personas_by_username_db(persona_id)
    if not persona:
        raise HTTPException(status_code=404, detail='Persona not found')
    print(persona)
    return persona
