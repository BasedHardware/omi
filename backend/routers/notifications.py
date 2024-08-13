import logging

from fastapi import APIRouter, Depends
from firebase_admin import messaging

import database.notifications as notification_db
from models.other import SaveFcmTokenRequest
from utils import auth

# logger = logging.getLogger('uvicorn.error')
# logger.setLevel(logging.DEBUG)
router = APIRouter()


@router.post('/v1/users/fcm-token')
def save_token(data: SaveFcmTokenRequest, uid: str = Depends(auth.get_current_user_uid)):
    notification_db.save_token(uid, data.dict())
    return {'status': 'Ok'}


def send_notification(token: str, title: str, body: str, data: dict = None):
    print('send_notification', token, title, body, data)
    notification = messaging.Notification(title=title, body=body)
    message = messaging.Message(notification=notification, token=token)

    if data:
        message.data = data

    try:
        response = messaging.send(message)
        print("Successfully sent message:", response)
    except Exception as e:
        print("Error sending message:", e)
