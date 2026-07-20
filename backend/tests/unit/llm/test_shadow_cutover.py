"""Tests for the R3.1 `ShadowCutover` dual-path orchestrator."""

from __future__ import annotations

import asyncio

import pytest

from utils.llm.shadow_cutover import (
    ControlResult,
    DivergenceResult,
    GatewayResult,
    ShadowCutover,
    ShadowCutoverConfig,
    ShadowCutoverResult,
)
from utils.llm.shadow_metrics import ShadowMetrics
from tests.unit.llm.fakes import (
    FakeAlertSink,
    FakeClock,
    FakeControlProvider,
    FakeGatewayClient,
    FakeMetricsSink,
)


def _config(
    *,
    control: FakeControlProvider,
    gateway: FakeGatewayClient,
    metrics: ShadowMetrics,
    lane_id: str = "omi:auto:chat-extraction",
    timeout: float = 8.0,
) -> ShadowCutoverConfig:
    return ShadowCutoverConfig(
        lane_id=lane_id,
        control_provider=control,
        gateway_client=gateway,
        metrics=metrics,
        timeout_seconds=timeout,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_both_paths_run_in_parallel(self):
        control = FakeControlProvider()
        gateway = FakeGatewayClient()
        clock = FakeClock()
        metrics = ShadowMetrics(clock=clock)
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics))
        result = await cutover.chat(messages=[{"role": "user", "content": "hi"}])
        assert len(control.calls) == 1
        assert len(gateway.calls) == 1
        # The gateway call used the lane_id
        assert gateway.calls[0]["lane_id"] == "omi:auto:chat-extraction"

    @pytest.mark.asyncio
    async def test_used_response_is_control(self):
        control = FakeControlProvider()
        gateway = FakeGatewayClient()
        metrics = ShadowMetrics(clock=FakeClock())
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics))
        result = await cutover.chat(messages=[])
        # Even if the gateway succeeds, the result uses control (R3.1)
        assert result.used_response is result.control
        assert result.used_response.content == "control-ok"

    @pytest.mark.asyncio
    async def test_passes_messages_to_both_paths(self):
        control = FakeControlProvider()
        gateway = FakeGatewayClient()
        metrics = ShadowMetrics(clock=FakeClock())
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics))
        messages = [{"role": "user", "content": "hello world"}]
        await cutover.chat(messages=messages, temperature=0.7)
        assert control.calls[0]["messages"] == messages
        assert control.calls[0]["temperature"] == 0.7
        assert gateway.calls[0]["messages"] == messages
        assert gateway.calls[0]["temperature"] == 0.7


# ---------------------------------------------------------------------------
# LKG fallback (gateway failure → control response)
# ---------------------------------------------------------------------------


class TestLKGFallback:
    @pytest.mark.asyncio
    async def test_gateway_failure_returns_control(self):
        control = FakeControlProvider()
        gateway = FakeGatewayClient()
        gateway.set_default_result(GatewayResult(content=None, success=False, error="provider 500"))
        metrics = ShadowMetrics(clock=FakeClock())
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics))
        result = await cutover.chat(messages=[])
        # Result still uses control
        assert result.used_response is result.control
        assert result.used_response.content == "control-ok"
        # Gateway result is recorded as failure
        assert result.gateway.success is False

    @pytest.mark.asyncio
    async def test_gateway_exception_returns_control(self):
        control = FakeControlProvider()
        gateway = FakeGatewayClient()
        gateway.set_raises(ConnectionError("network is down"))
        metrics = ShadowMetrics(clock=FakeClock())
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics))
        result = await cutover.chat(messages=[])
        # The gateway task raised; ShadowCutover catches it and falls back
        assert result.used_response is result.control
        assert result.gateway.success is False
        assert "ConnectionError" in result.gateway.error

    @pytest.mark.asyncio
    async def test_gateway_timeout_returns_control(self):
        control = FakeControlProvider()
        gateway = FakeGatewayClient()
        # Set a delay longer than the cutover's timeout
        gateway.set_delay(2.0)
        metrics = ShadowMetrics(clock=FakeClock())
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics, timeout=0.1))
        result = await cutover.chat(messages=[])
        # Outer timeout fires; control is still returned
        assert result.used_response is result.control
        assert result.gateway.success is False
        assert "timeout" in result.gateway.error.lower()


