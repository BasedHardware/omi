import base64
import json
import os
from datetime import datetime, timezone
from typing import List, Union

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


@try_catch_decorator
def get_generic_cache(path: str):
    key = base64.b64encode(f'{path}'.encode('utf-8'))
    key = key.decode('utf-8')

    data = r.get(f'cache:{key}')
    return json.loads(data) if data else None


@try_catch_decorator
def set_generic_cache(path: str, data: Union[dict, list], ttl: int = None):
    key = base64.b64encode(f'{path}'.encode('utf-8'))
    key = key.decode('utf-8')

    r.set(f'cache:{key}', json.dumps(data, default=str))
    if ttl:
        r.expire(f'cache:{key}', ttl)


@try_catch_decorator
def delete_generic_cache(path: str):
    key = base64.b64encode(f'{path}'.encode('utf-8'))
    key = key.decode('utf-8')
    r.delete(f'cache:{key}')


# ******************************************************
# *********************** APPS *************************
# ******************************************************


def set_app_usage_history_cache(app_id: str, usage: List[dict]):
    r.set(f'apps:{app_id}:usage', json.dumps(usage, default=str), ex=60 * 5)  # 5 minutes


def get_app_usage_history_cache(app_id: str) -> List[dict]:
    usage = r.get(f'apps:{app_id}:usage')
    if usage is None:
        return []
    usage = json.loads(usage)
    if not usage:
        return []
    return usage


def get_app_money_made_cache(app_id: str) -> dict:
    money = r.get(f'apps:{app_id}:money')
    if money is None:
        return {}
    money = json.loads(money)
    if not money:
        return {}
    return money


def set_app_money_made_cache(app_id: str, money: dict):
    r.set(f'apps:{app_id}:money', json.dumps(money, default=str), ex=60 * 5)  # 5 minutes


def set_plugin_review(plugin_id: str, uid: str, data: dict):
    reviews = r.get(f'plugins:{plugin_id}:reviews')
    if not reviews:
        reviews = {}
    else:
        reviews = eval(reviews)
    reviews[uid] = data
    r.set(f'plugins:{plugin_id}:reviews', str(reviews))


def get_specific_user_review(app_id: str, uid: str) -> dict:
    reviews = r.get(f'plugins:{app_id}:reviews')
    if not reviews:
        return {}
    reviews = eval(reviews)
    return reviews.get(uid, {})


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


def set_plugin_installs_count(plugin_id: str, count: int):
    r.set(f'plugins:{plugin_id}:installs', count)


def increase_plugin_installs_count(plugin_id: str):
    r.incr(f'plugins:{plugin_id}:installs')


def decrease_plugin_installs_count(plugin_id: str):
    r.decr(f'plugins:{plugin_id}:installs')


def get_plugin_installs_count(plugin_id: str) -> int:
    count = r.get(f'plugins:{plugin_id}:installs')
    if not count:
        return 0
    return int(count)


def set_user_has_soniox_speech_profile(uid: str):
    r.set(f'users:{uid}:has_soniox_speech_profile', '1')


def get_user_has_soniox_speech_profile(uid: str) -> bool:
    return r.exists(f'users:{uid}:has_soniox_speech_profile')


def remove_user_soniox_speech_profile(uid: str):
    r.delete(f'users:{uid}:has_soniox_speech_profile')


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


def cache_user_geolocation(uid: str, geolocation: dict):
    r.set(f'users:{uid}:geolocation', str(geolocation))
    r.expire(f'users:{uid}:geolocation', 60 * 30)  # FIXME: too much?


def get_cached_user_geolocation(uid: str):
    geolocation = r.get(f'users:{uid}:geolocation')
    if not geolocation:
        return None
    return eval(geolocation)


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


def set_in_progress_memory_id(uid: str, memory_id: str, ttl: int = 150):
    r.set(f'users:{uid}:in_progress_memory_id', memory_id)
    r.expire(f'users:{uid}:in_progress_memory_id', ttl)


def remove_in_progress_memory_id(uid: str):
    r.delete(f'users:{uid}:in_progress_memory_id')


def get_in_progress_memory_id(uid: str) -> str:
    memory_id = r.get(f'users:{uid}:in_progress_memory_id')
    if not memory_id:
        return ''
    return memory_id.decode()


def set_user_webhook_db(uid: str, wtype: str, url: str):
    r.set(f'users:{uid}:developer:webhook:{wtype}', url)


def disable_user_webhook_db(uid: str, wtype: str):
    r.set(f'users:{uid}:developer:webhook_status:{wtype}', str(False).lower())


def enable_user_webhook_db(uid: str, wtype: str):
    r.set(f'users:{uid}:developer:webhook_status:{wtype}', str(True).lower())


def user_webhook_status_db(uid: str, wtype: str):
    status = r.get(f'users:{uid}:developer:webhook_status:{wtype}')
    if status is None:
        return None
    return status.decode() == str(True).lower()


def get_user_webhook_db(uid: str, wtype: str) -> str:
    url = r.get(f'users:{uid}:developer:webhook:{wtype}')
    if not url:
        return ''
    return url.decode()


def get_filter_category_items(uid: str, category: str) -> List[str]:
    val = r.smembers(f'users:{uid}:filters:{category}')
    if not val:
        return []
    return [x.decode() for x in val]


def add_filter_category_item(uid: str, category: str, item: str):
    r.sadd(f'users:{uid}:filters:{category}', item)


def remove_filter_category_item(uid: str, category: str, item: str):
    r.srem(f'users:{uid}:filters:{category}', item)


def remove_all_filter_category_items(uid: str, category: str):
    r.delete(f'users:{uid}:filters:{category}')


def save_migrated_retrieval_memory_id(memory_id: str):
    r.sadd('migrated_retrieval_memory_ids', memory_id)
    r.expire('migrated_retrieval_memory_ids', 60 * 60 * 24 * 7)


def has_migrated_retrieval_memory_id(memory_id: str) -> bool:
    return r.sismember('migrated_retrieval_memory_ids', memory_id)
