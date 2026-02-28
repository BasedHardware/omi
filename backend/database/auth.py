from firebase_admin import auth

from database._client import db
from database.redis_db import cache_user_name, get_cached_user_name
import logging

logger = logging.getLogger(__name__)


def get_user_from_uid(uid: str):
    try:
        user = auth.get_user(uid) if uid else None
    except Exception as e:
        logger.error(e)
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


def _get_firestore_user_name(uid: str):
    """Fallback: get user name from Firestore user profile."""
    try:
        user_doc = db.collection('users').document(uid).get()
        if user_doc.exists:
            name = user_doc.to_dict().get('name')
            if name and isinstance(name, str):
                return name.split(' ')[0]
    except Exception as e:
        logger.error(f"Firestore user name lookup failed: {e}")
    return None


def get_user_name(uid: str, use_default: bool = True):
    # if cached_name := get_cached_user_name(uid):
    #     return cached_name
    default_name = 'The User' if use_default else None
    user = get_user_from_uid(uid)
    if not user:
        # Fallback to Firestore profile
        firestore_name = _get_firestore_user_name(uid)
        if firestore_name:
            cache_user_name(uid, firestore_name, ttl=60 * 60)
            return firestore_name
        return default_name

    display_name = user.get('display_name')
    if not display_name:
        # Fallback to Firestore profile
        firestore_name = _get_firestore_user_name(uid)
        if firestore_name:
            cache_user_name(uid, firestore_name, ttl=60 * 60)
            return firestore_name
        return default_name

    display_name = display_name.split(' ')[0]
    if display_name == 'AnonymousUser':
        firestore_name = _get_firestore_user_name(uid)
        if firestore_name:
            display_name = firestore_name
        else:
            display_name = default_name

    cache_user_name(uid, display_name, ttl=60 * 60)
    return display_name
