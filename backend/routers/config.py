import os

from fastapi import APIRouter, Depends

from utils.other.endpoints import get_current_user_uid

router = APIRouter()


@router.get('/v1/config/api-keys', tags=['config'])
def get_api_keys(uid: str = Depends(get_current_user_uid)):
    return {
        'elevenlabs_api_key': os.getenv('ELEVENLABS_API_KEY'),
    }
