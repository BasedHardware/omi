"""Pure-memory cost selection and task-scoped connection target identity."""

from __future__ import annotations

from contextvars import ContextVar

from config.live_stt_registry import Target, assigned, registry, DEFAULT_IDS, routing_on
from utils.stt.live_gate import GateState, gate_rate
from utils.stt.live_health import bounded_language
from utils.stt.live_metrics import COST_DECISION, COST_SHADOW
from utils.stt.provider_resilience import ProviderCircuitBreaker
from utils.stt.stream_close import ACCOUNT_REJECTION_REASONS

connecting_target: ContextVar[Target | None] = ContextVar('stt_connecting_target', default=None)
_target_circuits: dict[str, ProviderCircuitBreaker] = {}


class TargetEngineMismatch(RuntimeError):
    """The family callback cannot construct the target the router selected."""


def note_failed_route(receiver, family: str | None) -> int:
    targets = getattr(receiver, '_stt_failed_targets', None)
    if targets is None:
        receiver._stt_failed_targets = targets = set()
    try:
        active = routing_on(receiver.host.request.uid)
    except ValueError:
        active = False
    socket = receiver.stt_socket
    target = getattr(socket, 'routing_target', None)
    if (
        active
        and target
        and getattr(socket, '_routing_active', False)
        and (getattr(socket, 'typed_death_reason', None) not in ACCOUNT_REJECTION_REASONS)
    ):
        targets.add(target)
    elif family:
        receiver._stt_failed_providers.add(family)
    return len(receiver._stt_failed_providers) + len(targets)


def engine_matches(target: Target, models: dict[str, str | None] | None) -> bool:
    # Parakeet's actual window/RNNT choice is precomputed by LiveChainSession
    # using window_allocation/window_language_supported and endpoint config.
    return target.family != 'parakeet' or bool(models and models.get('parakeet') == target.id)


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
            if not result:
                COST_DECISION.labels(target=target.id, reason='cost_primary').inc()
            result.append(target)
    return result


def propose(
    health,
    configured_families,
    uid,
    language,
    static_primary,
    account_states=None,
    required_languages=(),
    engine_models=None,
    last_resorts=None,
):
    language = bounded_language(language)
    gate_rate()
    targets = []
    for target in registry():
        if target.family not in configured_families:
            continue
        if not engine_matches(target, engine_models):
            COST_DECISION.labels(target=target.id, reason='capability').inc()
            continue
        targets.append(target)
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
    if last_resorts is not None:
        last_resorts.extend(
            target
            for target in sorted(targets, key=lambda target: target.cost_per_audio_hour)
            if states.get(target.id, GateState()).stage == 0
            and not (
                account_states.get(target.family)
                and account_states[target.family].bench == 'account'
                and account_states[target.family].excluded
            )
            and target.capable(language)
            and all(target.capable(code) for code in required_languages)
            and assigned(uid, target.id, target.ramp())
        )
    chosen = proposed[0].id if proposed else 'unavailable'
    COST_SHADOW.labels(
        agreement=(
            'agree' if proposed and proposed[0].id == DEFAULT_IDS.get(static_primary, static_primary) else 'disagree'
        ),
        target=chosen,
    ).inc()
    return proposed
