"""Bounded fleet STT evidence; Redis faults leave the process-local route usable."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Callable

import redis.asyncio as aioredis

from config.stt_provider_policy import MODULATE_SUPPORTED_LANGUAGES, PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL
from utils.stt.live_metrics import LEG_TRANSCRIPT_OUTCOME, ROUTING_DECISION

logger = logging.getLogger(__name__)

PROVIDERS = frozenset({'modulate', 'soniox', 'deepgram', 'parakeet'})
LANGUAGES = MODULATE_SUPPORTED_LANGUAGES | frozenset().union(*PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL.values())
SCORE_BUCKET_SECONDS = 300
SCORE_BUCKETS = 3
REDIS_DEADLINE_SECONDS = 0.075
LOCAL_EVENTS_CAP = 256
LOCAL_KEYS_CAP = 256
KEY_PREFIX = 'omi:live-stt:v1'


def mode() -> str:
    value = os.getenv('STT_ROUTING_MODE', 'off').strip().lower()
    return value if value in {'off', 'shadow', 'on'} else 'off'


def bounded_language(language: str | None) -> str:
    token = (language or '').strip().lower().split('-', 1)[0]
    return token if token in LANGUAGES else 'other'


def _timeout() -> float:
    try:
        return min(0.1, max(0.01, float(os.getenv('STT_ROUTING_REDIS_TIMEOUT_SECONDS', '0.075'))))
    except ValueError:
        return REDIS_DEADLINE_SECONDS


@dataclass(frozen=True)
class ProviderState:
    score: float = 0.5
    samples: int = 0
    bench: str | None = None
    bench_until: float = 0.0

    @property
    def excluded(self) -> bool:
        return self.bench is not None and self.bench_until > time.time()


class FleetHealth:
    def __init__(self, *, clock: Callable[[], float] = time.time, redis_client: Any = None) -> None:
        self._clock = clock
        self._client = redis_client
        self._lock = threading.RLock()
        self._local: dict[tuple[str, str], deque[tuple[float, bool]]] = defaultdict(deque)
        self._benches: dict[str, tuple[str, float]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._redis_retry_at = 0.0

    def _redis(self) -> Any:
        if self._client is None:
            self._client = aioredis.Redis(
                host=os.getenv('REDIS_DB_HOST') or 'localhost',
                port=int(os.getenv('REDIS_DB_PORT', '6379')),
                password=os.getenv('REDIS_DB_PASSWORD'),
                socket_connect_timeout=_timeout(),
                socket_timeout=_timeout(),
                retry_on_timeout=False,
                decode_responses=True,
            )
        return self._client

    async def _bounded(self, operation: Any) -> Any:
        return await asyncio.wait_for(operation, timeout=_timeout())

    def _score_keys(self, provider: str, language: str, bucket: int) -> tuple[str, str]:
        stem = f'{KEY_PREFIX}:score:{provider}:{language}:{bucket}'
        return stem + ':text', stem + ':no_text'

    def _local_score(self, provider: str, language: str) -> ProviderState:
        cutoff = self._clock() - SCORE_BUCKET_SECONDS * SCORE_BUCKETS
        with self._lock:
            events = self._local.get((provider, language), ())
            recent = [success for when, success in events if when >= cutoff]
            bench, until = self._benches.get(provider, ('', 0.0))
        return ProviderState((sum(recent) + 1) / (len(recent) + 2), len(recent), bench or None, until)

    def record(self, provider: str, language: str | None, outcome: str) -> None:
        if provider not in PROVIDERS or outcome not in {'text', 'no_text'}:
            return
        lang = bounded_language(language)
        try:
            LEG_TRANSCRIPT_OUTCOME.labels(provider=provider, language=lang, outcome=outcome).inc()
        except Exception:
            pass
        if mode() == 'off':
            return
        with self._lock:
            key = provider, lang
            if key not in self._local and len(self._local) >= LOCAL_KEYS_CAP:
                self._local.pop(next(iter(self._local)))
            events = self._local[key]
            events.append((self._clock(), outcome == 'text'))
            while len(events) > LOCAL_EVENTS_CAP:
                events.popleft()
        self.schedule(self._write_result(provider, lang, outcome))

    async def _write_result(self, provider: str, language: str, outcome: str) -> None:
        if self._clock() < self._redis_retry_at:
            return
        bucket = int(self._clock() // SCORE_BUCKET_SECONDS)
        text_key, no_text_key = self._score_keys(provider, language, bucket)
        key = text_key if outcome == 'text' else no_text_key
        try:
            clear_bench = False
            if outcome == 'text':
                raw = await self._bounded(self._redis().get(f'{KEY_PREFIX}:state:{provider}'))
                if raw:
                    try:
                        clear_bench = float(str(raw).split(':', 1)[1]) <= self._clock()
                    except (IndexError, ValueError):
                        clear_bench = False
            pipe = self._redis().pipeline(transaction=False)
            pipe.incr(key)
            pipe.expire(key, SCORE_BUCKET_SECONDS * (SCORE_BUCKETS + 1))
            if clear_bench:
                pipe.delete(f'{KEY_PREFIX}:state:{provider}', f'{KEY_PREFIX}:probe:{provider}')
            await self._bounded(pipe.execute())
        except Exception:
            self._redis_retry_at = self._clock() + 10.0
            logger.debug('STT fleet health write fell back to local state', exc_info=True)

    def schedule(self, coroutine: Any) -> None:
        if mode() == 'off':
            coroutine.close()
            return
        try:
            loop = asyncio.get_running_loop()
            self._loop = loop
            loop.create_task(coroutine)
        except RuntimeError:
            loop = self._loop
            if loop is None or loop.is_closed():
                coroutine.close()
                return
            loop.call_soon_threadsafe(loop.create_task, coroutine)

    def quarantine(self, provider: str, kind: str, seconds: float) -> None:
        if provider not in PROVIDERS or kind not in {'account', 'selection'} or mode() == 'off':
            return
        until = self._clock() + max(1.0, seconds)
        with self._lock:
            self._benches[provider] = kind, until
        self.schedule(self._write_bench(provider, kind, until))

    async def _write_bench(self, provider: str, kind: str, until: float) -> None:
        if self._clock() < self._redis_retry_at:
            return
        try:
            await self._bounded(
                self._redis().set(
                    f'{KEY_PREFIX}:state:{provider}',
                    f'{kind}:{until:.3f}',
                    ex=max(1, int(until - self._clock()) + 300),
                )
            )
        except Exception:
            self._redis_retry_at = self._clock() + 10.0
            logger.debug('STT fleet bench write fell back to local state', exc_info=True)

    async def snapshot(self, providers: list[str], language: str | None) -> dict[str, ProviderState]:
        providers = [provider for provider in providers if provider in PROVIDERS]
        lang = bounded_language(language)
        local = {provider: self._local_score(provider, lang) for provider in providers}
        if mode() == 'off' or not providers or self._clock() < self._redis_retry_at:
            return local
        self._loop = asyncio.get_running_loop()
        bucket = int(self._clock() // SCORE_BUCKET_SECONDS)
        keys: list[str] = []
        for provider in providers:
            for index in range(SCORE_BUCKETS):
                keys.extend(self._score_keys(provider, lang, bucket - index))
            keys.append(f'{KEY_PREFIX}:state:{provider}')
        try:
            values = await self._bounded(self._redis().mget(keys))
            if not isinstance(values, list) or len(values) != len(keys):
                raise ValueError('invalid fleet health read')
            result: dict[str, ProviderState] = {}
            cursor = 0
            for provider in providers:
                counts = [int(raw or 0) for raw in values[cursor : cursor + SCORE_BUCKETS * 2]]
                cursor += SCORE_BUCKETS * 2
                raw_state = values[cursor]
                cursor += 1
                successes = sum(counts[::2])
                failures = sum(counts[1::2])
                state = str(raw_state or '').split(':', 1)
                kind = state[0] if len(state) == 2 and state[0] in {'account', 'selection'} else None
                until = float(state[1]) if kind else 0.0
                fallback = local[provider]
                # A local rejection must take effect immediately while its
                # fire-and-forget Redis write is still pending.
                if fallback.excluded and fallback.bench_until > until:
                    kind, until = fallback.bench, fallback.bench_until
                if successes + failures:
                    result[provider] = ProviderState(
                        (successes + 1) / (successes + failures + 2), successes + failures, kind, until
                    )
                else:
                    result[provider] = ProviderState(fallback.score, fallback.samples, kind, until)
            return result
        except Exception:
            self._redis_retry_at = self._clock() + 10.0
            logger.debug('STT fleet health read fell back to local state', exc_info=True)
            return local

    async def admit_recovery_probe(self, provider: str) -> bool:
        """One fleet probe after a shared bench expires; local admission survives Redis loss."""
        try:
            result = await self._bounded(self._redis().set(f'{KEY_PREFIX}:probe:{provider}', '1', ex=10, nx=True))
            return bool(result)
        except Exception:
            self._redis_retry_at = self._clock() + 10.0
            return True


health = FleetHealth()


def ordered_providers(
    providers: list[str], states: dict[str, ProviderState], uid: str | None, *, probe_percent: float = 2.0
) -> list[str]:
    """Rank eligible legs, preserving config order for ties and a small recovery probe floor."""
    candidates = [provider for provider in providers if not states.get(provider, ProviderState()).excluded]
    if not candidates:
        return []
    indexed = {provider: index for index, provider in enumerate(candidates)}
    ranked = sorted(candidates, key=lambda provider: (-states.get(provider, ProviderState()).score, indexed[provider]))
    if uid:
        floor = min(10.0, max(0.0, probe_percent))
        probes = [
            provider
            for provider in candidates
            if int.from_bytes(hashlib.sha256(f'stt-probe:{uid}:{provider}'.encode()).digest()[:8], 'big') / 2**64 * 100
            < floor
        ]
        if probes:
            probe = min(probes, key=lambda provider: (states.get(provider, ProviderState()).score, indexed[provider]))
            ranked.remove(probe)
            ranked.insert(0, probe)
            try:
                ROUTING_DECISION.labels(outcome='probe').inc()
            except Exception:
                pass
    return ranked
