import base64
import json
import os
from typing import List, Union, Optional
from datetime import datetime, timedelta, timezone

import redis

r = redis.Redis(
    host=os.getenv('REDIS_DB_HOST'),
    port=int(os.getenv('REDIS_DB_PORT')) if os.getenv('REDIS_DB_PORT') is not None else 6379,
    username='default',
    password=os.getenv('REDIS_DB_PASSWORD'),
    health_check_interval=30,
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


def migrate_user_apps_reviews(prev_uid: str, new_uid: str):
    for key in r.scan_iter(f'plugins:*:reviews'):
        app_id = key.decode().split(':')[1]
        reviews = r.get(key)
        if not reviews:
            continue
        reviews = eval(reviews)
        if prev_uid in reviews:
            reviews[new_uid] = reviews.pop(prev_uid)
            reviews[new_uid]['uid'] = new_uid
            r.set(f'plugins:{app_id}:reviews', str(reviews))


def set_user_paid_app(app_id: str, uid: str, ttl: int):
    r.set(f'users:{uid}:paid_apps:{app_id}', app_id, ex=ttl)


def get_user_paid_app(app_id: str, uid: str) -> str:
    val = r.get(f'users:{uid}:paid_apps:{app_id}')
    if not val:
        return None
    return val.decode()


def set_user_app_subscription_customer_id(app_id: str, uid: str, customer_id: str):
    """Store the Stripe customer ID for a user's app subscription"""
    r.set(f'users:{uid}:app_subs:{app_id}:customer_id', customer_id)


def get_user_app_subscription_customer_id(app_id: str, uid: str) -> str:
    """Get the Stripe customer ID for a user's app subscription"""
    val = r.get(f'users:{uid}:app_subs:{app_id}:customer_id')
    if not val:
        return None
    return val.decode()


def enable_app(uid: str, app_id: str):
    r.sadd(f'users:{uid}:enabled_plugins', app_id)


def disable_app(uid: str, app_id: str):
    r.srem(f'users:{uid}:enabled_plugins', app_id)


def get_enabled_apps(uid: str):
    val = r.smembers(f'users:{uid}:enabled_plugins')
    if not val:
        return []
    return [x.decode() for x in val]


def get_app_reviews(app_id: str) -> dict:
    reviews = r.get(f'plugins:{app_id}:reviews')
    if not reviews:
        return {}
    return eval(reviews)


def get_apps_reviews(app_ids: list) -> dict:
    if not app_ids:
        return {}

    keys = [f'plugins:{app_id}:reviews' for app_id in app_ids]
    reviews = r.mget(keys)
    if reviews is None:
        return {}
    return {app_id: eval(review) if review else {} for app_id, review in zip(app_ids, reviews)}


def set_app_installs_count(app_id: str, count: int):
    r.set(f'plugins:{app_id}:installs', count)


def increase_app_installs_count(app_id: str):
    r.incr(f'plugins:{app_id}:installs')


def decrease_app_installs_count(app_id: str):
    r.decr(f'plugins:{app_id}:installs')


def get_app_installs_count(app_id: str) -> int:
    count = r.get(f'plugins:{app_id}:installs')
    if not count:
        return 0
    return int(count)


def get_apps_installs_count(app_ids: list) -> dict:
    if not app_ids:
        return {}

    keys = [f'plugins:{app_id}:installs' for app_id in app_ids]
    counts = r.mget(keys)
    if counts is None:
        return {}
    return {app_id: int(count) if count else 0 for app_id, count in zip(app_ids, counts)}


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


# TODO: cache memories if speed improves dramatically
def cache_memories(uid: str, memories: List[dict]):
    r.set(f'users:{uid}:facts', str(memories))
    r.expire(f'users:{uid}:facts', 60 * 60)  # 1 hour, most people chat during a few minutes


def get_cached_memories(uid: str) -> List[dict]:
    memories = r.get(f'users:{uid}:facts')
    if not memories:
        return []
    return eval(memories)


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


# VISIIBILTIY OF CONVERSATIONS
def store_conversation_to_uid(conversation_id: str, uid: str):
    r.set(f'memories-visibility:{conversation_id}', uid)


def remove_conversation_to_uid(conversation_id: str):
    r.delete(f'memories-visibility:{conversation_id}')


def get_conversation_uid(conversation_id: str) -> str:
    uid = r.get(f'memories-visibility:{conversation_id}')
    if not uid:
        return ''
    return uid.decode()


def get_conversation_uids(conversation_ids: list) -> dict:
    if not conversation_ids:
        return {}

    conversation_keys = [f'memories-visibility:{conversation_id}' for conversation_id in conversation_ids]
    uids = r.mget(conversation_keys)
    if uids is None:
        return {}
    conversation_uids = {}
    for conversation_id, uid in zip(conversation_ids, uids):
        if uid:
            conversation_uids[conversation_id] = uid.decode()
    return conversation_uids


def add_public_conversation(conversation_id: str):
    r.sadd('public-memories', conversation_id)


def remove_public_conversation(conversation_id: str):
    r.srem('public-memories', conversation_id)


def get_public_conversations() -> List[str]:
    val = r.smembers('public-memories')
    if not val:
        return []
    return [x.decode() for x in val]


def set_in_progress_conversation_id(uid: str, conversation_id: str, ttl: int = 300):
    r.set(f'users:{uid}:in_progress_memory_id', conversation_id)
    r.expire(f'users:{uid}:in_progress_memory_id', ttl)


def remove_in_progress_conversation_id(uid: str):
    r.delete(f'users:{uid}:in_progress_memory_id')


def get_in_progress_conversation_id(uid: str) -> str:
    conversation_id = r.get(f'users:{uid}:in_progress_memory_id')
    if not conversation_id:
        return ''
    return conversation_id.decode()


def set_conversation_meeting_id(conversation_id: str, meeting_id: str, ttl: int = 86400):
    """Store the meeting_id for a conversation. TTL defaults to 24 hours."""
    r.set(f'conversation:{conversation_id}:meeting_id', meeting_id)
    r.expire(f'conversation:{conversation_id}:meeting_id', ttl)


def get_conversation_meeting_id(conversation_id: str) -> Optional[str]:
    """Retrieve the meeting_id associated with a conversation."""
    meeting_id = r.get(f'conversation:{conversation_id}:meeting_id')
    if not meeting_id:
        return None
    return meeting_id.decode()


def remove_conversation_meeting_id(conversation_id: str):
    """Remove the meeting_id association for a conversation."""
    r.delete(f'conversation:{conversation_id}:meeting_id')


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


def get_filter_category_items(uid: str, category: str, limit: Optional[int] = None) -> List[str]:
    key = f'users:{uid}:filters:{category}'
    if limit:
        # Get random sample if limit specified
        val = r.srandmember(key, limit)
    else:
        # Get all items (existing behavior)
        val = r.smembers(key)

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


def save_migrated_retrieval_conversation_id(conversation_id: str):
    r.sadd('migrated_retrieval_memory_ids', conversation_id)
    r.expire('migrated_retrieval_memory_ids', 60 * 60 * 24 * 7)


def set_proactive_noti_sent_at(uid: str, app_id: str, ts: int, ttl: int = 30):
    r.set(f'{uid}:{app_id}:proactive_noti_sent_at', ts, ex=ttl)


def get_proactive_noti_sent_at(uid: str, app_id: str):
    val = r.get(f'{uid}:{app_id}:proactive_noti_sent_at')
    if not val:
        return None
    return int(val)


def get_proactive_noti_sent_at_ttl(uid: str, app_id: str):
    return r.ttl(f'{uid}:{app_id}:proactive_noti_sent_at')


def set_user_preferred_app(uid: str, app_id: str):
    """Stores the user's preferred app ID."""
    key = f'user:{uid}:preferred_app'
    r.set(key, app_id)


def get_user_preferred_app(uid: str) -> Optional[str]:
    """Retrieves the user's preferred app ID, if set."""
    key = f'user:{uid}:preferred_app'
    app_id = r.get(key)
    return app_id.decode() if app_id else None


@try_catch_decorator
def set_user_data_protection_level(uid: str, level: str):
    """Caches the user's data protection level."""
    key = f'user:{uid}:data_protection_level'
    r.set(key, level)


@try_catch_decorator
def get_user_data_protection_level(uid: str) -> Optional[str]:
    """Retrieves the user's cached data protection level."""
    key = f'user:{uid}:data_protection_level'
    level = r.get(key)
    return level.decode() if level else None


# ******************************************************
# ******************* MCP API KEYS *********************
# ******************************************************


@try_catch_decorator
def cache_mcp_api_key(hashed_key: str, user_id: str, ttl: int = 3600):
    """Caches the user_id for a given hashed MCP API key."""
    r.set(f'mcp_api_key:{hashed_key}', user_id, ex=ttl)


@try_catch_decorator
def get_cached_mcp_api_key_user_id(hashed_key: str) -> Optional[str]:
    """Retrieves the user_id for a given hashed MCP API key from cache."""
    user_id = r.get(f'mcp_api_key:{hashed_key}')
    return user_id.decode() if user_id else None


@try_catch_decorator
def delete_cached_mcp_api_key(hashed_key: str):
    """Deletes a cached MCP API key."""
    r.delete(f'mcp_api_key:{hashed_key}')


# ******************************************************
# ****************** DEV API KEYS **********************
# ******************************************************


def cache_dev_api_key(hashed_key: str, user_id: str, scopes: Optional[List[str]] = None, ttl: int = 3600):
    """Caches the user_id and scopes for a given hashed Developer API key."""
    cache_data = {"user_id": user_id, "scopes": scopes}
    r.set(f'dev_api_key:{hashed_key}', json.dumps(cache_data), ex=ttl)


@try_catch_decorator
def get_cached_dev_api_key_user_id(hashed_key: str) -> Optional[str]:
    """Retrieves the user_id for a given hashed Developer API key from cache."""
    cached = r.get(f'dev_api_key:{hashed_key}')
    if not cached:
        return None
    data = json.loads(cached.decode())
    return data.get("user_id")


@try_catch_decorator
def get_cached_dev_api_key_data(hashed_key: str) -> Optional[dict]:
    """Retrieves the user_id and scopes for a given hashed Developer API key from cache."""
    cached = r.get(f'dev_api_key:{hashed_key}')
    if not cached:
        return None
    return json.loads(cached.decode())


@try_catch_decorator
def delete_cached_dev_api_key(hashed_key: str):
    """Deletes a cached Developer API key."""
    r.delete(f'dev_api_key:{hashed_key}')


# ******************************************************
# **************** DATA MIGRATION STATUS ***************
# ******************************************************


def set_migration_status(uid: str, status: str, processed: int = None, total: int = None, error: str = None):
    key = f"migration_status:{uid}"
    data = {"status": status}
    if processed is not None:
        data["processed"] = processed
    if total is not None:
        data["total"] = total
    if error is not None:
        data["error"] = error

    r.set(key, json.dumps(data), ex=3600)  # Expire after 1 hour


def get_migration_status(uid: str) -> dict:
    key = f"migration_status:{uid}"
    data = r.get(key)
    if data:
        status_data = json.loads(data)
        # If complete or failed, keep the status for a short time so the UI can fetch it.
        if status_data.get('status') in ['complete', 'failed']:
            r.expire(key, 60)  # Keep it for 1 minute
        return status_data
    return {"status": "idle"}


@try_catch_decorator
def clear_migration_status(uid: str):
    """Clear the migration status for a user."""
    r.delete(f'migration_status:{uid}')


# ******************************************************
# ******************* AUTH SESSION *********************
# ******************************************************


@try_catch_decorator
def set_auth_session(session_id: str, session_data: dict, ttl: int = 600):
    """Store auth session data with expiration (default 10 minutes)"""
    r.set(f'auth_session:{session_id}', json.dumps(session_data), ex=ttl)


@try_catch_decorator
def get_auth_session(session_id: str) -> dict:
    """Retrieve auth session data"""
    data = r.get(f'auth_session:{session_id}')
    return json.loads(data.decode('utf-8')) if data else None


@try_catch_decorator
def set_auth_code(auth_code: str, firebase_token: str, ttl: int = 300):
    """Store auth code with Firebase token (default 5 minutes)"""
    r.set(f'auth_code:{auth_code}', firebase_token, ex=ttl)


@try_catch_decorator
def get_auth_code(auth_code: str) -> str:
    """Retrieve Firebase token by auth code"""
    token = r.get(f'auth_code:{auth_code}')
    return token.decode('utf-8') if token else None


@try_catch_decorator
def delete_auth_code(auth_code: str):
    """Delete used auth code"""
    r.delete(f'auth_code:{auth_code}')


# ******************************************************
# ************** CREDIT LIMIT NOTIFICATIONS ************
# ******************************************************


def set_credit_limit_notification_sent(uid: str, ttl: int = 60 * 60 * 24):
    """Cache that credit limit notification was sent to user (24 hours TTL by default)"""
    r.set(f'users:{uid}:credit_limit_notification_sent', '1', ex=ttl)


def has_credit_limit_notification_been_sent(uid: str) -> bool:
    """Check if credit limit notification was already sent to user recently"""
    return r.exists(f'users:{uid}:credit_limit_notification_sent')


def set_silent_user_notification_sent(uid: str, ttl: int = 60 * 60 * 24):
    """Cache that silent user notification was sent to user (24 hours TTL by default)"""
    r.set(f'users:{uid}:silent_notification_sent', '1', ex=ttl)


def has_silent_user_notification_been_sent(uid: str) -> bool:
    """Check if silent user notification was already sent to user recently"""
    return r.exists(f'users:{uid}:silent_notification_sent')


# ******************************************************
# ******** CONVERSATION SUMMARY APP IDS ****************
# ******************************************************

CONVERSATION_SUMMARY_APPS_KEY = 'conversation_summary_app_ids'


@try_catch_decorator
def get_conversation_summary_app_ids() -> List[str]:
    """Get list of conversation summary app IDs from Redis"""
    app_ids = r.smembers(CONVERSATION_SUMMARY_APPS_KEY)
    return [app_id.decode('utf-8') if isinstance(app_id, bytes) else app_id for app_id in app_ids] if app_ids else []


@try_catch_decorator
def add_conversation_summary_app_id(app_id: str) -> bool:
    """Add an app ID to the conversation summary apps set"""
    result = r.sadd(CONVERSATION_SUMMARY_APPS_KEY, app_id)
    return result > 0


@try_catch_decorator
def remove_conversation_summary_app_id(app_id: str) -> bool:
    """Remove an app ID from the conversation summary apps set"""
    result = r.srem(CONVERSATION_SUMMARY_APPS_KEY, app_id)
    return result > 0


# ******************************************************
# *************** LISTEN RATE LIMIT ********************
# ******************************************************


def try_acquire_listen_lock(uid: str, ttl: int = 7) -> bool:
    """Atomically try to acquire listen rate limit lock. Returns True if acquired (not rate limited), False if already rate limited."""
    result = r.set(f'users:{uid}:listen_rate_limit', '1', ex=ttl, nx=True)
    return result is not None


def set_persona_update_timestamp(uid: str):
    """Mark that user has updated personas (expires at 00:00 UTC)"""
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    ttl = int((tomorrow - now).total_seconds())
    r.set(f'users:{uid}:persona_updated', '1', ex=ttl)


def can_update_persona(uid: str) -> bool:
    """Check if user can update personas (not updated since last 00:00 UTC)"""
    return not r.exists(f'users:{uid}:persona_updated')


# ******************************************************
# *************** SPEECH PROFILE CACHE *****************
# ******************************************************


@try_catch_decorator
def set_speech_profile_duration(uid: str, duration: float):
    """Cache speech profile duration (write-ahead on upload)"""
    r.set(f'users:{uid}:speech_profile_duration', str(duration))


@try_catch_decorator
def get_speech_profile_duration(uid: str) -> Optional[float]:
    """Get cached speech profile duration"""
    val = r.get(f'users:{uid}:speech_profile_duration')
    if val:
        return float(val.decode())
    return None


@try_catch_decorator
def delete_speech_profile_duration(uid: str):
    """Delete cached speech profile duration"""
    r.delete(f'users:{uid}:speech_profile_duration')


# ******************************************************
# ************ DAILY SUMMARY NOTIFICATIONS *************
# ******************************************************


def set_daily_summary_sent(uid: str, date: str, ttl: int = 60 * 60 * 2):
    """
    Mark that a daily summary was sent to user for a specific date.
    Default TTL is 2 hours to prevent duplicate sends within the same hour window.

    Args:
        uid: User ID
        date: Date string in YYYY-MM-DD format
        ttl: Time to live in seconds (default: 2 hours)
    """
    r.set(f'users:{uid}:daily_summary_sent:{date}', '1', ex=ttl)


def has_daily_summary_been_sent(uid: str, date: str) -> bool:
    """
    Check if daily summary was already sent to user for a specific date.

    Args:
        uid: User ID
        date: Date string in YYYY-MM-DD format

    Returns:
        True if summary was already sent for this date, False otherwise
    """
    return r.exists(f'users:{uid}:daily_summary_sent:{date}')
