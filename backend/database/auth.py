from typing import Any, Dict, Optional, cast

from firebase_admin import auth

from database._client import db
from database.redis_db import cache_user_name
import logging

logger = logging.getLogger(__name__)


def _firebase_get_user(uid: str) -> Any:
    """Wrap firebase_admin.auth.get_user at the SDK boundary.

    firebase_admin.auth ships incomplete type stubs; its UserRecord fields
    surface as partially-unknown. Sealing the call here lets callers treat the
    result as Any and read fields without propagating Unknown.
    """
    return auth.get_user(uid)  # type: ignore[reportUnknownMemberType]  # firebase_admin.auth stub gap


def get_user_from_uid(uid: str) -> Optional[Dict[str, Any]]:
    try:
        raw_user: Any = _firebase_get_user(uid) if uid else None
    except Exception as e:
        logger.error(e)
        raw_user = None
    if not raw_user:
        return None

    user: Any = raw_user

    return {
        'uid': user.uid,
        'email': user.email,
        'email_verified': user.email_verified,
        'phone_number': user.phone_number,
        'display_name': user.display_name,
        'photo_url': user.photo_url,
        'disabled': user.disabled,
    }


def _get_firestore_user_name(uid: str) -> Optional[str]:
    """Fallback: get user name from Firestore user profile."""
    try:
        user_doc = db.collection('users').document(uid).get()
        if getattr(user_doc, "exists", False):
            raw: object = user_doc.to_dict()
            data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
            name = data.get('name')
            if name and isinstance(name, str):
                return name.split(' ')[0]
    except Exception as e:
        logger.error(f"Firestore user name lookup failed: {e}")
    return None


def get_user_name(uid: str, use_default: bool = True) -> Optional[str]:
    default_name: Optional[str] = 'The User' if use_default else None
    user = get_user_from_uid(uid)
    if not user:
        # Fallback to Firestore profile
        firestore_name = _get_firestore_user_name(uid)
        if firestore_name:
            cache_user_name(uid, firestore_name, ttl=60 * 60)
            return firestore_name
        return default_name

    display_name_raw = user.get('display_name')
    if not display_name_raw:
        # Fallback to Firestore profile
        firestore_name = _get_firestore_user_name(uid)
        if firestore_name:
            cache_user_name(uid, firestore_name, ttl=60 * 60)
            return firestore_name
        return default_name

    display_name: str = display_name_raw.split(' ')[0]
    if display_name == 'AnonymousUser':
        firestore_name = _get_firestore_user_name(uid)
        if firestore_name:
            display_name = firestore_name
        elif use_default:
            display_name = 'The User'
        else:
            return None

    cache_user_name(uid, display_name, ttl=60 * 60)
    return display_name
