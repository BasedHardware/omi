from typing import Any, Dict, Optional, cast

from database.store import get_document_store
from database.redis_db import cache_user_name
import logging

logger = logging.getLogger(__name__)


def _store():
    return get_document_store()


def _firebase_get_user(uid: str) -> Any:
    """Look up a user's profile through the neutral auth port (ADR-0034). Returns a UserProfile whose
    fields (uid/email/email_verified/phone_number/display_name/photo_url/disabled) get_user_from_uid
    reads by attribute — same names as the former Firebase UserRecord, so no caller change."""
    from utils.auth import get_auth_provider

    return get_auth_provider().get_user_profile(uid)


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


def _get_stored_user_name(uid: str) -> Optional[str]:
    """Fallback: get user name from the stored user profile."""
    try:
        user_doc = _store().get(f'users/{uid}')
        if user_doc.exists:
            raw: object = user_doc.to_dict()
            data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
            name = data.get('name')
            if name and isinstance(name, str):
                return name.split(' ')[0]
    except Exception as e:
        logger.error(f"Stored user name lookup failed: {e}")
    return None


def get_user_name(uid: str, use_default: bool = True) -> Optional[str]:
    default_name: Optional[str] = 'The User' if use_default else None
    user = get_user_from_uid(uid)
    if not user:
        # Fallback to stored user profile
        stored_name = _get_stored_user_name(uid)
        if stored_name:
            cache_user_name(uid, stored_name, ttl=60 * 60)
            return stored_name
        return default_name

    display_name_raw = user.get('display_name')
    if not display_name_raw:
        # Fallback to stored user profile
        stored_name = _get_stored_user_name(uid)
        if stored_name:
            cache_user_name(uid, stored_name, ttl=60 * 60)
            return stored_name
        return default_name

    display_name: str = display_name_raw.split(' ')[0]
    if display_name == 'AnonymousUser':
        stored_name = _get_stored_user_name(uid)
        if stored_name:
            display_name = stored_name
        elif use_default:
            display_name = 'The User'
        else:
            return None

    cache_user_name(uid, display_name, ttl=60 * 60)
    return display_name
