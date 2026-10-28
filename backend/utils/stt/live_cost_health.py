"""Fleet-owned cost gate state. All I/O runs in bounded background tasks."""

from __future__ import annotations

from config.policy.listen import routing_mode_raw

import json
import hashlib
import logging
from dataclasses import replace
from abc import ABC, abstractmethod
from typing import Any, Callable, ContextManager

from config import live_stt_state
from config.live_stt_resilience import (
    escape_trial_votes_enabled,
    failover_surge_censor_enabled,
    sole_primary_hold_enabled,
)
from config.live_stt_registry import DEFAULT_TARGETS, Target, registry, assigned
from utils.stt.live_gate import GateState, begin_trial, transition, generation_allows, reset_generation_floor
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
    COST_ESCAPE_VOTES,
    MANAGED_LEGS_OPENED,
    MANAGED_LEGS_SETTLED,
    MANAGED_LEGS_OPEN,
    record_fleet_health_write_dropped,
    record_fleet_health_write_written,
    safe_counter_increment,
)
from utils.stt.live_signal import provider_observation
from utils.stt.live_reason import LIVE_STT_REASONS, normalize_live_stt_reason
from utils.observability.reasons import LiveSttReason, ReasonFamily, reason_label

logger = logging.getLogger(__name__)


class CostHealthUnavailable(RuntimeError):
    """Expected missing cache during a Redis outage; selection uses static order."""

    def __init__(self, message: str, *, states: dict[str, GateState] | None = None) -> None:
        super().__init__(message)
        self.states = states if states is not None else {}


class _IdentityChanged(RuntimeError):
    """An awaited write observed a different environment identity than queued."""


class _RedisCallFailed(RuntimeError):
    """A Redis operation itself failed, as distinct from post-commit bookkeeping."""


class _CostStateContention(RuntimeError):
    """The bounded CAS loop lost all retries without a Redis call failure."""


def trial_minimum_share(uid: str, entry: Target) -> int:
    """Smallest trial stage whose re-entry cohort holds this user (100: none).

    A vote is dropped while ``0 < stage < minimum_share``; 0 admits it at
    every trial stage (used while the escape serves the user).
    """
    if not assigned(uid, entry.id, entry.ramp()):
        return 100
    if assigned(uid, 'stt-reentry:' + entry.id, 5):
        return 5
    return 25 if assigned(uid, 'stt-reentry:' + entry.id, 25) else 100


COST_CACHE_CAP = 4096
CAS = """
local current = redis.call('GET', KEYS[1])
if (current or '') ~= ARGV[1] then return 0 end
local encoded = ARGV[2]
local ttl = tonumber(ARGV[3])
local result = 1
if ARGV[4] == 'hold' then
    local guard = false
    local guard_indices = cjson.decode(ARGV[6])
    local full_share = false
    for index = 2, #KEYS, 2 do
        local global = redis.call('GET', KEYS[index])
        local language = redis.call('GET', KEYS[index + 1])
        local stage = math.min(global and cjson.decode(global).stage or 100,
                               language and cjson.decode(language).stage or 100)
        for _, guard_index in ipairs(guard_indices) do
            if index == guard_index and stage >= 5 then guard = true end
        end
        if stage == 100 then full_share = true end
    end
    if guard and not full_share then
        encoded = ARGV[5]
        ttl = 0
        result = 2
    end
end
redis.call('SET', KEYS[1], encoded)
if ttl > 0 then redis.call('EXPIRE', KEYS[1], ttl) end
if #KEYS == 2 then
    local clock = redis.call('TIME')
    local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
    local seconds = tonumber(ARGV[4])
    redis.call('SET', KEYS[2], tostring(now + seconds), 'EX', seconds)
end
return result
"""

# A bench mass-failovers long-lived sessions onto the remaining targets over
# tens of minutes. 2026-10-28: the parakeet benches at 19:07/19:43Z pushed a
# death cluster onto soniox that burst-benched it 81 minutes after the last
# bench; 2026-10-20's second failure pulse ran 70 minutes after the 13:10Z
# parakeet bench. 90 minutes covers both timelines.
FAILOVER_SURGE_CENSOR_SECONDS = 90 * 60

