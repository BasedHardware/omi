"""Fail-closed shared relocation budgets and encrypted short-lived ASR index.

Quota keys are independent of audio fingerprints and receipt edits. Reservations
are atomic across a conversation and the fleet, consumed before provider/I/O
attempts, and never refunded after errors or cancellation.
"""

import hashlib
import json
from datetime import datetime, timezone
from functools import lru_cache

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry
from typing import Any

from database import redis_db
from utils import encryption

CONVERSATION_SECONDS_PER_DAY = 1800
CONVERSATION_DOWNLOADS_PER_DAY = 60
GLOBAL_SECONDS_PER_DAY = 18000
CACHE_SECONDS = 3600
_RESERVE = """
local seconds = tonumber(ARGV[1])
local downloads = tonumber(ARGV[2])
local used = tonumber(redis.call('HGET', KEYS[1], 'seconds') or '0')
local count = tonumber(redis.call('HGET', KEYS[1], 'downloads') or '0')
local global = tonumber(redis.call('GET', KEYS[2]) or '0')
if used + seconds > tonumber(ARGV[3]) or count + downloads > tonumber(ARGV[4])
   or global + seconds > tonumber(ARGV[5]) then return 0 end
redis.call('HINCRBY', KEYS[1], 'seconds', seconds)
redis.call('HINCRBY', KEYS[1], 'downloads', downloads)
redis.call('INCRBY', KEYS[2], seconds)
redis.call('EXPIRE', KEYS[1], 172800)
redis.call('EXPIRE', KEYS[2], 172800)
return 1
"""
_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""


@lru_cache(maxsize=1)
def _get_client():
    # The general Redis client has unbounded sockets. Relocation must not leave
    # cancelled background leaves holding DB workers indefinitely.
    options = dict(redis_db.r.connection_pool.connection_kwargs)
    options.update(socket_timeout=2, socket_connect_timeout=2, retry_on_timeout=False, retry=Retry(NoBackoff(), 0))
    return redis.Redis(connection_pool=redis.ConnectionPool(**options))


def identity(uid: str, conversation_id: str) -> str:
    return hashlib.sha256(json.dumps([uid, conversation_id]).encode()).hexdigest()


def reserve(uid: str, conversation_id: str, *, seconds: int = 0, downloads: int = 0) -> bool:
    if seconds < 0 or downloads < 0:
        raise ValueError('negative speaker location reservation')
    day = datetime.now(timezone.utc).strftime('%Y%m%d')
    return bool(
        _get_client().eval(
            _RESERVE,
            2,
            f'speaker_location:budget:{day}:{identity(uid, conversation_id)}',
            f'speaker_location:global:{day}',
            str(seconds),
            str(downloads),
            str(CONVERSATION_SECONDS_PER_DAY),
            str(CONVERSATION_DOWNLOADS_PER_DAY),
            str(GLOBAL_SECONDS_PER_DAY),
        )
    )


def acquire(uid: str, conversation_id: str, token: str) -> bool:
    return bool(_get_client().set(f'speaker_location:lock:{identity(uid, conversation_id)}', token, nx=True, ex=60))


def release(uid: str, conversation_id: str, token: str) -> None:
    _get_client().eval(_RELEASE, 1, f'speaker_location:lock:{identity(uid, conversation_id)}', token)


def read_index(uid: str, key: str) -> dict[str, Any]:
    raw = _get_client().get(f'speaker_location:index:{key}')
    if not raw:
        return {}
    if isinstance(raw, bytes):
        raw = raw.decode()
    if not isinstance(raw, str):
        raise ValueError('invalid speaker location ciphertext')
    result = json.loads(encryption.decrypt(raw, uid))
    if not isinstance(result, dict):
        raise ValueError('invalid speaker location index')
    return result


def write_index(uid: str, key: str, index: dict[str, Any]) -> None:
    raw = json.dumps(index)
    if len(raw.encode()) > 2_000_000:
        raise ValueError('speaker location index capacity exceeded')
    _get_client().set(f'speaker_location:index:{key}', encryption.encrypt(raw, uid), ex=CACHE_SECONDS)
