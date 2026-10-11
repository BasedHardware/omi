"""Fleet-owned cost gate state. All I/O runs in bounded background tasks."""

from __future__ import annotations

import json
import hashlib
import logging
from dataclasses import replace
from abc import ABC, abstractmethod
from typing import Any, Callable, ContextManager
import os

from config import live_stt_state
from config.live_stt_registry import DEFAULT_TARGETS, Target, registry, assigned
from utils.stt.live_gate import GateState, begin_trial, transition
from utils.stt.live_metrics import (
    COST_BENCH,
    COST_EVENTS,
    COST_STAGE,
    COST_SNAPSHOT_AT,
    COST_STATE_KNOWN,
    COST_OBSERVATIONS,
    COST_IGNORED_DEATHS,
    COST_LANGUAGE_STATE,
    COST_SETTLEMENTS,
    COST_VOTES,
    COST_ALL_DEGRADED,
    FLEET_HEALTH_WRITE_DROPPED,
    MANAGED_LEGS_OPENED,
    MANAGED_LEGS_SETTLED,
    MANAGED_LEGS_OPEN,
)
from utils.stt.live_signal import provider_observation
from utils.stt.live_reason import LIVE_STT_REASONS, normalize_live_stt_reason

logger = logging.getLogger(__name__)


class CostHealthUnavailable(RuntimeError):
    """Expected missing cache during a Redis outage; selection uses static order."""

    def __init__(self, message: str, *, states: dict[str, GateState] | None = None) -> None:
        super().__init__(message)
        self.states = states if states is not None else {}


class _IdentityChanged(RuntimeError):
    """An awaited write observed a different environment identity than queued."""


COST_CACHE_CAP = 4096
CAS = """
local current = redis.call('GET', KEYS[1])
if (current or '') ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[1], ARGV[2])
if tonumber(ARGV[3]) > 0 then redis.call('EXPIRE', KEYS[1], ARGV[3]) end
return 1
"""


