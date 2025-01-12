import os

from fastapi import APIRouter, Depends, Header, HTTPException

import database.notifications as notification_db
from models.other import SaveFcmTokenRequest
from utils.notifications import send_notification
from utils.other import endpoints as auth


# logger = logging.getLogger('uvicorn.error')
# logger.setLevel(logging.DEBUG)
v1_router = APIRouter(prefix='/v1', tags=['notifications'])


@v1_router.post('/users/fcm-token')
def save_token(data: SaveFcmTokenRequest, uid: str = Depends(auth.get_current_user_uid)):
    notification_db.save_token(uid, data.dict())
    return {'status': 'Ok'}


# ******************************************************
# ******************* TEAM ENDPOINTS *******************
# ******************************************************

@v1_router.post('/notification')
def send_notification_to_user(data: dict, secret_key: str = Header(...)):
    if secret_key != os.getenv('ADMIN_KEY'):
        raise HTTPException(status_code=403, detail='You are not authorized to perform this action')
    if not data.get('uid'):
        raise HTTPException(status_code=400, detail='uid is required')
    uid = data['uid']
    token = notification_db.get_token_only(uid)
    send_notification(token, data['title'], data['body'], data.get('data', {}))
    return {'status': 'Ok'}
