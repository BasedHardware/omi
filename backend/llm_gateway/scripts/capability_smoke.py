"""Capability smoke gate for the auto-router-on-LLM-gateway feature (R2).

For each lane in `get_supported_auto_lane_ids()`, run a fixture against the
lane's declared capabilities (`text_input`, `streaming`, `structured_output`,
`tools`) and verify the response:
  - Received (no timeout, no auth failure)
  - Structured output parses (json_object / json_schema modes)
  - Latency under the lane's `timeouts.request_ms`

Output: pass/fail per lane as JSON to stdout. The default provider
executes the configured gateway route; `fake` is only for tests.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, cast

from llm_gateway.gateway.config_loader import GatewayConfig, load_gateway_config
from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.errors import GatewayError
from llm_gateway.gateway.executor import ProviderRegistry, execute_chat_completion
from llm_gateway.gateway.resolver import get_supported_auto_lane_ids, resolve_chat_completion_route
from llm_gateway.gateway.schemas import (
    Capabilities,
    LaneConfig,
    RouteArtifact,
    StructuredOutputMode,
)
from llm_gateway.scripts.deterministic_provider import ProviderAuthError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------


@dataclass
class ProviderRequest:
    """The smoke's view of a single chat-completion request.

    Built by `build_fixture` based on the lane's declared capabilities.
    The provider decides what to return (or raise) for this request.
    """

    model: str
    messages: list[dict[str, Any]]
    response_format: Optional[dict[str, Any]] = None
    tools: Optional[list[dict[str, Any]]] = None
    stream: bool = False
    timeout_seconds: float = 8.0


@dataclass
class ProviderResponse:
    """The provider's reply. The smoke validates shape; the provider fills it."""

    content: str = ""
    tool_call: Optional[dict[str, Any]] = None
    structured_output: Any = None  # parsed JSON for json_object / json_schema
    usage: dict[str, int] = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0})


class Provider:
    """The smoke's contract with the provider layer (duck-typed).

    Subclasses or stand-in implementations:
      - FakeProvider
      - RealGatewayProvider
    """

    async def chat_completion(self, request: ProviderRequest) -> ProviderResponse:  # pragma: no cover
        raise NotImplementedError


class RealGatewayProvider(Provider):
    def __init__(self, config: GatewayConfig, registry: ProviderRegistry):
        self._config = config
        self._registry = registry

    async def chat_completion(self, request: ProviderRequest) -> ProviderResponse:
        if request.stream:
            raise ValueError("streaming smoke is unsupported")
        payload: dict[str, Any] = {"model": request.model, "messages": request.messages}
        if request.response_format is not None:
            payload["response_format"] = request.response_format
        if request.tools is not None:
            payload["tools"] = request.tools
        resolved = resolve_chat_completion_route(self._config, payload)
        result = await execute_chat_completion(
            resolved,
            build_omi_managed_credential_context(ServiceCaller(name="backend", usage_feature="capability-smoke")),
            self._registry,
        )
        return _provider_response_from_gateway(result.response, request)

    async def aclose(self) -> None:
        await self._registry.aclose()


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------


# Sample schemas used to exercise the json_schema path. Picked to be
# unambiguously valid JSON Schema and easy to validate.
_SAMPLE_JSON_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
    "additionalProperties": False,
}

# Sample tool for the tools path.
_SAMPLE_TOOL = {
    "type": "function",
    "function": {
        "name": "smoke_test_tool",
        "description": "Echo back the input for smoke testing.",
        "parameters": {
            "type": "object",
            "properties": {"input": {"type": "string"}},
            "required": ["input"],
            "additionalProperties": False,
        },
    },
}


