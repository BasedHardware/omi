from fastapi import APIRouter, Depends

import database.notifications as notification_db
from models.other import SaveFcmTokenRequest
from utils.other import endpoints as auth


# logger = logging.getLogger('uvicorn.error')
# logger.setLevel(logging.DEBUG)
router = APIRouter()


@router.post('/v1/users/fcm-token')
def save_token(data: SaveFcmTokenRequest, uid: str = Depends(auth.get_current_user_uid)):
    notification_db.save_token(uid, data.dict())
    return {'status': 'Ok'}
