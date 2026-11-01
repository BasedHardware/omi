"""Cloud Tasks queue model with a system throttle (plan F F1; swarm lane 4; contract (d)).

The sync stack's ``cloud_tasks.py`` is a recorder: it has no rate, retry or throttle. This
deterministic virtual-clock model has the semantics that caused two stalls in 12 hours:

- **Rate limits:** a token bucket (``max_dispatches_per_second``, ``max_burst_size``) and
  ``max_concurrent_dispatches``.
- **Retry policy:** ``min_backoff``·2^k up to ``max_doublings``, capped at ``max_backoff``; a task
  is dropped after ``max_attempts``. Any non-2xx is retried, including 409.
- **Named-task dedupe:** creating an existing name is ``already_exists``, never a second task.
- **System throttle (AIMD):** every ``adjust_interval_s`` the queue looks at the last
  ``window_s`` of responses. Any 429/503, or a *fast* 5xx share (latency < ``fast_s``) above
  ``trip_ratio`` with at least ``min_samples`` responses, halves the effective rate down to
  ``floor_rate``. Otherwise, only if the interval had successful completions, the effective rate
  grows by ``recovery_step`` (ramp-up depends on successes). ``update_config`` caps the effective
  rate but never raises it: a config PATCH is not a throttle reset.

Calibration (documented, not fitted to a hidden trace):

- 10-18 18:14Z ``sync-jobs``: 25/s, 160 concurrent, burst 10, 10 attempts, backoff 60-300 s.
  Effective rate fell to 0.4/s (18:2xZ) and 0.1/s (18:40Z) with 41 ok / 47 failed attempts per
  10 min (53% fast 500s, median 0.32 s). ``floor_rate`` = 0.1/s.
- Healthy contrast, ro-prod Monitoring 10-19 04:30-07:15Z: ``sync-jobs-fresh`` ran ~6.3-7.5k ok
  per 15 min with 8-15% non-ok attempts and did not collapse. ``trip_ratio`` = 0.25 sits
  between the two.
- 10-19 04:52Z ``sync-backfill``: the same signature (fast-500 first-summary retries):
  ~45/min admitted, 0-2/min done, 3,552 pending. Reproduced by ``scenario_sync_backfill_0452``.

Assumption to re-check against Monitoring after the 07:07Z 409 train: a 4xx (409) is per-task
retry feedback and does not trip the system throttle. The model encodes Google's documented
rule (429/503 or a high 5xx rate) and nothing stronger.
"""

from __future__ import annotations

import heapq
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Iterable


@dataclass(frozen=True)
class QueueConfig:
    max_dispatches_per_second: float = 25.0
    max_concurrent_dispatches: int = 160
    max_burst_size: int = 10
    max_attempts: int = 10
    min_backoff_s: float = 60.0
    max_backoff_s: float = 300.0
    max_doublings: int = 16


@dataclass(frozen=True)
class ThrottleModel:
    window_s: float = 60.0
    adjust_interval_s: float = 10.0
    fast_s: float = 5.0
    trip_ratio: float = 0.25
    min_samples: int = 8
    cut_factor: float = 0.5
    floor_rate: float = 0.1
    recovery_step: float = 0.05


@dataclass
class Task:
    name: str
    kind: str
    created_at: float
    schedule_at: float
    attempts: int = 0
    last_status: int | None = None
    done_at: float | None = None
    dropped: bool = False


# A handler answers (http_status, latency_seconds) for one dispatch attempt.
Handler = Callable[[Task, float], tuple[int, float]]


@dataclass
class QueueStats:
    created: int = 0
    already_exists: int = 0
    dispatched: int = 0
    completed: int = 0
    dropped: int = 0
    by_status: dict[int, int] = field(default_factory=dict)
    rate_trace: list[tuple[float, float]] = field(default_factory=list)  # (t, effective rate)

    def min_rate(self, after: float = 0.0) -> float:
        return min((r for t, r in self.rate_trace if t >= after), default=0.0)


