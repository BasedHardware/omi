"""Configured live connection attempts; legacy routing stays in streaming.py."""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from utils.stt.streaming import STTService

from config.stt_provider_policy import DEEPGRAM_PROVIDERS, provider_for_model_token, provider_for_service
from utils.observability.fallback import record_fallback
from utils.stt.live_failure import PendingLiveFailover
from utils.stt.live_metrics import CHAIN_EXHAUSTED, LEG_ATTEMPTS
from utils.stt.provider_resilience import EXPECTED_REJECTIONS, close_rejected_socket, fallback_socket_is_serving
from utils.stt.socket import STTSocket
from utils.stt.stream_close import ACCOUNT_REJECTION_REASONS

Connect = Callable[[], Awaitable[STTSocket | None]]


def failure_reason(error: BaseException) -> str:
    from utils.stt.streaming import DeepgramConnectionRejection, ParakeetConnectionError

    if isinstance(error, DeepgramConnectionRejection) or getattr(error, 'reason', None) == 'auth':
        return 'auth'
    if isinstance(error, ParakeetConnectionError):
        return error.reason
    if isinstance(error, TimeoutError):
        return 'timeout'
    return 'provider_5xx'


class RejectedStream(RuntimeError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def account_death(socket: STTSocket) -> bool:
    return getattr(socket, 'typed_death_reason', None) in ACCOUNT_REJECTION_REASONS


async def connect_configured_chain(
    *,
    primary_service: STTService,
    connect_primary: Connect,
    callbacks: dict[STTService, Connect | None],
    failed: set[str],
    models: list[str],
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
    candidates = [primary_service, *ordered]
    origin = primary_service.value
    prior_reason = 'circuit_open'
    attempted = False
    primary_open = False
    probes = max(1, int(os.getenv('STT_CIRCUIT_HALF_OPEN_PROBES', '1')))

    async def attempt(service: STTService, connect: Connect) -> tuple[STTSocket, STTService] | None:
        nonlocal origin, prior_reason, attempted
        attempted = True
        circuit = _circuit_for_primary(service)
        on_success, on_close = circuit.deferred_result_callbacks()
        socket = None
        try:
            socket = await connect()
            if socket is None:
                raise RejectedStream('config_incomplete')
            if not await fallback_socket_is_serving(socket):
                raise RejectedStream('auth' if account_death(socket) else 'provider_5xx')
        except BaseException as error:
            if socket is not None:
                close_rejected_socket(socket)
            if isinstance(error, asyncio.CancelledError):
                on_close()
                raise
            if not isinstance(error, Exception):
                on_close()
                raise
            reason = error.reason if isinstance(error, RejectedStream) else failure_reason(error)
            failed.add(provider_for_service(service) or service.value)
            if reason == 'auth':
                circuit.record_account_failure(float(os.getenv('STT_ACCOUNT_CIRCUIT_COOLDOWN_SECONDS', '1800')))
            elif reason in EXPECTED_REJECTIONS:
                on_close()
            else:
                circuit.record_failure()
            LEG_ATTEMPTS.labels(
                to_mode=service.value, outcome='rejected' if reason in EXPECTED_REJECTIONS else 'error'
            ).inc()
            if service != primary_service:
                record_fallback(
                    component='stt_selection',
                    from_mode=origin,
                    to_mode=service.value,
                    reason=reason,
                    outcome='degraded',
                )
            origin, prior_reason = service.value, reason
            return None
        LEG_ATTEMPTS.labels(to_mode=service.value, outcome='success').inc()
        attach_health = getattr(socket, 'set_health_callbacks', None)
        if getattr(socket, 'defers_selection_success', False) and callable(attach_health):
            attach_health(on_success, on_close)
        else:
            on_success()
        if service != primary_service or primary_open:
            pending = PendingLiveFailover(
                component='stt_selection', from_mode=origin, to_mode=service.value, reason=prior_reason
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
                )
        return socket, service

    for service in candidates:
        connect = callbacks.get(service)
        if connect is None or provider_for_service(service) in failed:
            continue
        circuit = _circuit_for_primary(service)
        if not circuit.allow_request(max_probes=probes):
            primary_open |= service == primary_service
            if service != primary_service:
                record_fallback(
                    component='stt_selection',
                    from_mode=origin,
                    to_mode=service.value,
                    reason='circuit_open',
                    outcome='degraded',
                )
            continue
        result = await attempt(service, connect)
        if result is not None:
            return result

    # Last-resort may force a non-account bench on a non-TDT primary only.
    # Windowed TDT shedding (capacity/5xx) must hold; account cooldown never yields.
    if (
        primary_open
        and not attempted
        and primary_service != STTService.parakeet
        and provider_for_service(primary_service) not in failed
    ):
        circuit = _circuit_for_primary(primary_service)
        if circuit.allow_request(max_probes=1, force=True):
            prior_reason = 'last_resort'
            result = await attempt(primary_service, connect_primary)
            if result is not None:
                return result
    CHAIN_EXHAUSTED.inc()
    record_fallback(
        component='stt_selection',
        from_mode=origin,
        to_mode='unavailable',
        reason=prior_reason,
        outcome='exhausted',
    )
    raise RuntimeError('Configured STT chain exhausted')