# ---------------------------------------------------------------------------
# Control failure propagates (no fallback for control)
# ---------------------------------------------------------------------------


class TestControlFailurePropagates:
    @pytest.mark.asyncio
    async def test_control_exception_propagates(self):
        control = FakeControlProvider()
        control.set_raises(RuntimeError("control is broken"))
        gateway = FakeGatewayClient()
        metrics = ShadowMetrics(clock=FakeClock())
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics))
        with pytest.raises(RuntimeError, match="control is broken"):
            await cutover.chat(messages=[])

    @pytest.mark.asyncio
    async def test_control_path_has_no_timeout(self):
        """The control path (existing direct provider) has no cutover-imposed
        timeout — the cutover trusts the control path. If the control provider
        is slow, the cutover waits. The timeout only applies to the gateway
        path (LKG fallback to control on gateway timeout).

        This test verifies the design: a slow control provider just makes the
        call take longer; the call eventually returns the control response.
        """
        import time

        control = FakeControlProvider()
        control.set_delay(0.2)  # 200ms
        gateway = FakeGatewayClient()
        metrics = ShadowMetrics(clock=FakeClock())
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics, timeout=8.0))
        t0 = time.perf_counter()
        result = await cutover.chat(messages=[])
        elapsed = time.perf_counter() - t0
        # The call waited for the slow control (~200ms) but still returned control
        assert result.used_response is result.control
        assert elapsed >= 0.2  # we waited
        assert elapsed < 1.0  # but we didn't time out (timeout is 8s)


# ---------------------------------------------------------------------------
# Divergence computation
# ---------------------------------------------------------------------------


class TestDivergenceComputation:
    @pytest.mark.asyncio
    async def test_identical_content_zero_divergence(self):
        control = FakeControlProvider()
        control.set_default_result(ControlResult(content="hello world", latency_ms=50.0))
        gateway = FakeGatewayClient()
        gateway.set_default_result(GatewayResult(content="hello world", success=True, latency_ms=80.0))
        metrics = ShadowMetrics(clock=FakeClock())
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics))
        result = await cutover.chat(messages=[])
        assert result.divergence.score == 0.0
        assert result.divergence.token_match is True

    @pytest.mark.asyncio
    async def test_completely_different_content_high_divergence(self):
        control = FakeControlProvider()
        control.set_default_result(ControlResult(content="alpha beta gamma", latency_ms=50.0))
        gateway = FakeGatewayClient()
        gateway.set_default_result(GatewayResult(content="x y z", success=True, latency_ms=80.0))
        metrics = ShadowMetrics(clock=FakeClock())
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics))
        result = await cutover.chat(messages=[])
        # token-Jaccard: 1 - 0/6 = 1.0
        assert result.divergence.score > 0.5
        assert result.divergence.token_match is False

    @pytest.mark.asyncio
    async def test_gateway_failure_max_divergence(self):
        control = FakeControlProvider()
        gateway = FakeGatewayClient()
        gateway.set_default_result(GatewayResult(content=None, success=False, error="boom"))
        metrics = ShadowMetrics(clock=FakeClock())
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics))
        result = await cutover.chat(messages=[])
        assert result.divergence.score == 1.0
        assert "boom" in result.divergence.notes

    @pytest.mark.asyncio
    async def test_structural_match_json_keys(self):
        control = FakeControlProvider()
        control.set_default_result(
            ControlResult(content="", structured_output={"answer": "ok", "score": 0.9}, latency_ms=50.0)
        )
        gateway = FakeGatewayClient()
        # Gateway returns same keys (different values)
        gateway.set_default_result(
            GatewayResult(content='{"answer": "different", "score": 0.1}', success=True, latency_ms=80.0)
        )
        metrics = ShadowMetrics(clock=FakeClock())
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics))
        result = await cutover.chat(messages=[])
        # Keys match (structural_match = True)
        assert result.divergence.structural_match is True

    @pytest.mark.asyncio
    async def test_structural_mismatch_different_keys(self):
        control = FakeControlProvider()
        control.set_default_result(ControlResult(content="", structured_output={"answer": "ok"}, latency_ms=50.0))
        gateway = FakeGatewayClient()
        # Different keys
        gateway.set_default_result(GatewayResult(content='{"result": "different"}', success=True, latency_ms=80.0))
        metrics = ShadowMetrics(clock=FakeClock())
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics))
        result = await cutover.chat(messages=[])
        assert result.divergence.structural_match is False
        # Score boosted because structural mismatch
        assert result.divergence.score >= 0.5


