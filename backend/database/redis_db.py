import base64
import json
import os
from typing import List, Union, Optional
from datetime import datetime, timedelta, timezone

import redis
import logging

logger = logging.getLogger(__name__)

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
            logger.error(f'Error calling {func.__name__} {e}')
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


def is_app_enabled(uid: str, app_id: str) -> bool:
    return r.sismember(f'users:{uid}:enabled_plugins', app_id)


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


def get_apps_installs_count(app_ids: list) -> dict:
    if not app_ids:
        return {}

    keys = [f'plugins:{app_id}:installs' for app_id in app_ids]
    counts = r.mget(keys)
    if counts is None:
        return {}
    return {app_id: int(count) if count else 0 for app_id, count in zip(app_ids, counts)}


def cache_user_name(uid: str, name: str, ttl: int = 60 * 60 * 24 * 7):
    r.set(f'users:{uid}:name', name)
    r.expire(f'users:{uid}:name', ttl)


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


def add_public_conversation(conversation_id: str):
    r.sadd('public-memories', conversation_id)


def remove_public_conversation(conversation_id: str):
    r.srem('public-memories', conversation_id)


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


@try_catch_decorator
def incr_daily_notification_count(uid: str) -> int:
    """Atomically increment the daily mentor notification count for a user. Returns new count."""
    from datetime import datetime, timezone

    key = f'{uid}:daily_noti_count:{datetime.now(timezone.utc).strftime("%Y-%m-%d")}'
    count = r.incr(key)
    r.expire(key, 90000)  # 25 hours TTL
    return count


@try_catch_decorator
def get_daily_notification_count(uid: str) -> int:
    """Get the current daily mentor notification count for a user."""
    from datetime import datetime, timezone

    key = f'{uid}:daily_noti_count:{datetime.now(timezone.utc).strftime("%Y-%m-%d")}'
    val = r.get(key)
    if not val:
        return 0
    return int(val)


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
# ******* IMPORTANT CONVERSATION NOTIFICATIONS *********
# ******************************************************


def set_important_conversation_notification_sent(uid: str, conversation_id: str):
    """Mark that important conversation notification was sent for this conversation (no expiry - one-time per conversation)"""
    r.set(f'users:{uid}:important_conv_notif:{conversation_id}', '1')


def has_important_conversation_notification_been_sent(uid: str, conversation_id: str) -> bool:
    """Check if important conversation notification was already sent for this conversation"""
    return r.exists(f'users:{uid}:important_conv_notif:{conversation_id}')


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
# *************** RATE LIMITING ************************
# ******************************************************

# Lua script: atomic increment + TTL in a single round-trip.
# Returns [current_count, ttl_remaining].  Sets TTL on first hit
# and self-heals any key that lost its TTL (prevents permanent buckets).
_RATE_LIMIT_LUA = r.register_script(
    """
local key = KEYS[1]
local window = tonumber(ARGV[1])
local current = redis.call('INCR', key)
if current == 1 then
    redis.call('EXPIRE', key, window)
end
local ttl = redis.call('TTL', key)
if ttl < 0 then
    redis.call('EXPIRE', key, window)
    ttl = window
end
return {current, ttl}
"""
)


def check_rate_limit(key: str, policy: str, max_requests: int, window: int) -> tuple[bool, int, int]:
    """Check per-key rate limit using a single atomic Lua call.

    Args:
        key: Rate limit subject (uid, ip, app_id:uid).
        policy: Policy name (used in Redis key namespace).
        max_requests: Maximum requests allowed in the window (after boost).
        window: Window size in seconds.

    Returns:
        (allowed, remaining, retry_after_seconds)
    """
    redis_key = f'rl:{policy}:{key}'
    current, ttl = _RATE_LIMIT_LUA(keys=[redis_key], args=[window])
    remaining = max(0, max_requests - current)
    allowed = current <= max_requests
    retry_after = max(0, ttl) if not allowed else 0
    return allowed, remaining, retry_after