class CloudTasksQueue:
    def __init__(
        self,
        handler: Handler,
        config: QueueConfig = QueueConfig(),
        throttle: ThrottleModel = ThrottleModel(),
        *,
        tick_s: float = 0.1,
    ):
        self.handler = handler
        self.config = config
        self.throttle = throttle
        self.tick_s = tick_s
        self.now = 0.0
        self.effective_rate = config.max_dispatches_per_second
        self.tokens = float(config.max_burst_size)
        self.tasks: dict[str, Task] = {}
        self._ready: list[tuple[float, int, str]] = []
        self._inflight: list[tuple[float, int, str, int, float]] = []
        self._responses: deque[tuple[float, int, float]] = deque()
        self._seq = 0
        self._next_adjust = throttle.adjust_interval_s
        self._interval_successes = 0
        self.stats = QueueStats()

    # -- API ---------------------------------------------------------------

    def create_task(self, name: str, kind: str, *, delay_s: float = 0.0) -> bool:
        """False (already_exists) when the name is still known to the queue."""
        if name in self.tasks:
            self.stats.already_exists += 1
            return False
        task = Task(name, kind, self.now, self.now + delay_s)
        self.tasks[name] = task
        self._push_ready(task)
        self.stats.created += 1
        return True

    def update_config(self, config: QueueConfig) -> None:
        """A PATCH caps the effective rate; it never resets system throttling upward."""
        self.config = config
        self.effective_rate = min(self.effective_rate, config.max_dispatches_per_second)
        self.tokens = min(self.tokens, float(config.max_burst_size))

    def pending(self, kind: str | None = None) -> int:
        return sum(
            1 for t in self.tasks.values() if t.done_at is None and not t.dropped and (kind is None or t.kind == kind)
        )

    def run_until(self, t_end: float, arrivals: Callable[[float, float], Iterable[tuple[str, str]]] | None = None):
        while self.now < t_end - 1e-9:
            start = self.now
            self.now = round(self.now + self.tick_s, 6)
            if arrivals is not None:
                for name, kind in arrivals(start, self.now):
                    self.create_task(name, kind)
            self._complete_due()
            self._refill()
            self._dispatch()
            if self.now >= self._next_adjust - 1e-9:
                self._adjust()
                self._next_adjust += self.throttle.adjust_interval_s
        return self.stats

    # -- internals ---------------------------------------------------------

    def _push_ready(self, task: Task) -> None:
        self._seq += 1
        heapq.heappush(self._ready, (task.schedule_at, self._seq, task.name))

    def _refill(self) -> None:
        self.tokens = min(float(self.config.max_burst_size), self.tokens + self.effective_rate * self.tick_s)

    def _dispatch(self) -> None:
        while (
            self._ready
            and self._ready[0][0] <= self.now
            and self.tokens >= 1.0
            and len(self._inflight) < self.config.max_concurrent_dispatches
        ):
            _, _, name = heapq.heappop(self._ready)
            task = self.tasks[name]
            task.attempts += 1
            self.tokens -= 1.0
            status, latency = self.handler(task, self.now)
            self._seq += 1
            heapq.heappush(self._inflight, (self.now + max(latency, 0.0), self._seq, name, status, latency))
            self.stats.dispatched += 1

    def _complete_due(self) -> None:
        while self._inflight and self._inflight[0][0] <= self.now:
            finish, _, name, status, latency = heapq.heappop(self._inflight)
            task = self.tasks[name]
            task.last_status = status
            self.stats.by_status[status] = self.stats.by_status.get(status, 0) + 1
            self._responses.append((finish, status, latency))
            if 200 <= status < 300:
                task.done_at = finish
                self.stats.completed += 1
                self._interval_successes += 1
                continue
            if task.attempts >= self.config.max_attempts:
                task.dropped = True
                self.stats.dropped += 1
                continue
            doublings = min(task.attempts - 1, self.config.max_doublings)
            backoff = min(self.config.min_backoff_s * (2**doublings), self.config.max_backoff_s)
            task.schedule_at = finish + backoff
            self._push_ready(task)

    def _adjust(self) -> None:
        horizon = self.now - self.throttle.window_s
        while self._responses and self._responses[0][0] < horizon:
            self._responses.popleft()
        n = len(self._responses)
        hard = any(s in (429, 503) for _, s, _ in self._responses)
        fast_5xx = sum(1 for _, s, lat in self._responses if s >= 500 and lat < self.throttle.fast_s)
        if hard or (n >= self.throttle.min_samples and fast_5xx / n > self.throttle.trip_ratio):
            self.effective_rate = max(self.throttle.floor_rate, self.effective_rate * self.throttle.cut_factor)
        elif self._interval_successes:
            self.effective_rate = min(
                self.config.max_dispatches_per_second, self.effective_rate + self.throttle.recovery_step
            )
        self._interval_successes = 0
        self.stats.rate_trace.append((self.now, round(self.effective_rate, 4)))


# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ScenarioResult:
    name: str
    passed: bool
    min_rate: float
    final_rate: float
    sync_created: int
    sync_completed: int
    sync_pending: int
    enrichment_status: int
    by_status: dict[int, int]
    reason: str

    def summary(self) -> dict:
        return dict(self.__dict__)


def _poisson_arrivals(rng: random.Random, rates_per_min: dict[str, float]):
    counters = {kind: 0 for kind in rates_per_min}

    def arrivals(t0: float, t1: float):
        out = []
        for kind, per_min in rates_per_min.items():
            expected = per_min / 60.0 * (t1 - t0)
            n = int(expected) + (1 if rng.random() < expected - int(expected) else 0)
            for _ in range(n):
                counters[kind] += 1
                out.append((f'{"sr-" if kind == "enrichment" else ""}{kind}-{counters[kind]:07d}', kind))
        return out

    return arrivals


