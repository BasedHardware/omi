"""Redis generations and writer tickets for Developer action-item pages.

SDK installation lives in action_item_write_fence, keeping response-cache
imports independent of the Firestore SDK classes.
A random version cannot alias a cached page after expiry/eviction. Overlapping
writers keep the version busy until all have completed. Uncertain Redis replies
poison caching instead of publishing an unfenced version. Never stores task data.
"""

import functools
import hashlib
import logging
from uuid import uuid4
from typing import Any


from database.redis_connection import create_bounded_redis_client
from database.fsr_cache_telemetry import record_fallback

logger = logging.getLogger(__name__)
VERSION_TTL = 7 * 86400
BUSY = '!busy'
_READ = """
if redis.call('EXISTS', KEYS[2]) == 1 then return '!busy' end
local version = redis.call('GET', KEYS[1])
if not version then
    redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[2])
    return ARGV[1]
end
return version
"""
_BEGIN = """
redis.call('SET', KEYS[1], '!busy')
if redis.call('HGET', KEYS[2], 'poison') then return 0 end
redis.call('HSET', KEYS[2], ARGV[1], '1')
return 1
"""
_END = """
redis.call('SET', KEYS[1], '!busy')
if not redis.call('HGET', KEYS[2], ARGV[1]) or ARGV[2] ~= '1' then
    redis.call('HSET', KEYS[2], 'poison', '1')
end
redis.call('HDEL', KEYS[2], ARGV[1])
if redis.call('HLEN', KEYS[2]) == 0 then
    redis.call('SET', KEYS[1], ARGV[3], 'EX', ARGV[4])
end
"""


@functools.lru_cache(maxsize=1)
def _redis() -> Any:
    return create_bounded_redis_client(0.1)


def _key(uid: str) -> str:
    return 'external-action-items:v1:{' + hashlib.sha256(uid.encode()).hexdigest() + '}'


def _unavailable() -> None:
    record_fallback(
        component='redis_cache',
        from_mode='write_version',
        to_mode='uncached',
        reason='unavailable',
        outcome='degraded',
        log=logger,
    )


def version(uid: str) -> str | None:
    try:
        key = _key(uid)
        value = _redis().eval(_READ, 2, key, key + ':writers', uuid4().hex, VERSION_TTL)
        value = value.decode() if isinstance(value, bytes) else value
        return value if isinstance(value, str) and value and value != BUSY else None
    except Exception:
        _unavailable()
        return None


def begin(uid: str) -> tuple[str, bool]:
    token = uuid4().hex
    try:
        key = _key(uid)
        return token, _redis().eval(_BEGIN, 2, key, key + ':writers', token) == 1
    except Exception:
        _unavailable()
        return token, False


def finish(uid: str, ticket: tuple[str, bool]) -> None:
    try:
        key = _key(uid)
        _redis().eval(_END, 2, key, key + ':writers', ticket[0], int(ticket[1]), uuid4().hex, VERSION_TTL)
    except Exception:
        _unavailable()
