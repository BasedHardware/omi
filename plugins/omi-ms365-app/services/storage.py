"""Token store: Redis if REDIS_URL is set, else in-memory.

Stores the MSAL SerializableTokenCache JSON blob keyed by the OMI user id.
In-memory mode is only for local dev — tokens are lost on restart.
"""
from __future__ import annotations

import json
import logging
from typing import Protocol

import redis.asyncio as redis

from config import get_settings

log = logging.getLogger(__name__)

_KEY_PREFIX = "omi:ms365:cache:"


class TokenStore(Protocol):
    async def get(self, user_id: str) -> str | None: ...
    async def set(self, user_id: str, cache_blob: str) -> None: ...
    async def delete(self, user_id: str) -> None: ...


class InMemoryStore:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    async def get(self, user_id: str) -> str | None:
        return self._data.get(user_id)

    async def set(self, user_id: str, cache_blob: str) -> None:
        self._data[user_id] = cache_blob

    async def delete(self, user_id: str) -> None:
        self._data.pop(user_id, None)


class RedisStore:
    def __init__(self, url: str) -> None:
        self._client: redis.Redis = redis.from_url(url, decode_responses=True)

    async def get(self, user_id: str) -> str | None:
        return await self._client.get(_KEY_PREFIX + user_id)

    async def set(self, user_id: str, cache_blob: str) -> None:
        # 90 days TTL — refresh tokens are long-lived but rotate them periodically.
        await self._client.set(_KEY_PREFIX + user_id, cache_blob, ex=90 * 24 * 3600)

    async def delete(self, user_id: str) -> None:
        await self._client.delete(_KEY_PREFIX + user_id)


_store: TokenStore | None = None


def get_store() -> TokenStore:
    global _store
    if _store is not None:
        return _store
    settings = get_settings()
    if settings.redis_url:
        log.info("Using Redis token store")
        _store = RedisStore(settings.redis_url)
    else:
        log.warning("No REDIS_URL set — using in-memory token store (dev only)")
        _store = InMemoryStore()
    return _store
