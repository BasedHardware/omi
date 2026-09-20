"""Routing foundation: an explicit session coordinator, shared by connect and serve-time replacement."""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from typing import Any, Awaitable, Callable

from config.stt_routing import ProviderSpec
from utils.executors import db_executor, run_blocking
from utils.observability.fallback import record_fallback
from utils.stt.routing_health import FailureReason, RedisHealthStore
from utils.stt.socket import STTSocket
from utils.stt.stream_close import PROVIDER_AUTH_REJECTED, PROVIDER_BUDGET_EXHAUSTED

logger = logging.getLogger(__name__)
TranscriptCallback = Callable[[list[dict[str, Any]]], None]
Connector = Callable[[ProviderSpec, TranscriptCallback], Awaitable[STTSocket | None]]


def failure_reason(error: Any) -> FailureReason:
    """Typed provider/account evidence only; never match or emit raw vendor text."""
    typed = getattr(error, 'typed_death_reason', None)
    status = getattr(error, 'status_code', None)
    if typed == PROVIDER_BUDGET_EXHAUSTED:
        return 'budget'
    if status == 402:
        return 'payment'
    if typed == PROVIDER_AUTH_REJECTED or status in (401, 403):
        return 'auth'
    if getattr(error, 'reason', None) in {'capacity_full', 'allocation_rejected'}:
        return 'capacity'
    if isinstance(error, TimeoutError):
        return 'timeout'
    return 'provider_error'


class LiveSTTRoute:
    """One immutable list per session; every attempt consumes a provider once.

    Health receipts are fenced by attempt identity. Late content is still
    delivered to its original callback; it cannot mark a successor recovered.
    """

    def __init__(
        self,
        candidates: tuple[ProviderSpec, ...],
        *,
        language: str,
        health: RedisHealthStore | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.candidates = candidates
        self.language = language
        self.health = health
        self.clock = clock
        self.attempted: set[str] = set()
        self.current: ProviderSpec | None = None
        self.epoch = ''
        self.current_socket: STTSocket | None = None
        self.transcript_receipts: list[tuple[str, int, str]] = []
        self.credited_attempts: set[str] = set()

    def next_candidate(self) -> ProviderSpec | None:
        return next((spec for spec in self.candidates if spec.provider not in self.attempted), None)

    async def _failure(self, spec: ProviderSpec, error: Any) -> None:
        reason = failure_reason(error)
        if self.health is not None and reason != 'capacity':
            await run_blocking(
                db_executor, self.health.failure, spec.provider, reason, now=self.clock(), jitter=random.random() * 0.25
            )
        record_fallback(
            component='stt_selection',
            from_mode=spec.service,
            to_mode='next_provider',
            reason=(
                'quota'
                if reason in {'budget', 'payment', 'quota'}
                else (
                    'auth'
                    if reason == 'auth'
                    else (
                        'timeout'
                        if reason == 'timeout'
                        else 'capacity_full' if reason == 'capacity' else 'provider_5xx'
                    )
                )
            ),
            outcome='degraded',
        )

    async def connect(
        self,
        connector: Connector,
        callback: TranscriptCallback,
        *,
        callback_for_provider: Callable[[ProviderSpec], TranscriptCallback] | None = None,
    ) -> tuple[STTSocket, ProviderSpec]:
        await self.flush_health_receipts()
        previous = self.current
        self.epoch = ''  # retire health credit; preserve late content in its original callback
        if previous is not None and self.current_socket is not None:
            await self._failure(previous, self.current_socket)
        self.current, self.current_socket = None, None
        while (spec := self.next_candidate()) is not None:
            self.attempted.add(spec.provider)
            owner = str(uuid.uuid4())
            generation = 0
            if self.health is not None:
                state, allowed = await run_blocking(
                    db_executor, self.health.acquire, spec.provider, now=self.clock(), owner=owner
                )
                if not allowed:
                    record_fallback(
                        component='stt_selection',
                        from_mode=spec.service,
                        to_mode='skipped',
                        reason='circuit_open',
                        outcome='degraded',
                    )
                    continue
                generation = state.generation
            self.epoch = owner

            def transcript(
                segments: list[dict[str, Any]],
                *,
                attempt: str = owner,
                provider: ProviderSpec = spec,
                admitted_generation: int = generation,
                sink: TranscriptCallback = callback_for_provider(spec) if callback_for_provider else callback,
            ) -> None:
                for segment in segments:
                    segment['stt_provider'] = provider.service
                nonempty = any(isinstance(segment.get('text'), str) and segment['text'].strip() for segment in segments)
                if nonempty and self.epoch == attempt and attempt not in self.credited_attempts:
                    self.credited_attempts.add(attempt)
                    if self.health is not None:
                        # SDK callbacks may run on a provider thread. Health IO is
                        # submitted by the async receiver through this explicit queue.
                        self.transcript_receipts.append((provider.provider, admitted_generation, attempt))
                    if previous is not None or len(self.attempted) > 1:
                        record_fallback(
                            component='stt_live_session' if previous else 'stt_selection',
                            from_mode=previous.service if previous else 'configured',
                            to_mode=provider.service,
                            reason='other',
                            outcome='recovered',
                        )
                sink(segments)

            try:
                async with asyncio.timeout(8):
                    socket = await connector(spec, transcript)
                if socket is None or socket.is_connection_dead:
                    if socket is not None:
                        socket.finish()
                    await self._failure(spec, socket)
                    continue
            except Exception as error:
                await self._failure(spec, error)
                continue
            self.current, self.current_socket = spec, socket
            logger.info('omi_stt_routing_event provider=%s decision=chosen reason=none', spec.provider)
            return socket, spec
        self.epoch = ''
        record_fallback(
            component='stt_selection',
            from_mode='configured',
            to_mode='unavailable',
            reason='other',
            outcome='exhausted',
        )
        raise RuntimeError('STT routing candidates exhausted')

    async def flush_health_receipts(self) -> None:
        while self.transcript_receipts:
            provider, generation, owner = self.transcript_receipts.pop(0)
            if self.health is not None:
                await run_blocking(db_executor, self.health.transcript, provider, generation=generation, owner=owner)
