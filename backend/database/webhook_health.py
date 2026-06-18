import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from database._client import db
from database.redis_db import r

logger = logging.getLogger(__name__)

_HEALTH_TTL = 7 * 86400  # 7 days
_CACHE_TTL = 60  # seconds — in-memory cache for disabled checks
_SUCCESS_DEBOUNCE = 60  # seconds — min interval between success writes per app
_CACHE_MAX_SIZE = 10000

ENDPOINT_REALTIME = 'realtime'
ENDPOINT_CHAT_TOOL = 'chat_tool'
ENDPOINT_MCP_TOOL = 'mcp_tool'
_ALL_ENDPOINTS = [ENDPOINT_REALTIME, ENDPOINT_CHAT_TOOL, ENDPOINT_MCP_TOOL]

_cache_lock = threading.Lock()
_disabled_cache: dict[str, tuple[bool, float, int]] = {}  # (value, timestamp, generation)


def _evict_oldest(d: dict):
    """Drop the oldest 20% of entries by timestamp. Caller must hold _cache_lock."""
    n = len(d) // 5
    if n < 1:
        n = 1
    if d and isinstance(next(iter(d.values())), tuple):
        oldest = sorted(d, key=lambda k: d[k][1])[:n]
    else:
        oldest = sorted(d, key=lambda k: d[k])[:n]
    for k in oldest:
        del d[k]


# Lua script: atomically record a failure and return graduated response action.
# Returns: 0 = no action, 1 = day1 warn, 2 = day2 warn, 3 = disable
_RECORD_FAILURE_LUA = """
local key = KEYS[1]
local now_ts = tonumber(ARGV[1])
local status = ARGV[2]
local error_msg = ARGV[3]
local ttl = tonumber(ARGV[4])

local first = redis.call('HGET', key, 'first_failure_at')
if not first or first == '' then
    redis.call('HSET', key,
        'first_failure_at', now_ts,
        'last_failure_at', now_ts,
        'last_success_at', '',
        'failure_count', 1,
        'last_status', status,
        'last_error', error_msg,
        'notified_day1', '0',
        'notified_day2', '0',
        'disabled', '0')
    redis.call('EXPIRE', key, ttl)
    return 0
end

local first_ts = tonumber(first)
local last_success = redis.call('HGET', key, 'last_success_at')
if last_success and last_success ~= '' then
    local last_success_ts = tonumber(last_success)
    if last_success_ts and last_success_ts >= first_ts then
        redis.call('HSET', key,
            'first_failure_at', now_ts,
            'last_failure_at', now_ts,
            'last_success_at', '',
            'failure_count', 1,
            'last_status', status,
            'last_error', error_msg,
            'notified_day1', '0',
            'notified_day2', '0',
            'disabled', '0')
        redis.call('EXPIRE', key, ttl)
        return 0
    end
end

redis.call('HSET', key,
    'last_failure_at', now_ts,
    'last_status', status,
    'last_error', error_msg)
redis.call('HINCRBY', key, 'failure_count', 1)
redis.call('EXPIRE', key, ttl)

local elapsed = now_ts - first_ts

if elapsed >= 259200 then
    local disabled = redis.call('HGET', key, 'disabled')
    if disabled ~= '1' then
        redis.call('HSET', key, 'disabled', '1')
        return 3
    end
    return 0
end

if elapsed >= 172800 then
    local notified = redis.call('HGET', key, 'notified_day2')
    if notified ~= '1' then
        redis.call('HSET', key, 'notified_day2', '1')
        return 2
    end
    return 0
end

if elapsed >= 86400 then
    local notified = redis.call('HGET', key, 'notified_day1')
    if notified ~= '1' then
        redis.call('HSET', key, 'notified_day1', '1')
        return 1
    end
end

return 0
"""

_record_failure_script = None


def _get_failure_script():
    global _record_failure_script
    if _record_failure_script is None:
        _record_failure_script = r.register_script(_RECORD_FAILURE_LUA)
    return _record_failure_script


def record_app_webhook_failure(app_id: str, status_code: int, error: str, endpoint: str = ENDPOINT_REALTIME) -> int:
    """Record a webhook failure for a marketplace app endpoint.

    Returns graduated response action:
    0 = no action, 1 = day1 warn, 2 = day2 warn, 3 = auto-disable
    """
    try:
        key = f'app_webhook_health:{app_id}:{endpoint}'
        now_ts = int(time.time())
        script = _get_failure_script()
        action = int(script(keys=[key], args=[now_ts, str(status_code), error[:200], _HEALTH_TTL]))
        if action == 3:
            r.setex(f'app_webhook_disabled:{app_id}', _HEALTH_TTL, '1')
            with _cache_lock:
                gen = _disabled_cache.get(app_id, (False, 0, 0))[2] + 1
                _disabled_cache[app_id] = (True, time.monotonic(), gen)
        return action
    except Exception as e:
        logger.warning(f'record_app_webhook_failure redis error app_id={app_id}: {e}')
        return 0


