"""Watch-only operation scopes joining provider reservations to billing units.

An operation owns one hold across retries, channels, and provider replacements.
Refusals are evidence only: this module never returns serving permission and
never suppresses audio. Renewal uses the billing clock, not packet counts.
"""

import asyncio
from contextvars import ContextVar, copy_context
from datetime import datetime, timezone
from functools import wraps
import inspect
import logging
import time
import threading
from contextlib import asynccontextmanager, suppress
from uuid import uuid4
from typing import Callable

from database import free_allowance_leases as ledger
from utils.executors import free_allowance_executor, run_blocking

logger = logging.getLogger(__name__)
current: ContextVar['Operation | None'] = ContextVar('free_allowance_operation', default=None)


class Operation:
    def __init__(
        self,
        uid: str,
        path: str,
        *,
        operation: str | None = None,
        seconds: float | None = None,
        live=False,
        billing_period: str | None = None,
    ):
        self.uid, self.path = uid, path
        self.operation = operation or uuid4().hex
        self.seconds, self.live = seconds, live
        self.billing_period = billing_period
        self.closed = False
        self.refused = False
        self.observed = False
        self.started: float | None = None
        self.reference: ledger.Reference | None = None
        self.provider = 'unknown'
        self.customer_funded = False
        self.lock = threading.RLock()
        self.clock: Callable[[], float] | None = None
        self.lease_until: float | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.changed = asyncio.Event()
        self.monitor_task: asyncio.Task | None = None

    def reserve(self, provider, *, customer_funded=False) -> None:
        try:
            free_allowance_executor.submit(
                copy_context().run, self._locked_reserve, provider, customer_funded=customer_funded
            ).result(timeout=2.5)
        except Exception:
            logger.warning('event=free_allowance_lease decision=observation_failed')

    def _locked_reserve(self, provider, *, customer_funded=False) -> None:
        with self.lock:
            self._reserve(provider, customer_funded=customer_funded)

    def _reserve(self, provider, *, customer_funded=False) -> None:
        # One synchronous implementation, usable through propagated executors.
        from utils.stt import allowance_watch as watch

        if self.closed or not watch.enabled() or self.path not in watch.PATHS:
            return
        if not customer_funded or self.reference is None:
            self.provider, self.customer_funded = provider, customer_funded
        try:
            decision, limit = watch.entitlement(self.uid, customer_funded=customer_funded)
            if limit is None:
                watch.emit(self.path, provider, decision, 0)
                return
            now = datetime.now(timezone.utc)
            self.reference = ledger.reference(self.uid, self.operation, now, billing_period=self.billing_period)
            if self.started is None:
                self.started = time.monotonic()
            elapsed = (self.clock() if self.clock is not None else time.monotonic() - self.started) if self.live else 0
            seconds = elapsed + ledger.LEASE_SECONDS if self.live else self.seconds
            if seconds is None or seconds <= 0:
                watch.emit(self.path, provider, 'duration_unavailable', 0)
                return
            from database import monthly_usage_totals

            try:
                result = ledger.reserve(
                    self.uid,
                    self.operation,
                    seconds,
                    limit,
                    now=now,
                    partial=self.live,
                    elapsed_seconds=elapsed,
                    billing_period=self.billing_period,
                )
            except monthly_usage_totals.UsageBaselineNotReady:
                stamp = datetime.strptime(self.reference.month, '%Y-%m').replace(tzinfo=timezone.utc)
                monthly_usage_totals.establish_verified_month(self.uid, stamp)
                result = ledger.reserve(
                    self.uid,
                    self.operation,
                    seconds,
                    limit,
                    now=now,
                    partial=self.live,
                    elapsed_seconds=elapsed,
                    billing_period=self.billing_period,
                )
            self.lease_until = result.lease.expires_at if result.lease is not None else None
            if self.loop is not None and not self.loop.is_closed():
                self.loop.call_soon_threadsafe(self.changed.set)
            self.refused = self.refused or result.reason == 'allowance_exhausted'
            self.observed = self.observed or result.reason in {'reserved', 'allowance_exhausted'}
            decision = {
                'reserved': 'would_allow',
                'allowance_exhausted': 'would_refuse',
            }.get(result.reason, result.reason)
            watch.emit(self.path, provider, decision, 0 if result.reason == 'already_settled' else seconds)
            watch.LEASE_DECISIONS.labels(self.path, result.reason).inc()
        except Exception:
            watch.emit(self.path, provider, 'usage_unavailable', 0)

    async def reserve_async(self, provider, *, customer_funded=False, timeout=2.5) -> None:
        if self.loop is None or self.loop.is_closed():
            self.loop = asyncio.get_running_loop()
        try:
            await asyncio.wait_for(
                run_blocking(free_allowance_executor, self._locked_reserve, provider, customer_funded=customer_funded),
                timeout=timeout,
            )
        except Exception:
            logger.warning('event=free_allowance_lease decision=observation_failed')

    def billed(self, seconds: float, *, daily_ptt=False) -> None:
        try:
            free_allowance_executor.submit(
                copy_context().run, self._locked_billed, seconds, daily_ptt=daily_ptt
            ).result(timeout=2.5)
        except Exception:
            logger.warning('event=free_allowance_lease decision=settlement_unavailable')

    def _locked_billed(self, seconds: float, *, daily_ptt=False) -> None:
        with self.lock:
            self._billed(seconds, daily_ptt=daily_ptt)

    def _billed(self, seconds: float, *, daily_ptt=False) -> None:
        from utils.stt import allowance_watch as watch

        reference = self.reference
        if reference is None:
            return
        try:
            source = {
                'live_open': 'live',
                'sync': 'upload',
                'prerecorded': 'upload',
                'batch_gpu': 'batch',
                'batch_provider': 'batch',
            }.get(self.path, self.path)
            if ledger.settle_billed(
                [reference],
                seconds,
                daily_ptt=daily_ptt,
                source=source,
                decision='would_refuse' if self.refused else 'would_allow' if self.observed else 'unobserved',
            ):
                watch.SETTLED_SECONDS.labels(self.path).inc(seconds)
            self.reference = None
            self.refused = False
            self.observed = False
            self.operation = uuid4().hex
            self.started = None
        except Exception:
            # Billing already committed. Never retry billing because telemetry
            # failed; retaining the old hold cannot manufacture free credit.
            logger.warning('event=free_allowance_lease decision=settlement_unavailable')

    def renew_delay(self) -> float:
        return max(0.05, min(10.0, (self.lease_until - time.time()) / 2)) if self.lease_until is not None else 10.0

    async def monitor(self) -> None:
        if self.loop is None or self.loop.is_closed():
            self.loop = asyncio.get_running_loop()
        while not self.closed:
            self.changed.clear()
            try:
                await asyncio.wait_for(self.changed.wait(), timeout=self.renew_delay())
                continue  # A newly issued deadline changes the wait, not the lease.
            except asyncio.TimeoutError:
                if self.reference is not None:
                    await self.reserve_async(self.provider, customer_funded=self.customer_funded)


