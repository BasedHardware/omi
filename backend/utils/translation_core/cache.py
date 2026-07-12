"""Single cache policy shared by whole-text and sentence translation."""

from __future__ import annotations

import json
import os
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, Protocol, cast

import redis
from redis.exceptions import RedisError

from config.translation import TranslationProfile
from utils.translation_core.metrics import TranslationMetrics


@dataclass(frozen=True)
class CachedTranslation:
    text: str
    detected_language: str = ''


class PersistentTranslationStore(Protocol):
    def get(self, fingerprint: str, target_language: str) -> CachedTranslation | None: ...

    def put(
        self,
        fingerprint: str,
        target_language: str,
        value: CachedTranslation,
        ttl_seconds: int,
    ) -> None: ...

    def is_negative(self, fingerprint: str, target_language: str) -> bool: ...

    def put_negative(self, fingerprint: str, target_language: str, ttl_seconds: int) -> None: ...


class RedisTranslationStore:
    """Lazy Redis adapter; importing translation never constructs a client."""

    def __init__(self, client_factory: Callable[[], Any] | None = None) -> None:
        self._client_factory = client_factory or _create_redis_client
        self._client: Any | None = None
        self._client_lock = Lock()

    def get(self, fingerprint: str, target_language: str) -> CachedTranslation | None:
        client = self._get_configured_client()
        if client is None:
            return None
        try:
            raw = client.get(_translation_key(fingerprint, target_language))
        except RedisError:
            return None
        if raw is None:
            return None
        try:
            decoded = raw.decode('utf-8') if isinstance(raw, bytes) else str(raw)
            value: object = json.loads(decoded)
        except (UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(value, dict):
            return None
        payload = cast(dict[object, object], value)
        text = payload.get('text')
        detected_language = payload.get('detected_lang', '')
        if not isinstance(text, str) or not text.strip() or not isinstance(detected_language, str):
            return None
        return CachedTranslation(text=text, detected_language=detected_language)

    def put(
        self,
        fingerprint: str,
        target_language: str,
        value: CachedTranslation,
        ttl_seconds: int,
    ) -> None:
        if not value.text.strip():
            return
        client = self._get_configured_client()
        if client is None:
            return
        encoded = json.dumps({'text': value.text, 'detected_lang': value.detected_language})
        try:
            client.set(
                _translation_key(fingerprint, target_language),
                encoded,
                ex=ttl_seconds,
            )
        except RedisError:
            return None

    def is_negative(self, fingerprint: str, target_language: str) -> bool:
        client = self._get_configured_client()
        if client is None:
            return False
        try:
            return bool(client.exists(_negative_key(fingerprint, target_language)))
        except RedisError:
            return False

    def put_negative(self, fingerprint: str, target_language: str, ttl_seconds: int) -> None:
        client = self._get_configured_client()
        if client is None:
            return
        try:
            client.set(
                _negative_key(fingerprint, target_language),
                '1',
                ex=ttl_seconds,
            )
        except RedisError:
            return None

    def _get_configured_client(self) -> Any | None:
        try:
            return self._get_client()
        except (ValueError, TypeError):
            return None

    def _get_client(self) -> Any:
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = self._client_factory()
        return self._client


class TranslationCache:
    """Bounded in-memory LRU backed by an optional persistent store."""

    def __init__(
        self,
        persistent: PersistentTranslationStore | None,
        metrics: TranslationMetrics,
        max_entries: int = 1000,
    ) -> None:
        self._persistent = persistent
        self._metrics = metrics
        self._max_entries = max_entries
        self._memory: OrderedDict[str, CachedTranslation] = OrderedDict()
        self._memory_lock = Lock()

    def get(self, fingerprint: str, target_language: str) -> CachedTranslation | None:
        key = _memory_key(fingerprint, target_language)
        with self._memory_lock:
            memory_value = self._memory.pop(key, None)
            if memory_value is not None:
                self._memory[key] = memory_value
        if memory_value is not None:
            self._metrics.cache('memory', 'hit')
            return memory_value
        self._metrics.cache('memory', 'miss')

        if self._persistent is None:
            return None
        persistent_value = self._persistent.get(fingerprint, target_language)
        self._metrics.cache('redis', 'hit' if persistent_value is not None else 'miss')
        if persistent_value is not None:
            self._put_memory(key, persistent_value)
        return persistent_value

    def put(
        self,
        fingerprint: str,
        target_language: str,
        value: CachedTranslation,
        profile: TranslationProfile,
    ) -> None:
        if not value.text.strip():
            return
        self._put_memory(_memory_key(fingerprint, target_language), value)
        if self._persistent is not None:
            self._persistent.put(fingerprint, target_language, value, profile.cache_ttl_seconds)

    def is_negative(self, fingerprint: str, target_language: str) -> bool:
        if self._persistent is None:
            return False
        found = self._persistent.is_negative(fingerprint, target_language)
        self._metrics.cache('negative', 'hit' if found else 'miss')
        return found

    def put_negative(self, fingerprint: str, target_language: str, profile: TranslationProfile) -> None:
        if self._persistent is not None:
            self._persistent.put_negative(fingerprint, target_language, profile.negative_cache_ttl_seconds)

    def _put_memory(self, key: str, value: CachedTranslation) -> None:
        with self._memory_lock:
            self._memory.pop(key, None)
            self._memory[key] = value
            while len(self._memory) > self._max_entries:
                self._memory.popitem(last=False)


_default_store: RedisTranslationStore | None = None
_default_store_lock = Lock()


def get_default_translation_store() -> RedisTranslationStore:
    """Return the process-scoped lazy Redis adapter shared by all sessions."""
    global _default_store
    if _default_store is None:
        with _default_store_lock:
            if _default_store is None:
                _default_store = RedisTranslationStore()
    return _default_store


def _create_redis_client() -> Any:
    host = os.getenv('REDIS_DB_HOST')
    port_raw = os.getenv('REDIS_DB_PORT')
    return redis.Redis(
        host=cast(str, host),
        port=int(port_raw) if port_raw is not None else 6379,
        username='default',
        password=os.getenv('REDIS_DB_PASSWORD'),
        health_check_interval=30,
    )


def _translation_key(fingerprint: str, target_language: str) -> str:
    return f'translate:v1:{fingerprint}:{target_language}'


def _negative_key(fingerprint: str, target_language: str) -> str:
    return f'translate:v2:neg:{fingerprint}:{target_language}'


def _memory_key(fingerprint: str, target_language: str) -> str:
    return f'{fingerprint}:{target_language}'
