"""Deterministic provider for the capability smoke (R2 default).

The smoke script (`capability_smoke.py`) defaults to this provider so
the smoke never makes real HTTP calls by default. Tests of the smoke
itself also use this provider.

`FakeProvider` lives on the production-side import path (not under
`tests/.../_private/`) so the smoke's default-import doesn't couple
production code to the test tree. Per cubic-dev-ai review on PR #8746.

Scenarios (set per call via `set_next_scenario`):
    - "pass": return a response matching the request's format
    - "timeout": raise asyncio.TimeoutError after a short delay
    - "auth_error": raise ProviderAuthError
    - "schema_violation": return malformed structured output
    - "malformed_json": return non-JSON content in a json_object response

The fake is intentionally minimal — it doesn't validate the response
shape, it just returns whatever the test configured. The real
validation lives in the smoke logic.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol


class ProviderAuthError(Exception):
    """Raised when a provider rejects the request due to auth (401/403)."""


class ProviderRequest:
    """The smoke's view of a single chat-completion request.

    Mirrors `llm_gateway.scripts.capability_smoke.ProviderRequest` (kept
    here as a copy so this module has zero production dependencies on
    the smoke module — useful for unit tests and for ad-hoc invocation).
    """

    def __init__(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_format: Optional[dict[str, Any]] = None,
        tools: Optional[list[dict[str, Any]]] = None,
        stream: bool = False,
        timeout_seconds: float = 8.0,
    ):
        self.model = model
        self.messages = messages
        self.response_format = response_format
        self.tools = tools
        self.stream = stream
        self.timeout_seconds = timeout_seconds


@dataclass
class FakeCall:
    """Recorded call for test introspection."""

    request: ProviderRequest
    response: Optional["ProviderResponse"]
    error: Optional[Exception]
    latency_seconds: float


@dataclass
class ProviderResponse:
    """The provider's reply."""

    content: str = ""
    tool_call: Optional[dict[str, Any]] = None
    structured_output: Any = None
    usage: dict[str, int] = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0})


class Provider(Protocol):
    """The smoke's contract with the provider layer."""

    async def chat_completion(self, request: ProviderRequest) -> ProviderResponse:  # pragma: no cover
        raise NotImplementedError


# ---------------------------------------------------------------------------
# FakeProvider: deterministic, configurable per call
# ---------------------------------------------------------------------------


class FakeProvider:
    """Configurable fake provider for the smoke.

    See module docstring for the scenario list.
    """

    def __init__(self) -> None:
        self._next_scenarios: list[str] = []
        self._calls: list[FakeCall] = []
        self._default_scenario = "pass"

    # ---- Scenario configuration -----------------------------------------

    def set_next_scenario(self, scenario: str) -> None:
        if scenario not in {"pass", "timeout", "auth_error", "schema_violation", "malformed_json"}:
            raise ValueError(f"unknown scenario: {scenario!r}")
        self._next_scenarios.append(scenario)

    def set_default_scenario(self, scenario: str) -> None:
        if scenario not in {"pass", "timeout", "auth_error", "schema_violation", "malformed_json"}:
            raise ValueError(f"unknown scenario: {scenario!r}")
        self._default_scenario = scenario

    def queue_scenarios(self, *scenarios: str) -> None:
        for s in scenarios:
            self.set_next_scenario(s)

    @property
    def calls(self) -> list[FakeCall]:
        return list(self._calls)

    def clear_calls(self) -> None:
        self._calls.clear()

    # ---- Provider implementation ----------------------------------------

    async def chat_completion(self, request: ProviderRequest) -> ProviderResponse:
        scenario = self._next_scenarios.pop(0) if self._next_scenarios else self._default_scenario
        t0 = time.perf_counter()
        try:
            if scenario == "timeout":
                await asyncio.sleep(request.timeout_seconds + 0.1)
                raise asyncio.TimeoutError("provider timed out")
            if scenario == "auth_error":
                err = ProviderAuthError("401 unauthorized")
                self._calls.append(FakeCall(request, None, err, time.perf_counter() - t0))
                raise err
            if scenario == "schema_violation":
                response = self._schema_violation_response(request)
            elif scenario == "malformed_json":
                response = ProviderResponse(content="not valid json {{")
            else:  # "pass"
                response = self._pass_response(request)
        except Exception as e:
            self._calls.append(FakeCall(request, None, e, time.perf_counter() - t0))
            raise
        latency = time.perf_counter() - t0
        self._calls.append(FakeCall(request, response, None, latency))
        return response

    # ---- Response builders -------------------------------------------------

    @staticmethod
    def _pass_response(request: ProviderRequest) -> ProviderResponse:
        """Build a response that matches ALL of the request's capabilities."""
        structured_output: Any = None
        if request.response_format:
            fmt_type = request.response_format.get("type")
            if fmt_type == "json_schema":
                schema = request.response_format.get("json_schema", {}).get("schema", {})
                schema_type = schema.get("type", "object")
                if schema_type == "object":
                    structured_output = {"answer": "smoke-ok"}
                elif schema_type == "string":
                    structured_output = "smoke-ok"
            elif fmt_type == "json_object":
                structured_output = {"answer": "smoke-ok"}

        tool_call: Optional[dict[str, Any]] = None
        if request.tools:
            tool_call = {
                "name": request.tools[0].get("name", "test_tool"),
                "arguments": '{"input": "smoke"}',
            }

        content = "smoke-ok"
        if tool_call is not None or structured_output is not None:
            content = ""

        return ProviderResponse(
            content=content,
            tool_call=tool_call,
            structured_output=structured_output,
        )

    @staticmethod
    def _schema_violation_response(request: ProviderRequest) -> ProviderResponse:
        """Return a response that DOESN'T match the requested schema."""
        fmt_type = (request.response_format or {}).get("type")
        if fmt_type in ("json_schema", "json_object"):
            return ProviderResponse(content="", structured_output="not-an-object")
        return ProviderResponse(content="wrong format")