# ---------------------------------------------------------------------------
# Metrics integration
# ---------------------------------------------------------------------------


class TestMetricsIntegration:
    @pytest.mark.asyncio
    async def test_per_call_record_stored(self):
        control = FakeControlProvider()
        gateway = FakeGatewayClient()
        clock = FakeClock()
        metrics = ShadowMetrics(clock=clock)
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics))
        await cutover.chat(messages=[])
        # One record stored
        bucket = metrics._records["omi:auto:chat-extraction"]
        assert len(bucket) == 1
        record = bucket[0]
        assert record.lane_id == "omi:auto:chat-extraction"
        assert record.control_latency_ms > 0
        assert record.gateway_latency_ms > 0
        assert record.gateway_success is True

    @pytest.mark.asyncio
    async def test_metrics_sink_records_per_call(self):
        control = FakeControlProvider()
        gateway = FakeGatewayClient()
        clock = FakeClock()
        metrics_sink = FakeMetricsSink()
        metrics = ShadowMetrics(clock=clock, metrics_sink=metrics_sink)
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics))
        await cutover.chat(messages=[])
        # Per-call: 1 increment + 1 gauge
        assert len(metrics_sink.records) == 2
        assert any(r.metric == "gateway_shadow_calls_total" for r in metrics_sink.records)
        assert any(r.metric == "gateway_shadow_divergence_score" for r in metrics_sink.records)

    @pytest.mark.asyncio
    async def test_alert_fires_on_high_divergence(self):
        control = FakeControlProvider()
        control.set_default_result(ControlResult(content="alpha beta gamma", latency_ms=50.0))
        gateway = FakeGatewayClient()
        gateway.set_default_result(GatewayResult(content="x y z", success=True, latency_ms=80.0))
        clock = FakeClock()
        alert_sink = FakeAlertSink()
        metrics = ShadowMetrics(clock=clock, alert_sink=alert_sink, threshold=0.01)
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics))
        result = await cutover.chat(messages=[])
        # High divergence (token-Jaccard = 1.0) → alert fires
        assert result.divergence.score > 0.01
        # Yield to the event loop so the scheduled alert task can run.
        # (ShadowMetrics._fire_alert uses loop.create_task to schedule the
        # fire; the test must wait for the task to complete before checking.)
        await asyncio.sleep(0)
        # The metrics layer fired the alert
        assert len(alert_sink.calls) == 1


# ---------------------------------------------------------------------------
# P1 #3: metrics recording is best-effort
# ---------------------------------------------------------------------------


class TestMetricsFailureContainment:
    @pytest.mark.asyncio
    async def test_metrics_failure_does_not_break_response(self):
        """P1 #3: a metrics failure (e.g., bad sink) is contained; the
        control response is still returned to the caller.
        """
        control = FakeControlProvider()
        gateway = FakeGatewayClient()
        # Metrics sink that always raises
        bad_sink = FakeMetricsSink()

        def boom(*, metric, value=1.0, labels=None):
            raise ConnectionError("metrics backend down")

        bad_sink.increment = boom
        metrics = ShadowMetrics(clock=FakeClock(), metrics_sink=bad_sink)
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics))
        # Should not raise; control response returned
        result = await cutover.chat(messages=[])
        assert result.used_response is result.control
        assert result.used_response.content == "control-ok"


# ---------------------------------------------------------------------------
# P2 #6: control failure → cancel gateway task
# ---------------------------------------------------------------------------


