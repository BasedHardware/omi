"""Cached, bounded fleet pressure for window admission; no I/O on admission."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import socket
import time
from contextlib import suppress
from dataclasses import dataclass
from time import time as wall_time

import httpx

from config.policy.listen import window_pressure_allocation
from utils.executors import start_background_task
from utils.observability.fallback import record_fallback
from utils.stt.live_metrics import (
    WINDOW_PRESSURE_FETCH_FAILURE,
    WINDOW_PRESSURE_REFRESH,
    WINDOW_PRESSURE_REFUSAL,
    WINDOW_PRESSURE_REPLICAS,
    WINDOW_PRESSURE_PROGRESS_TIME,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReplicaPressure:
    pending: int
    oldest: float
    observed_at: float


class BatchPressure:
    """Bounded last-good observations; freshness and admission age are separate."""

    REFRESH_SECONDS = 5.0
    STALE_SECONDS = 15.0
    # A one-second total deadline can cancel cold connections before TCP retry.
    # Polling is off the admission path; allow cold setup without unbounded waits.
    REQUEST_TIMEOUT_SECONDS = 3.0
    HTTP_OPERATION_TIMEOUT_SECONDS = 2.0
    MAX_SNAPSHOT_AGE_SECONDS = 60.0
    RESET_AFTER_FAILURES = 3
    MAX_REPLICAS = 64
    MAX_LIVE_PENDING_PER_REPLICA = 4
    MAX_LIVE_OLDEST_SECONDS = 0.75
    BUSY_REPLICA_SHARE = 0.5

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._observed_at = 0.0
        self._last_good_at = 0.0
        self._ready: tuple[str, ...] = ()
        self._samples: dict[str, ReplicaPressure] = {}
        self._max_pending = self.MAX_LIVE_PENDING_PER_REPLICA
        self._max_oldest = self.MAX_LIVE_OLDEST_SECONDS
        self._busy_share = self.BUSY_REPLICA_SHARE
        self._configured = True
        self._discovery_available = False
        self._max_snapshot_age = self.MAX_SNAPSHOT_AGE_SECONDS
        self._reset_after_failures = self.RESET_AFTER_FAILURES

    def start_from_env(self) -> None:
        try:
            allocation = window_pressure_allocation()
            min_replicas = int(os.getenv('PARAKEET_BATCH_PRESSURE_MIN_REPLICAS', '2'))
        except ValueError:
            return
        pool_host = os.getenv('PARAKEET_BATCH_PRESSURE_POOL_HOST', '')
        if not math.isfinite(allocation) or allocation <= 0 or not pool_host or min_replicas < 1:
            return
        self.start(pool_host, min_replicas)

    def _reset(self) -> None:
        self._observed_at = 0.0
        self._last_good_at = 0.0
        self._ready = ()
        self._samples.clear()
        self._discovery_available = False
        WINDOW_PRESSURE_PROGRESS_TIME.set(wall_time())
        self._publish_counts(time.monotonic())

    def start(self, pool_host: str, min_replicas: int) -> None:
        loop = asyncio.get_running_loop()
        if self._task is not None and not self._task.done():
            if self._task.get_loop() is not loop:
                raise RuntimeError('Batch pressure poller belongs to another running event loop')
            return
        self._reset()
        self._task = start_background_task(self._refresh_forever(pool_host, min_replicas), name='window_batch_pressure')

    async def stop(self) -> None:
        task = self._task
        if task is not None:
            if task.get_loop() is not asyncio.get_running_loop():
                raise RuntimeError('Batch pressure poller must stop on its owning event loop')
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        self._task = None
        self._reset()

    async def _refresh_forever(self, pool_host: str, min_replicas: int) -> None:
        failed_sweeps = 0
        while True:
            try:
                limits = httpx.Limits(
                    max_connections=self.MAX_REPLICAS,
                    max_keepalive_connections=self.MAX_REPLICAS,
                    keepalive_expiry=30.0,
                )
                async with httpx.AsyncClient(
                    timeout=self.HTTP_OPERATION_TIMEOUT_SECONDS, trust_env=False, limits=limits
                ) as client:
                    while True:
                        try:
                            usable = await self._refresh(pool_host, min_replicas, client)
                        except Exception:
                            self._unavailable()
                            usable = False
                        failed_sweeps = 0 if usable else failed_sweeps + 1
                        if failed_sweeps >= self._reset_after_failures:
                            WINDOW_PRESSURE_REFRESH.labels(outcome='reset_client').inc()
                            logger.warning(
                                'Batch pressure sampler resetting client after %d failed sweeps', failed_sweeps
                            )
                            failed_sweeps = 0
                            # Leave the context to close the pool, then rediscover
                            # with a new client. Cached timestamps are untouched.
                            break
                        await asyncio.sleep(self.REFRESH_SECONDS)
                # A reset still observes the polling cadence, including N=1.
                # Otherwise fast failures/config errors can spin new clients.
                await asyncio.sleep(self.REFRESH_SECONDS)
            except Exception:
                self._unavailable()
                await asyncio.sleep(self.REFRESH_SECONDS)

    def _unavailable(self) -> None:
        # Preserve the last discovery and samples only for the bounded grace.
        # Neither failure nor client replacement renews their timestamps.
        self._discovery_available = False
        self._publish_counts(time.monotonic())
        WINDOW_PRESSURE_REFRESH.labels(outcome='unavailable').inc()

    def _fresh(self, now: float, max_age: float = STALE_SECONDS) -> dict[str, ReplicaPressure]:
        return {
            ip: sample
            for ip, sample in self._samples.items()
            if ip in self._ready and now - sample.observed_at <= max_age
        }

    def _publish_counts(self, now: float) -> None:
        WINDOW_PRESSURE_REPLICAS.labels(state='ready').set(len(self._ready) if self._discovery_available else 0)
        WINDOW_PRESSURE_REPLICAS.labels(state='fresh').set(len(self._fresh(now)) if self._discovery_available else 0)

    def _reason(self, min_replicas: int, now: float, *, max_age: float = STALE_SECONDS) -> str | None:
        if self._observed_at <= 0 or (not self._discovery_available and max_age == self.STALE_SECONDS):
            return 'missing'
        if now - self._observed_at > max_age:
            return 'stale'
        fresh = self._fresh(now, max_age)
        ready_count = len(self._ready)
        quorum = max(min_replicas, ready_count // 2 + 1)
        if len(fresh) < quorum:
            return 'missing'
        busy = sum(
            sample.pending >= self._max_pending or sample.oldest >= self._max_oldest for sample in fresh.values()
        )
        # Unknown pods cannot provide headroom. At the default 50% threshold,
        # admission requires a strict majority of ready pods known healthy.
        if (busy + ready_count - len(fresh)) / ready_count >= self._busy_share:
            return 'pressure'
        return None

    def allows(self, pool_host: str, min_replicas: int) -> bool:
        if not pool_host or min_replicas < 1 or not self._configured:
            WINDOW_PRESSURE_REFUSAL.labels(reason='unconfigured').inc()
            return False
        now = time.monotonic()
        self._publish_counts(now)
        reason = self._reason(min_replicas, now)
        if (
            reason in ('missing', 'stale', 'pressure')
            and self._max_snapshot_age > self.STALE_SECONDS
            and self._last_good_at > 0
            and now - self._last_good_at <= self._max_snapshot_age
        ):
            # Re-run the same quorum/pressure math with bounded last-good samples.
            # New busy samples always supersede older healthy observations, and
            # departed pods were pruned by discovery. Never grant blind headroom.
            if self._reason(min_replicas, now, max_age=self._max_snapshot_age) is None:
                record_fallback(
                    component='stt_selection',
                    from_mode='fresh_pressure',
                    to_mode='cached_pressure',
                    reason='timeout',
                    outcome='degraded',
                )
                return True
        if reason is not None:
            WINDOW_PRESSURE_REFUSAL.labels(reason=reason).inc()
            return False
        return True

    def _read_thresholds(self) -> None:
        self._configured = False
        pending = int(
            os.getenv('PARAKEET_BATCH_PRESSURE_MAX_LIVE_PENDING_PER_REPLICA', str(self.MAX_LIVE_PENDING_PER_REPLICA))
        )
        oldest = float(os.getenv('PARAKEET_BATCH_PRESSURE_MAX_LIVE_OLDEST_SECONDS', str(self.MAX_LIVE_OLDEST_SECONDS)))
        share = float(os.getenv('PARAKEET_BATCH_PRESSURE_BUSY_REPLICA_SHARE', str(self.BUSY_REPLICA_SHARE)))
        max_age = float(
            os.getenv('PARAKEET_BATCH_PRESSURE_MAX_SNAPSHOT_AGE_SECONDS', str(self.MAX_SNAPSHOT_AGE_SECONDS))
        )
        reset_after = int(os.getenv('PARAKEET_BATCH_PRESSURE_RESET_AFTER_FAILURES', str(self.RESET_AFTER_FAILURES)))
        if pending < 1 or not math.isfinite(oldest) or oldest <= 0 or not math.isfinite(share) or not 0 < share <= 1:
            raise ValueError('Invalid Parakeet batch pressure thresholds')
        if (
            not math.isfinite(max_age)
            or not self.STALE_SECONDS <= max_age <= self.MAX_SNAPSHOT_AGE_SECONDS
            or reset_after < 1
        ):
            raise ValueError('Invalid Parakeet batch pressure recovery configuration')
        self._max_pending, self._max_oldest, self._busy_share = pending, oldest, share
        self._max_snapshot_age, self._reset_after_failures = max_age, reset_after
        self._configured = True

    def ready_replicas(self) -> tuple[str, ...]:
        """Fresh, DNS-ready identities for live-window direct pod routing."""
        fresh = self._fresh(time.monotonic())
        return tuple(ip for ip in self.discovered_replicas() if ip in fresh)

    def discovered_replicas(self) -> tuple[str, ...]:
        """Fresh DNS membership, independent of individual pressure samples."""
        now = time.monotonic()
        if (
            not getattr(self, '_discovery_available', True)
            or self._observed_at <= 0
            or now - self._observed_at > self.STALE_SECONDS
        ):
            return ()
        return self._ready

    async def _fetch(self, ip: str, client: httpx.AsyncClient) -> ReplicaPressure:
        response = await asyncio.wait_for(
            client.get(
                f'http://{ip}:8080/batch/metrics',
                # Leave room for HTTPX to report connect/read/pool timeouts
                # before the total deadline cancels the entire request.
                timeout=min(self.HTTP_OPERATION_TIMEOUT_SECONDS, self.REQUEST_TIMEOUT_SECONDS),
            ),
            timeout=self.REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        metrics = response.json()
        pending, oldest = metrics['live_pending_requests'], metrics['live_oldest_pending_seconds']
        if (
            any(
                isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0
                for value in (pending, oldest)
            )
            or int(pending) != pending
        ):
            raise ValueError('Invalid Parakeet live pressure sample')
        return ReplicaPressure(int(pending), float(oldest), time.monotonic())

    async def _refresh(self, pool_host: str, min_replicas: int, client: httpx.AsyncClient) -> bool:
        try:
            self._read_thresholds()
            if not pool_host or min_replicas < 1:
                raise ValueError('Parakeet batch pool discovery is not configured')
            addresses = await asyncio.wait_for(
                asyncio.get_running_loop().getaddrinfo(pool_host, 8080, family=socket.AF_INET, type=socket.SOCK_STREAM),
                timeout=self.REQUEST_TIMEOUT_SECONDS,
            )
            ips = tuple(sorted({address[4][0] for address in addresses}))
            if not ips or len(ips) > self.MAX_REPLICAS:
                # Known empty/out-of-bounds discovery is not a transient DNS
                # failure. The former membership cannot establish headroom.
                self._ready = ()
                self._samples.clear()
                self._last_good_at = 0.0
                raise ValueError('Parakeet batch pool outside bounded discovery size')
        except Exception:
            self._unavailable()
            return False
        self._ready = ips
        self._discovery_available = True
        # Remove departed pods; memory and quorum use the current ready set.
        self._samples = {ip: self._samples[ip] for ip in ips if ip in self._samples}
        results = await asyncio.gather(*(self._fetch(ip, client) for ip in ips), return_exceptions=True)
        received = 0
        for ip, result in zip(ips, results):
            if not isinstance(result, BaseException):
                self._samples[ip] = result
                received += 1
            else:
                if isinstance(result, httpx.ConnectTimeout):
                    cause = 'connect_timeout'
                elif isinstance(result, httpx.PoolTimeout):
                    cause = 'pool_timeout'
                elif isinstance(result, httpx.ReadTimeout):
                    cause = 'read_timeout'
                elif isinstance(result, (TimeoutError, httpx.TimeoutException)):
                    cause = 'deadline'
                elif isinstance(result, httpx.HTTPStatusError):
                    cause = 'http_status'
                elif isinstance(result, httpx.TransportError):
                    cause = 'transport'
                elif isinstance(result, (ValueError, KeyError, TypeError)):
                    cause = 'invalid_sample'
                else:
                    cause = 'other'
                WINDOW_PRESSURE_FETCH_FAILURE.labels(cause=cause).inc()
        now = time.monotonic()
        self._observed_at = now  # DNS succeeded; failed fetches retain their own old timestamps.
        if received:
            WINDOW_PRESSURE_PROGRESS_TIME.set(wall_time())
        self._publish_counts(now)
        reason = self._reason(min_replicas, now)
        if reason in (None, 'pressure'):
            # Grace requires a previously usable quorum, including its oldest
            # observation. Partial cold-start sweeps cannot bootstrap grace.
            self._last_good_at = min(sample.observed_at for sample in self._fresh(now).values())
        if reason == 'missing':
            outcome = 'unavailable'
        elif received < len(ips):
            outcome = 'partial'
        else:
            outcome = 'pressure' if reason else 'healthy'
        WINDOW_PRESSURE_REFRESH.labels(outcome=outcome).inc()
        # Count newly received samples, not cached freshness: otherwise old
        # samples postpone pool repair until they have already expired.
        return received >= max(min_replicas, len(ips) // 2 + 1)
