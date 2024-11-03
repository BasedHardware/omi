from firebase_admin import auth
from fastapi import HTTPException
from database.redis_db import cache_user_name, get_cached_user_name

def create_user(uid: str, user_data: dict) -> str:
    """Create a new user document"""
    from ._client import db
    user_ref = db.collection('users').document(uid)
    user_ref.set(user_data)
    return uid

def get_user(uid: str) -> dict:
    """Get user document by ID"""
    from ._client import db
    user_ref = db.collection('users').document(uid)
    user_doc = user_ref.get()
    if not user_doc.exists:
        raise HTTPException(status_code=404, detail="User not found")
    return user_doc.to_dict()

def delete_user(uid: str):
    """Delete user document"""
    from ._client import db
    user_ref = db.collection('users').document(uid)
    user_ref.delete()

def update_user(uid: str, user_data: dict):
    """Update user document"""
    from ._client import db
    user_ref = db.collection('users').document(uid)
    user_ref.update(user_data)

def validate_token(token: str) -> str:
    """Validate Firebase ID token"""
    try:
        decoded_token = auth.verify_id_token(token)
        return decoded_token['uid']
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

def get_user_from_uid(uid: str):
    try:
        user = auth.get_user(uid) if uid else None
    except Exception as e:
        print(e)
        user = None
    if not user:
        return None

    return {
        'uid': user.uid,
        'email': user.email,
        'email_verified': user.email_verified,
        'phone_number': user.phone_number,
        'display_name': user.display_name,
        'photo_url': user.photo_url,
        'disabled': user.disabled,
    }

def get_user_name(uid: str, use_default: bool = True):
    default_name = 'The User' if use_default else None
    user = get_user_from_uid(uid)
    if not user:
        return default_name

    display_name = user.get('display_name')
    if not display_name:
        return default_name

    display_name = display_name.split(' ')[0]
    if display_name == 'AnonymousUser':
        display_name = default_name

    cache_user_name(uid, display_name, ttl=60 * 60)
    return display_name

__all__ = [
    'create_user',
    'get_user',
    'delete_user',
    'update_user',
    'validate_token',
    'get_user_from_uid',
    'get_user_name'
]
