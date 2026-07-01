"""Tests for the R3.1 `ShadowMetrics` divergence tracking."""

from __future__ import annotations

import asyncio

import pytest

from utils.llm.shadow_metrics import (
    Alert,
    AlertSink,
    MetricsSink,
    PerCallRecord,
    ShadowMetrics,
)
from tests.unit.llm.fakes import (
    FakeAlertSink,
    FakeClock,
    FakeMetricsSink,
)


def _record(
    *,
    clock: FakeClock,
    lane_id: str = "omi:auto:chat-extraction",
    divergence: float = 0.0,
    gateway_success: bool = True,
    advance: float = 0.0,
) -> PerCallRecord:
    """Build a PerCallRecord at the current fake-clock time."""
    if advance:
        clock.advance(advance)
    return PerCallRecord(
        lane_id=lane_id,
        timestamp=clock(),
        control_latency_ms=50.0,
        gateway_latency_ms=80.0,
        gateway_success=gateway_success,
        divergence_score=divergence,
        token_match=divergence == 0.0,
        structural_match=divergence == 0.0,
    )


# ---------------------------------------------------------------------------
# Per-call recording
# ---------------------------------------------------------------------------


class TestRecord:
    def test_record_stores_per_call(self):
        clock = FakeClock()
        metrics = ShadowMetrics(clock=clock)
        record = _record(clock=clock, divergence=0.05)
        metrics.record(record)
        # Internal storage has 1 record
        assert len(metrics._records["omi:auto:chat-extraction"]) == 1

    def test_record_invokes_metrics_sink_per_call(self):
        clock = FakeClock()
        sink = FakeMetricsSink()
        metrics = ShadowMetrics(clock=clock, metrics_sink=sink)
        metrics.record(_record(clock=clock, lane_id="a"))
        metrics.record(_record(clock=clock, lane_id="b", advance=1.0))
        # Two per-call metric increments
        assert len(sink.records) == 4  # 2 increments + 2 gauges
        lanes = {r.labels["lane"] for r in sink.records if "lane" in r.labels}
        assert lanes == {"a", "b"}


# ---------------------------------------------------------------------------
# Rolling aggregate
# ---------------------------------------------------------------------------


class TestRollingAggregate:
    def test_no_records_aggregate_is_zero(self):
        clock = FakeClock()
        metrics = ShadowMetrics(clock=clock)
        assert metrics._aggregate(metrics._records.setdefault("x", __import__("collections").deque())) == 0.0

    def test_single_record_aggregate_is_score(self):
        clock = FakeClock()
        metrics = ShadowMetrics(clock=clock)
        metrics.record(_record(clock=clock, divergence=0.5))
        bucket = metrics._records["omi:auto:chat-extraction"]
        assert metrics._aggregate(bucket) == 0.5

    def test_multiple_records_aggregate_is_mean(self):
        clock = FakeClock()
        metrics = ShadowMetrics(clock=clock)
        for d in (0.1, 0.2, 0.3):
            metrics.record(_record(clock=clock, divergence=d, advance=1.0))
        bucket = metrics._records["omi:auto:chat-extraction"]
        # 3 records, mean = 0.2
        assert metrics._aggregate(bucket) == pytest.approx(0.2)

    def test_records_older_than_window_dropped(self):
        clock = FakeClock()
        metrics = ShadowMetrics(clock=clock, window_seconds=10.0)
        # Old record (advance 100s, well past the 10s window)
        # timestamp = 1000100
        metrics.record(_record(clock=clock, divergence=0.9, advance=100.0))
        # New record: advance 10.5s more → timestamp = 1000110.5
        # cutoff = 1000110.5 - 10 = 1000100.5
        # First record (at 1000100) is < 1000100.5 → dropped
        metrics.record(_record(clock=clock, divergence=0.1, advance=10.5))
        bucket = metrics._records["omi:auto:chat-extraction"]
        assert len(bucket) == 1
        assert bucket[0].divergence_score == 0.1


# ---------------------------------------------------------------------------
# Alert threshold
# ---------------------------------------------------------------------------