def build_fixture(lane: LaneConfig, artifact: RouteArtifact) -> ProviderRequest:
    """Build a chat-completion request that exercises the lane's capabilities.

    Includes:
      - One user message (text_input is always exercised)
      - response_format when structured_output != none
      - tools when capabilities.tools
      - stream=True when capabilities.streaming
    """
    messages = [{"role": "user", "content": f"smoke test for {lane.lane_id}"}]

    response_format: Optional[dict[str, Any]] = None
    if lane.capabilities.structured_output == StructuredOutputMode.JSON_OBJECT:
        response_format = {"type": "json_object"}
    elif lane.capabilities.structured_output == StructuredOutputMode.JSON_SCHEMA:
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": "capability_smoke", "schema": _SAMPLE_JSON_SCHEMA},
        }

    tools = [_SAMPLE_TOOL] if lane.capabilities.tools else None

    return ProviderRequest(
        model=lane.lane_id,
        messages=messages,
        response_format=response_format,
        tools=tools,
        stream=lane.capabilities.streaming,
        timeout_seconds=artifact.timeouts.request_ms / 1000.0,
    )


# ---------------------------------------------------------------------------
# Smoke runner
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """Result of a single capability check within a lane's smoke."""

    name: str
    passed: bool
    detail: str = ""


@dataclass
class LaneResult:
    """Smoke result for a single lane."""

    lane_id: str
    passed: bool
    latency_ms: float
    checks: list[CheckResult] = field(default_factory=list)
    failure_reason: str = ""


@dataclass
class SmokeSummary:
    """Top-level smoke result across all lanes."""

    lanes: list[LaneResult]
    summary: dict[str, Any]


def _validate_response(
    request: ProviderRequest,
    response: ProviderResponse,
    caps: Capabilities,
) -> list[CheckResult]:
    """Validate the response against the lane's declared capabilities.

    Returns one CheckResult per capability flag declared on the lane.
    """
    checks: list[CheckResult] = []

    # text_input: always required; verify a non-empty response
    has_text = bool(response.content or response.structured_output or response.tool_call)
    checks.append(
        CheckResult(
            name="text_input",
            passed=has_text,
            detail="received non-empty response" if has_text else "empty response",
        )
    )

    # streaming: just verify the call was made with stream=True. The fake
    # provider doesn't actually stream; real providers must accept stream=True.
    if caps.streaming:
        checks.append(
            CheckResult(
                name="streaming",
                passed=request.stream is True,
                detail=f"request.stream={request.stream}",
            )
        )

    # structured_output: json_object — verify response is a dict
    if caps.structured_output == StructuredOutputMode.JSON_OBJECT:
        valid = isinstance(response.structured_output, dict)
        checks.append(
            CheckResult(
                name="structured_output_json_object",
                passed=valid,
                detail=f"got {type(response.structured_output).__name__}",
            )
        )
    elif caps.structured_output == StructuredOutputMode.JSON_SCHEMA:
        # Verify response is a dict (matches the schema's top-level type)
        valid = isinstance(response.structured_output, dict)
        checks.append(
            CheckResult(
                name="structured_output_json_schema",
                passed=valid,
                detail=f"got {type(response.structured_output).__name__}",
            )
        )

    # tools: verify the response includes a tool_call
    if caps.tools:
        has_tool = response.tool_call is not None
        checks.append(
            CheckResult(
                name="tools",
                passed=has_tool,
                detail="tool_call present" if has_tool else "no tool_call in response",
            )
        )

    return checks


