import os
from datetime import datetime, timezone
from typing import List

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
    reviews[uid] = {'score': score, 'review': review, 'rated_at': datetime.now(timezone.utc).isoformat(), 'uid': uid}
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


def set_user_has_soniox_speech_profile(uid: str):
    r.set(f'users:{uid}:has_soniox_speech_profile', '1')


def get_user_has_soniox_speech_profile(uid: str) -> bool:
    return r.exists(f'users:{uid}:has_soniox_speech_profile')


def remove_user_soniox_speech_profile(uid: str):
    r.delete(f'users:{uid}:has_soniox_speech_profile')


def store_user_speech_profile(uid: str, data: List[List[int]]):
    r.set(f'users:{uid}:speech_profile', str(data))


def get_user_speech_profile(uid: str) -> List[List[int]]:
    data = r.get(f'users:{uid}:speech_profile')
    if not data:
        return []
    return eval(data)


def store_user_speech_profile_duration(uid: str, duration: int):
    r.set(f'users:{uid}:speech_profile_duration', duration)


def get_user_speech_profile_duration(uid: str) -> int:
    data = r.get(f'users:{uid}:speech_profile_duration')
    if not data:
        return 0
    return int(data)


def cache_user_name(uid: str, name: str, ttl: int = 60 * 60 * 24 * 7):
    r.set(f'users:{uid}:name', name)
    r.expire(f'users:{uid}:name', ttl)


def get_cached_user_name(uid: str) -> str:
    name = r.get(f'users:{uid}:name')
    if not name:
        return 'User'
    return name.decode()


# TODO: cache facts if speed improves dramatically
def cache_facts(uid: str, facts: List[dict]):
    r.set(f'users:{uid}:facts', str(facts))
    r.expire(f'users:{uid}:facts', 60 * 60)  # 1 hour, most people chat during a few minutes


def get_cached_facts(uid: str) -> List[dict]:
    facts = r.get(f'users:{uid}:facts')
    if not facts:
        return []
    return eval(facts)


def cache_signed_url(blob_path: str, signed_url: str, ttl: int = 60 * 60):
    r.set(f'urls:{blob_path}', signed_url)
    r.expire(f'urls:{blob_path}', ttl - 1)


def get_cached_signed_url(blob_path: str) -> str:
    signed_url = r.get(f'urls:{blob_path}')
    if not signed_url:
        return ''
    return signed_url.decode()


# VISIIBILTIY OF MEMORIES
def store_memory_to_uid(memory_id: str, uid: str):
    r.set(f'memories-visibility:{memory_id}', uid)


def remove_memory_to_uid(memory_id: str):
    r.delete(f'memories-visibility:{memory_id}')


def get_memory_uid(memory_id: str) -> str:
    uid = r.get(f'memories-visibility:{memory_id}')
    if not uid:
        return ''
    return uid.decode()


def add_public_memory(memory_id: str):
    r.sadd('public-memories', memory_id)


def remove_public_memory(memory_id: str):
    r.srem('public-memories', memory_id)


def get_public_memories() -> List[str]:
    val = r.smembers('public-memories')
    if not val:
        return []
    return [x.decode() for x in val]
