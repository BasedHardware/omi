"""Bounded discovery metadata cache; never caches grants, selections or events.

Event reads still load current preferences and call Google for selected events.
Keying by owner, credential digest and selection digest prevents reuse across
accounts, refreshed/reconnected grants and saved scope changes in any worker.
"""

import hashlib
import json
import threading

from cachetools import TTLCache

CATALOG_TTL_SECONDS = 30
MAX_CACHED_CALENDARS = 20_000
Catalog = tuple[str, frozenset[str]]
Key = tuple[str, str, str]
_cache: TTLCache[Key, Catalog] = TTLCache(
    maxsize=MAX_CACHED_CALENDARS, ttl=CATALOG_TTL_SECONDS, getsizeof=lambda value: 1 + len(value[1])
)
_lock = threading.Lock()


def cache_key(uid: str, access_token: str, selections: dict) -> Key:
    def digest(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    return digest(uid), digest(access_token), digest(json.dumps(selections, sort_keys=True, separators=(',', ':')))


def get(key: Key) -> Catalog | None:
    with _lock:
        return _cache.get(key)


def put(key: Key, primary: str, readable: frozenset[str]) -> None:
    with _lock:
        if 1 + len(readable) > _cache.maxsize:
            return
        _cache[key] = (primary, readable)


def invalidate(uid: str) -> None:
    owner = hashlib.sha256(uid.encode()).hexdigest()
    with _lock:
        for key in list(_cache):
            if key[0] == owner:
                del _cache[key]
