from firebase_admin import auth

from database.redis_db import get_cached_user_name, cache_user_name


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


def get_user_name(uid: str):
    # if cached_name := get_cached_user_name(uid):
    #     return cached_name

    user = get_user_from_uid(uid)
    display_name = user.get('display_name', 'User').split(' ')[0] if user else 'The User'
    if display_name == 'AnonymousUser':
        display_name = 'The User'

    cache_user_name(uid, display_name)
    return display_name
