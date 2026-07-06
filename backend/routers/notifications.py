import os
import hashlib
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Tuple, Optional

from database.redis_db import get_enabled_apps, r as redis_client
from database.chat import add_integration_chat_message
from utils.apps import get_available_app_by_id, verify_api_key
from utils.app_integrations import send_app_notification
import database.notifications as notification_db
from models.other import SaveFcmTokenRequest, SendNotificationRequest, SendAppNotificationRequest
from utils.notifications import send_notification
from utils.other import endpoints as auth
from models.app import App
from models.shared import StatusResponse

# logger = logging.getLogger('uvicorn.error')
# logger.setLevel(logging.DEBUG)
router = APIRouter()

# Rate limit settings - more conservative limits to prevent notification fatigue
RATE_LIMIT_PERIOD = 3600  # 1 hour in seconds
MAX_NOTIFICATIONS_PER_HOUR = 10  # Maximum notifications per hour per app per user


class FcmTokenResponse(BaseModel):
    status: str


class NotificationStatusResponse(BaseModel):
    status: str


def check_rate_limit(app_id: str, user_id: str) -> Tuple[bool, int, int, int]:
    """
    Check if the app has exceeded its rate limit for a specific user
    Returns: (allowed, remaining, reset_time, retry_after)
    """
    now = datetime.utcnow()
    hour_key = f"notification_rate_limit:{app_id}:{user_id}:{now.strftime('%Y-%m-%d-%H')}"

    # Check hourly limit
    hour_count = redis_client.get(hour_key)
    if hour_count is None:
        redis_client.setex(hour_key, RATE_LIMIT_PERIOD, 1)
        hour_count = 1
    else:
        hour_count = int(hour_count)

    # Calculate reset time
    hour_reset = RATE_LIMIT_PERIOD - (int(now.timestamp()) % RATE_LIMIT_PERIOD)
    reset_time = hour_reset

    # Check if hourly limit is exceeded
    if hour_count >= MAX_NOTIFICATIONS_PER_HOUR:
        return False, MAX_NOTIFICATIONS_PER_HOUR - hour_count, hour_reset, hour_reset

    # Increment counter
    redis_client.incr(hour_key)

    remaining = MAX_NOTIFICATIONS_PER_HOUR - hour_count - 1

    return True, remaining, reset_time, 0


@router.post('/v1/users/fcm-token', response_model=FcmTokenResponse)
def save_token(
    data: SaveFcmTokenRequest,
    uid: str = Depends(auth.get_current_user_uid),
    x_app_platform: str = Header(None, alias='X-App-Platform'),
    x_device_id_hash: str = Header(None, alias='X-Device-Id-Hash'),
):
    platform = x_app_platform or 'unknown'
    device_hash = x_device_id_hash or 'default'

    # Create key: ios_abc123, android_xyz456, macos_def789
    device_key = f"{platform}_{device_hash}"

    token_data = data.model_dump()
    token_data['device_key'] = device_key

    notification_db.save_token(uid, token_data)
    return {'status': 'Ok'}


# ******************************************************
# ******************* TEAM ENDPOINTS *******************
# ******************************************************


@router.post('/v1/notification', response_model=StatusResponse)
def send_notification_to_user(data: SendNotificationRequest, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    # Pydantic makes uid/title/body required (422 on missing); this guards against empty-string uid.
    if not data.uid:
        raise HTTPException(status_code=400, detail='uid is required')
    send_notification(data.uid, data.title, data.body, data.data)
    return {'status': 'Ok'}


@router.post('/v1/integrations/notification', response_model=NotificationStatusResponse)
def send_app_notification_to_user(
    request: Request, data: SendAppNotificationRequest, authorization: Optional[str] = Header(None)
):
    # Pydantic makes aid/message/uid required (422 on missing); these guard against empty-string values.
    if not data.message:
        raise HTTPException(status_code=400, detail='message is required')

    if not data.uid:
        raise HTTPException(status_code=400, detail='uid is required')
    uid = data.uid

    # Verify API key from Authorization header
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header. Must be 'Bearer API_KEY'")

    api_key = authorization.replace('Bearer ', '')
    if not verify_api_key(data.aid, api_key):
        raise HTTPException(status_code=403, detail="Invalid API key")

    # Get app details and convert to App model
    app_data = get_available_app_by_id(data.aid, uid)
    if not app_data:
        raise HTTPException(status_code=404, detail='App not found')
    app = App(**app_data)

    # Check if user has app installed
    user_enabled = set(get_enabled_apps(uid))
    if data.aid not in user_enabled:
        raise HTTPException(status_code=403, detail='User does not have this app installed')

    # Check rate limit
    allowed, remaining, reset_time, retry_after = check_rate_limit(app.id, uid)

    # Add rate limit headers to response
    headers = {
        'X-RateLimit-Limit': str(MAX_NOTIFICATIONS_PER_HOUR),
        'X-RateLimit-Remaining': str(remaining),
        'X-RateLimit-Reset': str(reset_time),
    }

    if not allowed:
        headers['Retry-After'] = str(retry_after)
        return JSONResponse(
            status_code=429,
            headers=headers,
            content={'detail': f'Rate limit exceeded. Maximum {MAX_NOTIFICATIONS_PER_HOUR} notifications per hour.'},
        )

    # Determine target from manifest (defaults to 'app' if not configured)
    target = 'app'
    if app.external_integration and app.external_integration.chat_messages_enabled:
        target = app.external_integration.chat_messages_target
        if target == 'main':
            # Prefix app name so users can identify which integration sent the message,
            # especially useful when an external app's error appears in the main chat.
            prefixed = f"[{app.name}]: {data.message}"
            add_integration_chat_message(prefixed, None, uid)
        else:
            add_integration_chat_message(data.message, app.id, uid)

    # Always send push notification
    send_app_notification(uid, app.name, app.id, data.message, target=target)

    return JSONResponse(status_code=200, headers=headers, content={'status': 'Ok'})
