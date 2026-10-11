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

from config.live_stt_registry import registry
from config.stt_provider_policy import MODULATE_SUPPORTED_LANGUAGES, PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL
from config import live_stt_state
from utils.executors import start_background_task
from utils.stt.live_cost_health import CostHealthMixin
from utils.stt.live_metrics import FLEET_HEALTH_WRITE_DROPPED, LEG_TRANSCRIPT_OUTCOME

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

BENCH_UPDATE = """
local endpoint = redis.call('GET', KEYS[1]) or ''
local account = redis.call('GET', KEYS[2]) or ''
local t = redis.call('TIME')
local now = t[1] + t[2] / 1000000
local function deadline(raw, kind)
  local sep = raw:find(':', 1, true)
  if not sep or raw:sub(1, sep - 1) ~= kind then return 0 end
  return tonumber(raw:sub(sep + 1)) or 0
end
local account_until = deadline(account, 'account')
local incoming = tonumber(ARGV[2])
if incoming == nil or incoming <= now then
  return {account_until > now and account or endpoint, '0'}
end
if ARGV[1] == 'selection' and account_until > now then
  return {account, '0'}
end
local key = ARGV[1] == 'account' and KEYS[2] or KEYS[1]
local raw = ARGV[1] == 'account' and account or endpoint
local until_at = deadline(raw, ARGV[1])
if until_at >= incoming then return {raw, '0'} end
local retained = math.max(until_at, incoming)
local value = ARGV[1] .. ':' .. string.format('%.3f', retained)
redis.call('SET', key, value, 'EX', math.ceil(retained - now) + 300)
return {value, '1'}
"""

BENCH_CLEANUP = """
local raw = redis.call('GET', KEYS[1])
if (raw or '') ~= ARGV[1] then
  return 0
end
local sep = raw:find(':', 1, true)
local deadline = sep and tonumber(raw:sub(sep + 1)) or 0
local t = redis.call('TIME')
local now = t[1] + t[2] / 1000000
if deadline > now then
  return 0
end
redis.call('DEL', KEYS[1], KEYS[2])
return 1
"""


def mode() -> str:
    value = os.getenv('STT_ROUTING_MODE', 'off').strip().lower()
    return value if value in {'off', 'shadow', 'on'} else 'off'


def bounded_language(language: str | None) -> str:
    token = (language or '').strip().lower().split('-', 1)[0]
    return token if token in LANGUAGES else 'other'


def scoped_identity(provider: str, endpoint: str | None) -> str:
    """Opaque in-memory partition for one serving endpoint's selection state."""
    if not endpoint:
        return provider
    return f'{provider}@{live_stt_state.fleet_prefix(provider, endpoint=endpoint)}'


def scope_family(identity: str) -> str:
    return identity.split('@', 1)[0]


def _selection_prefix(identity: str) -> str:
    if '@' in identity:
        return identity.split('@', 1)[1]
    return live_stt_state.fleet_prefix(identity)


def _selection_state_key(identity: str) -> str:
    return f'{_selection_prefix(identity)}:state:{scope_family(identity)}'


def _selection_probe_key(identity: str) -> str:
    return f'{_selection_prefix(identity)}:probe:{scope_family(identity)}'


def _selection_score_keys(identity: str, language: str, bucket: int) -> tuple[str, str]:
    family = scope_family(identity)
    stem = f'{_selection_prefix(identity)}:score:{family}:{language}:{bucket}'
    return stem + ':text', stem + ':no_text'


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