class CostHealthMixin(ABC):
    _clock: Callable[[], float]
    _lock: ContextManager[Any]
    _identity: str
    _redis_retry_at: float
    _cost_local: dict[tuple[str, str], GateState]
    _cost_cached: dict[tuple[str, str], GateState]
    _cost_interests: dict[tuple[str, str], float]
    _cost_preferred: dict[tuple[str, str], float]
    _cost_fresh: dict[tuple[str, str], float]
    _cost_unreconciled: set[tuple[str, str]]
    _cost_server_offset: float

    @abstractmethod
    def _redis(self) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def _bounded(self, operation: Any) -> Any:
        raise NotImplementedError

    @abstractmethod
    def schedule(self, coroutine: Any) -> None:
        raise NotImplementedError

    @abstractmethod
    def _check_identity(self) -> str:
        raise NotImplementedError

    def init_cost_health(self) -> None:
        self._cost_metrics_targets: set[str] = set()
        self._cost_local = {}
        self._cost_cached = {}
        self._cost_interests = {}
        self._cost_preferred = {}
        self._cost_fresh = {}
        self._cost_unreconciled = set()
        self._cost_server_offset = 0.0
        try:
            targets = registry()
        except (ValueError, TypeError):
            targets = DEFAULT_TARGETS
        self._init_cost_metrics(targets)

    def _init_cost_metrics(self, targets) -> None:
        for target in targets:
            if target.id in self._cost_metrics_targets:
                continue
            self._cost_metrics_targets.add(target.id)
            MANAGED_LEGS_OPENED.labels(target=target.id)
            MANAGED_LEGS_SETTLED.labels(target=target.id)
            MANAGED_LEGS_OPEN.labels(target=target.id)
            COST_ALL_DEGRADED.labels(target=target.id)
            for scope in ('global', 'language'):
                for result in ('applied', 'user_cap', 'window_full', 'generation', 'stage'):
                    COST_VOTES.labels(target=target.id, scope=scope, result=result)
            for event in ('bench', 'stage', 'unbench'):
                for scope in ('global', 'language'):
                    COST_EVENTS.labels(target=target.id, event=event, scope=scope)
            for reason in LIVE_STT_REASONS:
                failed = provider_observation('text' if reason == 'text' else 'failover', reason)
                outcome = 'censored' if failed is None else 'provider_failure' if failed else 'success'
                COST_OBSERVATIONS.labels(target=target.id, outcome=outcome, reason=reason)
                for boundary in ('client_gone', 'owner_teardown'):
                    COST_IGNORED_DEATHS.labels(target=target.id, reason=reason, boundary=boundary)
                for path in ('close', 'failover', 'connect'):
                    COST_SETTLEMENTS.labels(target=target.id, outcome=outcome, reason=reason, path=path)

    @staticmethod
    def _publish_cost_state(target: str, state: GateState) -> None:
        known = state.n > 0 or state.generation > 0 or state.stage < 100
        COST_STATE_KNOWN.labels(target=target).set(int(known))
        COST_BENCH.labels(target=target).set(int(state.stage == 0) if known else float('nan'))
        COST_STAGE.labels(target=target).set(state.stage if known else float('nan'))

    def _fleet_now(self) -> float:
        return self._clock() + self._cost_server_offset

    async def _server_now(self, expected_identity: str | None = None) -> float:
        seconds, micros = await self._redis().time()
        now = float(seconds) + float(micros) / 1_000_000
        identity = self._check_identity()
        if expected_identity is not None and identity != expected_identity:
            raise _IdentityChanged('live STT state identity changed')
        with self._lock:
            offset = now - self._clock()
            delta = offset - self._cost_server_offset
            # Fault-only local deadlines use the last known server offset.
            # Translate them once when the server clock becomes available.
            for key in self._cost_unreconciled:
                state = self._cost_local.get(key)
                if state is not None and state.stage == 0:
                    self._cost_local[key] = replace(state, until=max(0, state.until + delta))
            self._cost_server_offset = offset
        return now

    @staticmethod
    def _cost_target(target_id: str) -> Target | None:
        try:
            for entry in registry():
                if entry.id == target_id:
                    return entry
        except (ValueError, TypeError):
            return None
        return None

    def _cost_is_fresh(self, key: tuple[str, str], now: float) -> bool:
        fresh_at = self._cost_fresh.get(key)
        return fresh_at is not None and now - fresh_at <= 15 and now >= self._redis_retry_at

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
        self._init_cost_metrics(targets)
        self._check_identity()
        try:
            registered_ids = {entry.id for entry in registry()}
        except (ValueError, TypeError):
            registered_ids = set()
        now = self._clock()
        result: dict[str, GateState] = {}
        with self._lock:
            any_fresh = any(
                self._cost_is_fresh((target.id, lang), now) for target in targets for lang in ('all', language)
            )
            known = any(
                (target.id, lang) in self._cost_local
                or (state := self._cost_cached.get((target.id, lang), GateState())).n > 0
                or state.stage < 100
                for target in targets
                for lang in ('all', language)
            )
            if not any_fresh and now < self._redis_retry_at and not known:
                raise CostHealthUnavailable('cost health unavailable; restore configured order')
            unknown_language = False
            for target in targets:
                for lang in ('all', language):
                    self._cost_interests[(target.id, lang)] = now
                    if len(self._cost_interests) > 256:
                        self._cost_interests.pop(min(self._cost_interests, key=lambda item: self._cost_interests[item]))
                global_key = target.id, 'all'
                language_key = target.id, language
                fresh_global = self._cost_is_fresh(global_key, now)
                fresh_language = fresh_global if language == 'all' else self._cost_is_fresh(language_key, now)
                global_state = self._cost_view(global_key, fresh_global)
                lang_state = self._cost_view(language_key, fresh_language)
                comparison = 'agree'
                if language != 'all':
                    if not fresh_language:
                        if lang_state.stage < 100 or global_state.stage < 100:
                            comparison = (
                                'language_restricted' if lang_state.stage < global_state.stage else 'global_restricted'
                            )
                        elif language_key not in self._cost_fresh:
                            comparison = 'unknown'
                            unknown_language = True
                        else:
                            comparison = 'stale'
                    elif lang_state.stage < global_state.stage:
                        comparison = 'language_restricted'
                    elif global_state.stage < lang_state.stage:
                        comparison = 'global_restricted'
                elif not fresh_global:
                    comparison = 'stale'
                if target.id in registered_ids:
                    COST_LANGUAGE_STATE.labels(target=target.id, comparison=comparison).inc()
                if lang_state.n >= 30 or lang_state.stage < 100:
                    state = lang_state if lang_state.stage < global_state.stage else global_state
                else:
                    state = global_state
                result[target.id] = state
                self._publish_cost_state(target.id, global_state)
            if unknown_language:
                raise CostHealthUnavailable('unread language cost state; restore configured order', states=result)
        return result

    def prefer_recovery(self, target: str, language: str) -> None:
        self._check_identity()
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
        reason: str | None = None,
    ) -> bool:
        if not uid or os.getenv('STT_ROUTING_MODE', 'off') == 'off':
            return False
        identity = self._check_identity()
        witness = hashlib.sha256(('stt-evidence:' + uid).encode()).hexdigest()[:16]
        entry = next((entry for entry in registry() if entry.id == target), None)
        if entry is None:
            return False
        self._init_cost_metrics([entry])
        reason = normalize_live_stt_reason(
            reason,
            default=(
                outcome if outcome in {'text', 'no_text'} else 'connection_lost' if outcome == 'failover' else 'other'
            ),
        )
        failed = provider_observation(outcome, reason)
        COST_OBSERVATIONS.labels(
            target=target,
            outcome='censored' if failed is None else 'provider_failure' if failed else 'success',
            reason=reason,
        ).inc()
        if failed is None:
            return True
        minimum_share = (
            5
            if assigned(uid, 'stt-reentry:' + target, 5)
            else 25 if assigned(uid, 'stt-reentry:' + target, 25) else 100
        )
        if not assigned(uid, target, entry.ramp()):
            minimum_share = 100
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
                    updated = transition(state, failed, self._fleet_now(), witness=witness, language_only=lang != 'all')
                    self._cost_local.pop(key, None)
                    self._cost_local[key] = updated
                    if updated.stage == 0 and now < self._redis_retry_at:
                        self._cost_unreconciled.add(key)
                    if len(self._cost_local) > 256:
                        evicted = next(iter(self._cost_local))
                        self._cost_local.pop(evicted)
                        self._cost_unreconciled.discard(evicted)
                    if not self._cost_is_fresh(key, now):
                        self._cost_event(target, lang, state, updated, failed, local=True)
        self.schedule(
            self._write_cost_result(
                target, language, failed, generations, witness, minimum_share, expected_identity=identity
            )
        )
        return True

    def quarantine_target(self, target: str, seconds: float) -> None:
        identity = self._check_identity()

        def update(state: GateState) -> GateState:
            return replace(
                state,
                stage=0,
                until=max(state.until, self._fleet_now() + seconds),
                generation=state.generation + 1,
                healthy_users=(),
                healthy_window=-1,
                overflow_failures=(),
            )

        with self._lock:
            self._cost_local[(target, 'all')] = update(self._cost_local.get((target, 'all'), GateState()))
            self._cost_unreconciled.add((target, 'all'))
        self.schedule(self._write_cost_quarantine(target, update, expected_identity=identity))

    async def _write_cost_quarantine(
        self,
        target: str,
        update: Callable[[GateState], GateState],
        *,
        expected_identity: str | None = None,
    ) -> None:
        async def write():
            identity = self._check_identity()
            if expected_identity is not None and identity != expected_identity:
                raise _IdentityChanged('live STT state identity changed')
            await self._server_now(identity)
            await self._cost_update((target, 'all'), update, expected_identity=identity)

        try:
            await self._bounded(write())
        except _IdentityChanged:
            return
        except Exception:
            self._redis_retry_at = self._clock() + 10
            FLEET_HEALTH_WRITE_DROPPED.labels(kind='bench').inc()

    def cost_generations(self, target: str, language: str) -> dict[str, int]:
        self._check_identity()
        now = self._clock()
        with self._lock:
            return {
                lang: self._cost_view((target, lang), self._cost_is_fresh((target, lang), now)).generation
                for lang in ('all', language)
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
        if language == 'all':
            self._publish_cost_state(target, new)
        if not local:
            COST_EVENTS.labels(target=target, event=event, scope='global' if language == 'all' else 'language').inc()
        n, failures = (
            (new.n, new.failures) if new.n else (old.n + int(failed is not None), old.failures + int(bool(failed)))
        )
        logger.info(
            'live_stt_gate target=%s language=%s scope=%s event=%s stage=%d n=%d failures=%d rate=%.4f score=%.3f until=%.0f',
            target,
            language,
            'local' if local else 'fleet',
            event,
            new.stage,
            n,
            failures,
            failures / n if n else 0,
            max(new.evidence if new.n else old.evidence),
            new.until,
        )

    async def _cost_update(
        self,
        key: tuple[str, str],
        update: Callable[[GateState], GateState],
        failed: bool | None = None,
        *,
        expected_identity: str | None = None,
    ) -> GateState:
        identity = self._check_identity()
        if expected_identity is not None and identity != expected_identity:
            raise _IdentityChanged('live STT state identity changed')
        target = self._cost_target(key[0])
        if target is None:
            raise RuntimeError('cost state target not in registry')
        redis_key = live_stt_state.cost_key(target, key[1])
        for _ in range(5):
            raw = await self._redis().get(redis_key)
            if self._check_identity() != identity:
                raise _IdentityChanged('live STT state identity changed')
            old = GateState.decode(json.loads(raw)) if raw else GateState()
            new = update(old)
            if new == old:
                with self._lock:
                    if self._identity == identity:
                        self._cost_cached[key] = old
                        self._cost_fresh[key] = self._clock()
                return old
            encoded = json.dumps(new.encode(), separators=(',', ':'))
            # Healthy fairness data expires after three idle windows. Benches
            # and recovery trials have no healthy_users and must not expire
            # into a fresh stage-100 state (especially unprobed expensive legs).
            if await self._redis().eval(CAS, 1, redis_key, raw or '', encoded, 900 if new.stage == 100 else 0):
                if self._check_identity() != identity:
                    return new
                with self._lock:
                    self._cost_cached[key] = new
                    self._cost_fresh[key] = self._clock()
                self._cost_event(key[0], key[1], old, new, failed)
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
        *,
        expected_identity: str | None = None,
    ) -> None:
        async def write():
            identity = self._check_identity()
            if expected_identity is not None and identity != expected_identity:
                raise _IdentityChanged('live STT state identity changed')
            now = await self._server_now(identity)
            for lang in ('all', language):
                result = 'applied'

                def update(state: GateState, lang: str = lang) -> GateState:
                    nonlocal result
                    result = 'applied'
                    if 0 < state.stage < minimum_share:
                        result = 'stage'
                        return state
                    if generations is not None and state.generation != generations.get(lang, state.generation):
                        result = 'generation'
                        return state
                    updated = transition(state, failed, now, witness=witness, language_only=lang != 'all')
                    if state.stage in (5, 25) and {user[0]: user[1] for user in state.trial_users}.get(witness, 0) >= 3:
                        result = 'user_cap'
                    elif updated.stage == state.stage and updated.n == state.n and updated.failures == state.failures:
                        if state.stage == 0:
                            result = 'stage'
                        elif state.stage in (5, 25):
                            votes = {user[0]: user[1] for user in state.trial_users}
                            result = 'user_cap' if votes.get(witness, 0) >= 3 else 'window_full'
                        else:
                            result = 'user_cap' if dict(state.healthy_users).get(witness, 0) >= 3 else 'window_full'
                    return updated

                key = (target, lang)
                written = await self._cost_update(key, update, failed, expected_identity=identity)
                COST_VOTES.labels(target=target, scope='global' if lang == 'all' else 'language', result=result).inc()
                with self._lock:
                    if self._identity != identity:
                        return
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
        except _IdentityChanged:
            return
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
        identity = self._check_identity()
        now = self._clock()
        try:
            targets = registry()
        except (ValueError, TypeError):
            logger.debug('Cost gate registry invalid; retaining cached state')
            return
        self._init_cost_metrics(targets)
        with self._lock:
            self._cost_interests = {key: seen for key, seen in self._cost_interests.items() if now - seen < 900}
            # All pods observe global targets, including idle/ineligible pods.
            # Language interests still follow actual session traffic.
            self._cost_interests.update({(target.id, 'all'): now for target in targets})
            while len(self._cost_interests) > 256:
                current = {(target.id, 'all') for target in targets}
                expendable = [key for key in self._cost_interests if key not in current]
                self._cost_interests.pop(min(expendable, key=lambda key: self._cost_interests[key]))
            self._cost_preferred = {key: seen for key, seen in self._cost_preferred.items() if now - seen < 15}
            preferred = dict(self._cost_preferred)
            interests = set(self._cost_interests)
        keys = sorted(
            {(target.id, lang) for target in targets for lang in ('all', *sorted(live_stt_state.ROUTED_LANGUAGES))}
            | interests
        )
        if not keys or now < self._redis_retry_at:
            return
        by_id = {target.id: target for target in targets}
        key_targets = {key: by_id.get(key[0]) for key in keys}
        keys = [key for key in keys if key_targets[key] is not None]
        lease_keys = {key: live_stt_state.cost_lease_key(key_targets[key], key[1]) for key in keys if key in preferred}
        redis_keys = [live_stt_state.cost_key(key_targets[key], key[1]) for key in keys]

        async def refresh():
            fleet_now = await self._server_now(identity)
            values = await self._redis().mget(redis_keys)
            if self._check_identity() != identity:
                raise _IdentityChanged('live STT state identity changed')
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

                states[key] = await self._cost_update(key, reconcile, expected_identity=identity)
                with self._lock:
                    if self._cost_local.get(key) == local:
                        self._cost_unreconciled.discard(key)
            for key in preferred:
                state = states.get(key, GateState())
                if state.stage == 0 and state.until <= fleet_now:
                    # One coordinator begins a shared trial; stable UID selection bounds the fleet share.
                    if await self._redis().set(lease_keys[key], '1', nx=True, ex=10):
                        states[key] = await self._cost_update(
                            key, lambda state: begin_trial(state, fleet_now), expected_identity=identity
                        )
            if self._check_identity() != identity:
                return
            with self._lock:
                self._cost_cached = states
                while len(self._cost_cached) > COST_CACHE_CAP:
                    self._cost_cached.pop(next(iter(self._cost_cached)))
                self._cost_fresh = {key: self._clock() for key in states}
                COST_SNAPSHOT_AT.set(fleet_now)
                for target in targets:
                    self._publish_cost_state(target.id, states[(target.id, 'all')])

        try:
            await self._bounded(refresh())
        except _IdentityChanged:
            return
        except Exception:
            if self._check_identity() == identity:
                self._redis_retry_at = self._clock() + 10
            logger.debug('Cost gate refresh using local state', exc_info=True)
