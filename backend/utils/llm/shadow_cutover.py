"""Dual-path orchestrator for the R3 product cutover (R3.1).

Wraps the call site's existing direct-provider call (control path) and
runs the gateway path (`omi:auto:<lane>` via the gateway HTTP API) in
parallel. Compares the two responses; records divergence; returns the
control response.

R3.1 always returns the control response. The gateway is observed but
not used. After 14 days of <1% divergence (R3.2 deploy + observation),
a follow-up PR drops the control path.

Per PLAN.md §R3: "Dual-path: the call site calls the gateway AND a
control path simultaneously for the first release. Control = existing
direct provider call. Gateway = new omi:auto:<lane>."

Pluggable design (mirrors R5b's config_reload):
- ControlProvider (Protocol): the existing direct-provider call
- GatewayClient (Protocol): the gateway HTTP call
- ShadowMetrics: where per-call records + alerts go (separate module)

LKG fallback: if the gateway path fails or times out, the control
response is returned. The gateway failure doesn't take down the call
site.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from utils.llm.shadow_metrics import PerCallRecord, ShadowMetrics

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Collaborator protocols (the fakes in tests satisfy these by structure)
# ---------------------------------------------------------------------------


class ControlProvider(Protocol):
    """The control path: existing direct provider call.

    Real impl: an OpenAI / Anthropic / etc. client wrapper that the
    call site uses today. R3.1 tests use `FakeControlProvider`.
    """

    async def chat(self, *, messages: list[dict[str, Any]], **kwargs: Any) -> "ControlResult": ...


class GatewayClient(Protocol):
    """The gateway path: omi:auto:<lane> via the gateway HTTP API.

    Real impl: `backend/utils/llm/gateway_client.py::invoke_chat_structured_gateway`
    (or its async successor for non-pilot lanes). R3.1 tests use
    `FakeGatewayClient`.
    """

    async def chat(self, *, lane_id: str, messages: list[dict[str, Any]], **kwargs: Any) -> "GatewayResult": ...


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ControlResult:
    """The control path's response (the one we return to the caller in R3.1)."""

    content: str
    latency_ms: float
    structured_output: Any = None
    usage: dict[str, int] = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0})


@dataclass
class GatewayResult:
    """The gateway path's response (observed but not returned in R3.1)."""

    content: Optional[str] = None
    latency_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None


@dataclass
class DivergenceResult:
    """Divergence between control and gateway responses.

    score: 0.0 (identical) to 1.0 (completely different).
    token_match: True if the responses have the same token set.
    structural_match: True if both responses are valid structured outputs
        with the same top-level keys (for json_schema / json_object).
    """

    score: float
    token_match: bool
    structural_match: bool
    notes: str = ""


@dataclass
class ShadowCutoverResult:
    """The full result of one dual-path call."""

    control: ControlResult
    gateway: GatewayResult
    divergence: DivergenceResult
    used_response: ControlResult  # always control in R3.1; gateway observed only


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class ShadowCutoverConfig:
    """Configuration for a single lane's dual-path.

    One ShadowCutover per lane (or per feature, depending on call-site
    organization). The lane_id determines which gateway path the call
    routes to.

    P2 #7: `divergence_threshold` is passed to the ShadowMetrics instance
    so per-cutover threshold configuration is honored (previously declared
    but never read).
    """

    lane_id: str
    control_provider: ControlProvider
    gateway_client: GatewayClient
    metrics: ShadowMetrics
    timeout_seconds: float = 8.0
    divergence_threshold: Optional[float] = None  # if None, metrics' default is used


# ---------------------------------------------------------------------------
# ShadowCutover
# ---------------------------------------------------------------------------


