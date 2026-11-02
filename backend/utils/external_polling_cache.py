"""Opt-in developer polling policy; no plaintext identity leaves the process."""

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any

from utils.observability.fallback import record_fallback

NORMAL_TTL = 10
NEGATIVE_TTL = 10

# Server time and one atomic update keep classification consistent across hosts.
# Two distinct, sub-minute intervals are required; concurrent fan-out (<1s)
# cannot turn an ordinary client into a poller. A gap >=60s immediately resets.
CADENCE_SCRIPT = """
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local old = redis.call('GET', KEYS[1])
local streak = 0
if old then
    local split = string.find(old, ',')
    local last = tonumber(string.sub(old, 1, split - 1))
    streak = tonumber(string.sub(old, split + 1))
    local gap = now - last
    if gap < 1 then
        if streak >= 10 then return 300 end
        if streak >= 5 then return 120 end
        if streak >= 2 then return 60 end
        return 10
    end
    if gap < 60 then streak = math.min(10, streak + 1) else streak = 0 end
end
redis.call('SET', KEYS[1], tostring(now) .. ',' .. tostring(streak), 'EX', 120)
if streak >= 10 then return 300 end
if streak >= 5 then return 120 end
if streak >= 2 then return 60 end
return 10
"""


def identity(request: Any, uid: str, context: Any) -> str:
    # Never retain or log the credential, owner, app or key outside this digest.
    raw = [
        uid,
        getattr(context, 'app_id', None),
        getattr(context, 'key_id', None),
        request.headers.get('authorization', ''),
    ]
    if any(value is not None and not isinstance(value, str) for value in raw):
        raise ValueError('unsupported cache identity')
    return hashlib.sha256(json.dumps(raw, separators=(',', ':')).encode()).hexdigest()


def rollout_percent() -> int:
    if os.getenv('OMI_EXTERNAL_LIST_CACHE_ENABLED', '').strip().lower() == 'false':
        return 0
    if os.getenv('OMI_EXTERNAL_LIST_POLLING_CACHE_ENABLED', 'false').strip().lower() != 'true':
        return 0
    try:
        percent = int(os.getenv('OMI_EXTERNAL_LIST_POLLING_CACHE_PERCENT', '0'))
    except ValueError:
        return 0
    return percent if 0 <= percent <= 100 else 0


def enabled(digest: str) -> bool:
    percent = rollout_percent()
    return percent > 0 and int(digest[:8], 16) % 100 < percent


def adaptive_ttl(client: Any, request: Any, uid: str, context: Any, query: dict | None = None) -> int:
    if rollout_percent() == 0:
        return NORMAL_TTL
    try:
        route = request.url.path
        if route not in {'/v1/dev/user/conversations', '/v1/dev/user/memories'}:
            return NORMAL_TTL
        if query and query.get('cursor') is not None:
            return NORMAL_TTL  # Cursor expiry remains owned by the original reader.
        digest = identity(request, uid, context)
    except Exception:
        return NORMAL_TTL  # Unusable metadata can never break the source route.
    if not enabled(digest):
        return NORMAL_TTL
    # Paging/filter fan-out is not evidence that one query is being polled.
    raw = json.dumps([digest, route, query], sort_keys=True, separators=(',', ':'), default=str)
    key = 'external-poll:v1:' + hashlib.sha256(raw.encode()).hexdigest()
    try:
        ttl = int(client.eval(CADENCE_SCRIPT, 1, key))
        return ttl if ttl in {10, 60, 120, 300} else NORMAL_TTL
    except Exception:
        record_fallback(
            component='redis_cache', from_mode='poll_cadence', to_mode='none', reason='other', outcome='recovered'
        )
        return NORMAL_TTL


@dataclass(frozen=True)
class NegativeEntry:
    key: str
    expires_at: float


def negative_key(request: Any, uid: str, context: Any, item_id: str) -> NegativeEntry | None:
    if request is None or rollout_percent() == 0:
        return None
    try:
        digest = identity(request, uid, context)
        if not enabled(digest):
            return None
        # Route templates prevent raw item IDs from appearing in Redis key names.
        raw = [digest, getattr(request.scope.get('route'), 'path', request.url.path), item_id]
        key = 'external-missing:v1:' + hashlib.sha256(json.dumps(raw).encode()).hexdigest()
    except Exception:
        return None
    return NegativeEntry(key, time.time() + NEGATIVE_TTL)


def missing(client: Any, entry: NegativeEntry | None) -> bool:
    if entry is None:
        return False
    try:
        raw = client.get(entry.key)
        return raw is not None and time.time() < float(raw) <= entry.expires_at
    except Exception:
        return False


def remember_missing(client: Any, entry: NegativeEntry | None) -> None:
    if entry is not None:
        try:
            remaining_ms = int(1000 * (entry.expires_at - time.time()))
            if remaining_ms > 0:
                client.set(entry.key, str(entry.expires_at).encode(), px=remaining_ms)
        except Exception:
            pass  # Origin 404 is unchanged; an outage never becomes a cache hit.
