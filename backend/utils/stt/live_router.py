"""Pure-memory cost selection and task-scoped connection target identity."""

from __future__ import annotations

from contextvars import ContextVar
import threading
import time

from config import live_stt_state
from config.live_stt_registry import Target, assigned, registry, DEFAULT_IDS, routing_on
from config.stt_provider_policy import MODULATE_SUPPORTED_LANGUAGES, PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL
from utils.stt.live_gate import GateState, gate_rate
from utils.stt.live_health import bounded_language
from utils.stt.live_metrics import COST_DECISION, COST_SHADOW, COST_ALL_DEGRADED
from utils.stt.provider_resilience import ProviderCircuitBreaker
from utils.stt.stream_close import ACCOUNT_REJECTION_REASONS

connecting_target: ContextVar[Target | None] = ContextVar('stt_connecting_target', default=None)
_target_circuits: dict[str, ProviderCircuitBreaker] = {}
_target_circuits_lock = threading.Lock()
_TARGET_CIRCUITS_CAP = 64
_capacity_until: dict[str, float] = {}
_capacity_lock = threading.Lock()
_CAPACITY_COOLDOWN_SECONDS = 5.0
_capacity_clock = time.monotonic


def capacity_available(target: Target) -> bool:
    if target.at_capacity():
        return False
    with _capacity_lock:
        return _capacity_clock() >= _capacity_until.get(target.id, 0)


def note_capacity_full(target_id: str) -> None:
    with _capacity_lock:
        now = _capacity_clock()
        _capacity_until[target_id] = now + _CAPACITY_COOLDOWN_SECONDS
        if len(_capacity_until) > 64:
            del _capacity_until[min(_capacity_until, key=lambda identity: _capacity_until[identity])]


def capacity_refused_at(target: Target) -> float:
    with _capacity_lock:
        return _capacity_until.get(target.id, 0) - _CAPACITY_COOLDOWN_SECONDS


class TargetEngineMismatch(RuntimeError):
    """The family callback cannot construct the target the router selected."""


CAPABILITY_FAMILIES = frozenset({'parakeet', 'modulate', 'soniox'})


def _family_supports(target: Target, language: str, engine_models: dict[str, str | None] | None) -> bool:
    lang = language.strip().lower().split('-', 1)[0]
    if target.family == 'parakeet':
        engine = (engine_models or {}).get('parakeet')
        model = 'nvidia/parakeet-tdt-0.6b-v3' if engine == 'parakeet-window' else 'nvidia/parakeet-rnnt-1.1b'
        return lang in PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL[model]
    if target.family == 'modulate':
        return lang in MODULATE_SUPPORTED_LANGUAGES
    return target.family == 'soniox'


def permission_reason(
    target: Target,
    uid: str | None,
    language: str | None,
    required_languages=(),
    engine_models: dict[str, str | None] | None = None,
    account_states=None,
) -> str | None:
    """Closed deny reason for one target, or None when dialing is permitted."""
    if 'streaming' not in target.features:
        return 'capability'
    if not engine_matches(target, engine_models):
        return 'capability'
    lang = (language or '').strip().lower().split('-', 1)[0]
    if target.family in CAPABILITY_FAMILIES:
        if target.languages and (not lang or lang not in target.languages):
            return 'capability'
        if lang and not _family_supports(target, lang, engine_models):
            return 'capability'
        if any(
            (target.languages and code.strip().lower().split('-', 1)[0] not in target.languages)
            or not _family_supports(target, code, engine_models)
            for code in required_languages
        ):
            return 'capability'
    elif target.languages:
        if not lang or lang not in target.languages:
            return 'capability'
    ramp = target.ramp()
    if uid is None:
        if ramp < 100:
            return 'ramp_skip'
    elif not assigned(uid, target.id, ramp):
        return 'ramp_skip'
    state = (account_states or {}).get(target.family)
    if state is not None and state.bench == 'account' and state.excluded:
        return 'benched_skip'
    return None


def permitted_target(
    target: Target,
    uid: str | None,
    language: str | None,
    required_languages=(),
    engine_models: dict[str, str | None] | None = None,
    account_states=None,
) -> bool:
    """Hard permission for one target: engine, capability, ramp, account bench.

    Config ramps and explicit capability restrictions withdraw a target for
    every execution path, including static order and router faults. A UID-less
    caller keeps legacy 100% routes but cannot claim a partial cohort.
    """
    return permission_reason(target, uid, language, required_languages, engine_models, account_states) is None


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


def _circuit_identity(target: Target) -> str:
    return f'{target.family}@{live_stt_state.circuit_prefix(target.family, endpoint=live_stt_state.target_endpoint(target))}'