@asynccontextmanager
async def track(scope: Operation, *, close: bool = False):
    """Own a renewal task and its context through a complete provider operation."""
    token = current.set(scope)

    renewal = None
    if scope.loop is None or scope.loop.is_closed():
        scope.loop = asyncio.get_running_loop()
    if scope.loop is asyncio.get_running_loop() and (scope.monitor_task is None or scope.monitor_task.done()):
        renewal = asyncio.create_task(scope.monitor())
        scope.monitor_task = renewal
    try:
        yield scope
    finally:
        if close:
            scope.closed = True
        if renewal is not None:
            renewal.cancel()
            with suppress(asyncio.CancelledError):
                await renewal
        current.reset(token)


def operation(path: str, *, live=False):
    """Bind an authenticated entrypoint; child tasks inherit this billing unit."""

    def decorate(fn):
        signature = inspect.signature(fn, eval_str=True)

        @wraps(fn)
        async def wrapped(*args, **kwargs):
            bound = signature.bind_partial(*args, **kwargs)
            uid = bound.arguments.get('uid')
            if not isinstance(uid, str):
                return await fn(*args, **kwargs)
            identity = bound.arguments.get('content_id') or bound.arguments.get('job_id') or uuid4().hex
            scope = Operation(uid, path, operation=f'{path}:{identity}', live=live)
            try:
                async with track(scope):
                    return await fn(*args, **kwargs)
            finally:
                scope.closed = True

        setattr(wrapped, '__signature__', signature)
        return wrapped

    return decorate
