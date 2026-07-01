"""Deterministic fake provider for the capability smoke tests.

The smoke script (R2) is testable end-to-end without making real HTTP
calls. This fake implements the `Provider` protocol surface and lets
tests configure per-call outcomes:

- pass: returns a response matching the lane's capabilities
- timeout: raises `asyncio.TimeoutError` after a configurable delay
- auth_error: raises `ProviderAuthError`
- schema_violation: returns a response that doesn't match the requested
  json_schema (or json_object for json_object mode)
- malformed_json: returns a response with non-JSON content in a
  json_object / json_schema response

The fake is intentionally minimal — it doesn't validate the response
shape, it just returns whatever the test configured. The real validation
lives in the smoke logic (`capability_smoke.py`).

The fake lives under `tests/.../_private/` per the plan's convention:
test-only modules that production code must not import. The
`tests/unit/llm_gateway/test_capability_smoke.py` and any future smoke
integration tests use this fake; the production smoke script uses a
real provider (or a stub-by-default).
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

    Built by `capability_smoke.build_fixture` based on the lane's
    declared capabilities. The provider decides what to return (or
    raise) for this request.
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
class ProviderResponse:
    """The provider's reply. The smoke validates shape; the fake just returns."""

    content: str = ""
    tool_call: Optional[dict[str, Any]] = None
    structured_output: Any = None  # parsed JSON for json_object / json_schema
    usage: dict[str, int] = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0})


class Provider(Protocol):
    """The smoke's contract with the provider layer.

    Real implementations make HTTP calls; test implementations return
    predetermined responses. Either way, the smoke sees the same surface.
    """

    async def chat_completion(self, request: ProviderRequest) -> ProviderResponse: ...


# ---------------------------------------------------------------------------
# FakeProvider: deterministic, configurable per call
# ---------------------------------------------------------------------------


@dataclass
class FakeCall:
    """Recorded call for test introspection."""

    request: ProviderRequest
    response: Optional[ProviderResponse]
    error: Optional[Exception]
    latency_seconds: float


class FakeProvider:
    """Configurable fake provider for smoke tests.

    Scenarios (set per call via `set_next_scenario`):
        - "pass": return a valid response matching the request's format
        - "timeout": raise asyncio.TimeoutError after a short delay
        - "auth_error": raise ProviderAuthError
        - "schema_violation": return malformed structured output
        - "malformed_json": return non-JSON content in a json_object
          response (parse error on the smoke side)
    """

    def __init__(self) -> None:
        self._next_scenarios: list[str] = []
        self._calls: list[FakeCall] = []
        # Default pass: a basic "Hello" response.
        self._default_scenario = "pass"

    # ---- Scenario configuration -----------------------------------------

    def set_next_scenario(self, scenario: str) -> None:
        """Queue a scenario for the NEXT chat_completion call."""
        if scenario not in {"pass", "timeout", "auth_error", "schema_violation", "malformed_json"}:
            raise ValueError(f"unknown scenario: {scenario!r}")
        self._next_scenarios.append(scenario)

    def set_default_scenario(self, scenario: str) -> None:
        """Set the default scenario for all calls without a queued scenario."""
        if scenario not in {"pass", "timeout", "auth_error", "schema_violation", "malformed_json"}:
            raise ValueError(f"unknown scenario: {scenario!r}")
        self._default_scenario = scenario

    def queue_scenarios(self, *scenarios: str) -> None:
        """Queue multiple scenarios at once."""
        for s in scenarios:
            self.set_next_scenario(s)

    @property
    def calls(self) -> list[FakeCall]:
        """Recorded call history (for test introspection)."""
        return list(self._calls)

    def clear_calls(self) -> None:
        self._calls.clear()

    # ---- Provider implementation ----------------------------------------

    async def chat_completion(self, request: ProviderRequest) -> ProviderResponse:
        scenario = self._next_scenarios.pop(0) if self._next_scenarios else self._default_scenario
        t0 = time.perf_counter()
        try:
            if scenario == "timeout":
                # Sleep just past the request timeout to simulate the provider hanging.
                await asyncio.sleep(request.timeout_seconds + 0.1)
                # Unreachable in practice (caller should timeout first), but if
                # we get here, raise the timeout.
                raise asyncio.TimeoutError("provider timed out")
            if scenario == "auth_error":
                err = ProviderAuthError("401 unauthorized")
                self._calls.append(FakeCall(request, None, err, time.perf_counter() - t0))
                raise err
            if scenario == "schema_violation":
                # Return a response that DOESN'T match the requested schema
                # (or returns non-object for json_object).
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
        """Build a response that matches ALL of the request's capabilities.

        A lane may declare multiple capabilities (e.g. tools AND json_object).
        The pass response should satisfy all of them so the smoke's per-check
        validation passes.
        """
        # Structured output: emit JSON matching the requested format
        structured_output: Any = None
        if request.response_format:
            fmt_type = request.response_format.get("type")
            if fmt_type == "json_schema":
                schema = request.response_format.get("json_schema", {}).get("schema", {})
                # Emit a minimal valid response matching the schema's "type" field
                schema_type = schema.get("type", "object")
                if schema_type == "object":
                    structured_output = {"answer": "smoke-ok"}
                elif schema_type == "string":
                    structured_output = "smoke-ok"
            elif fmt_type == "json_object":
                structured_output = {"answer": "smoke-ok"}

        # Tools: emit a tool call if tools were provided
        tool_call: Optional[dict[str, Any]] = None
        if request.tools:
            tool_call = {
                "name": request.tools[0].get("name", "test_tool"),
                "arguments": '{"input": "smoke"}',
            }

        # Plain text response (text_input only)
        content = "smoke-ok"
        if tool_call is not None or structured_output is not None:
            # When we have tool_call or structured_output, the model often
            # returns empty content alongside them.
            content = ""

        return ProviderResponse(
            content=content,
            tool_call=tool_call,
            structured_output=structured_output,
        )

    @staticmethod
    def _schema_violation_response(request: ProviderRequest) -> ProviderResponse:
        """Return a response that DOESN'T match the requested schema.

        For json_schema: returns a string instead of the expected object
        (or null where the schema expects an object).
        For json_object: returns a string (not an object).
        """
        fmt_type = (request.response_format or {}).get("type")
        if fmt_type in ("json_schema", "json_object"):
            return ProviderResponse(content="", structured_output="not-an-object")
        return ProviderResponse(content="wrong format")