# Atomic TTS rate-limit: burst (sliding-window ZSET) + daily char counter.
# Returns [status, retry_after_seconds]:
#   0 = allow, 1 = burst exceeded, 2 = daily char limit exceeded.
# Burst uses a sorted set keyed by timestamp-ms for sliding-window accuracy,
# trimmed on every call (O(log n)). Daily char counter auto-expires at midnight
# UTC (caller passes seconds_until_midnight_utc as the TTL).
_TTS_RATE_LIMIT_LUA = r.register_script(
    """
local burst_key = KEYS[1]
local daily_key = KEYS[2]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local burst_limit = tonumber(ARGV[3])
local char_count = tonumber(ARGV[4])
local daily_limit = tonumber(ARGV[5])
local daily_ttl = tonumber(ARGV[6])

redis.call('ZREMRANGEBYSCORE', burst_key, 0, now_ms - window_ms)
local burst_current = redis.call('ZCARD', burst_key)
if burst_current >= burst_limit then
    return {1, math.floor(window_ms / 1000)}
end

local daily_current = tonumber(redis.call('GET', daily_key) or '0')
if daily_current + char_count > daily_limit then
    return {2, daily_ttl}
end

redis.call('ZADD', burst_key, now_ms, now_ms .. ':' .. math.random())
redis.call('PEXPIRE', burst_key, window_ms)
local new_daily = redis.call('INCRBY', daily_key, char_count)
if new_daily == char_count then
    redis.call('EXPIRE', daily_key, daily_ttl)
end
return {0, 0}
"""
)


def _seconds_until_midnight_utc() -> int:
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((tomorrow - now).total_seconds()))


def check_tts_rate_limit(
    uid: str,
    char_count: int,
    burst_limit: int = 50,
    burst_window_secs: int = 60,
    daily_char_limit: int = 10_000,
) -> tuple[int, int]:
    """Atomic per-user TTS rate limit check.

    Returns (status, retry_after_seconds) where status is:
        0  — allow
        1  — burst window exceeded
        2  — daily character limit exceeded
       -1  — Redis error (fail-open: caller should allow the request)
    """
    try:
        burst_key = f'tts:burst:{uid}'
        today_utc = datetime.now(timezone.utc).strftime('%Y%m%d')
        daily_key = f'tts:chars:{uid}:{today_utc}'
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        window_ms = burst_window_secs * 1000
        daily_ttl = _seconds_until_midnight_utc()
        result = _TTS_RATE_LIMIT_LUA(
            keys=[burst_key, daily_key],
            args=[now_ms, window_ms, burst_limit, char_count, daily_char_limit, daily_ttl],
        )
        return int(result[0]), int(result[1])
    except Exception as e:
        logger.error(f'check_tts_rate_limit: redis error uid={uid}: {e}')
        return -1, 0


def try_acquire_listen_lock(uid: str, ttl: int = 7) -> bool:
    """Atomically try to acquire listen rate limit lock. Returns True if acquired (not rate limited), False if already rate limited."""
    result = r.set(f'users:{uid}:listen_rate_limit', '1', ex=ttl, nx=True)
    return result is not None


def try_acquire_user_platform_write_lock(uid: str, platform: str, ttl: int = 600) -> bool:
    """Return True once every `ttl` seconds per (uid, platform) to throttle
    `last_active_platform` writes on chatty endpoints. The platform is part of
    the key so switching platforms bypasses the throttle and records the
    change immediately.
    """
    try:
        result = r.set(f'users:{uid}:platform_write:{platform}', '1', ex=ttl, nx=True)
        return result is not None
    except Exception:
        # Fail-open: if Redis is down, let the caller write through. Firestore
        # merge is idempotent, so worst case we write more often than intended.
        return True


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


# ******************************************************
# ************ DAILY SUMMARY NOTIFICATIONS *************
# ******************************************************


# ******************************************************
# *************** TASK SHARING TOKENS ******************
# ******************************************************

