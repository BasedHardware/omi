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
from utils.executors import start_background_task
from utils.stt.live_metrics import FLEET_HEALTH_WRITE_DROPPED, LEG_TRANSCRIPT_OUTCOME, ROUTING_DECISION

logger = logging.getLogger(__name__)

PROVIDERS = frozenset({'modulate', 'soniox', 'deepgram', 'parakeet'})
LANGUAGES = MODULATE_SUPPORTED_LANGUAGES | frozenset().union(*PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL.values())
SCORE_BUCKET_SECONDS = 300
SCORE_BUCKETS = 3
REDIS_DEADLINE_SECONDS = 0.075
CACHE_REFRESH_SECONDS = 5.0
CACHE_STALE_SECONDS = 15.0
INTEREST_STALE_SECONDS = 900.0
LOCAL_PROBE_INTERVAL_SECONDS = 10.0
LOCAL_EVENTS_CAP = 256
LOCAL_KEYS_CAP = 256
WRITE_IN_FLIGHT_LIMITS = {'result': 8, 'bench': 4}
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
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        redis_client: Any = None,
        probe_jitter: Callable[[str], float] | None = None,
    ) -> None:
        self._clock = clock
        self._client = redis_client
        self._lock = threading.RLock()
        self._local: dict[tuple[str, str], deque[tuple[float, bool]]] = defaultdict(deque)
        self._benches: dict[str, tuple[str, float]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._redis_retry_at = 0.0
        self._interests: dict[tuple[str, str], float] = {}
        self._cached_scores: dict[tuple[str, str], ProviderState] = {}
        self._cached_benches: dict[str, tuple[str, float]] = {}
        self._cache_at: float | None = None
        self._probe_ready: dict[str, float] = {}
        self._probe_pending: set[str] = set()
        self._local_probe_next: dict[str, float] = {}
        self._writes_in_flight = {'result': 0, 'bench': 0}
        # At most one deadline for each provider/kind, even during a Redis outage.
        self._pending_benches: dict[tuple[str, str], float] = {}
        self._bench_providers_in_flight: set[str] = set()
        seed = f'{os.getpid()}:{time.monotonic_ns()}'.encode()
        self._probe_jitter = probe_jitter or (
            lambda provider: int.from_bytes(hashlib.sha256(seed + provider.encode()).digest()[:4], 'big') / 2**32 * 5.0
        )

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
            FLEET_HEALTH_WRITE_DROPPED.labels(kind='result').inc()
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
            FLEET_HEALTH_WRITE_DROPPED.labels(kind='result').inc()
            logger.debug('STT fleet health write fell back to local state', exc_info=True)

    def schedule(self, coroutine: Any) -> None:
        """Best-effort result write; account/selection benches use the retry map."""
        if mode() == 'off':
            coroutine.close()
            return
        try:
            loop = asyncio.get_running_loop()
            self._loop = loop
            on_loop = True
        except RuntimeError:
            on_loop = False
            loop = self._loop
            if loop is None or loop.is_closed():
                coroutine.close()
                FLEET_HEALTH_WRITE_DROPPED.labels(kind='result').inc()
                return
        with self._lock:
            if self._writes_in_flight['result'] >= WRITE_IN_FLIGHT_LIMITS['result']:
                coroutine.close()
                FLEET_HEALTH_WRITE_DROPPED.labels(kind='result').inc()
                return
            self._writes_in_flight['result'] += 1

        def release() -> None:
            with self._lock:
                self._writes_in_flight['result'] -= 1

        def launch() -> None:
            try:
                task = start_background_task(coroutine, name='live_stt_fleet_result_write')
            except RuntimeError:
                coroutine.close()
                release()
                FLEET_HEALTH_WRITE_DROPPED.labels(kind='result').inc()
            else:
                task.add_done_callback(lambda _task: release())

        if on_loop:
            launch()
        else:
            try:
                loop.call_soon_threadsafe(launch)
            except RuntimeError:
                coroutine.close()
                release()
                FLEET_HEALTH_WRITE_DROPPED.labels(kind='result').inc()

    def quarantine(self, provider: str, kind: str, seconds: float) -> None:
        if provider not in PROVIDERS or kind not in {'account', 'selection'} or mode() == 'off':
            return
        until = self._clock() + max(1.0, seconds)
        with self._lock:
            previous_kind, previous_until = self._benches.get(provider, ('', 0.0))
            if kind == 'account' or previous_until <= self._clock() or previous_kind != 'account':
                self._benches[provider] = kind, max(until, previous_until) if kind == previous_kind else until
            key = provider, kind
            self._pending_benches[key] = max(until, self._pending_benches.get(key, 0.0))
        self._drain_pending_benches()

    async def _write_bench(self, provider: str, kind: str, until: float) -> bool:
        if until <= self._clock() or self._clock() < self._redis_retry_at:
            return False
        try:
            await self._bounded(
                self._redis().set(
                    f'{KEY_PREFIX}:state:{provider}',
                    f'{kind}:{until:.3f}',
                    ex=max(1, int(until - self._clock()) + 300),
                )
            )
            return True
        except Exception:
            self._redis_retry_at = self._clock() + 10.0
            logger.debug('STT fleet bench write fell back to local state', exc_info=True)
            return False

    def _account_bench_until(self, provider: str) -> float:
        """Keep a selection write from replacing an active account quarantine."""
        local_kind, local_until = self._benches.get(provider, ('', 0.0))
        cached_kind, cached_until = self._cached_benches.get(provider, ('', 0.0))
        return max(
            local_until if local_kind == 'account' else 0.0,
            cached_until if cached_kind == 'account' else 0.0,
            self._pending_benches.get((provider, 'account'), 0.0),
        )

    def _bench_write_done(self, provider: str, kind: str, until: float, task: asyncio.Task[bool]) -> None:
        success = False
        if not task.cancelled():
            try:
                success = task.result()
            except Exception:
                self._redis_retry_at = self._clock() + 10.0
                logger.debug('STT fleet bench write will retry', exc_info=True)
        with self._lock:
            self._bench_providers_in_flight.discard(provider)
            self._writes_in_flight['bench'] -= 1
            key = provider, kind
            if success and self._pending_benches.get(key, 0.0) <= until:
                self._pending_benches.pop(key, None)
        if not task.cancelled():
            self._drain_pending_benches()

    def _drain_pending_benches(self) -> None:
        """Start bounded Redis attempts without waiting on the connection path."""
        if mode() == 'off':
            return
        try:
            loop = asyncio.get_running_loop()
            self._loop = loop
            on_loop = True
        except RuntimeError:
            loop = self._loop
            on_loop = False
            if loop is None or loop.is_closed():
                return  # A later refresh will flush the retained deadlines.
        now = self._clock()
        attempts: list[tuple[str, str, float]] = []
        with self._lock:
            for key, until in tuple(self._pending_benches.items()):
                if until <= now:
                    self._pending_benches.pop(key, None)
            if now < self._redis_retry_at:
                return
            for (provider, kind), until in sorted(self._pending_benches.items()):
                if len(self._bench_providers_in_flight) >= WRITE_IN_FLIGHT_LIMITS['bench']:
                    break
                if provider in self._bench_providers_in_flight:
                    continue
                if kind == 'selection' and self._account_bench_until(provider) > now:
                    continue
                self._bench_providers_in_flight.add(provider)
                self._writes_in_flight['bench'] += 1
                attempts.append((provider, kind, until))

        for provider, kind, until in attempts:

            def launch(provider: str = provider, kind: str = kind, until: float = until) -> None:
                coroutine = self._write_bench(provider, kind, until)
                try:
                    task = start_background_task(coroutine, name='live_stt_fleet_bench_write')
                except RuntimeError:
                    coroutine.close()
                    self._redis_retry_at = self._clock() + 10.0
                    with self._lock:
                        self._bench_providers_in_flight.discard(provider)
                        self._writes_in_flight['bench'] -= 1
                else:
                    task.add_done_callback(
                        lambda task, provider=provider, kind=kind, until=until: self._bench_write_done(
                            provider, kind, until, task
                        )
                    )

            if on_loop:
                launch()
            else:
                try:
                    loop.call_soon_threadsafe(launch)
                except RuntimeError:
                    self._redis_retry_at = self._clock() + 10.0
                    with self._lock:
                        self._bench_providers_in_flight.discard(provider)
                        self._writes_in_flight['bench'] -= 1

    def cached_snapshot(self, providers: list[str], language: str | None) -> dict[str, ProviderState]:
        """Read only pod memory on connect; keep known benches when scores go stale."""
        providers = [provider for provider in providers if provider in PROVIDERS]
        lang = bounded_language(language)
        local = {provider: self._local_score(provider, lang) for provider in providers}
        if mode() == 'off' or not providers:
            return local
        now = self._clock()
        with self._lock:
            for provider in providers:
                key = provider, lang
                if key not in self._interests and len(self._interests) >= LOCAL_KEYS_CAP:
                    self._interests.pop(min(self._interests, key=lambda item: self._interests[item]))
                self._interests[key] = now
            fresh = (
                self._cache_at is not None
                and now - self._cache_at <= CACHE_STALE_SECONDS
                and now >= self._redis_retry_at
            )
            result: dict[str, ProviderState] = {}
            for provider in providers:
                cached = self._cached_scores.get((provider, lang), local[provider]) if fresh else local[provider]
                kind, until = self._cached_benches.get(provider, ('', 0.0))
                fallback = local[provider]
                if fallback.bench and (
                    (fallback.bench == 'account' and fallback.bench_until > now and kind != 'account')
                    or (until <= now and fallback.bench_until > until)
                    or (fallback.bench == kind and fallback.bench_until > until)
                ):
                    kind, until = fallback.bench or '', fallback.bench_until
                result[provider] = ProviderState(cached.score, cached.samples, kind or None, until)
            return result

    async def refresh_once(self) -> None:
        """One bounded Redis batch off the connection path, including probe leases."""
        if mode() == 'off':
            return
        self._loop = asyncio.get_running_loop()
        self._drain_pending_benches()
        if self._clock() < self._redis_retry_at:
            return
        now = self._clock()
        with self._lock:
            self._interests = {
                key: seen for key, seen in self._interests.items() if now - seen <= INTEREST_STALE_SECONDS
            }
            interests = sorted(self._interests)
        bucket = int(now // SCORE_BUCKET_SECONDS)
        keys: list[str] = []
        for provider, lang in interests:
            for index in range(SCORE_BUCKETS):
                keys.extend(self._score_keys(provider, lang, bucket - index))
        for provider in sorted(PROVIDERS):
            keys.append(f'{KEY_PREFIX}:state:{provider}')
        try:
            values = await self._bounded(self._redis().mget(keys))
            if not isinstance(values, list) or len(values) != len(keys):
                raise ValueError('invalid fleet health read')
            scores: dict[tuple[str, str], ProviderState] = {}
            cursor = 0
            for provider, lang in interests:
                counts = [int(raw or 0) for raw in values[cursor : cursor + SCORE_BUCKETS * 2]]
                cursor += SCORE_BUCKETS * 2
                successes = sum(counts[::2])
                failures = sum(counts[1::2])
                if successes + failures:
                    scores[(provider, lang)] = ProviderState(
                        (successes + 1) / (successes + failures + 2), successes + failures
                    )
            benches: dict[str, tuple[str, float]] = {}
            for provider in sorted(PROVIDERS):
                raw_state = values[cursor]
                cursor += 1
                state = str(raw_state or '').split(':', 1)
                if len(state) == 2 and state[0] in {'account', 'selection'}:
                    benches[provider] = state[0], float(state[1])
            with self._lock:
                self._cached_scores = scores
                self._cached_benches = benches
                self._cache_at = self._clock()
                expired = {provider for provider, (_, until) in benches.items() if until <= self._clock()}
                self._probe_ready = {
                    provider: lease_until
                    for provider, lease_until in self._probe_ready.items()
                    if provider in expired and lease_until > self._clock()
                }
                need_lease = expired - self._probe_ready.keys()
                self._probe_pending.update(need_lease)
            try:
                for provider in sorted(need_lease):
                    granted = await self._bounded(
                        self._redis().set(f'{KEY_PREFIX}:probe:{provider}', '1', ex=10, nx=True)
                    )
                    if granted:
                        with self._lock:
                            self._probe_ready[provider] = self._clock() + 9.0
            finally:
                with self._lock:
                    self._probe_pending.difference_update(need_lease)
        except Exception:
            self._redis_retry_at = self._clock() + 10.0
            with self._lock:
                self._cache_at = None
                self._probe_ready.clear()
                self._probe_pending.clear()
            logger.debug('STT fleet health read fell back to local state', exc_info=True)

    async def refresh_forever(self) -> None:
        while True:
            await self.refresh_once()
            await asyncio.sleep(CACHE_REFRESH_SECONDS)

    def try_admit_recovery_probe(self, provider: str) -> bool:
        """Consume a background fleet permit, or a jittered pod-local fallback."""
        now = self._clock()
        with self._lock:
            fresh = self._cache_at is not None and now - self._cache_at <= CACHE_STALE_SECONDS
            shared = fresh and now >= self._redis_retry_at and provider in self._cached_benches
            if shared:
                if self._probe_ready.get(provider, 0.0) > now:
                    self._probe_ready.pop(provider)
                    return True
                if provider not in self._probe_pending:
                    return False
            next_at = self._local_probe_next.get(provider)
            jitter = self._probe_jitter(provider)
            if next_at is None:
                next_at = now + jitter
            if now < next_at:
                self._local_probe_next[provider] = next_at
                return False
            self._local_probe_next[provider] = now + LOCAL_PROBE_INTERVAL_SECONDS + jitter
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