class FleetHealth(CostHealthMixin):
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.time,
        redis_client: Any = None,
        probe_jitter: Callable[[str], float] | None = None,
    ) -> None:
        self.init_cost_health()
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
        # Retain endpoint evidence even when account state wins or OFF skips it.
        self._cached_selection_benches: dict[str, tuple[str, float]] = {}
        self._cache_at: float | None = None
        self._probe_ready: dict[str, float] = {}
        self._probe_pending: set[str] = set()
        self._local_probe_next: dict[str, float] = {}
        self._writes_in_flight = {'result': 0, 'bench': 0}
        # At most one deadline for each provider/kind, even during a Redis outage.
        self._pending_benches: dict[tuple[str, str], float] = {}
        self._bench_providers_in_flight: dict[str, str] = {}
        seed = f'{os.getpid()}:{time.monotonic_ns()}'.encode()
        self._probe_jitter = probe_jitter or (
            lambda provider: int.from_bytes(hashlib.sha256(seed + provider.encode()).digest()[:4], 'big') / 2**32 * 5.0
        )
        self._identity = ''

    def _check_identity(self) -> str:
        """Reset in-memory views when stage/endpoint/credential identity changes."""
        try:
            targets = registry()
        except (ValueError, TypeError):
            targets = ()
        identity = live_stt_state.state_identity(targets)
        if not self._identity or identity == self._identity:
            self._identity = self._identity or identity
            return identity
        with self._lock:
            if not self._identity or self._identity == identity:
                self._identity = self._identity or identity
                return identity
            self._local.clear()
            self._benches.clear()
            self._interests.clear()
            self._cached_scores.clear()
            self._cached_benches.clear()
            self._cached_selection_benches.clear()
            self._cache_at = None
            self._probe_ready.clear()
            self._probe_pending.clear()
            self._local_probe_next.clear()
            self._pending_benches.clear()
            self._cost_local.clear()
            self._cost_cached.clear()
            self._cost_interests.clear()
            self._cost_preferred.clear()
            self._cost_fresh.clear()
            self._cost_unreconciled.clear()
            self._cost_server_offset = 0.0
            self._identity = identity
        return identity

    def _merge_bench(self, provider: str, retained: str) -> None:
        """Learn the strongest quarantine a shared bench update kept."""
        kind, _, raw_until = str(retained).partition(':')
        if kind not in {'account', 'selection'}:
            return
        try:
            until = float(raw_until)
        except ValueError:
            return
        now = self._clock()
        provider = scope_family(provider) if kind == 'account' else provider
        with self._lock:
            for benches in (self._benches, self._cached_benches):
                old_kind, old_until = benches.get(provider, ('', 0.0))
                if kind == 'account' or (kind == old_kind and until > old_until) or old_until <= now:
                    if kind == old_kind:
                        benches[provider] = kind, max(until, old_until)
                    else:
                        benches[provider] = kind, until

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

    def _score_keys(self, scope: str, language: str, bucket: int) -> tuple[str, str]:
        return _selection_score_keys(scope, language, bucket)

    def _local_score(self, scope: str, language: str) -> ProviderState:
        cutoff = self._clock() - SCORE_BUCKET_SECONDS * SCORE_BUCKETS
        with self._lock:
            events = self._local.get((scope, language), ())
            recent = [success for when, success in events if when >= cutoff]
            bench, until = self._benches.get(scope, ('', 0.0))
        return ProviderState((sum(recent) + 1) / (len(recent) + 2), len(recent), bench or None, until)

    def _combined_bench(self, scope: str, now: float) -> tuple[str, float]:
        """Strongest live deadline: an active family account bench dominates
        this endpoint's selection bench; an expired one still reports."""
        family = scope_family(scope)
        account_until = 0.0
        selection_until = 0.0
        for benches in (self._benches, self._cached_benches, self._cached_selection_benches):
            kind, until = benches.get(scope, ('', 0.0))
            if kind == 'account':
                account_until = max(account_until, until)
            elif kind == 'selection':
                selection_until = max(selection_until, until)
            if scope != family:
                kind, until = benches.get(family, ('', 0.0))
                if kind == 'account':
                    account_until = max(account_until, until)
        if account_until > now:
            return 'account', account_until
        if selection_until:
            return 'selection', selection_until
        if account_until:
            return 'account', account_until
        return '', 0.0

    def record(self, provider: str, language: str | None, outcome: str, *, endpoint: str | None = None) -> None:
        if provider not in PROVIDERS or outcome not in {'text', 'no_text'}:
            return
        lang = bounded_language(language)
        try:
            LEG_TRANSCRIPT_OUTCOME.labels(provider=provider, language=lang, outcome=outcome).inc()
        except Exception:
            pass
        if mode() == 'off':
            return
        identity = self._check_identity()
        scope = scoped_identity(provider, endpoint)
        with self._lock:
            key = scope, lang
            if key not in self._local and len(self._local) >= LOCAL_KEYS_CAP:
                self._local.pop(next(iter(self._local)))
            events = self._local[key]
            events.append((self._clock(), outcome == 'text'))
            while len(events) > LOCAL_EVENTS_CAP:
                events.popleft()
        self.schedule(self._write_result(provider, lang, outcome, endpoint=endpoint, expected_identity=identity))

    async def _write_result(
        self,
        provider: str,
        language: str,
        outcome: str,
        *,
        endpoint: str | None = None,
        expected_identity: str | None = None,
    ) -> None:
        if self._clock() < self._redis_retry_at:
            FLEET_HEALTH_WRITE_DROPPED.labels(kind='result').inc()
            return
        identity = self._check_identity()
        if expected_identity is not None and identity != expected_identity:
            FLEET_HEALTH_WRITE_DROPPED.labels(kind='result').inc()
            return
        scope = scoped_identity(provider, endpoint)
        bucket = int(self._clock() // SCORE_BUCKET_SECONDS)
        text_key, no_text_key = self._score_keys(scope, language, bucket)
        key = text_key if outcome == 'text' else no_text_key
        states = (
            (_selection_state_key(scope), _selection_probe_key(scope)),
            (
                live_stt_state.fleet_state_key(provider, account=True),
                live_stt_state.fleet_probe_key(provider, account=True),
            ),
        )
        try:
            expired: list[tuple[str, str, str]] = []
            if outcome == 'text':
                values = await self._bounded(self._redis().mget([state_key for state_key, _ in states]))
                if self._check_identity() != identity:
                    FLEET_HEALTH_WRITE_DROPPED.labels(kind='result').inc()
                    return
                if not isinstance(values, list) or len(values) != len(states):
                    raise ValueError('invalid fleet health read')
                for (state_key, probe_key), raw in zip(states, values):
                    if raw:
                        try:
                            if float(str(raw).split(':', 1)[1]) <= self._clock():
                                expired.append((state_key, probe_key, str(raw)))
                        except (IndexError, ValueError):
                            pass
            pipe = self._redis().pipeline(transaction=False)
            pipe.incr(key)
            pipe.expire(key, SCORE_BUCKET_SECONDS * (SCORE_BUCKETS + 1))
            await self._bounded(pipe.execute())
            if self._check_identity() != identity:
                FLEET_HEALTH_WRITE_DROPPED.labels(kind='result').inc()
                return
            for state_key, probe_key, clear_bench in expired:
                await self._bounded(self._redis().eval(BENCH_CLEANUP, 2, state_key, probe_key, clear_bench))
                if self._check_identity() != identity:
                    FLEET_HEALTH_WRITE_DROPPED.labels(kind='result').inc()
                    return
        except Exception:
            if self._check_identity() == identity:
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

    def quarantine(self, provider: str, kind: str, seconds: float, *, endpoint: str | None = None) -> None:
        # Account quarantine is a mode-independent hard exclusion: a quota/auth
        # rejection must withdraw the credential on every pod even while the
        # cost-routing kill switch is off. Selection benches stay routing-only.
        if provider not in PROVIDERS or kind not in {'account', 'selection'} or (mode() == 'off' and kind != 'account'):
            return
        self._check_identity()
        bench_identity = provider if kind == 'account' else scoped_identity(provider, endpoint)
        until = self._clock() + max(1.0, seconds)
        with self._lock:
            previous_kind, previous_until = self._benches.get(bench_identity, ('', 0.0))
            if kind == 'account' or previous_until <= self._clock() or previous_kind != 'account':
                self._benches[bench_identity] = kind, max(until, previous_until) if kind == previous_kind else until
            key = bench_identity, kind
            custom_pending = {
                item for item, item_kind in self._pending_benches if item_kind == 'selection' and '@' in item
            }
            admitted = (
                key in self._pending_benches
                or kind != 'selection'
                or '@' not in bench_identity
                or len(custom_pending) < 16
            )
            if admitted:
                while key not in self._pending_benches and len(self._pending_benches) >= LOCAL_KEYS_CAP:
                    self._pending_benches.pop(next(iter(self._pending_benches)))
                self._pending_benches[key] = max(until, self._pending_benches.get(key, 0.0))
        self._drain_pending_benches()

    async def _write_bench(
        self, bench_identity: str, kind: str, until: float, *, expected_identity: str | None = None
    ) -> bool:
        if until <= self._clock() or self._clock() < self._redis_retry_at:
            return False
        identity = self._check_identity()
        if expected_identity is not None and identity != expected_identity:
            return False
        selection_key = _selection_state_key(bench_identity)
        account_key = live_stt_state.fleet_state_key(scope_family(bench_identity), account=True)
        try:
            result = await self._bounded(
                self._redis().eval(BENCH_UPDATE, 2, selection_key, account_key, kind, f'{until:.3f}')
            )
        except Exception:
            if self._check_identity() == identity:
                self._redis_retry_at = self._clock() + 10.0
            logger.debug('STT fleet bench write fell back to local state', exc_info=True)
            return False
        if self._check_identity() != identity:
            return True
        retained = result[0] if isinstance(result, (list, tuple)) else str(result or '')
        if isinstance(retained, bytes):
            retained = retained.decode()
        with self._lock:
            self._merge_bench(bench_identity, retained)
        return True

    def _account_bench_until(self, provider: str) -> float:
        """Keep a selection write from replacing an active account quarantine."""
        local_kind, local_until = self._benches.get(provider, ('', 0.0))
        cached_kind, cached_until = self._cached_benches.get(provider, ('', 0.0))
        return max(
            local_until if local_kind == 'account' else 0.0,
            cached_until if cached_kind == 'account' else 0.0,
            self._pending_benches.get((provider, 'account'), 0.0),
        )

    def _bench_write_done(
        self, bench_identity: str, kind: str, until: float, identity: str, task: asyncio.Task[bool]
    ) -> None:
        success = False
        if not task.cancelled():
            try:
                success = task.result()
            except Exception:
                if self._check_identity() == identity:
                    self._redis_retry_at = self._clock() + 10.0
                logger.debug('STT fleet bench write will retry', exc_info=True)
        with self._lock:
            if self._bench_providers_in_flight.get(bench_identity) == identity:
                self._bench_providers_in_flight.pop(bench_identity, None)
            self._writes_in_flight['bench'] -= 1
            key = bench_identity, kind
            if success and self._identity == identity and self._pending_benches.get(key, 0.0) <= until:
                self._pending_benches.pop(key, None)
        if not task.cancelled():
            self._drain_pending_benches()

    def _drain_pending_benches(self) -> None:
        """Start bounded Redis attempts without waiting on the connection path."""
        # Off mode still flushes pending account benches; selection stays routing-only.
        account_only = mode() == 'off'
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
            expected_identity = self._check_identity()
            for (bench_identity, kind), until in sorted(self._pending_benches.items()):
                if len(self._bench_providers_in_flight) >= WRITE_IN_FLIGHT_LIMITS['bench']:
                    break
                if bench_identity in self._bench_providers_in_flight:
                    continue
                if account_only and kind != 'account':
                    continue
                if kind == 'selection' and self._account_bench_until(scope_family(bench_identity)) > now:
                    continue
                self._bench_providers_in_flight[bench_identity] = expected_identity
                self._writes_in_flight['bench'] += 1
                attempts.append((bench_identity, kind, until))

        for bench_identity, kind, until in attempts:

            def launch(
                bench_identity: str = bench_identity,
                kind: str = kind,
                until: float = until,
                identity: str = expected_identity,
            ) -> None:
                coroutine = self._write_bench(bench_identity, kind, until, expected_identity=identity)
                try:
                    task = start_background_task(coroutine, name='live_stt_fleet_bench_write')
                except RuntimeError:
                    coroutine.close()
                    self._redis_retry_at = self._clock() + 10.0
                    with self._lock:
                        if self._bench_providers_in_flight.get(bench_identity) == identity:
                            self._bench_providers_in_flight.pop(bench_identity, None)
                        self._writes_in_flight['bench'] -= 1
                else:
                    task.add_done_callback(
                        lambda task, bench_identity=bench_identity, kind=kind, until=until, identity=identity: (
                            self._bench_write_done(bench_identity, kind, until, identity, task)
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
                        self._bench_providers_in_flight.pop(bench_identity, None)
                        self._writes_in_flight['bench'] -= 1

    def cached_snapshot(
        self, providers: list[str], language: str | None, *, endpoint: str | None = None
    ) -> dict[str, ProviderState]:
        """Read only pod memory on connect; keep known benches when scores go stale."""
        self._check_identity()
        providers = [provider for provider in providers if provider in PROVIDERS]
        lang = bounded_language(language)
        scopes = {provider: scoped_identity(provider, endpoint) for provider in providers}
        local = {provider: self._local_score(scopes[provider], lang) for provider in providers}
        if not providers:
            return local
        # Scores and interests are routing state; a shared account quarantine
        # must still exclude targets while the routing kill switch is off.
        routing_off = mode() == 'off'
        now = self._clock()
        with self._lock:
            if routing_off:
                result: dict[str, ProviderState] = {}
                for provider in providers:
                    deadlines = [
                        until
                        for benches in (self._benches, self._cached_benches)
                        for kind, until in (benches.get(provider, ('', 0.0)),)
                        if kind == 'account' and until > now
                    ]
                    until = max(deadlines, default=0.0)
                    result[provider] = ProviderState(0.5, 0, 'account' if until else None, until)
                return result
            for provider in providers:
                key = scopes[provider], lang
                if key not in self._interests and len(self._interests) >= LOCAL_KEYS_CAP:
                    self._interests.pop(min(self._interests, key=lambda item: self._interests[item]))
                self._interests[key] = now
            fresh = (
                self._cache_at is not None
                and now - self._cache_at <= CACHE_STALE_SECONDS
                and now >= self._redis_retry_at
            )
            result = {}
            for provider in providers:
                scope = scopes[provider]
                cached = self._cached_scores.get((scope, lang), local[provider]) if fresh else local[provider]
                kind, until = self._combined_bench(scope, now)
                result[provider] = ProviderState(cached.score, cached.samples, kind or None, until)
            return result

    def has_fresh_fleet_snapshot(self) -> bool:
        """Whether cached routing state came from a recent successful fleet read."""
        self._check_identity()
        now = self._clock()
        with self._lock:
            return (
                self._cache_at is not None
                and now - self._cache_at <= CACHE_STALE_SECONDS
                and now >= self._redis_retry_at
            )

    async def refresh_once(self) -> None:
        """One bounded Redis batch off the connection path, including probe leases."""
        # Off mode keeps only shared account benches readable: account
        # quarantine is a mode-independent hard exclusion. Scores, selection
        # benches and probe leases are cost-routing state and stay unread.
        routing_off = mode() == 'off'
        identity = self._check_identity()
        self._loop = asyncio.get_running_loop()
        self._drain_pending_benches()
        if self._clock() < self._redis_retry_at:
            return
        now = self._clock()
        with self._lock:
            self._interests = {
                key: seen for key, seen in self._interests.items() if now - seen <= INTEREST_STALE_SECONDS
            }
            interests = [] if routing_off else sorted(self._interests)
            selection_scopes = (
                set()
                if routing_off
                else {scope for scope, _lang in interests}
                | {item for item, kind in self._pending_benches if kind == 'selection'}
            )
        identities = sorted(set(PROVIDERS) | selection_scopes)
        bucket = int(now // SCORE_BUCKET_SECONDS)
        keys: list[str] = []
        for scope, lang in interests:
            for index in range(SCORE_BUCKETS):
                keys.extend(self._score_keys(scope, lang, bucket - index))
        for bench_identity in identities:
            if not routing_off:
                keys.append(_selection_state_key(bench_identity))
            keys.append(live_stt_state.fleet_state_key(scope_family(bench_identity), account=True))
        probe_keys = {
            (bench_identity, account): (
                live_stt_state.fleet_probe_key(scope_family(bench_identity), account=True)
                if account
                else _selection_probe_key(bench_identity)
            )
            for bench_identity in identities
            for account in (False, True)
        }
        try:
            values = await self._bounded(self._redis().mget(keys))
            if self._check_identity() != identity:
                return
            if not isinstance(values, list) or len(values) != len(keys):
                raise ValueError('invalid fleet health read')
            scores: dict[tuple[str, str], ProviderState] = {}
            cursor = 0
            for scope, lang in interests:
                counts = [int(raw or 0) for raw in values[cursor : cursor + SCORE_BUCKETS * 2]]
                cursor += SCORE_BUCKETS * 2
                successes = sum(counts[::2])
                failures = sum(counts[1::2])
                if successes + failures:
                    scores[(scope, lang)] = ProviderState(
                        (successes + 1) / (successes + failures + 2), successes + failures
                    )
            benches: dict[str, tuple[str, float]] = {}
            selections: dict[str, tuple[str, float]] = {}
            for bench_identity in identities:
                if routing_off:
                    raw_endpoint, raw_account = None, values[cursor]
                    cursor += 1
                else:
                    raw_endpoint, raw_account = values[cursor], values[cursor + 1]
                    cursor += 2
                parsed = {}
                for account_flag, raw_state in ((False, raw_endpoint), (True, raw_account)):
                    state = str(raw_state or '').split(':', 1)
                    if len(state) == 2 and state[0] == ('account' if account_flag else 'selection'):
                        parsed[account_flag] = state[0], float(state[1])
                account_bench = parsed.get(True)
                selection_bench = parsed.get(False)
                if selection_bench is not None:
                    selections[bench_identity] = selection_bench
                if account_bench is not None and account_bench[1] > now:
                    benches[bench_identity] = account_bench
                elif selection_bench is not None:
                    benches[bench_identity] = selection_bench
                elif account_bench is not None:
                    benches[bench_identity] = account_bench
            with self._lock:
                if self._identity != identity:
                    return
                self._cached_scores = scores
                self._cached_benches = benches
                if not routing_off:
                    self._cached_selection_benches = selections
                self._cache_at = self._clock()
                if routing_off:
                    # Off mode loads shared benches only to enforce account
                    # exclusion; probe leases remain cost-routing state.
                    return
                expired = {bench_identity for bench_identity, (_, until) in benches.items() if until <= self._clock()}
                self._probe_ready = {
                    bench_identity: lease_until
                    for bench_identity, lease_until in self._probe_ready.items()
                    if bench_identity in expired and lease_until > self._clock()
                }
                need_lease = expired - self._probe_ready.keys()
                self._probe_pending.update(need_lease)
            try:
                for bench_identity in sorted(need_lease):
                    probe_key = probe_keys[(bench_identity, benches[bench_identity][0] == 'account')]
                    granted = await self._bounded(self._redis().set(probe_key, '1', ex=10, nx=True))
                    if self._check_identity() != identity:
                        return
                    if granted:
                        with self._lock:
                            self._probe_ready[bench_identity] = self._clock() + 9.0
            finally:
                with self._lock:
                    if self._identity == identity:
                        self._probe_pending.difference_update(need_lease)
        except Exception:
            if self._check_identity() != identity:
                return
            self._redis_retry_at = self._clock() + 10.0
            with self._lock:
                self._cache_at = None
                self._probe_ready.clear()
                self._probe_pending.clear()
            logger.debug('STT fleet health read fell back to local state', exc_info=True)

    async def refresh_forever(self) -> None:
        while True:
            await self.refresh_once()
            if mode() != 'off':
                await self.refresh_cost_once()
            await asyncio.sleep(CACHE_REFRESH_SECONDS)

    def try_admit_recovery_probe(self, provider: str, *, endpoint: str | None = None) -> bool:
        """Consume a background fleet permit, or a jittered pod-local fallback."""
        now = self._clock()
        scope = scoped_identity(provider, endpoint)
        with self._lock:
            fresh = self._cache_at is not None and now - self._cache_at <= CACHE_STALE_SECONDS
            shared = fresh and now >= self._redis_retry_at and scope in self._cached_benches
            if shared:
                if self._probe_ready.get(scope, 0.0) > now:
                    self._probe_ready.pop(scope)
                    return True
                if scope not in self._probe_pending:
                    return False
            next_at = self._local_probe_next.get(scope)
            jitter = self._probe_jitter(scope)
            if next_at is None:
                next_at = now + jitter
            if now < next_at:
                self._local_probe_next[scope] = next_at
                return False
            self._local_probe_next[scope] = now + LOCAL_PROBE_INTERVAL_SECONDS + jitter
            return True


health = FleetHealth()
