"""Configured live connection attempts; legacy routing stays in streaming.py."""

from __future__ import annotations

from config.policy.listen import listen_value

import asyncio
import logging
import threading
import time
from collections import deque
from typing import TYPE_CHECKING, Awaitable, Callable, Mapping

if TYPE_CHECKING:
    from utils.stt.streaming import STTService

from config.stt_provider_policy import DEEPGRAM_PROVIDERS, provider_for_model_token, provider_for_service
from utils.observability.fallback import record_fallback
from utils.stt.connect_metrics import CONNECT_FAILURE, CONNECT_SUCCESS, record_stt_provider_connect
from utils.stt.live_failure import PendingLiveFailover, fallback_metric_reason
from utils.stt.live_outcome import LiveLegOutcome, record_managed_leg_handoff
from utils.stt.live_reason import LIVE_STT_REASONS, normalize_live_stt_reason
from utils.stt.live_signal import provider_observation
from utils.observability.demand_cohort import record_metric
from utils.observability.demand_cohort import demand_cohort
from utils.stt.live_metrics import CHAIN_EXHAUSTED, LEG_ATTEMPTS, ROUTING_DECISION_LATENCY, WINDOW_ADMISSION
from utils.stt.live_health import health, bounded_language, mode as routing_mode
from utils.stt.live_router import (
    connecting_target,
    permitted_target,
    propose,
    target_circuit,
    TargetEngineMismatch,
    engine_matches,
    capacity_available,
    note_capacity_full,
    capacity_refused_at,
)
from config.live_stt_registry import routing_on, DEFAULT_IDS, registry, Target
from config.live_stt_recovery import recovery_enabled
from utils.stt.recovery_state import current_recovery
from utils.stt.replay_delivery import abort_replay_socket
from utils.stt.live_cost_health import CostHealthUnavailable
from utils.stt.live_gate import GateState
from utils.stt.connect_backoff import ConnectLease, connect_backoff
from utils.stt.live_metrics import CONNECT_BACKOFF, COST_DECISION, COST_FAIL_OPEN, COST_NO_PERMITTED_TARGET
from utils.stt.live_metrics import SAME_TARGET_RETRIES
from utils.stt.live_retry import RETRY_JITTER_SECONDS, retry_jitter_seconds, same_target_retry_allowed
from utils.stt.pod_drain import is_draining
from utils.stt.provider_resilience import (
    EXPECTED_REJECTIONS,
    ProviderCircuitBreaker,
    close_rejected_socket,
    fallback_socket_is_serving,
)
from utils.stt.socket import STTSocket
from utils.stt import parakeet_window as window
from utils.stt.stream_close import ACCOUNT_REJECTION_REASONS, PROVIDER_RATE_LIMITED
from utils.stt import paid_admission

Connect = Callable[[], Awaitable[STTSocket | None]]
logger = logging.getLogger(__name__)


def _connect_backoff_event(provider: str, event: str) -> None:
    CONNECT_BACKOFF.labels(provider=provider, event=event).inc()


connect_backoff().on_event = _connect_backoff_event
_connect_failure_lock = threading.Lock()
_FAILURE_EVIDENCE_SECONDS = 60.0
_recent_connect_failures: deque[tuple[float, str]] = deque(maxlen=1000)


def _connect_failures_before_shed() -> int:
    try:
        return min(1000, max(1, int(listen_value('shed_connect_failures', 'STT_SHED_CONNECT_FAILURES', '3'))))
    except ValueError:
        return 3


def _note_connect_result(*, failed_provider: str | None) -> None:
    with _connect_failure_lock:
        if failed_provider is None:
            _recent_connect_failures.clear()
        else:
            _recent_connect_failures.append((time.monotonic(), failed_provider))


def _safe_cost_stage(identity: str, language: str | None) -> int:
    """Gate stage for a static/shadow route; unknown state never blocks a retry."""
    try:
        return health.cost_stage(identity, bounded_language(language))
    except Exception:
        return 100


def failure_reason(error: BaseException) -> str:
    from utils.stt.streaming import (
        DeepgramConnectionRejection,
        ModulateConnectionRejection,
        ParakeetConnectionError,
    )

    if isinstance(error, DeepgramConnectionRejection) or getattr(error, 'reason', None) == 'auth':
        return 'auth'
    if isinstance(error, ModulateConnectionRejection):
        # Velma answered the upgrade with account state (402 payment / 429
        # insufficient credits) or a rate limit; .reason is already the bounded
        # token, so provider_budget_exhausted reaches the ACCOUNT_REJECTION
        # handling below instead of collapsing into provider_5xx.
        return error.reason
    if isinstance(error, ParakeetConnectionError):
        # The window leg's startup latch defaults to a typed token, but a
        # wrapper that hands back an unlatched value would slip past the
        # vocabulary here and resurface downstream as the ``other`` metric
        # bucket (P59).
        reason = error.reason
        return reason if reason in LIVE_STT_REASONS else 'provider_5xx'
    if isinstance(error, TimeoutError):
        return 'timeout'
    if getattr(error, 'reason', None) == 'provider_rate_limited':
        return 'provider_429'
    return 'provider_5xx'


def dial_failure_reason(error: BaseException) -> str:
    """Typed reason for a candidate dial that raised, never a metric bucket.

    ``RejectedStream`` carries our own refusal of the dial, so a reason the
    live vocabulary cannot name (a selection sentinel raised through a nested
    chain, any unclassified token) is our side of the fence, not the
    provider's: it types as ``config_incomplete`` — censored for provider
    evidence, exactly like the ``other`` bucket it replaces. The former
    ``default='other'`` here latched the fallback metric's bucket token onto
    leg outcomes, so a Soniox leg death surfaced as ``reason=other`` on every
    later failover hop (2026-10-22 P59: 0.5 -> 37.5/h on the live-tail
    catch-up train 72936c9).
    """
    raw = error.reason if isinstance(error, RejectedStream) else failure_reason(error)
    return normalize_live_stt_reason(raw, default='config_incomplete')