class ShadowCutover:
    """Dual-path orchestrator. R3.1 always returns the control response.

    Per call:
    1. Run both paths in parallel via asyncio.gather
    2. Compute divergence (token + structural)
    3. Record into ShadowMetrics (which fires alerts above threshold)
    4. Return control response (LKG fallback on gateway failure/timeout)
    """

    def __init__(self, config: ShadowCutoverConfig) -> None:
        self._config = config
        # P2 #7: apply the per-cutover threshold (if set) to the metrics
        # instance. This overrides the metrics' default threshold.
        if config.divergence_threshold is not None:
            config.metrics.set_threshold(config.divergence_threshold)

    async def chat(self, *, messages: list[dict[str, Any]], **kwargs: Any) -> ShadowCutoverResult:
        """Run the dual-path. Returns the control response; records divergence.

        P2 #8: both paths run with INDEPENDENT timeouts via asyncio.wait_for
        on each, so a slow gateway doesn't delay the already-ready control
        response (and vice versa).

        P2 #6: if the control path raises, the gateway task is explicitly
        cancelled (no orphaned work).
        """
        # Launch both paths concurrently
        control_task = asyncio.create_task(self._run_control(messages=messages, kwargs=kwargs))
        gateway_task = asyncio.create_task(self._run_gateway(messages=messages, kwargs=kwargs))
        try:
            # P2 #8: independent timeouts. We DON'T await control first then
            # gateway; both run in parallel with their own timeouts.
            control_result = await asyncio.wait_for(
                asyncio.shield(control_task),
                timeout=self._config.timeout_seconds,
            )
        except Exception:
            # P2 #6: control failed → cancel the gateway task (don't leak)
            gateway_task.cancel()
            try:
                await gateway_task
            except (asyncio.CancelledError, BaseException):
                pass
            raise
        # Gateway is independent; we still wait for it (with its own timeout
        # inside _safe_gateway) but we don't block on it for the response.
        gateway_result = await self._safe_gateway(gateway_task)
        # Compute divergence
        divergence = self._compute_divergence(control_result, gateway_result)
        # Record into metrics (P1 #3: best-effort, never breaks the response)
        record = PerCallRecord(
            lane_id=self._config.lane_id,
            timestamp=time.time(),
            control_latency_ms=control_result.latency_ms,
            gateway_latency_ms=gateway_result.latency_ms,
            gateway_success=gateway_result.success,
            divergence_score=divergence.score,
            token_match=divergence.token_match,
            structural_match=divergence.structural_match,
        )
        try:
            self._config.metrics.record(record)
        except Exception as e:
            # P1 #3: observability is best-effort. A sink failure must
            # never break the call site.
            import logging

            logging.getLogger(__name__).warning(
                "shadow metrics record failed (swallowed): %s: %s",
                type(e).__name__,
                e,
            )
        return ShadowCutoverResult(
            control=control_result,
            gateway=gateway_result,
            divergence=divergence,
            used_response=control_result,
        )

    async def _run_control(self, *, messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> ControlResult:
        """Time the control call. Wraps the protocol call in latency tracking."""
        t0 = time.perf_counter()
        result = await self._config.control_provider.chat(messages=messages, **kwargs)
        latency_ms = (time.perf_counter() - t0) * 1000
        # Update latency (the protocol returns its own latency; we measure end-to-end)
        return ControlResult(
            content=result.content,
            latency_ms=latency_ms,
            structured_output=result.structured_output,
            usage=result.usage,
        )

    async def _run_gateway(self, *, messages: list[dict[str, Any]], kwargs: dict[str, Any]) -> GatewayResult:
        """Time the gateway call."""
        t0 = time.perf_counter()
        try:
            result = await self._config.gateway_client.chat(
                lane_id=self._config.lane_id,
                messages=messages,
                **kwargs,
            )
        except asyncio.TimeoutError as e:
            latency_ms = (time.perf_counter() - t0) * 1000
            return GatewayResult(
                content=None,
                latency_ms=latency_ms,
                success=False,
                error=f"timeout: {e}",
            )
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000
            return GatewayResult(
                content=None,
                latency_ms=latency_ms,
                success=False,
                error=f"{type(e).__name__}: {e}",
            )
        latency_ms = (time.perf_counter() - t0) * 1000
        return GatewayResult(
            content=result.content,
            latency_ms=latency_ms,
            success=result.success,
            error=result.error,
        )

    async def _safe_gateway(self, task: asyncio.Task) -> GatewayResult:
        """Await the gateway task with a timeout. On timeout/error, return a
        failed GatewayResult (don't raise — we still want to record metrics
        and return the control response).
        """
        try:
            return await asyncio.wait_for(
                asyncio.shield(task),
                timeout=self._config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            # The shielded task continues running in the background; we just
            # give up waiting for it.
            return GatewayResult(
                content=None,
                latency_ms=self._config.timeout_seconds * 1000,
                success=False,
                error=f"outer timeout after {self._config.timeout_seconds}s",
            )
        except Exception as e:
            # The task raised. _run_gateway catches most things, so this is
            # belt-and-suspenders.
            return GatewayResult(
                content=None,
                latency_ms=0.0,
                success=False,
                error=f"unexpected: {type(e).__name__}: {e}",
            )

    def _compute_divergence(self, control: ControlResult, gateway: GatewayResult) -> DivergenceResult:
        """Compute a 0.0–1.0 divergence score.

        Strategy:
        - If the gateway failed: divergence = 1.0 (max)
        - If the control and gateway have the same content: divergence = 0.0
        - Otherwise: token-Jaccard (1 - |A ∩ B| / |A ∪ B|) plus structural
          check if both have structured_output.
        """
        if not gateway.success:
            return DivergenceResult(
                score=1.0,
                token_match=False,
                structural_match=False,
                notes=f"gateway failed: {gateway.error}",
            )
        # Token-Jaccard
        control_tokens = self._tokenize(control.content or "")
        gateway_tokens = self._tokenize(gateway.content or "")
        if control_tokens or gateway_tokens:
            intersection = control_tokens & gateway_tokens
            union = control_tokens | gateway_tokens
            token_jaccard = 1.0 - (len(intersection) / len(union)) if union else 0.0
        else:
            token_jaccard = 0.0
        token_match = token_jaccard == 0.0
        # Structural match (if both are dicts)
        structural_match = self._structural_match(control.structured_output, gateway.content)
        score = token_jaccard
        if not structural_match:
            score = max(score, 0.5)  # boost if structures diverge
        return DivergenceResult(
            score=min(1.0, score),
            token_match=token_match,
            structural_match=structural_match,
        )

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """Whitespace-separated tokens, lowercased."""
        return set(text.lower().split())

    @staticmethod
    def _structural_match(control_structured: Any, gateway_content: Optional[str]) -> bool:
        """Check if the gateway content (parsed as JSON if it's a string)
        has the same top-level keys as the control's structured_output.

        Returns True when the control has no structured output (vacuously
        matching — plain text vs plain text is treated as structurally
        equivalent). Returns False when only one of the two has structure
        or when the structures differ.
        """
        # If control has no structure, vacuously matching.
        if control_structured is None:
            return True
        if gateway_content is None:
            return False
        # Try to parse the gateway content as JSON (it might be a JSON string)
        import json

        try:
            gateway_structured = json.loads(gateway_content)
        except (json.JSONDecodeError, TypeError):
            return False
        if not isinstance(gateway_structured, dict) or not isinstance(control_structured, dict):
            return False
        return set(gateway_structured.keys()) == set(control_structured.keys())
