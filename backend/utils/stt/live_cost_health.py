"""Fleet-owned cost gate state. All I/O runs in bounded background tasks."""

from __future__ import annotations

import json
import logging
from dataclasses import replace
import os

from config.live_stt_registry import DEFAULT_IDS
from utils.stt.live_gate import GateState, begin_trial, transition
from utils.stt.live_metrics import COST_BENCH, COST_EVENTS, COST_STAGE, FLEET_HEALTH_WRITE_DROPPED

logger = logging.getLogger(__name__)
PREFIX = 'omi:live-stt:cost-v1'
CAS = """
local current = redis.call('GET', KEYS[1])
if (current or '') ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[1], ARGV[2])
return 1
"""


class CostHealthMixin:
    def init_cost_health(self) -> None:
        self._cost_local = {}
        self._cost_cached = {}
        self._cost_interests = {}
        self._cost_preferred = {}
        self._cost_fresh_at = None

    def _target_id(self, provider: str) -> str:
        return DEFAULT_IDS.get(provider, provider)

    def cost_snapshot(self, targets, language: str) -> dict[str, GateState]:
        now = self._clock()
        result = {}
        with self._lock:
            fresh = self._cost_fresh_at is not None and now - self._cost_fresh_at <= 15 and now >= self._redis_retry_at
            known = any(
                (target.id, lang) in self._cost_local
                or (state := self._cost_cached.get((target.id, lang), GateState())).n > 0
                or state.stage < 100
                for target in targets
                for lang in ('all', language)
            )
            if not fresh and now < self._redis_retry_at and not known:
                raise RuntimeError('cost health unavailable; restore configured order')
            for target in targets:
                for lang in ('all', language):
                    self._cost_interests[(target.id, lang)] = now
                    if len(self._cost_interests) > 256:
                        self._cost_interests.pop(min(self._cost_interests, key=self._cost_interests.get))
                source = self._cost_cached if fresh else self._cost_local
                global_state = source.get((target.id, 'all'), GateState())
                lang_state = source.get((target.id, language), GateState())
                # Retain a known bench during Redis faults. Never start pod-owned trials.
                cached = self._cost_cached.get((target.id, 'all'), GateState())
                if not fresh and cached.stage < global_state.stage:
                    global_state = cached
                if lang_state.n >= 30 or lang_state.stage < 100:
                    state = lang_state if lang_state.stage < global_state.stage else global_state
                else:
                    state = global_state
                local = self._cost_local.get((target.id, 'all'), GateState())
                if not fresh and local.stage == 0 and local.generation >= state.generation:
                    state = local
                result[target.id] = state
                COST_BENCH.labels(target=target.id).set(int(state.stage == 0))
                COST_STAGE.labels(target=target.id).set(state.stage)
        return result

    def prefer_recovery(self, target: str, language: str) -> None:
        with self._lock:
            self._cost_preferred[(target, 'all')] = self._clock()
            self._cost_preferred[(target, language)] = self._clock()

    def record_session(
        self, target: str, language: str, outcome: str, generations: dict[str, int] | None = None
    ) -> None:
        if os.getenv('STT_ROUTING_MODE', 'off') == 'off' or outcome not in {'text', 'no_text', 'failover'}:
            return
        target = self._target_id(target)
        failed = outcome != 'text'
        now = self._clock()
        with self._lock:
            for lang in ('all', language):
                key = (target, lang)
                state = self._cost_local.get(key, GateState())
                cached = self._cost_cached.get(key)
                if cached is not None and cached.generation > state.generation:
                    state = cached
                if generations is None or state.generation == generations.get(lang, state.generation):
                    updated = transition(state, failed, now)
                    self._cost_local[key] = updated
                    if len(self._cost_local) > 256:
                        self._cost_local.pop(next(iter(self._cost_local)))
                    if self._cost_fresh_at is None:
                        self._cost_event(target, lang, state, updated, failed)
        self.schedule(self._write_cost_result(target, language, failed, generations))

    def quarantine_target(self, target: str, seconds: float) -> None:
        now = self._clock()

        def update(state):
            return replace(state, stage=0, until=max(state.until, now + seconds), generation=state.generation + 1)

        with self._lock:
            self._cost_local[(target, 'all')] = update(self._cost_local.get((target, 'all'), GateState()))
        self.schedule(self._write_cost_quarantine(target, update))

    async def _write_cost_quarantine(self, target, update):
        try:
            await self._bounded(self._cost_update((target, 'all'), update))
        except Exception:
            self._redis_retry_at = self._clock() + 10
            FLEET_HEALTH_WRITE_DROPPED.labels(kind='bench').inc()

    def cost_generations(self, target: str, language: str) -> dict[str, int]:
        now = self._clock()
        source = (
            self._cost_cached
            if self._cost_fresh_at is not None and now - self._cost_fresh_at <= 15
            else self._cost_local
        )
        return {lang: source.get((target, lang), GateState()).generation for lang in ('all', language)}

    def _cost_event(self, target, language, old, new, failed=None) -> None:
        if old.stage == new.stage:
            return
        event = 'bench' if new.stage == 0 else 'unbench' if new.stage == 100 else 'stage'
        COST_EVENTS.labels(target=target, event=event).inc()
        n, failures = (
            (new.n, new.failures) if new.n else (old.n + int(failed is not None), old.failures + int(bool(failed)))
        )
        logger.info(
            'live_stt_gate target=%s language=%s event=%s stage=%d n=%d failures=%d rate=%.4f until=%.0f',
            target,
            language,
            event,
            new.stage,
            n,
            failures,
            failures / n if n else 0,
            new.until,
        )

    async def _cost_update(self, key, update, failed=None):
        redis_key = f'{PREFIX}:{key[0]}:{key[1]}'
        for _ in range(5):
            raw = await self._redis().get(redis_key)
            old = GateState.decode(json.loads(raw)) if raw else GateState()
            new = update(old)
            if new == old:
                return old
            encoded = json.dumps(new.encode(), separators=(',', ':'))
            if await self._redis().eval(CAS, 1, redis_key, raw or '', encoded):
                self._cost_event(*key, old, new, failed)
                with self._lock:
                    self._cost_cached[key] = new
                return new
        raise RuntimeError('cost state contention')

    async def _write_cost_result(self, target, language, failed, generations):
        async def write():
            for lang in ('all', language):

                def update(state, lang=lang):
                    if generations is not None and state.generation != generations.get(lang, state.generation):
                        return state
                    return transition(state, failed, self._clock())

                await self._cost_update((target, lang), update, failed)

        try:
            if self._clock() < self._redis_retry_at:
                raise RuntimeError('Redis backoff')
            await self._bounded(write())
        except Exception:
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
