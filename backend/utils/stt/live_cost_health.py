"""Fleet-owned cost gate state. All I/O runs in bounded background tasks."""

from __future__ import annotations

import json
import hashlib
import logging
from dataclasses import replace
from abc import ABC, abstractmethod
from typing import Any, Callable, ContextManager
import os

from config.live_stt_registry import DEFAULT_IDS, Target, registry, assigned
from utils.stt.live_gate import GateState, begin_trial, transition
from utils.stt.live_metrics import COST_BENCH, COST_EVENTS, COST_STAGE, FLEET_HEALTH_WRITE_DROPPED

logger = logging.getLogger(__name__)


class CostHealthUnavailable(RuntimeError):
    """Expected missing cache during a Redis outage; selection uses static order."""


PREFIX = 'omi:live-stt:cost-v1'
CAS = """
local current = redis.call('GET', KEYS[1])
if (current or '') ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[1], ARGV[2])
return 1
"""


class CostHealthMixin(ABC):
    _clock: Callable[[], float]
    _lock: ContextManager[Any]
    _redis_retry_at: float
    _cost_local: dict[tuple[str, str], GateState]
    _cost_cached: dict[tuple[str, str], GateState]
    _cost_interests: dict[tuple[str, str], float]
    _cost_preferred: dict[tuple[str, str], float]
    _cost_fresh_at: float | None
    _cost_unreconciled: set[tuple[str, str]]

    @abstractmethod
    def _redis(self) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def _bounded(self, operation: Any) -> Any:
        raise NotImplementedError

    @abstractmethod
    def schedule(self, coroutine: Any) -> None:
        raise NotImplementedError

    def init_cost_health(self) -> None:
        self._cost_local = {}
        self._cost_cached = {}
        self._cost_interests = {}
        self._cost_preferred = {}
        self._cost_fresh_at = None
        self._cost_unreconciled = set()

    def _target_id(self, provider: str) -> str:
        return DEFAULT_IDS.get(provider, provider)

    def _cost_is_fresh(self, now: float) -> bool:
        return self._cost_fresh_at is not None and now - self._cost_fresh_at <= 15 and now >= self._redis_retry_at

    def _cost_view(self, key: tuple[str, str], fresh: bool) -> GateState:
        local = self._cost_local.get(key, GateState())
        cached = self._cost_cached.get(key, GateState())
        state = cached if fresh else local
        if not fresh and cached.stage < state.stage:
            state = cached
        if local.stage == 0 and local.generation >= state.generation and (not fresh or key in self._cost_unreconciled):
            state = local
        return state

    def cost_snapshot(self, targets: list[Target] | tuple[Target, ...], language: str) -> dict[str, GateState]:
        now = self._clock()
        result: dict[str, GateState] = {}
        with self._lock:
            fresh = self._cost_is_fresh(now)
            known = any(
                (target.id, lang) in self._cost_local
                or (state := self._cost_cached.get((target.id, lang), GateState())).n > 0
                or state.stage < 100
                for target in targets
                for lang in ('all', language)
            )
            if not fresh and now < self._redis_retry_at and not known:
                raise CostHealthUnavailable('cost health unavailable; restore configured order')
            for target in targets:
                for lang in ('all', language):
                    self._cost_interests[(target.id, lang)] = now
                    if len(self._cost_interests) > 256:
                        self._cost_interests.pop(min(self._cost_interests, key=lambda item: self._cost_interests[item]))
                global_state = self._cost_view((target.id, 'all'), fresh)
                lang_state = self._cost_view((target.id, language), fresh)
                if lang_state.n >= 30 or lang_state.stage < 100:
                    state = lang_state if lang_state.stage < global_state.stage else global_state
                else:
                    state = global_state
                result[target.id] = state
                COST_BENCH.labels(target=target.id).set(int(state.stage == 0))
                COST_STAGE.labels(target=target.id).set(state.stage)
        return result

    def prefer_recovery(self, target: str, language: str) -> None:
        with self._lock:
            self._cost_preferred[(target, 'all')] = self._clock()
            self._cost_preferred[(target, language)] = self._clock()

    def record_session(
        self,
        target: str,
        language: str,
        outcome: str,
        generations: dict[str, int] | None = None,
        uid: str | None = None,
    ) -> None:
        if not uid or os.getenv('STT_ROUTING_MODE', 'off') == 'off' or outcome not in {'text', 'no_text', 'failover'}:
            return
        witness = hashlib.sha256(('stt-evidence:' + uid).encode()).hexdigest()[:16]
        target = self._target_id(target)
        entry = next((entry for entry in registry() if entry.id == target), None)
        if entry is None:
            return
        minimum_share = (
            5
            if assigned(uid, 'stt-reentry:' + target, 5)
            else 25 if assigned(uid, 'stt-reentry:' + target, 25) else 100
        )
        if not assigned(uid, target, entry.ramp()):
            minimum_share = 100
        failed = outcome != 'text'
        now = self._clock()
        with self._lock:
            for lang in ('all', language):
                key = (target, lang)
                state = self._cost_local.get(key, GateState())
                cached = self._cost_cached.get(key)
                if cached is not None and cached.generation > state.generation:
                    state = cached
                if 0 < state.stage < minimum_share:
                    continue
                if generations is None or state.generation == generations.get(lang, state.generation):
                    updated = transition(state, failed, now, witness=witness)
                    self._cost_local.pop(key, None)
                    self._cost_local[key] = updated
                    if updated.stage == 0 and now < self._redis_retry_at:
                        self._cost_unreconciled.add(key)
                    if len(self._cost_local) > 256:
                        evicted = next(iter(self._cost_local))
                        self._cost_local.pop(evicted)
                        self._cost_unreconciled.discard(evicted)
                    if not self._cost_is_fresh(now):
                        self._cost_event(target, lang, state, updated, failed, local=True)
        self.schedule(self._write_cost_result(target, language, failed, generations, witness, minimum_share))

    def quarantine_target(self, target: str, seconds: float) -> None:
        now = self._clock()

        def update(state: GateState) -> GateState:
            return replace(state, stage=0, until=max(state.until, now + seconds), generation=state.generation + 1)

        with self._lock:
            self._cost_local[(target, 'all')] = update(self._cost_local.get((target, 'all'), GateState()))
            self._cost_unreconciled.add((target, 'all'))
        self.schedule(self._write_cost_quarantine(target, update))

    async def _write_cost_quarantine(self, target: str, update: Callable[[GateState], GateState]) -> None:
        try:
            await self._bounded(self._cost_update((target, 'all'), update))
        except Exception:
            self._redis_retry_at = self._clock() + 10
            FLEET_HEALTH_WRITE_DROPPED.labels(kind='bench').inc()

    def cost_generations(self, target: str, language: str) -> dict[str, int]:
        now = self._clock()
        with self._lock:
            return {
                lang: self._cost_view((target, lang), self._cost_is_fresh(now)).generation for lang in ('all', language)
            }

    def _cost_event(
        self,
        target: str,
        language: str,
        old: GateState,
        new: GateState,
        failed: bool | None = None,
        *,
        local: bool = False,
    ) -> None:
        if old.stage == new.stage:
            return
        event = 'bench' if new.stage == 0 else 'unbench' if new.stage == 100 else 'stage'
        if not local:
            COST_EVENTS.labels(target=target, event=event).inc()
        n, failures = (
            (new.n, new.failures) if new.n else (old.n + int(failed is not None), old.failures + int(bool(failed)))
        )
        logger.info(
            'live_stt_gate target=%s language=%s scope=%s event=%s stage=%d n=%d failures=%d rate=%.4f until=%.0f',
            target,
            language,
            'local' if local else 'fleet',
            event,
            new.stage,
            n,
            failures,
            failures / n if n else 0,
            new.until,
        )

    async def _cost_update(
        self, key: tuple[str, str], update: Callable[[GateState], GateState], failed: bool | None = None
    ) -> GateState:
        redis_key = f'{PREFIX}:{key[0]}:{key[1]}'
        for _ in range(5):
            raw = await self._redis().get(redis_key)
            old = GateState.decode(json.loads(raw)) if raw else GateState()
            new = update(old)
            if new == old:
                return old
            encoded = json.dumps(new.encode(), separators=(',', ':'))
            if await self._redis().eval(CAS, 1, redis_key, raw or '', encoded):
                self._cost_event(key[0], key[1], old, new, failed)
                with self._lock:
                    self._cost_cached[key] = new
                return new
        raise RuntimeError('cost state contention')

    async def _write_cost_result(
        self,
        target: str,
        language: str,
        failed: bool,
        generations: dict[str, int] | None,
        witness: str,
        minimum_share: int = 5,
    ) -> None:
        async def write():
            for lang in ('all', language):

                def update(state: GateState, lang: str = lang) -> GateState:
                    if 0 < state.stage < minimum_share:
                        return state
                    if generations is not None and state.generation != generations.get(lang, state.generation):
                        return state
                    return transition(state, failed, self._clock(), witness=witness)

                key = (target, lang)
                written = await self._cost_update(key, update, failed)
                with self._lock:
                    local = self._cost_local.get(key, GateState())
                    if key not in self._cost_unreconciled and (
                        written.generation > local.generation or written.n >= local.n
                    ):
                        self._cost_local.pop(key, None)
                        self._cost_local[key] = written
                        if len(self._cost_local) > 256:
                            evicted = next(iter(self._cost_local))
                            self._cost_local.pop(evicted)
                            self._cost_unreconciled.discard(evicted)

        try:
            if self._clock() < self._redis_retry_at:
                raise RuntimeError('Redis backoff')
            await self._bounded(write())
        except Exception:
            with self._lock:
                for lang in ('all', language):
                    key = (target, lang)
                    local = self._cost_local.get(key, GateState())
                    if local.stage == 0:
                        if key not in self._cost_unreconciled:
                            self._cost_event(target, lang, GateState(), local, local=True)
                        self._cost_unreconciled.add(key)
            FLEET_HEALTH_WRITE_DROPPED.labels(kind='result').inc()
            self._redis_retry_at = self._clock() + 10

    async def refresh_cost_once(self) -> None:
        now = self._clock()
        with self._lock:
            self._cost_interests = {key: seen for key, seen in self._cost_interests.items() if now - seen < 900}
            self._cost_preferred = {key: seen for key, seen in self._cost_preferred.items() if now - seen < 15}
            keys = sorted(self._cost_interests)
            preferred = dict(self._cost_preferred)
        if not keys or now < self._redis_retry_at:
            return

        async def refresh():
            values = await self._redis().mget([f'{PREFIX}:{target}:{lang}' for target, lang in keys])
            if not isinstance(values, list) or len(values) != len(keys):
                raise ValueError('invalid cost gate snapshot')
            states = {key: GateState.decode(json.loads(raw)) if raw else GateState() for key, raw in zip(keys, values)}
            with self._lock:
                local_benches = {
                    key: state
                    for key, state in self._cost_local.items()
                    if state.stage == 0 and key in self._cost_unreconciled
                }
            for key, local in local_benches.items():
                if key not in states:
                    continue

                def reconcile(remote: GateState, local: GateState = local) -> GateState:
                    if local.generation >= remote.generation and (remote.stage > 0 or local.until > remote.until):
                        return replace(local, generation=max(local.generation, remote.generation + 1))
                    return remote

                states[key] = await self._cost_update(key, reconcile)
                with self._lock:
                    if self._cost_local.get(key) == local:
                        self._cost_unreconciled.discard(key)
            for key in preferred:
                state = states.get(key, GateState())
                if state.stage == 0 and state.until <= now:
                    # One coordinator begins a shared trial; stable UID selection bounds the fleet share.
                    if await self._redis().set(f'{PREFIX}:lease:{key[0]}:{key[1]}', '1', nx=True, ex=10):
                        states[key] = await self._cost_update(key, lambda state: begin_trial(state, now))
            with self._lock:
                self._cost_cached = states
                self._cost_fresh_at = self._clock()

        try:
            await self._bounded(refresh())
        except Exception:
            self._cost_fresh_at = None
            self._redis_retry_at = self._clock() + 10
            logger.debug('Cost gate refresh using local state', exc_info=True)