# Lua script: atomically record success with debounce and recovery detection.
# Returns: 1 = written, 0 = debounced (skipped)
_RECORD_SUCCESS_LUA = """
local key = KEYS[1]
local now_ts = tonumber(ARGV[1])
local debounce_secs = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])

local first_failure = redis.call('HGET', key, 'first_failure_at')
local last_success = redis.call('HGET', key, 'last_success_at')

if first_failure and first_failure ~= '' then
    local ff = tonumber(first_failure)
    local ls = (last_success and last_success ~= '') and tonumber(last_success) or 0
    if ff >= ls then
        redis.call('HSET', key, 'last_success_at', now_ts)
        redis.call('EXPIRE', key, ttl)
        return 1
    end
end

if last_success and last_success ~= '' then
    local ls = tonumber(last_success)
    if ls and (now_ts - ls) < debounce_secs then
        return 0
    end
end

redis.call('HSET', key, 'last_success_at', now_ts)
redis.call('EXPIRE', key, ttl)
return 1
"""

_record_success_script = None


def _get_success_script():
    global _record_success_script
    if _record_success_script is None:
        _record_success_script = r.register_script(_RECORD_SUCCESS_LUA)
    return _record_success_script


def record_app_webhook_success(app_id: str, endpoint: str = ENDPOINT_REALTIME):
    """Record a successful webhook delivery for a specific endpoint. Debounced atomically in Redis.

    Uses a Lua script that bypasses debounce when a failure exists without a newer
    success (recovery case). Works correctly across multiple pods.
    """
    try:
        key = f'app_webhook_health:{app_id}:{endpoint}'
        now_ts = int(time.time())
        script = _get_success_script()
        script(keys=[key], args=[now_ts, _SUCCESS_DEBOUNCE, _HEALTH_TTL])
    except Exception as e:
        logger.warning(f'record_app_webhook_success redis error app_id={app_id}: {e}')


def clear_app_webhook_health(app_id: str):
    """Clear all webhook health state for an app. Used on re-enable."""
    with _cache_lock:
        gen = _disabled_cache.get(app_id, (False, 0, 0))[2] + 1
        _disabled_cache[app_id] = (False, time.monotonic(), gen)
    try:
        keys_to_delete = [f'app_webhook_disabled:{app_id}']
        for ep in _ALL_ENDPOINTS:
            keys_to_delete.append(f'app_webhook_health:{app_id}:{ep}')
        r.delete(*keys_to_delete)
    except Exception as e:
        logger.warning(f'clear_app_webhook_health redis error app_id={app_id}: {e}')


def is_app_webhook_disabled(app_id: str) -> bool:
    """Check if an app's webhook has been auto-disabled. Cached in-memory for 60s."""
    now = time.monotonic()
    with _cache_lock:
        cached = _disabled_cache.get(app_id)
        if cached is not None:
            value, ts, _gen = cached
            if (now - ts) < _CACHE_TTL:
                return value
        pre_gen = cached[2] if cached else 0
    try:
        key = f'app_webhook_disabled:{app_id}'
        val = r.get(key)
        result = val == b'1'
        with _cache_lock:
            cur = _disabled_cache.get(app_id)
            cur_gen = cur[2] if cur else 0
            if cur_gen == pre_gen:
                _disabled_cache[app_id] = (result, now, pre_gen)
                if len(_disabled_cache) > _CACHE_MAX_SIZE:
                    _evict_oldest(_disabled_cache)
        return result
    except Exception:
        return False


def get_app_webhook_health(app_id: str, endpoint: Optional[str] = None) -> Optional[dict]:
    """Get health state for an app's webhook endpoint(s). Returns None if no data."""
    try:
        if endpoint:
            key = f'app_webhook_health:{app_id}:{endpoint}'
            data = r.hgetall(key)
            if not data:
                return None
            return {k.decode(): v.decode() for k, v in data.items()}
        result = {}
        for ep in _ALL_ENDPOINTS:
            key = f'app_webhook_health:{app_id}:{ep}'
            data = r.hgetall(key)
            if data:
                result[ep] = {k.decode(): v.decode() for k, v in data.items()}
        return result if result else None
    except Exception:
        return None


def disable_app_in_firestore(app_id: str, error: str, failure_hours: int):
    """Mark an app as disabled in Firestore due to webhook failures."""
    with _cache_lock:
        gen = _disabled_cache.get(app_id, (False, 0, 0))[2] + 1
        _disabled_cache[app_id] = (True, time.monotonic(), gen)
    try:
        apps_collection = 'plugins_data'
        app_ref = db.collection(apps_collection).document(app_id)
        app_ref.update(
            {
                'disabled': True,
                'disabled_reason': 'webhook_failures',
                'disabled_at': datetime.now(timezone.utc).isoformat(),
                'disabled_error': error[:200],
                'disabled_failure_duration_hours': failure_hours,
            }
        )
        logger.info(f'Auto-disabled app {app_id} in Firestore after {failure_hours}h of webhook failures')
    except Exception as e:
        logger.error(f'Failed to disable app {app_id} in Firestore: {e}')


