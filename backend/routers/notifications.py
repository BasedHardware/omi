import logging
from firebase_admin import messaging
from fastapi import APIRouter
import database.notifications as notification_db

logger = logging.getLogger('uvicorn.error')
logger.setLevel(logging.DEBUG)
# from utils import auth
router = APIRouter()


@router.post('/v1/users/fcm-token')
def save_token(data: dict ):
    try:
        user_id = data['user_id']
        token = data['token']
        time_zone = data['time_zone']
        notification_db.save_token(user_id, token, time_zone)    

    except Exception:
        raise HTTPException(status_code=400, detail='No valid data')
    return {'status': 'success'}


def send_notification(token: str, title: str, body: str, data = None):
    notification = messaging.Notification(
        title=title,
        body=body,
    )

    message = messaging.Message(
        notification=notification,
        token=token,
    )

    if data:
        message.data = data

    try:
        response = messaging.send(message)
        print("Successfully sent message:", response)
    except Exception as e:
        print("Error sending message:", e)

