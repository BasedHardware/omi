import re
from typing import Any, Dict, Optional, cast

from firebase_admin import auth

from database._client import get_firestore_client
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


# Only the first profile line may declare identity. Requiring a complete name
# bullet or an explicit "is" clause avoids treating arbitrary biography prose as
# a name. The optional parenthesized spelling supports bilingual identities.
_PROFILE_IDENTITY = re.compile(
    r"- (?P<name>[A-Z\u3400-\u9fff\u3040-\u30ff\uac00-\ud7a3][\w'-]+(?: [A-Z\u3400-\u9fff\u3040-\u30ff\uac00-\ud7a3][\w'-]+){0,2}?)"
    r"(?: [（(][\w '\-]+[）)])?(?: is .+)?"
)


def _profile_first_name(profile_text: object) -> Optional[str]:
    if not isinstance(profile_text, str) or not profile_text:
        return None
    first_line = profile_text.splitlines()[0].strip()
    match = _PROFILE_IDENTITY.fullmatch(first_line)
    return match.group('name').split(' ')[0] if match else None


def _get_firestore_user_name(uid: str, *, firestore_client: Any = None) -> Optional[str]:
    """Resolve the explicit profile name before its first-line AI identity bullet."""
    try:
        client = firestore_client if firestore_client is not None else get_firestore_client()
        user_doc = client.collection('users').document(uid).get()
        if getattr(user_doc, "exists", False):
            raw: object = user_doc.to_dict()
            data: Dict[str, Any] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else {}
            name = data.get('name')
            if name and isinstance(name, str):
                return name.split(' ')[0]
            ai_profile = data.get('ai_user_profile')
            if isinstance(ai_profile, dict):
                profile = cast(Dict[str, Any], ai_profile)
                return _profile_first_name(profile.get('profile_text'))
    except Exception as e:
        logger.error(f"Firestore user name lookup failed: {e}")
    return None


def get_user_name(uid: str, use_default: bool = True) -> Optional[str]:
    """Owner first name: Firebase, explicit Firestore name, then AI identity line.

    Callers share this precedence and the existing one-hour name cache. Unknown
    identities preserve the historical ``use_default`` contract.
    """
    user = get_user_from_uid(uid)
    display_name_raw = user.get('display_name') if user else None
    name = display_name_raw.split(' ')[0] if display_name_raw else None
    if not name or name == 'AnonymousUser':
        name = _get_firestore_user_name(uid)
    if name:
        cache_user_name(uid, name, ttl=60 * 60)
        return name
    return 'The User' if use_default else None