class RejectedStream(RuntimeError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class LiveChainExhausted(RuntimeError):
    """Every configured candidate was refused inside one dial — terminal for
    the episode, so the owner latches exhaustion instead of redialing."""


class ProviderChainUnavailable(RuntimeError):
    def __init__(self, retry_after: int):
        self.retry_after = max(1, min(retry_after, 3600))
        super().__init__('Configured STT chain exhausted: providers unavailable')


class NoPermittedTarget(ProviderChainUnavailable):
    """Every configured route is withdrawn by ramp, capability, or account bench."""


async def _allow_rescue_probe(circuit: ProviderCircuitBreaker, probes: int, deadline: float) -> bool:
    """Wait for another bounded recovery handshake instead of exhausting a burst."""
    while True:
        if circuit.allow_request(max_probes=probes, force=True):
            return True
        if circuit.state != 'half_open' or not circuit.account_cooldown_elapsed():
            return False
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(0.01)


async def connect_configured_chain(
    *,
    primary_service: STTService,
    connect_primary: Connect,
    callbacks: Mapping[STTService, Connect | None],
    failed: set[str],
    models: list[str],
    routing_uid: str | None = None,
    routing_language: str | None = None,
    routing_languages: tuple[str, ...] = (),
    routing_models: dict[str, str | None] | None = None,
    failed_targets: set[str] | None = None,
    _routing_static: bool = False,
    optional_handover: bool = False,
) -> tuple[STTSocket, STTService]:
    from utils.stt.streaming import STTService, _circuit_for_primary  # type: ignore[reportPrivateUsage]  # shared circuit owner

    recovery_on = recovery_enabled()
    ordered: list[STTService] = []
    for model in models:
        provider = provider_for_model_token(model)
        if provider is None:
            continue
        service = STTService.deepgram if provider in DEEPGRAM_PROVIDERS else STTService(provider)
        if service != primary_service and service not in ordered:
            ordered.append(service)
    callbacks = {**callbacks, primary_service: connect_primary}
    failed_targets = failed_targets if failed_targets is not None else set()
    candidates = [primary_service, *ordered]
    decision_started = time.perf_counter()
    mode = routing_mode()
    fleet_states = {}
    active = False
    canary = False
    capacity_targets = {}
    try:
        targets = registry()
    except (ValueError, TypeError):
        targets = None
    if targets is None and routing_uid:
        COST_FAIL_OPEN.labels(reason='router_error').inc()
        record_fallback(
            component='stt_selection',
            from_mode=primary_service.value,
            to_mode=primary_service.value,
            reason='config_incomplete',
            outcome='degraded',
        )
        raise ProviderChainUnavailable(5)
    if targets is not None:
        capacity_targets = {target.id: target for target in targets if engine_matches(target, routing_models)}
        for target in list(capacity_targets.values()):
            if target.endpoint is None:
                capacity_targets.setdefault(DEFAULT_IDS[target.family], target)
    configured_families = [service.value for service in candidates if callbacks.get(service) is not None]
    try:
        account_states = health.cached_snapshot(configured_families, routing_language)
    except Exception:
        COST_FAIL_OPEN.labels(reason='router_error').inc()
        record_fallback(
            component='stt_selection',
            from_mode=primary_service.value,
            to_mode=primary_service.value,
            reason='config_incomplete',
            outcome='degraded',
        )
        raise ProviderChainUnavailable(5)
    fleet_states = account_states

    def route_target(service: STTService) -> tuple[Target, dict[str, str | None] | None]:
        if targets:
            for target in targets:
                if (
                    target.family == service.value
                    and target.endpoint is None
                    and engine_matches(target, routing_models)
                ):
                    return target, routing_models
        engine = (routing_models or {}).get(service.value)
        pseudo = Target(
            id=engine or ('parakeet' if service.value == 'parakeet' else DEFAULT_IDS.get(service.value, service.value)),
            family=service.value,
            cost_per_audio_hour=0.0,
        )
        return pseudo, {service.value: pseudo.id}

    configured_candidates = []
    try:
        for service in candidates:
            target, engine_models = route_target(service)
            if permitted_target(
                target,
                routing_uid,
                routing_language,
                routing_languages,
                engine_models,
                account_states,
            ):
                configured_candidates.append(service)
    except (ValueError, TypeError):
        # Permissions apply even in shadow/off. A malformed allocation cannot
        # prove permission for a dial, and is not a provider transport failure.
        COST_FAIL_OPEN.labels(reason='router_error').inc()
        record_fallback(
            component='stt_selection',
            from_mode=primary_service.value,
            to_mode=primary_service.value,
            reason='config_incomplete',
            outcome='degraded',
        )
        raise ProviderChainUnavailable(5) from None
    routes = [(service, None) for service in configured_candidates]

    def fallback_routes(states: dict[str, GateState]) -> tuple[list[tuple[STTService, Target | None]], bool]:
        if not canary or targets is None:
            return [(service, None) for service in configured_candidates], False
        represented = {
            target.family for target in targets if target.endpoint is None and engine_matches(target, routing_models)
        }
        permitted: dict[str, list[Target]] = {}
        for target in targets:
            if permitted_target(
                target, routing_uid, routing_language, routing_languages, routing_models, account_states
            ):
                permitted.setdefault(target.family, []).append(target)
        fallback: list[tuple[STTService, Target | None]] = []
        for service in candidates:
            if callbacks.get(service) is None:
                continue
            fallback.extend((service, target) for target in permitted.get(service.value, ()))
            if service in configured_candidates and service.value not in represented:
                fallback.append((service, None))

        def conservative_stage(route: tuple[STTService, Target | None]) -> int:
            service, target = route
            identity = target.id if target is not None else DEFAULT_IDS.get(service.value)
            return states.get(identity or '', GateState()).stage

        fallback.sort(key=lambda route: (conservative_stage(route) < 100, -conservative_stage(route)))
        return fallback, True

    routing_decision: dict = {}
    gate_states: dict[str, GateState] = {}
    if mode != 'off' and routing_uid and not _routing_static:
        try:
            canary = routing_on(routing_uid)
            last_resorts = []
            proposed = propose(
                health,
                configured_families,
                routing_uid,
                routing_language,
                primary_service.value,
                fleet_states,
                routing_languages,
                routing_models,
                last_resorts,
                decision=routing_decision,
            )
            gate_states = routing_decision.get('states') or {}
            if canary:
                active = True
                # An override endpoint does not replace the configured family
                # endpoint unless that endpoint is itself in the target chain.
                # Registry withdrawal/capability/ramp exclusions also own the
                # default endpoint. Re-appending it as a "legacy" tail would
                # bypass the very exclusion the policy just decided.
                routes = [(STTService(target.family), target) for target in proposed]
                routes.extend((STTService(target.family), target) for target in last_resorts)
                # Preserve every permitted configured endpoint, even when the
                # proposal omitted it for capacity or health. Hard withdrawals
                # were already applied by configured_candidates. A custom
                # endpoint must never consume the family's default tail.
                for service in configured_candidates:
                    if any(s == service and (t is None or t.endpoint is None) for s, t in routes):
                        continue
                    target, _ = route_target(service)
                    if (
                        routing_decision.get('exclude_benched')
                        and routes
                        and gate_states.get(target.id, GateState()).stage == 0
                    ):
                        # The escape keeps a benched family out while a
                        # stage>0 route can serve; it must not return as tail.
                        COST_DECISION.labels(target=target.id, reason='benched_skip').inc()
                        continue
                    routes.append((service, target if targets and target in targets else None))
        except CostHealthUnavailable as error:
            COST_FAIL_OPEN.labels(reason='cache_unavailable').inc()
            routes, active = fallback_routes(error.states)
            logger.debug('live_stt_cost_router cache unavailable; using configured order')
            if canary:
                record_fallback(
                    component='stt_selection',
                    from_mode=primary_service.value,
                    to_mode=primary_service.value,
                    reason='config_incomplete',
                    outcome='degraded',
                )
        except Exception:
            COST_FAIL_OPEN.labels(reason='router_error').inc()
            routes, active = fallback_routes({})
            logger.exception('live_stt_cost_router using configured order')
            record_fallback(
                component='stt_selection',
                from_mode=primary_service.value,
                to_mode=primary_service.value,
                reason='config_incomplete',
                outcome='degraded',
            )
    if not routes:
        COST_NO_PERMITTED_TARGET.inc()
        waits = [
            state.bench_until - time.time()
            for state in account_states.values()
            if state.bench == 'account' and state.excluded
        ]
        raise NoPermittedTarget(int(max(waits, default=0) + 0.999) or 5)
    ROUTING_DECISION_LATENCY.observe(time.perf_counter() - decision_started)
    # Mid-session deaths can open every pod-local circuit without proving that
    # new connects fail. Require repeated real connect failures before shedding.
    # A cooled circuit still reaches the normal half-open recovery probe.
    eligible = [
        service
        for service in configured_candidates
        if callbacks.get(service) is not None and provider_for_service(service) not in failed
    ]
    all_benched = False
    if eligible and not active:
        circuits = [_circuit_for_primary(service) for service in eligible]
        # Half-open is an admission state: allow_request() may grant its
        # recovery probe. Only open circuits still inside cooldown are benched.
        all_benched = all(circuit.state == 'open' and not circuit.cooldown_elapsed() for circuit in circuits)
        eligible_names = {service.value for service in eligible}
        with _connect_failure_lock:
            cutoff = time.monotonic() - _FAILURE_EVIDENCE_SECONDS
            while _recent_connect_failures and _recent_connect_failures[0][0] < cutoff:
                _recent_connect_failures.popleft()
            threshold = _connect_failures_before_shed()
            confirmed_failures = len(_recent_connect_failures) >= threshold and all(
                provider in eligible_names for _, provider in list(_recent_connect_failures)[-threshold:]
            )
        fleet_snapshot_fresh = health.has_fresh_fleet_snapshot()
        fleet_has_healthy_provider = fleet_snapshot_fresh and any(
            (state := fleet_states.get(service.value)) is not None
            and not state.excluded
            and state.samples > 0
            and state.score > 0.5
            for service in eligible
        )
        fleet_confirms_outage = fleet_snapshot_fresh and all(
            fleet_states.get(service.value) is not None and fleet_states[service.value].excluded for service in eligible
        )
        if all_benched and not fleet_has_healthy_provider and (fleet_confirms_outage or confirmed_failures):
            waits = [circuit.account_cooldown_seconds_remaining for circuit in circuits if circuit.state == 'open']
            if fleet_confirms_outage:
                waits.extend(max(0.0, fleet_states[service.value].bench_until - time.time()) for service in eligible)
            retry_after = max(5, int(max(waits, default=0) + 0.999))
            raise ProviderChainUnavailable(retry_after)
    primary_target = routes[0][1] if active and routes else None
    policy_primary = primary_target.id if primary_target is not None else None
    origin = routes[0][0].value if active and routes else primary_service.value

    def backup(service: STTService, target) -> bool:
        return target.id != policy_primary if active and target is not None else active or service != primary_service

    def note_skip(service: STTService, cause: str) -> None:
        nonlocal origin_skip
        token = f'{service.value}:{cause}'
        if token not in skips and len(skips) < 12:
            skips.append(token)
        if origin_skip is None and prior_outcome is None and service.value == origin:
            origin_skip = cause

    def hop_reason() -> str:
        # A dialed failure owns the hop (origin moved to it); otherwise the
        # origin's own skip cause explains why it is not serving.
        return prior_reason if prior_outcome is not None or origin_skip is None else origin_skip

    prior_reason = 'circuit_open'
    prior_capacity_subtype: str | None = None
    prior_outcome: LiveLegOutcome | None = None
    # Why the origin route never served when it was never dialed. Without it
    # the hop inherits the 'circuit_open' sentinel, which the live reason
    # vocabulary normalized to connection_lost: a recovery chain that skipped
    # a session-excluded Soniox logged an untyped Soniox death (prod
    # 2026-10-20: 454 of 489 such lines had no Soniox dial).
    origin_skip: str | None = None if any(service.value == origin for service, _ in routes) else 'policy'
    skips: list[str] = []
    attempted = False
    primary_open = False
    probes = max(1, int(listen_value('circuit_half_open_probes', 'STT_CIRCUIT_HALF_OPEN_PROBES', '1')))
    capacity_blocked = set()
    capacity_resorts = []
    backoff_skipped = []
    parakeet_capacity_refused = (
        active
        and paid_admission.enabled()
        and STTService.parakeet in configured_candidates
        and callbacks.get(STTService.parakeet) is not None
        and (
            any(target.family == 'parakeet' and not capacity_available(target) for target in capacity_targets.values())
            or ((routing_models or {}).get('parakeet') == 'parakeet-window' and not window.admission.available())
        )
    )

    def attempt_identity(service: STTService, target) -> str:
        if target is not None:
            return target.id
        if service.value == 'parakeet':
            return (routing_models or {}).get('parakeet') or 'parakeet'
        return DEFAULT_IDS.get(service.value) or service.value

    async def _restore_configured_chain() -> tuple[STTSocket, STTService]:
        record_fallback(
            component='stt_selection',
            from_mode=origin,
            to_mode=primary_service.value,
            reason='config_incomplete',
            outcome='degraded',
        )
        return await connect_configured_chain(
            primary_service=primary_service,
            connect_primary=connect_primary,
            callbacks=callbacks,
            failed=failed,
            models=models,
            routing_uid=routing_uid,
            routing_language=routing_language,
            routing_languages=routing_languages,
            routing_models=routing_models,
            failed_targets=failed_targets,
            _routing_static=True,
        )

    def _paid_spillover_scope(service: STTService) -> bool:
        return (
            active
            and paid_admission.enabled()
            and service.value in {'soniox', 'modulate', 'deepgram'}
            and (parakeet_capacity_refused or prior_reason == 'capacity_full')
        )

    async def attempt(
        service: STTService, connect: Connect, target=None, *, force_backoff: bool = False, rescue: bool = False
    ) -> tuple[STTSocket, STTService] | None:
        nonlocal origin, prior_reason, prior_capacity_subtype, primary_open
        if not recovery_on:
            # Legacy dialing has no backoff lease or recovery reservation
            # between here and its connect(), so this is already the last
            # policy gate before the dial.
            if _paid_spillover_scope(service) and not await paid_admission.admit(service.value):
                # Release any half-open probe acquired by the route loop.
                # Budget denial is policy, never a provider-health failure.
                _, release = target_circuit(target, _circuit_for_primary(service)).deferred_result_callbacks()
                release()
                return await _restore_configured_chain()
            return await _attempt_legacy(service, connect, target)
        circuit = target_circuit(target, _circuit_for_primary(service))
        on_success, on_close = circuit.deferred_result_callbacks()
        backoff_lease = connect_backoff().acquire(
            attempt_identity(service, target), provider=service.value, force=force_backoff
        )
        if backoff_lease is None:
            on_close()
            if not force_backoff:
                backoff_skipped.append((service, connect, target, rescue))
            primary_open |= not backup(service, target)
            prior_reason, prior_capacity_subtype = 'circuit_open', None
            note_skip(service, 'circuit_open')
            record_fallback(
                component='stt_selection',
                from_mode=origin,
                to_mode=service.value,
                reason='circuit_open',
                outcome='degraded',
            )
            return None
        try:
            # The spillover budget admits paid dials, not selection attempts:
            # spend it only after the backoff lease exists and the episode
            # still has dial time, so skipped or expired attempts cannot burn
            # the per-minute cap without any provider traffic.
            episode = current_recovery.get()
            if episode is not None and episode.dial_budget() <= 0:
                on_close()
                note_skip(service, 'recovery_budget')
                return None
            if _paid_spillover_scope(service) and not await paid_admission.admit(service.value):
                # Release any half-open probe acquired for this attempt.
                # Budget denial is policy, never a provider-health failure.
                on_close()
                return await _restore_configured_chain()
            return await _attempt_dial(service, connect, target, circuit, on_success, on_close, backoff_lease)
        finally:
            backoff_lease.finish()

    async def _attempt_legacy(
        service: STTService, connect: Connect, target=None
    ) -> tuple[STTSocket, STTService] | None:
        nonlocal origin, prior_reason, prior_capacity_subtype, prior_outcome, attempted
        attempted = True
        if active and backup(service, target):
            target_id = target.id if target is not None else DEFAULT_IDS.get(service.value, service.value)
            COST_DECISION.labels(target=target_id, reason='failover').inc()
        circuit = target_circuit(target, _circuit_for_primary(service))
        on_success, on_close = circuit.deferred_result_callbacks()
        socket = None
        try:
            token = connecting_target.set(target)
            try:
                socket = await connect()
            finally:
                connecting_target.reset(token)
            if socket is None:
                raise RejectedStream('config_incomplete')
            if (
                target is not None
                and hasattr(socket, 'routing_model')
                and (
                    not engine_matches(target, {service.value: getattr(socket, 'routing_model')})
                    or target.endpoint != getattr(socket, 'routing_endpoint', None)
                    or target.id != getattr(socket, 'routing_target', None)
                )
            ):
                raise TargetEngineMismatch('Connected engine differs from selected target')
            if not await fallback_socket_is_serving(socket):
                # The typed death reason (provider_budget_exhausted /
                # provider_auth_rejected) reaches the connect counter so a 402
                # labels error_class=budget, not auth; 'auth' stays reserved
                # for actual authentication refusals.
                death_reason = normalize_live_stt_reason(
                    getattr(socket, 'typed_death_reason', None), getattr(socket, 'death_reason', None)
                )
                if death_reason in ACCOUNT_REJECTION_REASONS:
                    raise RejectedStream(death_reason)
                if death_reason == PROVIDER_RATE_LIMITED:
                    raise RejectedStream('provider_429')
                raise RejectedStream(death_reason)
        except BaseException as error:
            if isinstance(error, asyncio.CancelledError):
                if prior_outcome is not None:
                    PendingLiveFailover(
                        component='stt_selection',
                        from_mode=origin,
                        to_mode='unavailable',
                        reason=prior_reason,
                        source_outcome=prior_outcome,
                    ).note_failure(None)
                if socket is not None:
                    close_rejected_socket(socket)
                on_close()
                raise
            if not isinstance(error, Exception):
                if socket is not None:
                    close_rejected_socket(socket)
                on_close()
                raise
            if isinstance(error, TargetEngineMismatch):
                if prior_outcome is not None:
                    PendingLiveFailover(
                        component='stt_selection',
                        from_mode=origin,
                        to_mode=service.value,
                        reason=prior_reason,
                        source_outcome=prior_outcome,
                    ).note_failure(None, continuing=True)
                if socket is not None:
                    close_rejected_socket(socket)
                on_close()
                COST_FAIL_OPEN.labels(reason='engine_mismatch').inc()
                record_fallback(
                    component='stt_selection',
                    from_mode=service.value,
                    to_mode=primary_service.value,
                    reason='config_incomplete',
                    outcome='degraded',
                )
                return await connect_configured_chain(
                    primary_service=primary_service,
                    connect_primary=connect_primary,
                    callbacks=callbacks,
                    failed=failed,
                    models=models,
                    routing_uid=routing_uid,
                    routing_language=routing_language,
                    routing_languages=routing_languages,
                    routing_models=routing_models,
                    failed_targets=failed_targets,
                    _routing_static=True,
                )
            reason = dial_failure_reason(error)
            if prior_outcome is not None:
                PendingLiveFailover(
                    component='stt_selection',
                    from_mode=origin,
                    to_mode=service.value,
                    reason=prior_reason,
                    source_outcome=prior_outcome,
                ).note_failure(reason, continuing=True)
            rejected_outcome = getattr(socket, 'leg_outcome', None) or LiveLegOutcome(
                (
                    target.id
                    if target is not None
                    else (
                        (routing_models or {}).get('parakeet') or 'parakeet'
                        if service.value == 'parakeet'
                        else DEFAULT_IDS.get(service.value, service.value)
                    )
                ),
                bounded_language(routing_language),
                routing_uid,
                None,
                health.record_session,
            )
            rejected_outcome.claim(reason, connect=True)
            if socket is not None and rejected_outcome.connection_cause is None:
                rejected_outcome.connection_cause = getattr(socket, 'connection_cause', None)
            if socket is not None:
                close_rejected_socket(socket)
            account_rejection = reason in ACCOUNT_REJECTION_REASONS
            provider_failure = provider_observation('connect_failure', reason) is True
            if provider_failure or account_rejection or reason == 'auth':
                _note_connect_result(failed_provider=service.value)
            # Preserve legacy omi_fallback_total quota/auth labels while the
            # health observation and connect counter retain precise tokens.
            fallback_reason = fallback_metric_reason(reason)
            capacity_subtype = getattr(error, 'capacity_subtype', None) if reason == 'capacity_full' else None
            if active and target is not None and not (reason == 'auth' or account_rejection):
                failed_targets.add(target.id)
            else:
                failed.add(provider_for_service(service) or service.value)
            record_stt_provider_connect(provider=service.value, outcome=CONNECT_FAILURE, reason=reason)
            if active and target is not None and reason == 'capacity_full':
                COST_DECISION.labels(target=target.id, reason='capacity_skip').inc()
            if reason == 'auth' or account_rejection:
                circuit.record_account_failure(
                    float(
                        listen_value('account_circuit_cooldown_seconds', 'STT_ACCOUNT_CIRCUIT_COOLDOWN_SECONDS', '1800')
                    ),
                    error_class=reason,
                )
                health.quarantine(service.value, 'account', circuit.account_cooldown_seconds_remaining)
                if active and target is not None:
                    health.quarantine_target(target.id, circuit.account_cooldown_seconds_remaining)
            elif not provider_failure:
                on_close()
                if reason == 'capacity_full':
                    identity = (
                        target.id
                        if target is not None
                        else (
                            (routing_models or {}).get('parakeet')
                            if service.value == 'parakeet'
                            else DEFAULT_IDS.get(service.value)
                        )
                    )
                    if identity is not None and identity in capacity_targets:
                        note_capacity_full(capacity_targets[identity].id)
            else:
                circuit.record_failure(error_class=reason)
                if circuit.state == 'open':
                    health.quarantine(
                        service.value,
                        'selection',
                        circuit.account_cooldown_seconds_remaining,
                        endpoint=target.endpoint if target is not None else None,
                    )
            LEG_ATTEMPTS.labels(
                to_mode=service.value, outcome='rejected' if reason in EXPECTED_REJECTIONS else 'error'
            ).inc()
            prior_outcome = rejected_outcome
            origin, prior_reason, prior_capacity_subtype = service.value, fallback_reason, capacity_subtype
            return None
        LEG_ATTEMPTS.labels(to_mode=service.value, outcome='success').inc()
        _note_connect_result(failed_provider=None)
        record_stt_provider_connect(provider=service.value, outcome=CONNECT_SUCCESS)
        attach_health = getattr(socket, 'set_health_callbacks', None)
        if getattr(socket, 'defers_selection_success', False) and callable(attach_health):
            attach_health(on_success, on_close)
        else:
            on_success()
        if backup(service, target) or primary_open or prior_outcome is not None:
            pending = PendingLiveFailover(
                component='stt_selection',
                from_mode=origin,
                to_mode=service.value,
                reason=hop_reason(),
                capacity_subtype=prior_capacity_subtype,
                source_outcome=prior_outcome,
            )
            attach_outcome = getattr(socket, 'set_selection_outcome', None)
            if callable(attach_outcome):
                attach_outcome(pending)
            else:
                pending.note_transcript()
        record_managed_leg_handoff(socket)
        return socket, service

    async def _attempt_dial(
        service: STTService,
        connect: Connect,
        target,
        circuit: ProviderCircuitBreaker,
        on_success: Callable[[], None],
        on_close: Callable[[], None],
        backoff_lease: ConnectLease,
    ) -> tuple[STTSocket, STTService] | None:
        nonlocal origin, prior_reason, prior_capacity_subtype, prior_outcome, attempted
        socket = None
        recovery = current_recovery.get()
        dial_budget = recovery.dial_budget() if recovery is not None else None

        def cleanup_budget() -> float:
            remaining = recovery.remaining() if recovery is not None else None
            return min(2.0, max(0.0, remaining)) if remaining is not None else 2.0

        attempted = True
        if active and backup(service, target):
            target_id = target.id if target is not None else DEFAULT_IDS.get(service.value, service.value)
            COST_DECISION.labels(target=target_id, reason='failover').inc()
        # A dial spending a same-target retry slot: its failure is the same blip
        # the dead leg already voted for, so it must not vote again.
        is_retry_dial = getattr(recovery, 'is_retry_dial', None)
        retry_dial = bool(is_retry_dial(attempt_identity(service, target))) if callable(is_retry_dial) else False
        try:
            if recovery is not None and dial_budget is not None and dial_budget <= 0:
                on_close()
                backoff_lease.finish()
                note_skip(service, 'recovery_budget')
                return None
            if recovery is not None and not recovery.reserve(attempt_identity(service, target), service.value):
                on_close()
                backoff_lease.finish()
                note_skip(service, 'recovery_budget')
                return None
            take_jitter = getattr(recovery, 'take_retry_jitter', None)
            jitter = take_jitter(attempt_identity(service, target)) if callable(take_jitter) else 0.0
            if isinstance(jitter, (int, float)) and jitter > 0:
                # A same-target retry after a transport death: spread the
                # redial so a fleet-wide drop does not reconnect in lockstep.
                slept = min(float(jitter), (dial_budget or RETRY_JITTER_SECONDS[1]) / 4)
                await asyncio.sleep(slept)
                if dial_budget is not None:
                    dial_budget = max(0.001, dial_budget - slept)
            token = connecting_target.set(target)
            try:
                if dial_budget is not None:
                    async with asyncio.timeout(dial_budget):
                        socket = await connect()
                        serving = socket is not None and await fallback_socket_is_serving(socket)
                else:
                    socket = await connect()
                    serving = socket is not None and await fallback_socket_is_serving(socket)
            finally:
                connecting_target.reset(token)
            if socket is None:
                raise RejectedStream('config_incomplete')
            if (
                target is not None
                and hasattr(socket, 'routing_model')
                and (
                    not engine_matches(target, {service.value: getattr(socket, 'routing_model')})
                    or target.endpoint != getattr(socket, 'routing_endpoint', None)
                    or target.id != getattr(socket, 'routing_target', None)
                )
            ):
                raise TargetEngineMismatch('Connected engine differs from selected target')
            if not serving:
                # The typed death reason (provider_budget_exhausted /
                # provider_auth_rejected) reaches the connect counter so a 402
                # labels error_class=budget, not auth; 'auth' stays reserved
                # for actual authentication refusals.
                death_reason = normalize_live_stt_reason(
                    getattr(socket, 'typed_death_reason', None), getattr(socket, 'death_reason', None)
                )
                if death_reason in ACCOUNT_REJECTION_REASONS:
                    raise RejectedStream(death_reason)
                if death_reason == PROVIDER_RATE_LIMITED:
                    raise RejectedStream('provider_429')
                raise RejectedStream(death_reason)
        except BaseException as error:
            if isinstance(error, asyncio.CancelledError):
                backoff_lease.finish()
                if prior_outcome is not None:
                    PendingLiveFailover(
                        component='stt_selection',
                        from_mode=origin,
                        to_mode='unavailable',
                        reason=prior_reason,
                        source_outcome=prior_outcome,
                    ).note_failure(None)
                if socket is not None:
                    try:
                        await abort_replay_socket(socket, timeout=cleanup_budget())
                    finally:
                        on_close()
                else:
                    on_close()
                raise
            if not isinstance(error, Exception):
                backoff_lease.finish()
                if socket is not None:
                    try:
                        await abort_replay_socket(socket, timeout=cleanup_budget())
                    finally:
                        on_close()
                else:
                    on_close()
                raise
            if isinstance(error, TargetEngineMismatch):
                backoff_lease.finish()
                if prior_outcome is not None:
                    PendingLiveFailover(
                        component='stt_selection',
                        from_mode=origin,
                        to_mode=service.value,
                        reason=prior_reason,
                        source_outcome=prior_outcome,
                    ).note_failure(None, continuing=True)
                if socket is not None:
                    try:
                        await abort_replay_socket(socket, timeout=cleanup_budget())
                    finally:
                        on_close()
                else:
                    on_close()
                COST_FAIL_OPEN.labels(reason='engine_mismatch').inc()
                record_fallback(
                    component='stt_selection',
                    from_mode=service.value,
                    to_mode=primary_service.value,
                    reason='config_incomplete',
                    outcome='degraded',
                )
                return await connect_configured_chain(
                    primary_service=primary_service,
                    connect_primary=connect_primary,
                    callbacks=callbacks,
                    failed=failed,
                    models=models,
                    routing_uid=routing_uid,
                    routing_language=routing_language,
                    routing_languages=routing_languages,
                    routing_models=routing_models,
                    failed_targets=failed_targets,
                    _routing_static=True,
                )
            reason = dial_failure_reason(error)
            backoff_lease.finish(
                refused=reason in ('provider_429', PROVIDER_RATE_LIMITED) or isinstance(error, ConnectionRefusedError)
            )
            if prior_outcome is not None:
                PendingLiveFailover(
                    component='stt_selection',
                    from_mode=origin,
                    to_mode=service.value,
                    reason=prior_reason,
                    source_outcome=prior_outcome,
                ).note_failure(reason, continuing=True)
            rejected_outcome = getattr(socket, 'leg_outcome', None) or LiveLegOutcome(
                (
                    target.id
                    if target is not None
                    else (
                        (routing_models or {}).get('parakeet') or 'parakeet'
                        if service.value == 'parakeet'
                        else DEFAULT_IDS.get(service.value, service.value)
                    )
                ),
                bounded_language(routing_language),
                routing_uid,
                None,
                health.record_session,
            )
            rejected_outcome.claim(reason, connect=True)
            if retry_dial:
                rejected_outcome.evidence = False
            if socket is not None and rejected_outcome.connection_cause is None:
                rejected_outcome.connection_cause = getattr(socket, 'connection_cause', None)
            if socket is not None:
                await abort_replay_socket(socket, timeout=cleanup_budget())
            account_rejection = reason in ACCOUNT_REJECTION_REASONS
            provider_failure = provider_observation('connect_failure', reason) is True
            if provider_failure or account_rejection or reason == 'auth':
                _note_connect_result(failed_provider=service.value)
            # Preserve legacy omi_fallback_total quota/auth labels while the
            # health observation and connect counter retain precise tokens.
            fallback_reason = fallback_metric_reason(reason)
            capacity_subtype = getattr(error, 'capacity_subtype', None) if reason == 'capacity_full' else None
            if active and target is not None and not (reason == 'auth' or account_rejection):
                failed_targets.add(target.id)
            else:
                failed.add(provider_for_service(service) or service.value)
            record_stt_provider_connect(provider=service.value, outcome=CONNECT_FAILURE, reason=reason)
            if active and target is not None and reason == 'capacity_full':
                COST_DECISION.labels(target=target.id, reason='capacity_skip').inc()
            if reason == 'auth' or account_rejection:
                circuit.record_account_failure(
                    float(
                        listen_value('account_circuit_cooldown_seconds', 'STT_ACCOUNT_CIRCUIT_COOLDOWN_SECONDS', '1800')
                    ),
                    error_class=reason,
                )
                health.quarantine(service.value, 'account', circuit.account_cooldown_seconds_remaining)
                if active and target is not None:
                    health.quarantine_target(target.id, circuit.account_cooldown_seconds_remaining)
            elif reason in ('provider_429', PROVIDER_RATE_LIMITED):
                on_close()
            elif not provider_failure:
                on_close()
                if reason == 'capacity_full':
                    identity = (
                        target.id
                        if target is not None
                        else (
                            (routing_models or {}).get('parakeet')
                            if service.value == 'parakeet'
                            else DEFAULT_IDS.get(service.value)
                        )
                    )
                    if identity is not None and identity in capacity_targets:
                        note_capacity_full(capacity_targets[identity].id)
            else:
                circuit.record_failure(error_class=reason)
                if circuit.state == 'open':
                    health.quarantine(
                        service.value,
                        'selection',
                        circuit.account_cooldown_seconds_remaining,
                        endpoint=target.endpoint if target is not None else None,
                    )
            LEG_ATTEMPTS.labels(
                to_mode=service.value, outcome='rejected' if reason in EXPECTED_REJECTIONS else 'error'
            ).inc()
            prior_outcome = rejected_outcome
            origin, prior_reason, prior_capacity_subtype = service.value, fallback_reason, capacity_subtype
            return None
        LEG_ATTEMPTS.labels(to_mode=service.value, outcome='success').inc()
        backoff_lease.finish(success=True)
        _note_connect_result(failed_provider=None)
        record_stt_provider_connect(provider=service.value, outcome=CONNECT_SUCCESS)
        attach_health = getattr(socket, 'set_health_callbacks', None)
        if getattr(socket, 'defers_selection_success', False) and callable(attach_health):
            attach_health(on_success, on_close)
        else:
            on_success()
        if backup(service, target) or primary_open or prior_outcome is not None:
            pending = PendingLiveFailover(
                component='stt_selection',
                from_mode=origin,
                to_mode=service.value,
                reason=hop_reason(),
                capacity_subtype=prior_capacity_subtype,
                source_outcome=prior_outcome,
            )
            attach_outcome = getattr(socket, 'set_selection_outcome', None)
            if callable(attach_outcome):
                attach_outcome(pending)
            else:
                pending.note_transcript()
        record_managed_leg_handoff(socket)
        return socket, service

    retried: set[str] = set()

    async def _same_target_retry(
        service: STTService, connect: Connect, target, identity: str
    ) -> tuple[STTSocket, STTService] | None:
        """One jittered redial of the route that just failed at connect."""
        outcome = prior_outcome
        if outcome is None or identity in retried:
            return None
        stage = gate_states[identity].stage if identity in gate_states else _safe_cost_stage(identity, routing_language)
        circuit = target_circuit(target, _circuit_for_primary(service))
        if not same_target_retry_allowed(
            outcome.reason,
            text_seen=False,
            stage=stage,
            circuit_open=circuit.state == 'open',
            already_retried=False,
            family=service.value,
        ):
            return None
        if is_draining():
            return None  # our own restart: let the client reconnect elsewhere
        retried.add(identity)
        episode = current_recovery.get() if recovery_on else None
        dial_identity = attempt_identity(service, target)
        delay = retry_jitter_seconds()
        if episode is not None:
            remaining = episode.remaining()
            if remaining is not None:
                delay = min(delay, max(0.0, remaining / 4))
        await asyncio.sleep(delay)
        if is_draining():
            return None  # SIGTERM arrived during the jitter
        if not circuit.allow_request(max_probes=probes):
            SAME_TARGET_RETRIES.labels(provider=service.value, path='connect', outcome='refused').inc()
            return None
        # The redial is admitted; only now take this identity's own retry slot
        # (never the Soniox rescue re-entry).
        if (
            episode is not None
            and not episode.can_attempt(dial_identity)
            and not episode.grant_transient_retry(dial_identity)
        ):
            _, release = circuit.deferred_result_callbacks()
            release()
            SAME_TARGET_RETRIES.labels(provider=service.value, path='connect', outcome='refused').inc()
            return None
        failed_targets.discard(identity)
        failed.discard(provider_for_service(service) or service.value)
        before = prior_outcome
        result = await attempt(service, connect, target)
        if result is None and prior_outcome is not None and prior_outcome is not before:
            # The first failure already voted; one blip is one health vote.
            prior_outcome.evidence = False
        SAME_TARGET_RETRIES.labels(
            provider=service.value, path='connect', outcome='served' if result is not None else 'failed'
        ).inc()
        return result

    recovery = current_recovery.get() if recovery_on else None
    for service, target in routes:
        connect = callbacks.get(service)
        identity = (
            target.id
            if target is not None
            else (
                (routing_models or {}).get('parakeet')
                if service.value == 'parakeet'
                else DEFAULT_IDS.get(service.value)
            )
        )
        if connect is None:
            note_skip(service, 'unconfigured')
            continue
        if provider_for_service(service) in failed or identity in failed_targets:
            note_skip(service, 'session_excluded')
            continue
        if recovery is not None and identity is not None and not recovery.can_attempt(identity):
            note_skip(service, 'recovery_budget')
            continue
        capacity_target = target if target is not None else capacity_targets.get(identity or '')
        if (routing_models or {}).get(service.value) == 'parakeet-window':
            if not window.admission.available():
                WINDOW_ADMISSION.labels(outcome='overflow').inc()
                capacity_blocked.add(service)
                prior_reason, prior_capacity_subtype = 'capacity_full', 'admission'
                note_skip(service, 'capacity_full')
                record_fallback(
                    component='stt_selection',
                    from_mode=origin,
                    to_mode=service.value,
                    reason='capacity_full',
                    outcome='degraded',
                    capacity_subtype='admission',
                )
                continue
        if capacity_target is not None and not capacity_available(capacity_target):
            capacity_blocked.add(service)
            capacity_resorts.append((service, target, capacity_target))
            COST_DECISION.labels(target=capacity_target.id, reason='capacity_skip').inc()
            note_skip(service, 'capacity_full')
            continue
        circuit = target_circuit(target, _circuit_for_primary(service))
        if not circuit.allow_request(max_probes=probes):
            note_skip(service, 'circuit_open')
            primary_open |= not backup(service, target)
            if backup(service, target):
                record_fallback(
                    component='stt_selection',
                    from_mode=origin,
                    to_mode=service.value,
                    reason='circuit_open',
                    outcome='degraded',
                )
            continue
        dialed_before = prior_outcome
        result = await attempt(service, connect, target)
        if result is not None:
            return result
        if prior_outcome is not None and prior_outcome is not dialed_before and identity is not None:
            result = await _same_target_retry(service, connect, target, identity)
            if result is not None:
                return result

    # Capacity is advisory when it would suppress every usable route. Dial only
    # one least-recently-refused candidate; retain account/local circuit gates.
    if not attempted and capacity_resorts:
        for service, target, capacity_target in sorted(
            capacity_resorts, key=lambda route: capacity_refused_at(route[2])
        ):
            account = fleet_states.get(service.value)
            if account is not None and account.bench == 'account' and account.excluded:
                continue
            if recovery is not None and not recovery.can_attempt(attempt_identity(service, target)):
                continue
            circuit = target_circuit(target, _circuit_for_primary(service))
            connect = callbacks.get(service)
            if connect is None or not circuit.allow_request(max_probes=probes):
                continue
            prior_reason = 'capacity_full'
            primary_open = True
            record_fallback(
                component='stt_selection',
                from_mode=origin,
                to_mode=service.value,
                reason='capacity_full',
                outcome='degraded',
            )
            result = await attempt(service, connect, target)
            if result is not None:
                return result
            break  # one real escape dial, even if it is still full

    # A refusal/open window cannot consume the rescue path. Try each remaining
    # non-TDT provider once, even if the rejected primary was windowed TDT or
    # an earlier leg already attempted admission. Failed/account/cooled legs
    # stay excluded; force only relaxes a non-account selection bench.
    if not active:
        rescue_deadline = asyncio.get_running_loop().time() + 12.0
        for service in configured_candidates:
            connect = callbacks.get(service)
            if (
                service == STTService.parakeet
                or service in capacity_blocked
                or connect is None
                or provider_for_service(service) in failed
            ):
                continue
            if recovery is not None and not recovery.can_attempt(attempt_identity(service, None)):
                continue
            state = fleet_states.get(service.value)
            if state is not None and state.bench == 'account' and state.excluded:
                continue
            if await _allow_rescue_probe(_circuit_for_primary(service), probes, rescue_deadline):
                prior_reason = 'last_resort'
                prior_capacity_subtype = None
                result = await attempt(service, connect, rescue=True)
                if result is not None:
                    return result
    if recovery_on and not attempted and backoff_skipped:
        for service, connect, target, rescue in sorted(
            backoff_skipped,
            key=lambda route: connect_backoff().cooldown_until(attempt_identity(route[0], route[2])),
        ):
            identity = attempt_identity(service, target)
            if connect is None or provider_for_service(service) in failed or identity in failed_targets:
                continue
            if recovery is not None and not recovery.can_attempt(identity):
                continue
            account = fleet_states.get(service.value)
            if account is not None and account.bench == 'account' and account.excluded:
                continue
            circuit = target_circuit(target, _circuit_for_primary(service))
            if not circuit.allow_request(max_probes=probes, force=rescue):
                continue
            primary_open = True
            record_fallback(
                component='stt_selection',
                from_mode=origin,
                to_mode=service.value,
                reason='circuit_open',
                outcome='degraded',
            )
            result = await attempt(service, connect, target, force_backoff=True, rescue=rescue)
            if result is not None:
                return result
            break
    if optional_handover:
        raise RejectedStream(prior_reason)
    record_metric(CHAIN_EXHAUSTED, {'demand_cohort': demand_cohort()}, 1)
    pending = PendingLiveFailover(
        component='stt_selection',
        from_mode=origin,
        to_mode='unavailable',
        reason=hop_reason(),
        capacity_subtype=prior_capacity_subtype,
        source_outcome=prior_outcome,
    )
    # Bounded tokens only (family:cause): why no successor was available. The
    # reason is the hop's own, so a claimed dial death wins over a later skip.
    logger.warning(
        'live_stt_chain_exhausted origin=%s reason=%s skips=%s',
        origin,
        fallback_metric_reason(pending.reason),
        ','.join(skips) or 'none',
    )
    pending.note_failure(None)
    if recovery_on:
        raise LiveChainExhausted('Configured STT chain exhausted')
    raise RuntimeError('Configured STT chain exhausted')
