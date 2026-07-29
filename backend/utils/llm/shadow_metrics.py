"""Divergence tracking + alert for the R3 dual-path cutover (R3.1).

Tracks per-call records + rolling-24h aggregate divergence per lane.
Fires an alert (via pluggable AlertSink) when rolling-24h aggregate
divergence > threshold (default 1%).

Pluggable design:
- AlertSink: where alerts go (Prometheus counter + Sentry in R3.2; fakes
  in R3.1 tests).
- MetricsSink: where per-call metrics go (existing observability infra in
  R3.2; fakes in R3.1 tests).
- Clock: for testability (default `time.time`; tests use FakeClock).

This is the R3.1 infrastructure component. The actual call-site swap
(R3.2) plugs in real AlertSink + MetricsSink.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, Deque, Optional, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sinks (Protocol — production code can plug in real implementations)
# ---------------------------------------------------------------------------


class AlertSink(Protocol):
    """Where divergence alerts go. Real impl: Prometheus counter + Sentry."""

    async def fire(self, *, lane_id: str, message: str, metadata: dict[str, Any]) -> None: ...


class MetricsSink(Protocol):
    """Where per-call metrics go. Real impl: existing observability infra."""

    def increment(self, *, metric: str, value: float = 1.0, labels: Optional[dict[str, str]] = None) -> None: ...

    def gauge(self, *, metric: str, value: float, labels: Optional[dict[str, str]] = None) -> None: ...


# ---------------------------------------------------------------------------
# Per-call record
# ---------------------------------------------------------------------------


@dataclass
class PerCallRecord:
    """One shadow-cutover call's outcome. Recorded into ShadowMetrics."""

    lane_id: str
    timestamp: float
    control_latency_ms: float
    gateway_latency_ms: float
    gateway_success: bool
    divergence_score: float  # 0.0 (identical) to 1.0 (completely different)
    token_match: bool
    structural_match: bool


# ---------------------------------------------------------------------------
# Alert (return value of record())
# ---------------------------------------------------------------------------


@dataclass
class Alert:
    """A divergence alert. Returned by ShadowMetrics.record() when fired."""

    lane_id: str
    aggregate_score: float
    window_seconds: float
    sample_count: int
    message: str = ""


# ---------------------------------------------------------------------------
# ShadowMetrics
# ---------------------------------------------------------------------------


