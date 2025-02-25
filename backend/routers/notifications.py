import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from typing import Tuple

from database.redis_db import get_enabled_plugins, r as redis_client
from utils.apps import get_available_app_by_id
from utils.plugins import send_plugin_notification
import database.notifications as notification_db
from models.other import SaveFcmTokenRequest
from utils.notifications import send_notification
from utils.other import endpoints as auth
from models.app import App


# logger = logging.getLogger('uvicorn.error')
# logger.setLevel(logging.DEBUG)
router = APIRouter()

# Rate limit settings - more conservative limits to prevent notification fatigue
RATE_LIMIT_PERIOD = 3600  # 1 hour in seconds
MAX_NOTIFICATIONS_PER_HOUR = 10  # Maximum notifications per hour per app per user
BURST_LIMIT = 3  # Maximum notifications in a 5-minute window
BURST_WINDOW = 300  # 5 minutes in seconds

def check_rate_limit(app_id: str, user_id: str) -> Tuple[bool, int, int, int]:
    """
    Check if the app has exceeded its rate limit for a specific user
    Returns: (allowed, remaining, reset_time, retry_after)
    """
    now = datetime.utcnow()
    hour_key = f"notification_rate_limit:{app_id}:{user_id}:{now.strftime('%Y-%m-%d-%H')}"
    burst_key = f"notification_rate_limit_burst:{app_id}:{user_id}:{int(now.timestamp() // BURST_WINDOW)}"
    
    # Check hourly limit
    hour_count = redis_client.get(hour_key)
    if hour_count is None:
        redis_client.setex(hour_key, RATE_LIMIT_PERIOD, 1)
        hour_count = 1
    else:
        hour_count = int(hour_count)

    # Check burst limit
    burst_count = redis_client.get(burst_key)
    if burst_count is None:
        redis_client.setex(burst_key, BURST_WINDOW, 1)
        burst_count = 1
    else:
        burst_count = int(burst_count)

    # Calculate reset times
    hour_reset = RATE_LIMIT_PERIOD - (int(now.timestamp()) % RATE_LIMIT_PERIOD)
    burst_reset = BURST_WINDOW - (int(now.timestamp()) % BURST_WINDOW)
    reset_time = min(hour_reset, burst_reset)

    # Check if either limit is exceeded
    if hour_count >= MAX_NOTIFICATIONS_PER_HOUR:
        return False, MAX_NOTIFICATIONS_PER_HOUR - hour_count, hour_reset, hour_reset
    if burst_count >= BURST_LIMIT:
        return False, BURST_LIMIT - burst_count, burst_reset, burst_reset

    # Increment counters
    redis_client.incr(hour_key)
    redis_client.incr(burst_key)
    
    remaining = min(
        MAX_NOTIFICATIONS_PER_HOUR - hour_count - 1,
        BURST_LIMIT - burst_count - 1
    )
    
    return True, remaining, reset_time, 0


@router.post('/v1/users/fcm-token')
def save_token(data: SaveFcmTokenRequest, uid: str = Depends(auth.get_current_user_uid)):
    notification_db.save_token(uid, data.dict())
    return {'status': 'Ok'}

# ******************************************************
# ******************* TEAM ENDPOINTS *******************
# ******************************************************

@router.post('/v1/notification')
def send_notification_to_user(data: dict, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    if not data.get('uid'):
        raise HTTPException(status_code=400, detail='uid is required')
    uid = data['uid']
    token = notification_db.get_token_only(uid)
    send_notification(token, data['title'], data['body'], data.get('data', {}))
    return {'status': 'Ok'}


@router.post('/v1/integrations/notification')
def send_app_notification_to_user(
    request: Request,
    data: dict,
):
    # Check app-based auth
    if 'aid' not in data:
        raise HTTPException(status_code=400, detail='aid (app id) in request body is required')
    
    if not data.get('uid'):
        raise HTTPException(status_code=400, detail='uid is required')
    uid = data['uid']
    
    # Get app details and convert to App model
    app_data = get_available_app_by_id(data['aid'], uid)
    if not app_data:
        raise HTTPException(status_code=404, detail='App not found')
    app = App(**app_data)
    
    # Check if user has app installed
    user_enabled = set(get_enabled_plugins(uid))
    if data['aid'] not in user_enabled:
        raise HTTPException(status_code=403, detail='User does not have this app installed')
    
    # Verify app secret
    app_secret = request.headers.get('X-App-Secret')
    if not app_secret:
        raise HTTPException(status_code=400, detail='X-App-Secret header is required')
    if app_secret != app.app_secret:
        raise HTTPException(status_code=403, detail='Invalid app secret')

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
            content={
                'detail': f'Rate limit exceeded. Maximum {MAX_NOTIFICATIONS_PER_HOUR} notifications per hour and {BURST_LIMIT} notifications per {BURST_WINDOW} seconds.'
            }
        )

    token = notification_db.get_token_only(uid)
    send_plugin_notification(token, app.name, app.id, data['message'])
    return JSONResponse(
        status_code=200,
        headers=headers,
        content={'status': 'Ok'}
    )