# --- Developer webhook health (per-user, per-type) ---

_DEV_FAILURE_THRESHOLD = 100

_DEV_RECORD_FAILURE_LUA = """
local key = KEYS[1]
local now_ts = ARGV[1]
local status = ARGV[2]
local error_msg = ARGV[3]
local ttl = tonumber(ARGV[4])
local threshold = tonumber(ARGV[5])

local already_disabled = redis.call('HGET', key, 'disabled')
if already_disabled == '1' then
    return 0
end

local count = redis.call('HINCRBY', key, 'failure_count', 1)
redis.call('HSET', key,
    'last_failure_at', now_ts,
    'last_status', status,
    'last_error', error_msg)
redis.call('EXPIRE', key, ttl)

if count >= threshold then
    redis.call('HSET', key, 'disabled', '1')
    return 1
end
return 0
"""

_dev_failure_script = None


def _get_dev_failure_script():
    global _dev_failure_script
    if _dev_failure_script is None:
        _dev_failure_script = r.register_script(_DEV_RECORD_FAILURE_LUA)
    return _dev_failure_script


def _record_dev_webhook_failure_fallback(uid: str, wtype_str: str, status_code: int, error: str) -> bool:
    """Non-Lua fallback for Redis clients without scripting (e.g. fakeredis in e2e).

    Keep this behavior equivalent to ``_DEV_RECORD_FAILURE_LUA``: once a webhook
    is already disabled, additional failures must not return True again because
    callers use the True transition to send the auto-disable notification.
    """
    key = f'dev_webhook_health:{uid}:{wtype_str}'
    already_disabled = r.hget(key, 'disabled')
    if isinstance(already_disabled, bytes):
        already_disabled = already_disabled.decode()
    if already_disabled == '1':
        return False

    try:
        count = int(r.hincrby(key, 'failure_count', 1))
    except Exception:
        current = r.hget(key, 'failure_count')
        if isinstance(current, bytes):
            current = current.decode()
        try:
            count = int(current or 0) + 1
        except (TypeError, ValueError):
            count = 1
        r.hset(key, 'failure_count', str(count))

    disabled = count >= _DEV_FAILURE_THRESHOLD
    r.hset(
        key,
        mapping={
            'last_failure_at': str(int(time.time())),
            'last_status': str(status_code),
            'last_error': error[:200],
        },
    )
    if disabled:
        r.hset(key, 'disabled', '1')
    r.expire(key, _HEALTH_TTL)
    return disabled


def record_dev_webhook_failure(uid: str, wtype: str, status_code: int, error: str) -> bool:
    """Record a developer webhook failure. Returns True if threshold exceeded (should disable)."""
    wtype_str = wtype.value if hasattr(wtype, 'value') else str(wtype)
    try:
        key = f'dev_webhook_health:{uid}:{wtype_str}'
        now_ts = int(time.time())
        script = _get_dev_failure_script()
        result = int(
            script(keys=[key], args=[now_ts, str(status_code), error[:200], _HEALTH_TTL, _DEV_FAILURE_THRESHOLD])
        )
        return result == 1
    except Exception as e:
        logger.warning(f'record_dev_webhook_failure redis error uid={uid} type={wtype}: {e}')
        # fakeredis and some constrained Redis-compatible stores do not support
        # the Lua script API used in production. Fall back to the same state
        # transition with ordinary commands so hermetic tests and degraded Redis
        # deployments still record failures instead of silently resetting health.
        try:
            return _record_dev_webhook_failure_fallback(uid, wtype_str, status_code, error)
        except Exception as fallback_error:
            logger.warning(
                f'record_dev_webhook_failure redis error uid={uid} type={wtype}: {e}; fallback={fallback_error}'
            )
            return False


def record_dev_webhook_success(uid: str, wtype: str):
    """Record a successful developer webhook delivery. Resets failure state."""
    try:
        wtype_str = wtype.value if hasattr(wtype, 'value') else str(wtype)
        key = f'dev_webhook_health:{uid}:{wtype_str}'
        now_ts = int(time.time())
        r.hset(
            key,
            mapping={
                'failure_count': '0',
                'last_failure_at': '',
                'last_success_at': str(now_ts),
                'last_status': '200',
                'last_error': '',
                'disabled': '0',
            },
        )
        r.expire(key, _HEALTH_TTL)
    except Exception as e:
        logger.warning(f'record_dev_webhook_success redis error uid={uid} type={wtype}: {e}')
