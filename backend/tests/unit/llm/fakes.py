"""Deterministic fakes for the R3.1 dual-path infrastructure.

Lives in `tests/unit/llm/` (production-side importable; production code
NEVER imports from here). Per R2's pattern: fakes are test doubles,
not production dependencies. Mirrors R2's `deterministic_provider.py`
but for the dual-path side (control provider + gateway client + alert
sink + metrics sink).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

# ---------------------------------------------------------------------------
# Protocol mirrors (for type checking — these match the production Protocols)
# ---------------------------------------------------------------------------
#
# The real Protocols live in `utils/llm/shadow_cutover.py` and
# `utils/llm/shadow_metrics.py`. We re-declare them here to avoid a
# circular import (the fakes need to be test-importable without importing
# the production modules). The duck-typed call sites in the production
# code use `runtime_checkable` Protocol, so the fakes satisfy them by
# structure.
# ---------------------------------------------------------------------------


@dataclass
class ControlResult:
    """The control path's response. Mirrors `shadow_cutover.ControlResult`."""

    content: str
    latency_ms: float
    structured_output: Any = None
    usage: dict[str, int] = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0})


@dataclass
class GatewayResult:
    """The gateway path's response. Mirrors `shadow_cutover.GatewayResult`."""

    content: Optional[str] = None
    latency_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None


class FakeControlProvider:
    """Deterministic fake of the control path (existing direct provider).

    Configures per-call return values. By default, returns a "control-ok"
    response with low latency.
    """

    def __init__(self) -> None:
        self._next_results: list[ControlResult] = []
        self._default_result = ControlResult(content="control-ok", latency_ms=50.0)
        self._calls: list[dict[str, Any]] = []
        self._raise_on_call: Optional[Exception] = None
        self._delay_seconds: float = 0.0

    def set_next_result(self, result: ControlResult) -> None:
        self._next_results.append(result)

    def set_default_result(self, result: ControlResult) -> None:
        self._default_result = result

    def queue_results(self, *results: ControlResult) -> None:
        for r in results:
            self.set_next_result(r)

    def set_raises(self, exc: Exception) -> None:
        """If set, the next call raises this exception."""
        self._raise_on_call = exc

    def set_delay(self, seconds: float) -> None:
        """Simulate a slow call (e.g., 0.1s)."""
        self._delay_seconds = seconds

    @property
    def calls(self) -> list[dict[str, Any]]:
        return list(self._calls)

    def clear_calls(self) -> None:
        self._calls.clear()

    async def chat(self, *, messages: list[dict[str, Any]], **kwargs: Any) -> ControlResult:
        self._calls.append({"messages": messages, **kwargs})
        if self._delay_seconds > 0:
            await asyncio.sleep(self._delay_seconds)
        if self._raise_on_call is not None:
            exc = self._raise_on_call
            self._raise_on_call = None  # only raise once
            raise exc
        result = self._next_results.pop(0) if self._next_results else self._default_result
        return result


class FakeGatewayClient:
    """Deterministic fake of the gateway path (omi:auto:<lane> via HTTP)."""

    def __init__(self) -> None:
        self._next_results: list[GatewayResult] = []
        self._default_result = GatewayResult(content="gateway-ok", latency_ms=80.0)
        self._calls: list[dict[str, Any]] = []
        self._raise_on_call: Optional[Exception] = None
        self._delay_seconds: float = 0.0

    def set_next_result(self, result: GatewayResult) -> None:
        self._next_results.append(result)

    def set_default_result(self, result: GatewayResult) -> None:
        self._default_result = result

    def queue_results(self, *results: GatewayResult) -> None:
        for r in results:
            self.set_next_result(r)

    def set_raises(self, exc: Exception) -> None:
        self._raise_on_call = exc

    def set_delay(self, seconds: float) -> None:
        self._delay_seconds = seconds

    @property
    def calls(self) -> list[dict[str, Any]]:
        return list(self._calls)

    def clear_calls(self) -> None:
        self._calls.clear()

    async def chat(self, *, lane_id: str, messages: list[dict[str, Any]], **kwargs: Any) -> GatewayResult:
        self._calls.append({"lane_id": lane_id, "messages": messages, **kwargs})
        if self._delay_seconds > 0:
            await asyncio.sleep(self._delay_seconds)
        if self._raise_on_call is not None:
            exc = self._raise_on_call
            self._raise_on_call = None
            raise exc
        result = self._next_results.pop(0) if self._next_results else self._default_result
        return result


@dataclass
class AlertCall:
    """A recorded alert call. Used by `FakeAlertSink`."""

    lane_id: str
    message: str
    metadata: dict[str, Any]
    timestamp: float


class FakeAlertSink:
    """Records alert calls for test introspection."""

    def __init__(self) -> None:
        self.calls: list[AlertCall] = []

    async def fire(self, *, lane_id: str, message: str, metadata: dict[str, Any]) -> None:
        self.calls.append(
            AlertCall(
                lane_id=lane_id,
                message=message,
                metadata=metadata,
                timestamp=time.time(),
            )
        )


@dataclass
class MetricsRecord:
    """A recorded metrics call. Used by `FakeMetricsSink`."""

    metric: str
    value: float
    labels: dict[str, str]
    timestamp: float


class FakeMetricsSink:
    """Records metrics calls for test introspection."""

    def __init__(self) -> None:
        self.records: list[MetricsRecord] = []

    def increment(self, *, metric: str, value: float = 1.0, labels: Optional[dict[str, str]] = None) -> None:
        self.records.append(
            MetricsRecord(
                metric=metric,
                value=value,
                labels=labels or {},
                timestamp=time.time(),
            )
        )

    def gauge(self, *, metric: str, value: float, labels: Optional[dict[str, str]] = None) -> None:
        self.records.append(
            MetricsRecord(
                metric=metric,
                value=value,
                labels=labels or {},
                timestamp=time.time(),
            )
        )


# ---------------------------------------------------------------------------
# Fake clock (for ShadowMetrics tests)
# ---------------------------------------------------------------------------


class FakeClock:
    """A fake clock for testing time-based logic (rolling-24h aggregate).

    The default time is 1_000_000.0 (a fixed epoch). Call `advance(seconds)`
    to move time forward.
    """

    def __init__(self, start: float = 1_000_000.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds
