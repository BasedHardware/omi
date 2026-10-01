"""Cached, bounded fleet pressure for window admission; no I/O on admission."""

from __future__ import annotations

import asyncio
import math
import os
import socket
import time
from contextlib import suppress
from dataclasses import dataclass

import httpx

from utils.executors import start_background_task
from utils.stt.live_metrics import WINDOW_PRESSURE_REFRESH, WINDOW_PRESSURE_REFUSAL, WINDOW_PRESSURE_REPLICAS


@dataclass(frozen=True)
class ReplicaPressure:
    pending: int
    oldest: float
    observed_at: float


class BatchPressure:
    """Retain each ready replica's last valid sample for at most 15 seconds."""

    REFRESH_SECONDS = 5.0
    STALE_SECONDS = 15.0
    REQUEST_TIMEOUT_SECONDS = 1.0
    MAX_REPLICAS = 64
    MAX_LIVE_PENDING_PER_REPLICA = 4
    MAX_LIVE_OLDEST_SECONDS = 0.75
    BUSY_REPLICA_SHARE = 0.5

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._observed_at = 0.0
        self._ready: tuple[str, ...] = ()
        self._samples: dict[str, ReplicaPressure] = {}
        self._max_pending = self.MAX_LIVE_PENDING_PER_REPLICA
        self._max_oldest = self.MAX_LIVE_OLDEST_SECONDS
        self._busy_share = self.BUSY_REPLICA_SHARE
        self._configured = True

    def start_from_env(self) -> None:
        if os.getenv('STT_CONNECT_ORDER_FROM_CONFIG', 'false').lower() != 'true':
            return
        try:
            allocation = float(os.getenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '0'))
            min_replicas = int(os.getenv('PARAKEET_BATCH_PRESSURE_MIN_REPLICAS', '2'))
        except ValueError:
            return
        pool_host = os.getenv('PARAKEET_BATCH_PRESSURE_POOL_HOST', '')
        if not math.isfinite(allocation) or allocation <= 0 or not pool_host or min_replicas < 1:
            return
        self.start(pool_host, min_replicas)

    def _reset(self) -> None:
        self._observed_at = 0.0
        self._ready = ()
        self._samples.clear()
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
        while True:
            try:
                limits = httpx.Limits(
                    max_connections=self.MAX_REPLICAS,
                    max_keepalive_connections=self.MAX_REPLICAS,
                    keepalive_expiry=30.0,
                )
                async with httpx.AsyncClient(
                    timeout=self.REQUEST_TIMEOUT_SECONDS, trust_env=False, limits=limits
                ) as client:
                    while True:
                        try:
                            await self._refresh(pool_host, min_replicas, client)
                        except Exception:
                            self._unavailable()
                        await asyncio.sleep(self.REFRESH_SECONDS)
            except Exception:
                self._unavailable()
                await asyncio.sleep(self.REFRESH_SECONDS)

    def _unavailable(self) -> None:
        # DNS/client faults leave the fleet unknown, even if old pod samples exist.
        self._observed_at = 0.0
        self._ready = ()
        self._publish_counts(time.monotonic())
        WINDOW_PRESSURE_REFRESH.labels(outcome='unavailable').inc()

    def _fresh(self, now: float) -> dict[str, ReplicaPressure]:
        return {ip: sample for ip, sample in self._samples.items() if now - sample.observed_at <= self.STALE_SECONDS}

    def _publish_counts(self, now: float) -> None:
        WINDOW_PRESSURE_REPLICAS.labels(state='ready').set(len(self._ready))
        WINDOW_PRESSURE_REPLICAS.labels(state='fresh').set(len(self._fresh(now)) if self._ready else 0)

    def _reason(self, min_replicas: int, now: float) -> str | None:
        if self._observed_at <= 0:
            return 'missing'
        if now - self._observed_at > self.STALE_SECONDS:
            return 'stale'
        fresh = self._fresh(now)
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
        if pending < 1 or not math.isfinite(oldest) or oldest <= 0 or not math.isfinite(share) or not 0 < share <= 1:
            raise ValueError('Invalid Parakeet batch pressure thresholds')
        self._max_pending, self._max_oldest, self._busy_share = pending, oldest, share
        self._configured = True

    async def _fetch(self, ip: str, client: httpx.AsyncClient) -> ReplicaPressure:
        response = await asyncio.wait_for(
            client.get(f'http://{ip}:8080/batch/metrics', timeout=self.REQUEST_TIMEOUT_SECONDS),
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

    async def _refresh(self, pool_host: str, min_replicas: int, client: httpx.AsyncClient) -> None:
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
                raise ValueError('Parakeet batch pool outside bounded discovery size')
        except Exception:
            self._unavailable()
            return
        self._ready = ips
        # Remove departed pods; memory and quorum use the current ready set.
        self._samples = {ip: self._samples[ip] for ip in ips if ip in self._samples}
        results = await asyncio.gather(*(self._fetch(ip, client) for ip in ips), return_exceptions=True)
        received = 0
        for ip, result in zip(ips, results):
            if not isinstance(result, BaseException):
                self._samples[ip] = result
                received += 1
        now = time.monotonic()
        self._observed_at = now  # DNS succeeded; failed fetches retain their own old timestamps.
        self._publish_counts(now)
        reason = self._reason(min_replicas, now)
        if reason == 'missing':
            outcome = 'unavailable'
        elif received < len(ips):
            outcome = 'partial'
        else:
            outcome = 'pressure' if reason else 'healthy'
        WINDOW_PRESSURE_REFRESH.labels(outcome=outcome).inc()