async def smoke_lane(
    lane: LaneConfig,
    artifact: RouteArtifact,
    provider: Provider,
) -> LaneResult:
    """Run the smoke for one lane. Returns a LaneResult (never raises — failures are recorded)."""
    request = build_fixture(lane, artifact)
    t0 = time.perf_counter()
    try:
        response = await asyncio.wait_for(
            provider.chat_completion(request),
            timeout=request.timeout_seconds + 1.0,  # 1s grace over the request timeout
        )
    except asyncio.TimeoutError:
        latency_ms = (time.perf_counter() - t0) * 1000
        return LaneResult(
            lane_id=lane.lane_id,
            passed=False,
            latency_ms=latency_ms,
            failure_reason=f"timeout after {request.timeout_seconds + 1.0:.1f}s",
        )
    except ProviderAuthError:
        latency_ms = (time.perf_counter() - t0) * 1000
        return LaneResult(
            lane_id=lane.lane_id,
            passed=False,
            latency_ms=latency_ms,
            failure_reason="provider_auth_error",
        )
    except GatewayError as exc:
        latency_ms = (time.perf_counter() - t0) * 1000
        return LaneResult(
            lane_id=lane.lane_id,
            passed=False,
            latency_ms=latency_ms,
            failure_reason=f"gateway_{exc.failure_class.value if exc.failure_class else 'error'}",
        )
    except Exception:
        latency_ms = (time.perf_counter() - t0) * 1000
        return LaneResult(
            lane_id=lane.lane_id,
            passed=False,
            latency_ms=latency_ms,
            failure_reason="provider_error",
        )

    latency_ms = (time.perf_counter() - t0) * 1000
    checks = _validate_response(request, response, lane.capabilities)
    all_passed = all(c.passed for c in checks) and latency_ms <= request.timeout_seconds * 1000
    return LaneResult(
        lane_id=lane.lane_id,
        passed=all_passed,
        latency_ms=latency_ms,
        checks=checks,
        failure_reason="" if all_passed else "one or more capability checks failed or latency exceeded",
    )


def _build_provider(
    provider_arg: str,
    config: GatewayConfig | None = None,
    registry: ProviderRegistry | None = None,
) -> Provider:
    """Build the selected smoke provider."""
    if provider_arg == "fake":
        # The deterministic provider lives on the production-side import
        # path (NOT in tests/.../_private/) so the smoke's default doesn't
        # couple production code to the test tree. Per cubic-dev-ai review
        # on PR #8746.
        from llm_gateway.scripts.deterministic_provider import FakeProvider

        fake = FakeProvider()
        fake.set_default_scenario("pass")
        return cast(Provider, fake)
    if provider_arg == "real":
        if config is None:
            raise ValueError("real provider requires gateway config")
        if registry is None:
            from llm_gateway.routers.dependencies import get_provider_registry

            registry = get_provider_registry()
        return RealGatewayProvider(config, registry)
    raise ValueError(f"unknown provider: {provider_arg!r}")


def _provider_response_from_gateway(response: Mapping[str, Any], request: ProviderRequest) -> ProviderResponse:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], Mapping):
        raise ValueError("gateway response has no choices")
    message = choices[0].get("message")
    if not isinstance(message, Mapping):
        raise ValueError("gateway response has no message")
    content = message.get("content")
    text = content if isinstance(content, str) else ""
    tool_calls = message.get("tool_calls")
    tool_call = (
        tool_calls[0] if isinstance(tool_calls, list) and tool_calls and isinstance(tool_calls[0], dict) else None
    )
    structured_output: Any = None
    if request.response_format is not None:
        try:
            structured_output = json.loads(text)
        except json.JSONDecodeError:
            structured_output = None
    return ProviderResponse(content=text, tool_call=tool_call, structured_output=structured_output)


