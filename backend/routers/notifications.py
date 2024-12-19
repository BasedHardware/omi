import os

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from database.redis_db import get_enabled_plugins
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


@router.post('/v1/users/fcm-token')
def save_token(data: SaveFcmTokenRequest, uid: str = Depends(auth.get_current_user_uid)):
    notification_db.save_token(uid, data.dict())
    return {'status': 'Ok'}


# ******************************************************
# ******************* TEAM ENDPOINTS *******************
# ******************************************************

@router.post('/v1/notification')
def send_notification_to_user(
    request: Request,
    data: dict, 
    secret_key: str | None = Header(default=None),
):
    # Check admin key auth if provided
    if secret_key is not None:
        if secret_key != os.getenv('ADMIN_KEY'):
            raise HTTPException(status_code=403, detail='Invalid admin key')
    else:
        # Check app-based auth
        if 'aid' not in data:
            raise HTTPException(status_code=400, detail='Either secret_key header or aid (app id) in request body is required')
        
        # Get app details and convert to App model
        app_data = get_available_app_by_id(data['aid'], data['uid'])
        if not app_data:
            raise HTTPException(status_code=404, detail='App not found')
        app = App(**app_data)
        
        # Check if user has app installed
        user_enabled = set(get_enabled_plugins(data['uid']))
        if data['aid'] not in user_enabled:
            raise HTTPException(status_code=403, detail='User does not have this app installed')
        
        # Verify request origin matches app webhook URL
        if not app.works_externally():
            raise HTTPException(status_code=400, detail='App is not an external integration')
            
        app_webhook_url = app.external_integration.webhook_url if app.external_integration else None
        if not app_webhook_url:
            raise HTTPException(status_code=400, detail='App does not have a webhook URL configured')
        
        # Extract base URLs for comparison
        from urllib.parse import urlparse
        app_base_url = urlparse(app_webhook_url).netloc
        
        # Try to get the request origin from headers
        request_origin = request.headers.get('origin') or request.headers.get('referer')
        if not request_origin:
            raise HTTPException(status_code=400, detail='Origin or Referer header is required when using app auth')
            
        request_base_url = urlparse(request_origin).netloc
        if app_base_url != request_base_url:
            raise HTTPException(status_code=403, detail='Request origin does not match app webhook URL')

    if not data.get('uid'):
        raise HTTPException(status_code=400, detail='uid is required')
    uid = data['uid']
    token = notification_db.get_token_only(uid)

    if 'aid' in data:
        send_plugin_notification(token, app.name, app.id, data['message'])
    else:
        send_notification(token, data['title'], data['body'], data.get('data', {}))
    return {'status': 'Ok'}
