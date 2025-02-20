import base64
import json
import os
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
# ********************* APP BY ID **********************
# ******************************************************

def set_app_cache_by_id(app_id: str, app: dict):
    r.set(f'apps:{app_id}', json.dumps(app, default=str), ex=60 * 10)  # 10 minutes cached


def get_app_cache_by_id(app_id: str) -> dict | None:
    app = r.get(f'apps:{app_id}')
    app = json.loads(app) if app else None
    return app


def delete_app_cache_by_id(app_id: str):
    r.delete(f'apps:{app_id}')


# ******************************************************
# ********************** PERSONA ***********************
# ******************************************************

def is_username_taken(username: str) -> bool:
    """Check if username is taken by checking if it exists in the username:uid mapping"""
    value = r.exists(f'username:{username}:uid')
    if value == 0:
        return False
    return True


def get_uid_by_username(username: str) -> str | None:
    """Get the UID that owns this username"""
    uid = r.get(f'username:{username}:uid')
    return uid.decode() if uid else None


def get_usernames_by_uid(uid: str) -> List[str]:
    """Get all usernames owned by a UID"""
    usernames = r.smembers(f'uid:{uid}:usernames')
    return [u.decode() for u in usernames] if usernames else []


def delete_username(username: str):
    """Delete username and remove it from owner's set"""
    # Get current owner
    uid = get_uid_by_username(username)
    if uid:
        # Remove from owner's set
        r.srem(f'uid:{uid}:usernames', username)
        # Delete username:uid mapping
        r.delete(f'username:{username}:uid')


def save_username(username: str, uid: str):
    """Save username and add to owner's set"""
    # Save username:uid mapping
    r.set(f'username:{username}:uid', uid)
    # Add to owner's set of usernames
    r.sadd(f'uid:{uid}:usernames', username)


# ******************************************************
# *********************** APPS *************************
# ******************************************************


def set_app_usage_count_cache(app_id: str, count: int):
    r.set(f'apps:{app_id}:usage_count', count, ex=60 * 15)  # 15 minutes


def get_app_usage_count_cache(app_id: str) -> int | None:
    count = r.get(f'apps:{app_id}:usage_count')
    if not count:
        return None
    return eval(count)


def set_app_money_made_amount_cache(app_id: str, amount: float):
    r.set(f'apps:{app_id}:money_made', amount, ex=60 * 15)  # 15 minutes


def get_app_money_made_amount_cache(app_id: str) -> float | None:
    amount = r.get(f'apps:{app_id}:money_made')
    if not amount:
        return None
    return eval(amount)


def set_app_usage_history_cache(app_id: str, usage: List[dict]):
    r.set(f'apps:{app_id}:usage', json.dumps(usage, default=str), ex=60 * 10)  # 10 minutes


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
    r.set(f'apps:{app_id}:money', json.dumps(money, default=str), ex=60 * 10)  # 10 minutes


def set_app_review_cache(app_id: str, uid: str, data: dict):
    reviews = r.get(f'plugins:{app_id}:reviews')
    if not reviews:
        reviews = {}
    else:
        reviews = eval(reviews)
    reviews[uid] = data
    r.set(f'plugins:{app_id}:reviews', str(reviews))


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


def set_user_paid_app(app_id: str, uid: str, ttl: int):
    r.set(f'users:{uid}:paid_apps:{app_id}', app_id, ex=ttl)


def get_user_paid_app(app_id: str, uid: str) -> str:
    val = r.get(f'users:{uid}:paid_apps:{app_id}')
    if not val:
        return None
    return val.decode()


def enable_app(uid: str, app_id: str):
    r.sadd(f'users:{uid}:enabled_plugins', app_id)


def disable_app(uid: str, app_id: str):
    r.srem(f'users:{uid}:enabled_plugins', app_id)


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


def get_plugins_reviews(plugin_ids: list) -> dict:
    if not plugin_ids:
        return {}

    keys = [f'plugins:{plugin_id}:reviews' for plugin_id in plugin_ids]
    reviews = r.mget(keys)
    if reviews is None:
        return {}
    return {
        plugin_id: eval(review) if review else {}
        for plugin_id, review in zip(plugin_ids, reviews)
    }


def set_plugin_installs_count(plugin_id: str, count: int):
    r.set(f'plugins:{plugin_id}:installs', count)


def increase_app_installs_count(app_id: str):
    r.incr(f'plugins:{app_id}:installs')


def decrease_app_installs_count(app_id: str):
    r.decr(f'plugins:{app_id}:installs')


def get_plugin_installs_count(plugin_id: str) -> int:
    count = r.get(f'plugins:{plugin_id}:installs')
    if not count:
        return 0
    return int(count)


def get_plugins_installs_count(plugin_ids: list) -> dict:
    if not plugin_ids:
        return {}

    keys = [f'plugins:{plugin_id}:installs' for plugin_id in plugin_ids]
    counts = r.mget(keys)
    if counts is None:
        return {}
    return {
        plugin_id: int(count) if count else 0
        for plugin_id, count in zip(plugin_ids, counts)
    }


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


def get_memory_uids(memory_ids: list) -> dict:
    if not memory_ids:
        return {}

    memory_keys = [f'memories-visibility:{memory_id}' for memory_id in memory_ids]
    uids = r.mget(memory_keys)
    if uids is None:
        return {}
    memory_uids = {}
    for memory_id, uid in zip(memory_ids, uids):
        if uid:
            memory_uids[memory_id] = uid.decode()
    return memory_uids


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


def add_filter_category_items(uid: str, category: str, items: list):
    if items:
        r.sadd(f'users:{uid}:filters:{category}', *items)


def remove_filter_category_item(uid: str, category: str, item: str):
    r.srem(f'users:{uid}:filters:{category}', item)


def remove_all_filter_category_items(uid: str, category: str):
    r.delete(f'users:{uid}:filters:{category}')


def save_migrated_retrieval_memory_id(memory_id: str):
    r.sadd('migrated_retrieval_memory_ids', memory_id)
    r.expire('migrated_retrieval_memory_ids', 60 * 60 * 24 * 7)


def has_migrated_retrieval_memory_id(memory_id: str) -> bool:
    return r.sismember('migrated_retrieval_memory_ids', memory_id)


def set_proactive_noti_sent_at(uid: str, plugin_id: str, ts: int, ttl: int = 30):
    r.set(f'{uid}:{plugin_id}:proactive_noti_sent_at', ts, ex=ttl)


def get_proactive_noti_sent_at(uid: str, plugin_id: str):
    val = r.get(f'{uid}:{plugin_id}:proactive_noti_sent_at')
    if not val:
        return None
    return int(val)


def get_proactive_noti_sent_at_ttl(uid: str, plugin_id: str):
    return r.ttl(f'{uid}:{plugin_id}:proactive_noti_sent_at')
