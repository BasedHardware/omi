import os
from typing import Any, Dict, Optional, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from database.redis_db import get_enabled_apps
from database.chat import add_integration_chat_message
from utils.apps import (
    verify_api_key,
    get_available_app_by_id,
)
import database.notifications as notification_db
from models.other import FcmTokenResponse, SaveFcmTokenRequest
from models.integrations import IntegrationNotificationResponse
from utils.notifications import (
    send_notification,
)
from utils.notification_dispatch import (
    APP_NOTIFICATION_LIMIT,
    NotificationDispatchStatus,
    NotificationIntent,
    NotificationPolicy,
    dispatch_notification,
)
from utils.other import endpoints as auth
from models.app import App

# logger = logging.getLogger('uvicorn.error')
# logger.setLevel(logging.DEBUG)
router = APIRouter()


@router.post('/v1/users/fcm-token', response_model=FcmTokenResponse)
def save_token(
    data: SaveFcmTokenRequest,
    uid: str = Depends(auth.get_current_user_uid),
    x_app_platform: Optional[str] = Header(None, alias='X-App-Platform'),
    x_device_id_hash: Optional[str] = Header(None, alias='X-Device-Id-Hash'),
) -> FcmTokenResponse:
    platform = x_app_platform or 'unknown'
    device_hash = x_device_id_hash or 'default'

    # Create key: ios_abc123, android_xyz456, macos_def789
    device_key = f"{platform}_{device_hash}"

    token_data: Dict[str, Any] = data.model_dump()
    token_data['device_key'] = device_key

    notification_db.save_token(uid, token_data)
    return FcmTokenResponse(status='Ok')


# ******************************************************
# ******************* TEAM ENDPOINTS *******************
# ******************************************************


@router.post('/v1/notification')
def send_notification_to_user(data: Dict[str, Any], secret_key: str = Header(...)) -> Dict[str, str]:
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    if not data.get('uid'):
        raise HTTPException(status_code=400, detail='uid is required')
    uid = cast(str, data['uid'])
    title = cast(str, data['title'])
    body = cast(str, data['body'])
    notification_data = cast(Dict[str, Any], data.get('data', {}))
    send_notification(uid, title, body, notification_data)
    return {'status': 'Ok'}


@router.post('/v1/integrations/notification', response_model=IntegrationNotificationResponse)
def send_app_notification_to_user(
    request: Request,
    data: Dict[str, Any],
    authorization: Optional[str] = Header(None),
) -> JSONResponse:
    # Check app-based auth
    if 'aid' not in data:
        raise HTTPException(status_code=400, detail='aid (app id) in request body is required')
    if not data.get('message'):
        raise HTTPException(status_code=400, detail='message is required')

    if not data.get('uid'):
        raise HTTPException(status_code=400, detail='uid is required')
    uid = cast(str, data['uid'])

    # Verify API key from Authorization header
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header. Must be 'Bearer API_KEY'")

    api_key = authorization.replace('Bearer ', '')
    aid = cast(str, data['aid'])
    if not verify_api_key(aid, api_key):
        raise HTTPException(status_code=403, detail="Invalid API key")

    # Get app details and convert to App model
    app_data = get_available_app_by_id(aid, uid)
    if not app_data:
        raise HTTPException(status_code=404, detail='App not found')
    app = App(**app_data)

    # Check if user has app installed
    user_enabled = set(get_enabled_apps(uid))
    if app.id not in user_enabled:
        raise HTTPException(status_code=403, detail='User does not have this app installed')

    message = cast(str, data['message'])

    # Determine target from manifest (defaults to 'app' if not configured).
    # Resolve it before dispatch so the typed payload carries the same navigation
    # destination as the chat message written below.
    target = 'app'
    if app.external_integration and app.external_integration.chat_messages_enabled:
        target = app.external_integration.chat_messages_target

    intent = NotificationIntent.app_integration(
        user_id=uid,
        app_name=app.name,
        app_id=app.id,
        message=message,
        target=target,
        source='api.v1.integration',
        policy=NotificationPolicy.EXTERNAL_APP_HOURLY,
    )
    outcome = dispatch_notification(intent)
    if outcome.rate_limit is None:
        raise RuntimeError('external app notification dispatch did not return rate-limit metadata')
    headers = outcome.rate_limit.headers()

    if outcome.status == NotificationDispatchStatus.SUPPRESSED:
        return JSONResponse(
            status_code=429,
            headers=headers,
            content={'detail': f'Rate limit exceeded. Maximum {APP_NOTIFICATION_LIMIT} notifications per hour.'},
        )

    if app.external_integration and app.external_integration.chat_messages_enabled:
        if target == 'main':
            # Prefix app name so users can identify which integration sent the message,
            # especially useful when an external app's error appears in the main chat.
            prefixed = f"[{app.name}]: {message}"
            add_integration_chat_message(prefixed, None, uid)
        else:
            add_integration_chat_message(message, app.id, uid)

    return JSONResponse(status_code=200, headers=headers, content={'status': 'Ok'})