class _TargetCircuitAdmissionRefused(ProviderCircuitBreaker):
    def allow_request(self, *, max_probes: int = 1, force: bool = False) -> bool:
        return False

    def cooldown_elapsed(self) -> bool:
        return False

    @property
    def state(self) -> str:
        return 'open'


_target_circuit_admission_refused = _TargetCircuitAdmissionRefused(failure_threshold=3, cooldown_seconds=30)


def target_circuit(target: Target | None, default: ProviderCircuitBreaker | None = None) -> ProviderCircuitBreaker:
    if target is None or target.endpoint is None:
        if default is None:
            raise ValueError('Default live target requires its family circuit')
        return default
    identity = _circuit_identity(target)
    account = live_stt_state.fleet_prefix(target.family, account=True)
    with _target_circuits_lock:
        circuit = _target_circuits.get(identity)
        if circuit is None:
            if len(_target_circuits) >= _TARGET_CIRCUITS_CAP:
                evicted = next(
                    (key for key, entry in _target_circuits.items() if entry.state == 'closed'),
                    None,
                )
                if evicted is None:
                    return _target_circuit_admission_refused
                del _target_circuits[evicted]
            circuit = _target_circuits[identity] = ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30)
        circuit.sync_account_identity(account)
    return circuit


def select(targets, states, uid, language, *, features=frozenset({'streaming'}), required_languages=(), recovery=None):
    eligible, available, result = [], [], []
    for target in sorted(targets, key=lambda item: item.cost_per_audio_hour):
        if not target.capable(language, features) or any(
            not target.capable(code, features) for code in required_languages
        ):
            reason = 'capability'
        elif not assigned(uid, target.id, target.ramp()):
            reason = 'ramp_skip'
        else:
            eligible.append(target)
            if capacity_available(target):
                available.append(target)
                continue
            reason = 'capacity_skip'
        COST_DECISION.labels(target=target.id, reason=reason).inc()

    for target in available:
        state = states.get(target.id, GateState())
        terminal = target == available[-1]
        absorbs = any(
            states.get(t.id, GateState()).stage == 100
            for t in available
            if t != target and t.cost_per_audio_hour <= target.cost_per_audio_hour
        )
        protected = terminal and not absorbs
        if state.stage == 0:
            COST_DECISION.labels(target=target.id, reason='benched_skip').inc()
            if not result and recovery:
                recovery(target.id, language)
        elif not assigned(uid, 'stt-reentry:' + target.id, state.stage) and not protected:
            COST_DECISION.labels(target=target.id, reason='ramp_skip').inc()
        if protected or (state.stage > 0 and assigned(uid, 'stt-reentry:' + target.id, state.stage)):
            result.append(target)

    def health_order(target):
        state = states.get(target.id, GateState())
        return -state.stage, state.failures / state.n if state.n else 0, target.cost_per_audio_hour

    if available and all(states.get(target.id, GateState()).stage < 100 for target in available):
        # Availability escape: health stages demote, they cannot remove the
        # whole chain. Config ramps and account gates remain hard exclusions.
        result = sorted(available, key=health_order)
    elif not result and eligible:
        # All capacity-signalled/cooled: normal admission decides one escape.
        result = sorted(eligible, key=capacity_refused_at)
    if result:
        if all(states.get(target.id, GateState()).stage < 100 for target in (available or eligible)):
            COST_ALL_DEGRADED.labels(target=result[0].id).inc()
        COST_DECISION.labels(target=result[0].id, reason='cost_primary').inc()
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
    account_states = (
        account_states if account_states is not None else health.cached_snapshot(configured_families, language)
    )
    targets = []
    for target in registry():
        if target.family not in configured_families:
            continue
        reason = permission_reason(target, uid, language, required_languages, engine_models, account_states)
        if reason is not None:
            COST_DECISION.labels(target=target.id, reason=reason).inc()
            continue
        targets.append(target)
    states = health.cost_snapshot(targets, language)
    proposed = select(
        targets, states, uid, language, required_languages=required_languages, recovery=health.prefer_recovery
    )
    if last_resorts is not None:
        last_resorts.extend(
            target
            for target in sorted(targets, key=lambda target: target.cost_per_audio_hour)
            if states.get(target.id, GateState()).stage < 100
            and target not in proposed
            and permitted_target(target, uid, language, required_languages, engine_models, account_states)
            and capacity_available(target)
        )
    chosen = proposed[0].id if proposed else 'unavailable'
    static_target = (
        (engine_models or {}).get('parakeet')
        if static_primary == 'parakeet'
        else DEFAULT_IDS.get(static_primary, static_primary)
    )
    ids = {target.id for target in registry()}
    static_target = static_target if static_target in ids else 'unregistered'
    COST_SHADOW.labels(
        agreement='agree' if chosen == static_target else 'disagree',
        static_primary=static_target,
        proposed_primary=chosen,
    ).inc()
    return proposed
