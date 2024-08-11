import os
from datetime import datetime

import redis

r = redis.Redis(
    host=os.getenv('REDIS_DB_HOST'),
    port=int(os.getenv('REDIS_DB_PORT')) if os.getenv('REDIS_DB_PORT') is not None else 6379,
    username='default',
    password=os.getenv('REDIS_DB_PASSWORD'),
    health_check_interval=30
)


def try_catch_decorator(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            print(f'Error calling {func.__name__}', e)
            return None

    return wrapper


def set_plugin_review(plugin_id: str, uid: str, score: float, review: str = ''):
    reviews = r.get(f'plugins:{plugin_id}:reviews')
    if not reviews:
        reviews = {}
    else:
        reviews = eval(reviews)
    reviews[uid] = {'score': score, 'review': review, 'rated_at': datetime.utcnow().isoformat(), 'uid': uid}
    r.set(f'plugins:{plugin_id}:reviews', str(reviews))


def migrate_user_plugins_reviews(prev_uid: str, new_uid: str):
    for key in r.scan_iter(f'plugins:*:reviews'):
        plugin_id = key.decode().split(':')[1]
        reviews = r.get(key)
        if not reviews:
            continue
        reviews = eval(reviews)
        if prev_uid in reviews:
            reviews[new_uid] = reviews.pop(prev_uid)
            reviews[new_uid]['uid'] = new_uid
            r.set(f'plugins:{plugin_id}:reviews', str(reviews))


def enable_plugin(uid: str, plugin_id: str):
    r.sadd(f'users:{uid}:enabled_plugins', plugin_id)


def disable_plugin(uid: str, plugin_id: str):
    r.srem(f'users:{uid}:enabled_plugins', plugin_id)


def get_enabled_plugins(uid: str):
    val = r.smembers(f'users:{uid}:enabled_plugins')
    if not val:
        return []
    return [x.decode() for x in val]


def get_plugin_reviews(plugin_id: str) -> dict:
    reviews = r.get(f'plugins:{plugin_id}:reviews')
    if not reviews:
        return {}
    return eval(reviews)


def user_has_speech_profile(uid: str) -> bool:
    return r.exists(f'speech_profiles:{uid}') != 0


def set_user_has_speech_profile(uid: str):
    r.set(f'speech_profiles:{uid}', 1)