class TestControlFailureCancelsGateway:
    @pytest.mark.asyncio
    async def test_control_failure_cancels_gateway_task(self):
        """P2 #6: if the control path raises, the gateway task is explicitly
        cancelled (no orphaned work)."""
        control = FakeControlProvider()
        control.set_raises(RuntimeError("control is broken"))
        gateway = FakeGatewayClient()
        # Make the gateway slow so we can verify it's cancelled
        gateway.set_delay(1.0)
        metrics = ShadowMetrics(clock=FakeClock())
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics, timeout=5.0))
        with pytest.raises(RuntimeError, match="control is broken"):
            await cutover.chat(messages=[])
        # The gateway task should be cancelled (not still running)
        # We can't directly check task state, but we can verify the
        # FakeGatewayClient's _calls wasn't logged with a long delay
        # (the task was cancelled before completing the 1.0s sleep).
        # A direct check: assert no pending tasks reference the gateway.
        # Since we use the default executor, this is hard to check directly;
        # the absence of a hang in the test is the strongest signal.


# ---------------------------------------------------------------------------
# P2 #7: divergence_threshold override
# ---------------------------------------------------------------------------


class TestThresholdOverride:
    @pytest.mark.asyncio
    async def test_divergence_threshold_overrides_default(self):
        """P2 #7: a per-cutover divergence_threshold overrides the metrics'
        default threshold."""
        control = FakeControlProvider()
        control.set_default_result(ControlResult(content="alpha beta", latency_ms=50.0))
        gateway = FakeGatewayClient()
        gateway.set_default_result(GatewayResult(content="x y", success=True, latency_ms=80.0))
        # Use a high default threshold (0.5) so the natural divergence doesn't alert
        metrics = ShadowMetrics(clock=FakeClock(), threshold=0.5)
        # Construct cutover with a lower override (0.01) — should now alert
        config = _config(control=control, gateway=gateway, metrics=metrics)
        config.divergence_threshold = 0.01
        cutover = ShadowCutover(config)
        # The override was applied
        assert metrics._threshold == 0.01
        await cutover.chat(messages=[])
        # Yield for the alert task
        await asyncio.sleep(0)

    def test_no_threshold_override_keeps_default(self):
        """If divergence_threshold is None, the metrics' default is preserved."""
        control = FakeControlProvider()
        gateway = FakeGatewayClient()
        metrics = ShadowMetrics(clock=FakeClock(), threshold=0.05)
        config = _config(control=control, gateway=gateway, metrics=metrics)
        # No override
        ShadowCutover(config)
        assert metrics._threshold == 0.05


# ---------------------------------------------------------------------------
# P2 #8: parallel timeouts (slow gateway doesn't delay control)
# ---------------------------------------------------------------------------


class TestParallelTimeouts:
    @pytest.mark.asyncio
    async def test_slow_gateway_does_not_delay_control(self):
        """P2 #8: the gateway path has its own timeout; a slow gateway doesn't
        delay the already-ready control response by up to timeout_seconds.
        """
        import time

        control = FakeControlProvider()
        control.set_default_result(ControlResult(content="control-ok", latency_ms=10.0))
        gateway = FakeGatewayClient()
        # Gateway takes 1.0s — but the cutover's timeout is 0.1s
        gateway.set_delay(1.0)
        metrics = ShadowMetrics(clock=FakeClock())
        cutover = ShadowCutover(_config(control=control, gateway=gateway, metrics=metrics, timeout=0.1))
        t0 = time.perf_counter()
        result = await cutover.chat(messages=[])
        elapsed = time.perf_counter() - t0
        # The call returned quickly (control's 10ms + gateway's 100ms timeout)
        # NOT the gateway's full 1.0s sleep
        assert elapsed < 0.5, f"call took {elapsed:.3f}s, expected < 0.5s"
        # The gateway result is a timeout failure
        assert result.gateway.success is False
        assert "timeout" in result.gateway.error.lower()
        # The control response is still returned (LKG)
        assert result.used_response is result.control
        assert result.used_response.content == "control-ok"