def run_enrichment_stall(
    enrichment_status: int,
    *,
    name: str,
    config: QueueConfig,
    sync_per_min: float,
    enrichment_per_min: float,
    duration_s: float,
    sync_latency_s: tuple[float, float] = (2.0, 30.0),
    enrichment_latency_s: float = 0.32,
    seed: int = 1,
    throttle: ThrottleModel = ThrottleModel(),
) -> ScenarioResult:
    """Shared fresh queue: direct sync jobs succeed; first-summary wakes stay pending forever
    (deleted merge donors / open live targets, sol-queue-stall §3) and answer ``enrichment_status``."""
    rng = random.Random(seed)

    def handler(task: Task, now: float) -> tuple[int, float]:
        if task.kind == 'enrichment':
            return enrichment_status, enrichment_latency_s
        return 200, rng.uniform(*sync_latency_s)

    queue = CloudTasksQueue(handler, config, throttle)
    arrivals = _poisson_arrivals(rng, {'sync': sync_per_min, 'enrichment': enrichment_per_min})
    stats = queue.run_until(duration_s, arrivals)
    sync_created = sum(1 for t in queue.tasks.values() if t.kind == 'sync')
    sync_pending = queue.pending('sync')
    sync_completed = sync_created - sync_pending
    settled = duration_s / 2
    min_rate = stats.min_rate(after=settled)
    # PASS: the queue keeps its configured rate and direct jobs keep up with intake
    # (everything older than one minute has completed).
    keeps_rate = min_rate >= 0.5 * config.max_dispatches_per_second
    keeps_up = sync_pending <= sync_per_min * 1.0 + 5
    reason = (
        'ok'
        if keeps_rate and keeps_up
        else (f'effective rate collapsed to {min_rate}/s' if not keeps_rate else f'{sync_pending} direct jobs stuck')
    )
    return ScenarioResult(
        name,
        keeps_rate and keeps_up,
        min_rate,
        queue.effective_rate,
        sync_created,
        sync_completed,
        sync_pending,
        enrichment_status,
        dict(sorted(stats.by_status.items())),
        reason,
    )


SYNC_JOBS_1018 = QueueConfig(25.0, 160, 10, 10, 60.0, 300.0)
SYNC_BACKFILL = QueueConfig(30.0, 30, 10, 10, 60.0, 300.0)  # backend/AGENTS.md: 30 concurrent, 30/s cap


def scenario_enrichment_fast_500_throttle(enrichment_status: int, *, duration_s: float = 900.0, seed: int = 1):
    """10-18 18:14Z ``sync-jobs`` shape: ~191 direct jobs/min + ~37 first-summary wakes/min."""
    return run_enrichment_stall(
        enrichment_status,
        name='enrichment_fast_500_throttle',
        config=SYNC_JOBS_1018,
        sync_per_min=191.0,
        enrichment_per_min=37.0,
        duration_s=duration_s,
        seed=seed,
    )


def scenario_sync_backfill_0452(enrichment_status: int, *, duration_s: float = 900.0, seed: int = 2):
    """10-19 04:52Z ``sync-backfill`` shape: ~45 admissions/min, first-summary retries on the same queue."""
    return run_enrichment_stall(
        enrichment_status,
        name='sync_backfill_0452',
        config=SYNC_BACKFILL,
        sync_per_min=45.0,
        enrichment_per_min=20.0,
        duration_s=duration_s,
        sync_latency_s=(5.0, 40.0),  # 30 concurrent x ~22 s mean keeps up with 45/min when unthrottled
        seed=seed,
    )


def enrichment_route_status() -> int:
    """HTTP status the *current* ``routers.batch_pipeline.enrichment_response`` answers for an
    expected first-summary wait (``FirstSummaryCallbackPending``). Real route code; the runtime
    fence and the adapter are the only stand-ins."""
    import asyncio

    from routers import batch_pipeline
    from utils.sync import reprocess

    def pending(*_args, **_kwargs):
        raise reprocess.FirstSummaryCallbackPending('no processing output yet')

    saved = (reprocess.owns_runtime, batch_pipeline.run_enrichment)
    reprocess.owns_runtime = lambda: True
    batch_pipeline.run_enrichment = pending
    try:
        response = asyncio.run(
            batch_pipeline.enrichment_response({'kind': 'sync_reprocess', 'key': 'a' * 64, 'task_token': 'b' * 32})
        )
    finally:
        reprocess.owns_runtime, batch_pipeline.run_enrichment = saved
    return int(response.status_code)


def main(argv: list[str] | None = None) -> int:
    """``python -m testing.fakes.cloud_tasks_queue`` from backend/ with the hermetic test env
    (``ENCRYPTION_SECRET`` from tests/conftest.py); exit 1 when a scenario stalls."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description='Cloud Tasks throttle scenarios against the current route code')
    parser.add_argument('--duration-s', type=float, default=3600.0)
    args = parser.parse_args(argv)
    status = enrichment_route_status()
    results = [
        scenario_enrichment_fast_500_throttle(status, duration_s=args.duration_s),
        scenario_sync_backfill_0452(status, duration_s=args.duration_s),
    ]
    for r in results:
        print(json.dumps(r.summary(), sort_keys=True))
    return 0 if all(r.passed for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