TASK_SHARE_TTL = 60 * 60 * 24 * 30  # 30 days


@try_catch_decorator
def store_task_share(token: str, uid: str, display_name: str, task_ids: list):
    """Store a task share token in Redis with 30-day TTL."""
    data = json.dumps({"uid": uid, "display_name": display_name, "task_ids": task_ids})
    return r.set(f'task_share:{token}', data, ex=TASK_SHARE_TTL)


@try_catch_decorator
def get_task_share(token: str) -> Optional[dict]:
    """Get task share data by token. Returns None if expired or not found."""
    data = r.get(f'task_share:{token}')
    if data:
        return json.loads(data)
    return None


@try_catch_decorator
def try_accept_task_share(token: str, uid: str) -> bool:
    """Atomically mark a task share as accepted. Returns True on first acceptance, False if already accepted."""
    key = f'task_share:{token}:accepted'
    if r.sadd(key, uid) == 1:
        r.expire(key, TASK_SHARE_TTL)
        return True
    return False


def undo_accept_task_share(token: str, uid: str):
    """Rollback a task share acceptance (best-effort). Used when post-claim validation fails."""
    key = f'task_share:{token}:accepted'
    r.srem(key, uid)


CHAT_SHARE_TTL = 60 * 60 * 24 * 30  # 30 days


def store_chat_share(token: str, uid: str, display_name: str, message_ids: list):
    """Store a chat share token in Redis with 30-day TTL."""
    data = json.dumps({"uid": uid, "display_name": display_name, "message_ids": message_ids})
    return r.set(f'chat_share:{token}', data, ex=CHAT_SHARE_TTL)


@try_catch_decorator
def get_chat_share(token: str) -> Optional[dict]:
    """Get chat share data by token. Returns None if expired or not found."""
    data = r.get(f'chat_share:{token}')
    if data:
        return json.loads(data)
    return None


def try_acquire_daily_summary_lock(uid: str, date: str, ttl: int = 60 * 60 * 2) -> bool:
    """Atomically acquire lock BEFORE expensive LLM work. Returns True if acquired, False if another job instance already holds it."""
    result = r.set(f'users:{uid}:daily_summary_lock:{date}', '1', ex=ttl, nx=True)
    return result is not None


@try_catch_decorator
def set_credits_invalidation_signal(uid: str, ttl: int = 120):
    """Signal active WebSocket sessions to refresh credits immediately.

    Called when subscription changes (Stripe webhook, upgrade, etc.).
    Active transcribe loops check this on each 60s tick and force a Firestore refresh.
    TTL is 2 min — long enough for all streams to see it on their next 60s tick.
    Uses GET (not GETDEL) so multiple concurrent streams all see the signal.
    """
    r.set(f'credits_invalidated:{uid}', '1', ex=ttl)


@try_catch_decorator
def check_credits_invalidation(uid: str) -> bool:
    """Check if credits need immediate refresh.

    Returns True if invalidation signal is present (caller should refresh).
    Uses GET (not GETDEL) so all concurrent streams for the same user see the signal.
    The signal auto-expires via its TTL.
    """
    result = r.get(f'credits_invalidated:{uid}')
    return result is not None


# ******************************************************
# *************** GOAL RATE LIMITING *******************
# ******************************************************


def try_acquire_goal_extraction_lock(uid: str, ttl: int = 300) -> bool:
    """Per-user rate limit for goal extraction. Returns True if acquired (not rate limited)."""
    result = r.set(f'users:{uid}:goal_extraction_lock', '1', ex=ttl, nx=True)
    return result is not None


def try_acquire_conversation_goal_lock(uid: str, conversation_id: str, ttl: int = 3600) -> bool:
    """Idempotency lock: one goal extraction per conversation. Returns True if acquired."""
    result = r.set(f'users:{uid}:conv_goal_lock:{conversation_id}', '1', ex=ttl, nx=True)
    return result is not None
