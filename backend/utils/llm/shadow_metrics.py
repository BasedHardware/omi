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
from dataclasses import dataclass, field
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
    - The clock is injectable for testability (default `time.time`).

    The default AlertSink and MetricsSink are no-ops (record but don't
    fire / increment). R3.2 wires the real sinks.
    """

    DEFAULT_WINDOW_SECONDS = 86400  # 24h
    DEFAULT_THRESHOLD = 0.01  # 1%

    def __init__(
        self,
        *,
        alert_sink: Optional[AlertSink] = None,
        metrics_sink: Optional[MetricsSink] = None,
        clock: Callable[[], float] = time.time,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        threshold: float = DEFAULT_THRESHOLD,
    ) -> None:
        self._alert_sink = alert_sink
        self._metrics_sink = metrics_sink
        self._clock = clock
        self._window_seconds = window_seconds
        self._threshold = threshold
        # Per-lane record ring buffers
        self._records: dict[str, Deque[PerCallRecord]] = {}
        # Track which lanes have already alerted (suppress duplicate alerts)
        self._alerted_lanes: set[str] = set()

    def record(self, record: PerCallRecord) -> Optional[Alert]:
        """Record a per-call result. Returns an Alert if the rolling aggregate
        exceeds the threshold; None otherwise.

        On Alert: also calls AlertSink.fire() (if configured) and updates
        MetricsSink counters.
        """
        # Append to the lane's ring buffer
        bucket = self._records.setdefault(record.lane_id, deque())
        bucket.append(record)
        # Drop records older than the window
        cutoff = record.timestamp - self._window_seconds
        while bucket and bucket[0].timestamp < cutoff:
            bucket.popleft()
        # Update metrics sink (per-call)
        if self._metrics_sink is not None:
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
                self._fire_alert(alert)
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
        if self._alert_sink is None:
            logger.warning(alert.message)
            return
        # AlertSink.fire is async; in R3.1 tests we use a fake with an
        # async fire. In R3.2 with a real sink, this is the call site.
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(
                self._alert_sink.fire(
                    lane_id=alert.lane_id,
                    message=alert.message,
                    metadata={
                        "aggregate_score": alert.aggregate_score,
                        "window_seconds": alert.window_seconds,
                        "sample_count": alert.sample_count,
                    },
                )
            )
        except RuntimeError:
            # No running loop (sync context). Fall back to sync fire.
            asyncio.run(
                self._alert_sink.fire(
                    lane_id=alert.lane_id,
                    message=alert.message,
                    metadata={
                        "aggregate_score": alert.aggregate_score,
                        "window_seconds": alert.window_seconds,
                        "sample_count": alert.sample_count,
                    },
                )
            )

    def clear(self) -> None:
        """Drop all per-lane records and alert state. Test helper."""
        self._records.clear()
        self._alerted_lanes.clear()