class ShadowMetrics:
    """Per-call + rolling-window divergence tracking.

    Behavior:
    - record(record): stores the per-call record; computes rolling-window
      aggregate; fires an alert (via AlertSink) if aggregate > threshold.
    - The rolling window is `window_seconds` (default 86400 = 24h).
    - Records older than `window_seconds` are dropped from the aggregate.
    - **Memory cap**: as a safety net, each lane is also capped at
      `max_records_per_lane` records (default 10,000). For high-volume
      lanes, this becomes the effective limit — the rolling window is
      truncated to the most recent N records per lane. The cap prevents
      unbounded memory growth if the clock is stuck or the time-based
      window eviction doesn't trigger for any reason.
    - The clock is injectable for testability (default `time.time`).

    The default AlertSink and MetricsSink are no-ops (record but don't
    fire / increment). R3.2 wires the real sinks.
    """

    DEFAULT_WINDOW_SECONDS = 86400  # 24h
    DEFAULT_THRESHOLD = 0.01  # 1%
    # Memory safety: cap per-lane record count even if the window hasn't
    # naturally dropped entries. P2 #4: unbounded memory growth.
    DEFAULT_MAX_RECORDS_PER_LANE = 10_000

    def __init__(
        self,
        *,
        alert_sink: Optional[AlertSink] = None,
        metrics_sink: Optional[MetricsSink] = None,
        clock: Callable[[], float] = time.time,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        threshold: float = DEFAULT_THRESHOLD,
        max_records_per_lane: int = DEFAULT_MAX_RECORDS_PER_LANE,
    ) -> None:
        # P1 (cubic follow-up): validate the cap. Negative or zero would
        # cause IndexError on the evict loop (negative lets popleft on an
        # empty bucket; zero immediately empties the bucket so aggregation
        # is always 0 and alerts never fire). Reject loudly at construction.
        if max_records_per_lane <= 0:
            raise ValueError(f"max_records_per_lane must be > 0, got {max_records_per_lane}")
        self._alert_sink = alert_sink
        self._metrics_sink = metrics_sink
        self._clock = clock
        self._window_seconds = window_seconds
        self._threshold = threshold
        self._max_records_per_lane = max_records_per_lane
        # Per-lane record ring buffers
        self._records: dict[str, Deque[PerCallRecord]] = {}
        # Track which lanes have already alerted (suppress duplicate alerts)
        self._alerted_lanes: set[str] = set()

    def set_threshold(self, threshold: float) -> None:
        """Update the rolling-window divergence alert threshold."""
        self._threshold = threshold

    def record(self, record: PerCallRecord) -> Optional[Alert]:
        """Record a per-call result. Returns an Alert if the rolling aggregate
        exceeds the threshold; None otherwise.

        On Alert: also calls AlertSink.fire() (if configured) and updates
        MetricsSink counters.

        P1 #2 + P1 #3 (cubic review): metrics and alert sink failures are
        SAFELY CONTAINED — a sink exception is logged but does not break the
        call site. Observability is best-effort.
        """
        # Append to the lane's ring buffer
        bucket = self._records.setdefault(record.lane_id, deque())
        bucket.append(record)
        # Drop records older than the window (time-based eviction)
        cutoff = record.timestamp - self._window_seconds
        while bucket and bucket[0].timestamp < cutoff:
            bucket.popleft()
        # P2 #4: cap deque size as a memory safety net (in case the time-based
        # window somehow doesn't trigger eviction, e.g., clock stuck)
        while len(bucket) > self._max_records_per_lane:
            bucket.popleft()
        # Update metrics sink (per-call) — safely contained
        if self._metrics_sink is not None:
            try:
                self._metrics_sink.increment(
                    metric="gateway_shadow_calls_total",
                    value=1.0,
                    labels={"lane": record.lane_id, "gateway_success": str(record.gateway_success).lower()},
                )
                self._metrics_sink.gauge(
                    metric="gateway_shadow_divergence_score",
                    value=record.divergence_score,
                    labels={"lane": record.lane_id},
                )
            except Exception as e:
                logger.warning("metrics sink failed (swallowed): %s: %s", type(e).__name__, e)
        # Compute the rolling aggregate
        aggregate = self._aggregate(bucket)
        if aggregate > self._threshold:
            alert = Alert(
                lane_id=record.lane_id,
                aggregate_score=aggregate,
                window_seconds=self._window_seconds,
                sample_count=len(bucket),
                message=(
                    f"lane {record.lane_id} divergence {aggregate:.2%} "
                    f"over {self._window_seconds}s (threshold {self._threshold:.2%})"
                ),
            )
            if record.lane_id not in self._alerted_lanes:
                self._alerted_lanes.add(record.lane_id)
                # P2 #5: don't mark as alerted-until-fire-completes. We
                # optimistically mark it before (so a burst of N alerts
                # doesn't fire N times in a row) but clear the flag if the
                # fire fails — so the next divergence re-fires correctly.
                # Wrap in try/except so a sink failure doesn't break record().
                try:
                    self._fire_alert(alert)
                except Exception as e:
                    logger.warning("alert sink failed (swallowed): %s: %s", type(e).__name__, e)
                    # Clear the flag so the next divergence re-fires.
                    self._alerted_lanes.discard(record.lane_id)
            return alert
        # Below threshold: clear the alerted state (next time we cross, we'll alert again)
        self._alerted_lanes.discard(record.lane_id)
        return None

    def _aggregate(self, bucket: Deque[PerCallRecord]) -> float:
        """Mean divergence score over the rolling window."""
        if not bucket:
            return 0.0
        return sum(r.divergence_score for r in bucket) / len(bucket)

    def _fire_alert(self, alert: Alert) -> None:
        alert_sink = self._alert_sink
        if alert_sink is None:
            logger.warning(alert.message)
            return
        # AlertSink.fire is async; in R3.1 tests we use a fake with an
        # async fire. In R3.2 with a real sink, this is the call site.
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop (sync context). Fire synchronously.
            try:
                asyncio.run(
                    alert_sink.fire(
                        lane_id=alert.lane_id,
                        message=alert.message,
                        metadata={
                            "aggregate_score": alert.aggregate_score,
                            "window_seconds": alert.window_seconds,
                            "sample_count": alert.sample_count,
                        },
                    )
                )
            except Exception as e:
                logger.warning("alert sink failed (swallowed): %s: %s", type(e).__name__, e)
                # P2 #5: clear the flag so the next divergence re-fires.
                self._alerted_lanes.discard(alert.lane_id)
            return
        # Async context: schedule the fire as a task. P2 #5: the inner
        # coroutine catches its own exception and clears the alerted state
        # if the fire fails — so the next divergence re-fires correctly.
        lane_id = alert.lane_id

        async def _fire() -> None:
            try:
                await alert_sink.fire(
                    lane_id=lane_id,
                    message=alert.message,
                    metadata={
                        "aggregate_score": alert.aggregate_score,
                        "window_seconds": alert.window_seconds,
                        "sample_count": alert.sample_count,
                    },
                )
            except Exception as e:
                logger.warning("alert sink failed (swallowed): %s: %s", type(e).__name__, e)
                self._alerted_lanes.discard(lane_id)

        loop.create_task(_fire())

    def clear(self) -> None:
        """Drop all per-lane records and alert state. Test helper."""
        self._records.clear()
        self._alerted_lanes.clear()