class TestAlertThreshold:
    def test_below_threshold_no_alert(self):
        clock = FakeClock()
        sink = FakeAlertSink()
        metrics = ShadowMetrics(clock=clock, alert_sink=sink, threshold=0.01)
        result = metrics.record(_record(clock=clock, divergence=0.005))
        assert result is None
        assert len(sink.calls) == 0

    def test_above_threshold_fires_alert(self):
        clock = FakeClock()
        sink = FakeAlertSink()
        metrics = ShadowMetrics(clock=clock, alert_sink=sink, threshold=0.01)
        result = metrics.record(_record(clock=clock, divergence=0.05))
        assert result is not None
        assert result.lane_id == "omi:auto:chat-extraction"
        assert result.aggregate_score == 0.05
        assert "0.05" in result.message or "5" in result.message
        # AlertSink fired
        assert len(sink.calls) == 1

    def test_alert_suppressed_after_dropping_below_threshold(self):
        clock = FakeClock()
        sink = FakeAlertSink()
        # Use a tiny window so the rolling window doesn't include old high
        # divergence records when the next low divergence record arrives.
        metrics = ShadowMetrics(clock=clock, alert_sink=sink, threshold=0.01, window_seconds=0.1)
        # First: above threshold — alert fires (timestamp = 1000001)
        metrics.record(_record(clock=clock, divergence=0.05, advance=1.0))
        # Second: advances clock past the window so the first record is dropped
        # (timestamp = 1000010, cutoff = 1000010 - 0.1 = 1000009.9; record 1 at
        # 1000001 is < 1000009.9 → dropped; aggregate = 0.0)
        metrics.record(_record(clock=clock, divergence=0.0, advance=9.0))
        # Third: above threshold again — alert fires
        result = metrics.record(_record(clock=clock, divergence=0.05, advance=1.0))
        assert result is not None
        assert len(sink.calls) == 2

    def test_duplicate_alert_suppressed_in_window(self):
        """If the lane is already above threshold, subsequent above-threshold
        records don't re-fire the alert (until the lane drops below threshold).
        """
        clock = FakeClock()
        sink = FakeAlertSink()
        metrics = ShadowMetrics(clock=clock, alert_sink=sink, threshold=0.01)
        metrics.record(_record(clock=clock, divergence=0.05, advance=1.0))
        # Still above threshold
        metrics.record(_record(clock=clock, divergence=0.05, advance=1.0))
        metrics.record(_record(clock=clock, divergence=0.05, advance=1.0))
        # Only 1 alert (the rest suppressed)
        assert len(sink.calls) == 1


# ---------------------------------------------------------------------------
# Per-lane isolation
# ---------------------------------------------------------------------------


class TestPerLaneIsolation:
    def test_lanes_tracked_independently(self):
        clock = FakeClock()
        sink = FakeAlertSink()
        metrics = ShadowMetrics(clock=clock, alert_sink=sink, threshold=0.01)
        # Lane A: above threshold
        metrics.record(_record(clock=clock, lane_id="a", divergence=0.05))
        # Lane B: below threshold
        metrics.record(_record(clock=clock, lane_id="b", divergence=0.005, advance=1.0))
        # Only lane A alerted
        assert len(sink.calls) == 1
        assert sink.calls[0].lane_id == "a"

    def test_clear_drops_all_state(self):
        clock = FakeClock()
        metrics = ShadowMetrics(clock=clock, threshold=0.01)
        metrics.record(_record(clock=clock, divergence=0.5))
        metrics.record(_record(clock=clock, lane_id="b", divergence=0.5, advance=1.0))
        assert len(metrics._records) == 2
        metrics.clear()
        assert len(metrics._records) == 0
        assert len(metrics._alerted_lanes) == 0


# ---------------------------------------------------------------------------
# No-op default sinks (production may not configure them)
# ---------------------------------------------------------------------------


class TestNoOpSinks:
    def test_no_alert_sink_does_not_raise(self):
        clock = FakeClock()
        metrics = ShadowMetrics(clock=clock, alert_sink=None, threshold=0.01)
        # Above threshold, no AlertSink configured — should not raise
        result = metrics.record(_record(clock=clock, divergence=0.5))
        assert result is not None

    def test_no_metrics_sink_does_not_raise(self):
        clock = FakeClock()
        metrics = ShadowMetrics(clock=clock, metrics_sink=None, threshold=0.01)
        # Below threshold, no MetricsSink configured
        result = metrics.record(_record(clock=clock, divergence=0.005))
        assert result is None
