import logging

from firebase_admin import messaging
from fastapi import APIRouter
from utils.redis_utils import set_user_token, get_user_token, set_user_timezone, get_user_timezone


logger = logging.getLogger('uvicorn.error')
logger.setLevel(logging.DEBUG)
# from utils import auth
router = APIRouter()


@router.post('/save-token')
def save_token(data: dict ):
    try:
        user_id = data['user_id']
        token = data['token']
        time_zone = data['time_zone']
        set_user_token(user_id, token)
        set_user_timezone(user_id,time_zone)

    except Exception:
        raise HTTPException(status_code=400, detail='No valid data')
    return {'status': 'success'}


@router.post('/send-notification')
def send_notification(token: str, title: str, body: str):
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        token=token,
    )

    try:
        response = messaging.send(message)
        print("Successfully sent message:", response)
    except Exception as e:
        print("Error sending message:", e)