# 2026-10-28: modulate-velma-2 promoted to the only stage-100 primary at a
# 6.2% trial rate while soniox trialed healthy at stage 5, then served ~9%
# failure for six hours. While the guard target is at stage >= 5, the held
# target may not become the only stage-100 primary.
SOLE_PRIMARY_FAMILY = 'modulate'
SOLE_PRIMARY_GUARD_FAMILY = 'soniox'


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
    _cost_surge_until: dict[str, float]
    _cost_server_offset: float

    @abstractmethod
    def _redis(self) -> Any:
        raise NotImplementedError

    @abstractmethod
    async def _bounded(self, operation: Any) -> Any:
        raise NotImplementedError

    @abstractmethod
    def schedule(self, coroutine: Any, *, write_path: str, kind: str) -> None:
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
        self._cost_surge_until = {}
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
                for boundary in ('client_gone', 'owner_teardown', 'pod_draining', 'failover_surge'):
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
        try:
            seconds, micros = await self._redis().time()
        except Exception as exc:
            raise _RedisCallFailed('Redis TIME failed') from exc
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

    def _effective_stages(self, uid: str, language: str) -> dict[str, int]:
        """Gate stage of every registry target that could serve this user.

        Mirrors ``live_router.select``'s escape test without capacity: a target
        counts when it is capable of the language and the user is inside its
        config ramp. Uses the same conservative global/language view.
        """
        try:
            targets = registry()
        except (ValueError, TypeError):
            return {}
        try:
            # A malformed ramp (e.g. strict window percent) proves nothing:
            # keep the cohort-only rule rather than guess an escape.
            servable = [
                target for target in targets if target.capable(language) and assigned(uid, target.id, target.ramp())
            ]
        except (ValueError, TypeError):
            return {}
        now = self._clock()
        stages: dict[str, int] = {}
        with self._lock:
            for target in servable:
                stage = 100
                for lang in ('all', language):
                    key = (target.id, lang)
                    stage = min(stage, self._cost_view(key, self._cost_is_fresh(key, now)).stage)
                stages[target.id] = stage
        return stages

    def cost_stage(self, target: str, language: str) -> int:
        """Conservative (global/language minimum) gate stage; no side effects."""
        now = self._clock()
        with self._lock:
            return min(
                self._cost_view((target, lang), self._cost_is_fresh((target, lang), now)).stage
                for lang in ('all', language)
            )

    def _open_failover_surge(self, benched: str, until: float | None = None) -> None:
        """Open the failover-surge window on every target that inherits the legs.

        Benching a target mass-failovers its in-flight sessions onto the
        remaining targets; their connect deaths in the window are censored
        from burst evidence (2026-10-28 burst bench at a 1.0% rate).
        """
        try:
            others = [entry.id for entry in registry() if entry.id != benched]
        except (ValueError, TypeError):
            return
        now = self._fleet_now()
        with self._lock:
            for target in others:
                deadline = until if until is not None else now + FAILOVER_SURGE_CENSOR_SECONDS
                if deadline > self._cost_surge_until.get(target, 0.0):
                    self._cost_surge_until[target] = deadline
            if len(self._cost_surge_until) > 64:
                for target in [key for key, until in self._cost_surge_until.items() if until <= now]:
                    del self._cost_surge_until[target]

    def _failover_surge_open(self, target: str, now: float) -> bool:
        return failover_surge_censor_enabled() and now < self._cost_surge_until.get(target, 0.0)

    async def _fresh_failover_surge(self, target: str, now: float, identity: str) -> bool:
        """A failed vote must see source benches committed before its Redis time.

        Snapshot cadence is not a censor boundary: a different pod can bench
        a source and overload this target before this pod's next refresh.
        """
        if not failover_surge_censor_enabled():
            return False
        sources = [entry for entry in registry() if entry.id != target]
        if sources:
            try:
                values = await self._redis().mget([live_stt_state.cost_surge_key(entry) for entry in sources])
            except Exception as exc:
                raise _RedisCallFailed('Redis surge MGET failed') from exc
            if self._check_identity() != identity:
                raise _IdentityChanged('live STT state identity changed')
            for source, raw in zip(sources, values):
                if raw:
                    self._open_failover_surge(source.id, float(raw))
        return self._failover_surge_open(target, now)

    def _sole_primary_blocked(self, target: str, stages: dict[str, int]) -> bool:
        """Held target may not become the only stage-100 share (2026-10-28)."""
        entry = self._cost_target(target)
        guards = {entry.id for entry in registry() if entry.family == SOLE_PRIMARY_GUARD_FAMILY}
        if (
            entry is None
            or entry.family != SOLE_PRIMARY_FAMILY
            or not any(stages.get(guard, 0) >= 5 for guard in guards)
        ):
            return False
        return all(stage < 100 for other, stage in stages.items() if other != target)

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
        if not uid or routing_mode_raw() == 'off':
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
        minimum_share = trial_minimum_share(uid, entry)
        now = self._clock()
        stages = self._effective_stages(uid, language)
        promotion_stages = {
            candidate.id: stages[candidate.id]
            for candidate in registry()
            if candidate.id in stages and not candidate.at_capacity()
        }
        if minimum_share > 0 and escape_trial_votes_enabled() and assigned(uid, target, entry.ramp()):
            if stages and all(stage < 100 for stage in stages.values()):
                # No stage-100 target serves this user: the escape routed
                # them here regardless of the re-entry cohort, so their
                # outcome is real trial evidence. Dropping it starved
                # promotion for hours (2026-10-20: 240 dropped vs 4 counted).
                if 0 < stages.get(target, 100) < minimum_share:
                    safe_counter_increment(
                        COST_ESCAPE_VOTES, metric_name='omi_stt_cost_routing_escape_votes_total', target=target
                    )
                minimum_share = 0
        surge = failed and self._failover_surge_open(target, self._fleet_now())
        if surge:
            COST_IGNORED_DEATHS.labels(
                target=target,
                reason=reason_label(ReasonFamily.LIVE_STT, reason, LiveSttReason),
                boundary='failover_surge',
            ).inc()
        hold = (
            sole_primary_hold_enabled()
            and entry.family == SOLE_PRIMARY_FAMILY
            and self._sole_primary_blocked(target, promotion_stages)
        )
        with self._lock:
            for lang in ('all', language):
                key = (target, lang)
                state = self._cost_local.get(key, GateState())
                cached = self._cost_cached.get(key)
                if cached is not None and cached.generation > state.generation:
                    state = cached
                if 0 < state.stage < minimum_share:
                    continue
                if generation_allows(
                    state.generation,
                    generations.get(lang) if generations is not None else None,
                    connect=outcome == 'connect_failure',
                ):
                    updated = transition(
                        state,
                        failed,
                        self._fleet_now(),
                        witness=witness,
                        language_only=lang != 'all',
                        failover_surge=surge,
                        block_full_share=hold,
                    )
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
                target,
                language,
                failed,
                generations,
                witness,
                minimum_share,
                promotion_targets=tuple(promotion_stages),
                connect=outcome == 'connect_failure',
                expected_identity=identity,
            ),
            write_path='cost_routing_result',
            kind='result',
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
        self.schedule(
            self._write_cost_quarantine(target, update, expected_identity=identity),
            write_path='cost_bench',
            kind='bench',
        )

    async def _write_cost_quarantine(
        self,
        target: str,
        update: Callable[[GateState], GateState],
        *,
        expected_identity: str | None = None,
    ) -> None:
        write_committed = False
        write_dropped = False

        def record_commit() -> None:
            nonlocal write_committed
            if not write_committed:
                write_committed = True
                record_fleet_health_write_written(write_path='cost_bench', kind='bench')

        def record_drop(reason: str) -> None:
            nonlocal write_dropped
            if write_committed and reason != 'identity_changed_after_commit':
                return
            if not write_dropped:
                write_dropped = True
                record_fleet_health_write_dropped(write_path='cost_bench', kind='bench', reason=reason)

        async def write():
            identity = self._check_identity()
            if expected_identity is not None and identity != expected_identity:
                raise _IdentityChanged('live STT state identity changed')
            await self._server_now(identity)
            await self._cost_update(
                (target, 'all'),
                update,
                expected_identity=identity,
                on_commit=record_commit,
                on_identity_changed=record_drop,
            )

        try:
            await self._bounded(write())
        except _IdentityChanged:
            record_drop('identity_changed_after_commit' if write_committed else 'identity_changed')
            return
        except (_RedisCallFailed, TimeoutError):
            self._redis_retry_at = self._clock() + 10
            if not write_committed:
                record_drop('redis_error')
            logger.debug('STT cost-bench Redis write failed', exc_info=True)
        except Exception:
            if not write_committed:
                record_drop('redis_error')
            logger.debug('STT cost-bench write bookkeeping failed', exc_info=True)

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
        if event == 'bench':
            self._open_failover_surge(target)
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
        on_commit: Callable[[], None] | None = None,
        on_identity_changed: Callable[[str], None] | None = None,
        hold_update: Callable[[GateState], GateState] | None = None,
        promotion_targets: tuple[str, ...] | None = None,
    ) -> GateState:
        identity = self._check_identity()
        if expected_identity is not None and identity != expected_identity:
            raise _IdentityChanged('live STT state identity changed')
        target = self._cost_target(key[0])
        if target is None:
            raise RuntimeError('cost state target not in registry')
        redis_key = live_stt_state.cost_key(target, key[1])
        for _ in range(5):
            try:
                raw = await self._redis().get(redis_key)
            except Exception as exc:
                raise _RedisCallFailed('Redis GET failed') from exc
            if self._check_identity() != identity:
                raise _IdentityChanged('live STT state identity changed')
            if raw:
                old = GateState.decode(json.loads(raw))
            else:
                # Healthy evidence may expire, but a reset fence must outlive
                # even long-lived pre-reset sessions and outstanding dials.
                try:
                    floor = await self._redis().get(live_stt_state.cost_reset_key(target))
                except Exception as exc:
                    raise _RedisCallFailed('Redis reset generation GET failed') from exc
                if self._check_identity() != identity:
                    raise _IdentityChanged('live STT state identity changed')
                old = GateState(generation=reset_generation_floor(floor))
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
            try:
                bench = old.stage != 0 and new.stage == 0
                keys = [redis_key, live_stt_state.cost_surge_key(target)] if bench else [redis_key]
                extra = [FAILOVER_SURGE_CENSOR_SECONDS] if bench else []
                held = None
                if old.stage == 25 and new.stage == 100 and hold_update is not None:
                    # Eligibility is captured for the actual serving user and
                    # language before hashing the witness. An incapable or
                    # withdrawn target cannot count as a full-share escape.
                    others = [
                        entry
                        for entry in registry()
                        if entry.id != target.id
                        and (
                            entry.id in promotion_targets
                            if promotion_targets is not None
                            else entry.family == SOLE_PRIMARY_GUARD_FAMILY and entry.capable(key[1])
                        )
                    ]
                    guard_indices = [
                        2 + 2 * i for i, entry in enumerate(others) if entry.family == SOLE_PRIMARY_GUARD_FAMILY
                    ]
                    if guard_indices:
                        held = hold_update(old)
                        keys += [live_stt_state.cost_key(entry, lang) for entry in others for lang in ('all', key[1])]
                        extra = ['hold', json.dumps(held.encode(), separators=(',', ':')), json.dumps(guard_indices)]
                committed = await self._redis().eval(
                    CAS,
                    len(keys),
                    *keys,
                    raw or '',
                    encoded,
                    900 if new.stage == 100 else 0,
                    *extra,
                )
            except Exception as exc:
                raise _RedisCallFailed('Redis cost-state CAS failed') from exc
            if committed:
                if committed == 2 and held is not None:
                    new = held
                if on_commit is not None:
                    try:
                        on_commit()
                    except Exception:
                        logger.debug('Cost-state commit metric callback failed', exc_info=True)
                try:
                    identity_changed = self._check_identity() != identity
                except Exception:
                    logger.debug('Cost-state post-commit identity check failed', exc_info=True)
                    return new
                if identity_changed:
                    if on_identity_changed is not None:
                        try:
                            on_identity_changed('identity_changed_after_commit')
                        except Exception:
                            logger.debug('Cost-state post-commit identity metric callback failed', exc_info=True)
                    return new
                try:
                    with self._lock:
                        self._cost_cached[key] = new
                        self._cost_fresh[key] = self._clock()
                except Exception:
                    logger.debug('Cost-state post-commit cache update failed', exc_info=True)
                try:
                    self._cost_event(key[0], key[1], old, new, failed)
                except Exception:
                    logger.debug('Cost-state post-commit metric update failed', exc_info=True)
                return new
        raise _CostStateContention('cost state contention')

    async def _write_cost_result(
        self,
        target: str,
        language: str,
        failed: bool,
        generations: dict[str, int] | None,
        witness: str,
        minimum_share: int = 5,
        *,
        connect: bool = False,
        expected_identity: str | None = None,
        promotion_targets: tuple[str, ...] | None = None,
    ) -> None:
        write_committed = False
        write_dropped = False

        def record_commit() -> None:
            nonlocal write_committed
            if not write_committed:
                write_committed = True
                record_fleet_health_write_written(write_path='cost_routing_result', kind='result')

        def record_drop(reason: str) -> None:
            nonlocal write_dropped
            if write_committed and reason != 'identity_changed_after_commit':
                return
            if not write_dropped:
                write_dropped = True
                record_fleet_health_write_dropped(write_path='cost_routing_result', kind='result', reason=reason)

        async def write():
            identity = self._check_identity()
            if expected_identity is not None and identity != expected_identity:
                raise _IdentityChanged('live STT state identity changed')
            now = await self._server_now(identity)
            surge = failed and await self._fresh_failover_surge(target, now, identity)
            entry = self._cost_target(target)
            guarded = sole_primary_hold_enabled() and entry is not None and entry.family == SOLE_PRIMARY_FAMILY
            for lang in ('all', language):
                result = 'applied'

                def update(state: GateState, lang: str = lang, *, hold: bool = False) -> GateState:
                    nonlocal result
                    result = 'applied'
                    if 0 < state.stage < minimum_share:
                        result = 'stage'
                        return state
                    if not generation_allows(
                        state.generation, generations.get(lang) if generations is not None else None, connect=connect
                    ):
                        result = 'generation'
                        return state
                    updated = transition(
                        state,
                        failed,
                        now,
                        witness=witness,
                        language_only=lang != 'all',
                        failover_surge=surge,
                        block_full_share=hold,
                    )
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
                written = await self._cost_update(
                    key,
                    update,
                    failed,
                    expected_identity=identity,
                    on_commit=record_commit,
                    on_identity_changed=record_drop,
                    hold_update=(lambda state: update(state, hold=True)) if guarded else None,
                    promotion_targets=promotion_targets,
                )
                if write_committed and write_dropped:
                    return
                # The counter records the logical write once, after the first successful CAS.
                # Repeated scope updates belong to the same scheduled write.
                safe_counter_increment(
                    COST_VOTES,
                    metric_name='omi_stt_cost_routing_votes_total',
                    target=target,
                    scope='global' if lang == 'all' else 'language',
                    result=result,
                )
                with self._lock:
                    if self._identity != identity:
                        record_drop('identity_changed_after_commit' if write_committed else 'identity_changed')
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

        if self._clock() < self._redis_retry_at:
            record_drop('redis_backoff')
            return

        try:
            await self._bounded(write())
        except _IdentityChanged:
            record_drop('identity_changed_after_commit' if write_committed else 'identity_changed')
            return
        except (_RedisCallFailed, TimeoutError):
            with self._lock:
                for lang in ('all', language):
                    key = (target, lang)
                    local = self._cost_local.get(key, GateState())
                    if local.stage == 0:
                        if key not in self._cost_unreconciled:
                            try:
                                self._cost_event(target, lang, GateState(), local, local=True)
                            except Exception:
                                logger.debug('Cost-routing failure metric update failed', exc_info=True)
                        self._cost_unreconciled.add(key)
            if not write_committed:
                record_drop('redis_error')
            self._redis_retry_at = self._clock() + 10
            logger.debug('STT cost-routing Redis write failed', exc_info=True)
        except Exception:
            if not write_committed:
                record_drop('redis_error')
            logger.debug('STT cost-routing write bookkeeping failed', exc_info=True)

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
        reset_keys = [live_stt_state.cost_reset_key(target) for target in targets]
        surge_keys = [live_stt_state.cost_surge_key(target) for target in targets]

        async def refresh():
            fleet_now = await self._server_now(identity)
            values = await self._redis().mget([*redis_keys, *reset_keys, *surge_keys])
            if self._check_identity() != identity:
                raise _IdentityChanged('live STT state identity changed')
            if not isinstance(values, list) or len(values) != len(keys) + len(reset_keys) + len(surge_keys):
                raise ValueError('invalid cost gate snapshot')
            floors = {target.id: reset_generation_floor(raw) for target, raw in zip(targets, values[len(keys) :])}
            surge_deadlines = {
                target.id: float(raw) for target, raw in zip(targets, values[len(keys) + len(reset_keys) :]) if raw
            }
            states = {
                key: GateState.decode(json.loads(raw)) if raw else GateState(generation=floors[key[0]])
                for key, raw in zip(keys, values[: len(keys)])
            }
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
            # Shared deadlines survive cold pods and the source's 0->5 trial.
            # Repeated snapshots must never extend the original window.
            for target, deadline in surge_deadlines.items():
                self._open_failover_surge(target, deadline)

        try:
            await self._bounded(refresh())
        except _IdentityChanged:
            return
        except Exception:
            if self._check_identity() == identity:
                self._redis_retry_at = self._clock() + 10
            logger.debug('Cost gate refresh using local state', exc_info=True)
