from firebase_admin import auth

from database.redis_db import cache_user_name, get_cached_user_name


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
    # if cached_name := get_cached_user_name(uid):
    #     return cached_name
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