def _iter_target_lanes(
    cfg: GatewayConfig,
    *,
    lane_filter: Optional[str] = None,
) -> list[tuple[LaneConfig, RouteArtifact]]:
    """Return (lane, artifact) pairs to smoke. Filters by lane_filter if given.

    Only includes lanes in get_supported_auto_lane_ids() (R5b's restriction
    excludes the 3 audio/embedding placeholders). For each lane, picks
    the active_route artifact.

    Raises ConfigValidationError if a supported lane is missing from
    lanes.yaml or if its active_route doesn't resolve to a real artifact.
    Per cubic-dev-ai review on PR #8746: missing lanes must fail
    loudly so config regressions don't get a falsely-green smoke result.
    """
    from llm_gateway.gateway.config_loader import ConfigValidationError

    pairs: list[tuple[LaneConfig, RouteArtifact]] = []
    for lane_id in sorted(get_supported_auto_lane_ids()):
        if lane_filter and lane_id != lane_filter:
            continue
        if lane_id not in cfg.lanes:
            raise ConfigValidationError(
                f"get_supported_auto_lane_ids() contains {lane_id!r} but lanes.yaml has no such lane. "
                f"Add it to lanes.yaml or remove it from the supported allowlist."
            )
        lane = cfg.lanes[lane_id]
        if lane.active_route not in cfg.route_artifacts:
            raise ConfigValidationError(
                f"lane {lane_id!r} active_route {lane.active_route!r} has no matching route_artifacts.yaml entry. "
                f"Add the artifact to route_artifacts.yaml or fix the lane's active_route."
            )
        artifact = cfg.route_artifacts[lane.active_route]
        pairs.append((lane, artifact))
    return pairs


def build_summary(results: list[LaneResult]) -> dict[str, Any]:
    """Build the top-level summary dict from per-lane results."""
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    failed_lanes = sorted(r.lane_id for r in results if not r.passed)
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "failed_lanes": failed_lanes,
    }


def results_to_json(results: list[LaneResult]) -> dict[str, Any]:
    """Serialize smoke results."""
    return {
        "lanes": [
            {
                "lane_id": r.lane_id,
                "passed": r.passed,
                "latency_ms": round(r.latency_ms, 2),
                "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in r.checks],
                "failure_reason": r.failure_reason,
            }
            for r in results
        ],
        "summary": build_summary(results),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Path resolution — package-relative, NOT CWD-relative (per R5b's design)
# ---------------------------------------------------------------------------
_PACKAGE_DIR = Path(__file__).resolve().parent
_DEFAULT_GATEWAY_CONFIG_DIR = (_PACKAGE_DIR.parent / "config").resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Capability smoke gate for the auto-router-on-LLM-gateway feature (R2).",
    )
    parser.add_argument(
        "--lane",
        help="Smoke one lane only (e.g. omi:auto:realtime-ptt). Default: smoke all supported lanes.",
    )
    parser.add_argument(
        "--provider",
        choices=["fake", "real"],
        default="real",
        help="Provider implementation. Default: 'real' uses the configured gateway; 'fake' is test-only.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Also write the JSON output to this file. Default: stdout only.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print only the summary line; skip the per-lane detail. Useful for fast pre-flight checks.",
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=_DEFAULT_GATEWAY_CONFIG_DIR,
        help=(
            "Directory containing lanes.yaml, route_artifacts.yaml, feature_bundles.yaml. "
            f"Default: {_DEFAULT_GATEWAY_CONFIG_DIR} (package-relative)."
        ),
    )
    args = parser.parse_args(argv)

    cfg = load_gateway_config(args.config_dir, prod_mode=False)
    pairs = _iter_target_lanes(cfg, lane_filter=args.lane)
    if not pairs:
        print(
            json.dumps({"error": f"no lanes matched (filter={args.lane!r})", "summary": build_summary([])}),
            file=sys.stderr,
        )
        return 1

    provider = _build_provider(args.provider, cfg)

    async def _run() -> list[LaneResult]:
        try:
            results: list[LaneResult] = []
            for lane, artifact in pairs:
                results.append(await smoke_lane(lane, artifact, provider))
            return results
        finally:
            if isinstance(provider, RealGatewayProvider):
                await provider.aclose()

    results = asyncio.run(_run())
    payload = results_to_json(results)

    if args.dry_run:
        # Summary only — for fast pre-flight checks
        print(json.dumps({"summary": payload["summary"]}, indent=2))
    else:
        print(json.dumps(payload, indent=2))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(payload, indent=2))
        print(f"wrote {args.out}", file=sys.stderr)

    # Exit code: 0 if all passed, 1 if any failed
    return 0 if payload["summary"]["failed"] == 0 else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
