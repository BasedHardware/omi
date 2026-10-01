"""Pure-memory cost selection and task-scoped connection target identity."""

from __future__ import annotations

from contextvars import ContextVar

from config.live_stt_registry import Target, assigned, registry, DEFAULT_IDS
from utils.stt.live_gate import GateState, gate_rate
from utils.stt.live_health import bounded_language
from utils.stt.live_metrics import COST_DECISION, COST_SHADOW
from utils.stt.provider_resilience import ProviderCircuitBreaker

connecting_target: ContextVar[Target | None] = ContextVar('stt_connecting_target', default=None)
_target_circuits: dict[str, ProviderCircuitBreaker] = {}


def target_circuit(target: Target | None, default: ProviderCircuitBreaker | None = None) -> ProviderCircuitBreaker:
    if target is None or (target.id == DEFAULT_IDS.get(target.family) and target.endpoint is None):
        if default is None:
            raise ValueError('Default live target requires its family circuit')
        return default
    if target.id not in _target_circuits:
        _target_circuits[target.id] = ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30)
    return _target_circuits[target.id]


def select(targets, states, uid, language, *, features=frozenset({'streaming'}), required_languages=(), recovery=None):
    result = []
    for target in sorted(targets, key=lambda item: item.cost_per_audio_hour):
        state = states.get(target.id, GateState())
        reason = None
        if not target.capable(language, features) or any(
            not target.capable(code, features) for code in required_languages
        ):
            reason = 'capability'
        elif not assigned(uid, target.id, target.ramp()):
            reason = 'ramp_skip'
        elif target.at_capacity():
            reason = 'capacity_skip'
        elif state.stage == 0:
            reason = 'benched_skip'
            if not result and recovery:
                recovery(target.id, language)
        elif not assigned(uid, 'stt-reentry:' + target.id, state.stage):
            reason = 'ramp_skip'
        if reason:
            COST_DECISION.labels(target=target.id, reason=reason).inc()
        else:
            COST_DECISION.labels(target=target.id, reason='cost_primary' if not result else 'failover').inc()
            result.append(target)
    return result


def propose(health, configured_families, uid, language, static_primary, account_states=None, required_languages=()):
    language = bounded_language(language)
    gate_rate()
    targets = [target for target in registry() if target.family in configured_families]
    states = health.cost_snapshot(targets, language)
    account_states = (
        account_states if account_states is not None else health.cached_snapshot(configured_families, language)
    )
    for target in targets:
        account = account_states.get(target.family)
        if account and account.bench == 'account' and account.excluded:
            states[target.id] = GateState(stage=0, until=account.bench_until)
    proposed = select(
        targets, states, uid, language, required_languages=required_languages, recovery=health.prefer_recovery
    )
    chosen = proposed[0].id if proposed else 'unavailable'
    COST_SHADOW.labels(
        agreement=(
            'agree' if proposed and proposed[0].id == DEFAULT_IDS.get(static_primary, static_primary) else 'disagree'
        ),
        target=chosen,
    ).inc()
    return proposed
