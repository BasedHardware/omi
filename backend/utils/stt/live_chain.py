"""Configured live connection attempts; legacy routing stays in streaming.py."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from collections import deque
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from utils.stt.streaming import STTService

from config.stt_provider_policy import DEEPGRAM_PROVIDERS, provider_for_model_token, provider_for_service
from utils.observability.fallback import capacity_fallback_kwargs, record_fallback
from utils.stt.connect_metrics import CONNECT_FAILURE, CONNECT_SUCCESS, record_stt_provider_connect
from utils.stt.live_failure import PendingLiveFailover, fallback_metric_reason
from utils.stt.live_metrics import CHAIN_EXHAUSTED, LEG_ATTEMPTS, ROUTING_DECISION_LATENCY
from utils.stt.live_health import health, bounded_language, mode as routing_mode
from utils.stt.live_router import (
    connecting_target,
    propose,
    target_circuit,
    TargetEngineMismatch,
    engine_matches,
    capacity_available,
    note_capacity_full,
    capacity_refused_at,
)
from config.live_stt_registry import routing_on, DEFAULT_IDS, registry
from utils.stt.live_cost_health import CostHealthUnavailable
from utils.stt.live_metrics import COST_DECISION, COST_FAIL_OPEN
from utils.stt.provider_resilience import EXPECTED_REJECTIONS, close_rejected_socket, fallback_socket_is_serving
from utils.stt.socket import STTSocket
from utils.stt.stream_close import ACCOUNT_REJECTION_REASONS, PROVIDER_RATE_LIMITED

Connect = Callable[[], Awaitable[STTSocket | None]]
logger = logging.getLogger(__name__)
_connect_failure_lock = threading.Lock()
_FAILURE_EVIDENCE_SECONDS = 60.0
_recent_connect_failures: deque[tuple[float, str]] = deque(maxlen=1000)


def _connect_failures_before_shed() -> int:
    try:
        return min(1000, max(1, int(os.getenv('STT_SHED_CONNECT_FAILURES', '3'))))
    except ValueError:
        return 3


def _note_connect_result(*, failed_provider: str | None) -> None:
    with _connect_failure_lock:
        if failed_provider is None:
            _recent_connect_failures.clear()
        else:
            _recent_connect_failures.append((time.monotonic(), failed_provider))


def failure_reason(error: BaseException) -> str:
    from utils.stt.streaming import DeepgramConnectionRejection, ParakeetConnectionError

    if isinstance(error, DeepgramConnectionRejection) or getattr(error, 'reason', None) == 'auth':
        return 'auth'
    if isinstance(error, ParakeetConnectionError):
        return error.reason
    if isinstance(error, TimeoutError):
        return 'timeout'
    if getattr(error, 'reason', None) == 'provider_rate_limited':
        return 'provider_429'
    return 'provider_5xx'


class RejectedStream(RuntimeError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class ProviderChainUnavailable(RuntimeError):
    def __init__(self, retry_after: int):
        self.retry_after = max(1, min(retry_after, 3600))
        super().__init__('Configured STT chain exhausted: providers unavailable')


async def connect_configured_chain(
    *,
    primary_service: STTService,
    connect_primary: Connect,
    callbacks: dict[STTService, Connect | None],
    failed: set[str],
    models: list[str],
    routing_uid: str | None = None,
    routing_language: str | None = None,
    routing_languages: tuple[str, ...] = (),
    routing_models: dict[str, str | None] | None = None,
    failed_targets: set[str] | None = None,
) -> tuple[STTSocket, STTService]:
    from utils.stt.streaming import STTService, _circuit_for_primary  # type: ignore[reportPrivateUsage]  # shared circuit owner

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
    configured_candidates = candidates[:]
    decision_started = time.perf_counter()
    mode = routing_mode()
    fleet_states = {}
    active = False
    routes = [(service, None) for service in candidates]
    canary = False
    capacity_targets = {}
    if mode != 'off' and routing_uid:
        try:
            canary = routing_on(routing_uid)
            configured = [service.value for service in candidates if callbacks.get(service) is not None]
            fleet_states = health.cached_snapshot(configured, routing_language)
            last_resorts = []
            proposed = propose(
                health,
                configured,
                routing_uid,
                routing_language,
                primary_service.value,
                fleet_states,
                routing_languages,
                routing_models,
                last_resorts,
            )
            capacity_targets = {target.id: target for target in registry() if engine_matches(target, routing_models)}
            for target in list(capacity_targets.values()):
                if target.endpoint is None:
                    capacity_targets.setdefault(DEFAULT_IDS[target.family], target)
            active = canary and bool(proposed)
            if canary and not proposed:
                COST_FAIL_OPEN.labels(reason='empty_proposal').inc()
                record_fallback(
                    component='stt_selection',
                    from_mode=primary_service.value,
                    to_mode=primary_service.value,
                    reason='config_incomplete',
                    outcome='degraded',
                )
            if active:
                # An override endpoint does not replace the configured family
                # endpoint unless that endpoint is itself in the target chain.
                represented = {target.family for target in (*proposed, *last_resorts) if target.endpoint is None}
                tail = [(service, None) for service in configured_candidates if service.value not in represented]
                tail = [
                    (service, target)
                    for service, target in tail
                    if (entry := capacity_targets.get(DEFAULT_IDS.get(service.value, ''))) is None
                    or capacity_available(entry)
                ]
                routes = [(STTService(target.family), target) for target in proposed] + tail
                routes.extend((STTService(target.family), target) for target in last_resorts)
        except CostHealthUnavailable:
            COST_FAIL_OPEN.labels(reason='cache_unavailable').inc()
            active = False
            capacity_targets = {}
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
            active = False
            capacity_targets = {}
            routes = [(service, None) for service in configured_candidates]
            logger.exception('live_stt_cost_router using configured order')
            record_fallback(
                component='stt_selection',
                from_mode=primary_service.value,
                to_mode=primary_service.value,
                reason='config_incomplete',
                outcome='degraded',
            )
    ROUTING_DECISION_LATENCY.observe(time.perf_counter() - decision_started)
    # Mid-session deaths can open every pod-local circuit without proving that
    # new connects fail. Require repeated real connect failures before shedding.
    # A cooled circuit still reaches the normal half-open recovery probe.
    eligible = [service for service in configured_candidates if callbacks.get(service) is not None]
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

    prior_reason = 'circuit_open'
    prior_capacity_subtype: str | None = None
    attempted = False
    primary_open = False
    probes = max(1, int(os.getenv('STT_CIRCUIT_HALF_OPEN_PROBES', '1')))
    capacity_blocked = set()
    capacity_resorts = []

    async def attempt(service: STTService, connect: Connect, target=None) -> tuple[STTSocket, STTService] | None:
        nonlocal origin, prior_reason, prior_capacity_subtype, attempted
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
                death_reason = getattr(socket, 'typed_death_reason', None)
                if death_reason in ACCOUNT_REJECTION_REASONS:
                    raise RejectedStream(death_reason)
                if death_reason == PROVIDER_RATE_LIMITED:
                    raise RejectedStream('provider_429')
                raise RejectedStream('provider_5xx')
        except BaseException as error:
            if socket is not None:
                close_rejected_socket(socket)
            if isinstance(error, asyncio.CancelledError):
                on_close()
                raise
            if not isinstance(error, Exception):
                on_close()
                raise
            if isinstance(error, TargetEngineMismatch):
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
                    failed_targets=failed_targets,
                    routing_models=routing_models,
                )
            reason = error.reason if isinstance(error, RejectedStream) else failure_reason(error)
            health.record_connect_failure(
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
                reason,
            )
            if reason not in EXPECTED_REJECTIONS and reason != 'config_incomplete':
                _note_connect_result(failed_provider=service.value)
            account_rejection = reason in ACCOUNT_REJECTION_REASONS
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
                circuit.record_account_failure(float(os.getenv('STT_ACCOUNT_CIRCUIT_COOLDOWN_SECONDS', '1800')))
                health.quarantine(service.value, 'account', circuit.account_cooldown_seconds_remaining)
                if active and target is not None:
                    health.quarantine_target(target.id, circuit.account_cooldown_seconds_remaining)
            elif reason in EXPECTED_REJECTIONS:
                on_close()
                if canary and reason == 'capacity_full':
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
                circuit.record_failure()
                if circuit.state == 'open':
                    health.quarantine(service.value, 'selection', circuit.account_cooldown_seconds_remaining)
            LEG_ATTEMPTS.labels(
                to_mode=service.value, outcome='rejected' if reason in EXPECTED_REJECTIONS else 'error'
            ).inc()
            if backup(service, target):
                record_fallback(
                    component='stt_selection',
                    from_mode=origin,
                    to_mode=service.value,
                    reason=fallback_reason,
                    outcome='degraded',
                    **capacity_fallback_kwargs(capacity_subtype),
                )
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
        if backup(service, target) or primary_open:
            pending = PendingLiveFailover(
                component='stt_selection',
                from_mode=origin,
                to_mode=service.value,
                reason=prior_reason,
                capacity_subtype=prior_capacity_subtype,
            )
            attach_outcome = getattr(socket, 'set_selection_outcome', None)
            if callable(attach_outcome):
                attach_outcome(pending)
            else:
                record_fallback(
                    component='stt_selection',
                    from_mode=origin,
                    to_mode=service.value,
                    reason=prior_reason,
                    outcome='recovered',
                    **capacity_fallback_kwargs(prior_capacity_subtype),
                )
        return socket, service

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
        if connect is None or provider_for_service(service) in failed or identity in failed_targets:
            continue
        capacity_target = target if target is not None else capacity_targets.get(identity or '')
        if canary and capacity_target is not None and not capacity_available(capacity_target):
            capacity_blocked.add(service)
            capacity_resorts.append((service, target, capacity_target))
            COST_DECISION.labels(target=capacity_target.id, reason='capacity_skip').inc()
            continue
        circuit = target_circuit(target, _circuit_for_primary(service))
        if not circuit.allow_request(max_probes=probes):
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
        result = await attempt(service, connect, target)
        if result is not None:
            return result

    # Capacity is advisory when it would suppress every usable route. Dial only
    # one least-recently-refused candidate; retain account/local circuit gates.
    if canary and not attempted and capacity_resorts:
        for service, target, capacity_target in sorted(
            capacity_resorts, key=lambda route: capacity_refused_at(route[2])
        ):
            account = fleet_states.get(service.value)
            if account is not None and account.bench == 'account' and account.excluded:
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

    # Last-resort may force a non-account bench on a non-TDT primary only.
    # Windowed TDT shedding (capacity/5xx) must hold; account cooldown never yields.
    if (
        not active
        and primary_open
        and not attempted
        and primary_service != STTService.parakeet
        and primary_service not in capacity_blocked
        and provider_for_service(primary_service) not in failed
    ):
        circuit = _circuit_for_primary(primary_service)
        if circuit.allow_request(max_probes=1, force=True):
            prior_reason = 'last_resort'
            prior_capacity_subtype = None
            result = await attempt(primary_service, connect_primary)
            if result is not None:
                return result
    if not active and all_benched and not attempted:
        # A spent primary must not strand a still-serving fallback whose local
        # selection circuit opened on a mid-session death.
        for service in configured_candidates:
            connect = callbacks.get(service)
            if (
                service == STTService.parakeet
                or service in capacity_blocked
                or connect is None
                or provider_for_service(service) in failed
            ):
                continue
            state = fleet_states.get(service.value)
            if state is not None and state.bench == 'account' and state.excluded:
                continue
            if _circuit_for_primary(service).allow_request(max_probes=1, force=True):
                prior_reason = 'last_resort'
                prior_capacity_subtype = None
                result = await attempt(service, connect)
                if result is not None:
                    return result
                break
    CHAIN_EXHAUSTED.inc()
    record_fallback(
        component='stt_selection',
        from_mode=origin,
        to_mode='unavailable',
        reason=prior_reason,
        outcome='exhausted',
        **capacity_fallback_kwargs(prior_capacity_subtype),
    )
    raise RuntimeError('Configured STT chain exhausted')
