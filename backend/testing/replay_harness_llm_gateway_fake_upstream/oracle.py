"""Loopback-only structural oracle for the LLM gateway provider terminal path.

This is not a provider conformance suite. It drives the real FastAPI gateway,
route resolver, executor, and OpenAI-compatible provider adapter against a
controlled local fake upstream. Printed evidence is intentionally restricted
to path shape, event ordering, schema keys, status/error classes, and a bounded
timing outcome. The fake never retains prompts, completions, token values,
provider bodies, headers, credentials, or identifiers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import warnings
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx

# The pinned Starlette/httpx combination emits an import-time warning. The
# oracle's stdout is reserved for its structural evidence JSON.
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import OpenAICompatibleChatCompletionProvider
from llm_gateway.main import app
from llm_gateway.routers import dependencies

GATEWAY_PATH = "/v1/chat/completions"
ROUND_TRIP_DEADLINE_SECONDS = 5.0
MAX_LOOPBACK_REQUEST_BYTES = 16 * 1024
EXPECTED_PROVIDER_REQUEST_KEYS = ("messages", "model", "reasoning_effort", "stream")
EXPECTED_GATEWAY_RESPONSE_KEYS = ("choices", "created", "id", "model", "object")


class OracleFailure(AssertionError):
    """A bounded structural assertion failed."""


@dataclass
class _LoopbackOpenAI:
    """Local fake upstream that retains only allowlisted structural evidence."""

    endpoint_path: str = GATEWAY_PATH
    events: list[str] = field(default_factory=list)
    request_schema_keys: tuple[str, ...] = ()
    request_count: int = 0
    _server: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None
    _handler_failure: BaseException | None = None

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise RuntimeError("loopback upstream has not started")
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def __enter__(self) -> "_LoopbackOpenAI":
        upstream = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
                try:
                    if self.path.split("?", 1)[0] != upstream.endpoint_path:
                        raise OracleFailure("provider adapter used an unexpected upstream path")
                    upstream.events.append("upstream_request")
                    upstream.request_count += 1

                    # Parse one bounded body, then retain only its top-level schema
                    # keys. No body values are captured or logged.
                    content_length = int(self.headers.get("Content-Length", "0"))
                    if content_length <= 0 or content_length > MAX_LOOPBACK_REQUEST_BYTES:
                        raise OracleFailure("provider adapter sent an invalid request size")
                    request_body = json.loads(self.rfile.read(content_length))
                    if not isinstance(request_body, dict):
                        raise OracleFailure("provider adapter sent a non-object request")
                    upstream.request_schema_keys = tuple(sorted(request_body))
                    if upstream.request_schema_keys != EXPECTED_PROVIDER_REQUEST_KEYS:
                        raise OracleFailure("provider request schema changed unexpectedly")

                    response_body = {
                        "id": "loopback",
                        "object": "chat.completion",
                        "created": 0,
                        "model": "loopback",
                        "choices": [{"index": 0, "message": {"role": "assistant"}, "finish_reason": "stop"}],
                    }
                    encoded_response = json.dumps(response_body, separators=(",", ":")).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded_response)))
                    self.end_headers()
                    upstream.events.append("upstream_response")
                    self.wfile.write(encoded_response)
                except BaseException as error:
                    upstream._handler_failure = error
                    self.send_response(500)
                    self.end_headers()

            def log_message(self, _format: str, *_args: object) -> None:
                # BaseHTTPRequestHandler would otherwise print request details.
                return None

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _traceback: Any) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=ROUND_TRIP_DEADLINE_SECONDS)
        if self._handler_failure is not None:
            raise self._handler_failure


@contextmanager
def _temporary_environment(values: Mapping[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@contextmanager
def _bounded_evidence_logging() -> Iterator[None]:
    """Keep oracle output inside the structural-evidence allowlist."""

    loggers = [logging.getLogger("llm_gateway.gateway.metrics")]
    previous_levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        for logger, previous_level in zip(loggers, previous_levels):
            logger.setLevel(previous_level)


def _status_class(status_code: int) -> str:
    return f"{status_code // 100}xx"


def _valid_gateway_request() -> dict[str, object]:
    # Empty content proves only the route contract and prevents prompt capture.
    return {"model": "omi:auto:chat-structured", "messages": [{"role": "user", "content": ""}]}


def _loopback_http_client(**kwargs: Any) -> httpx.AsyncClient:
    """Construct a client that cannot read ambient proxy settings.

    This harness owns both endpoints.  Inheriting a developer or CI proxy here
    could route the fake provider request outside the process instead of to
    127.0.0.1, so every harness-owned client opts out explicitly.
    """

    return httpx.AsyncClient(trust_env=False, **kwargs)


async def _post_with_deadline(
    client: Any,
    *,
    path: str,
    payload: dict[str, object],
    headers: dict[str, str],
    deadline_seconds: float = ROUND_TRIP_DEADLINE_SECONDS,
) -> httpx.Response:
    """Bound the request itself, rather than checking elapsed time afterward."""

    try:
        async with asyncio.timeout(deadline_seconds):
            return await client.post(path, json=payload, headers=headers)
    except TimeoutError as error:
        raise OracleFailure("gateway loopback round trip exceeded its bounded deadline") from error


async def _run_gateway_oracle(upstream: _LoopbackOpenAI) -> dict[str, Any]:
    """Drive the real ASGI app and fake provider while both clients are live."""

    previous_overrides = dict(app.dependency_overrides)
    registry: ProviderRegistry | None = None
    try:
        async with _loopback_http_client() as provider_http_client:
            registry = ProviderRegistry(
                {
                    "openai": OpenAICompatibleChatCompletionProvider(
                        base_url=upstream.base_url,
                        http_client=provider_http_client,
                    ),
                }
            )
            # This override is test-owned. Production construction remains the
            # cached registry in llm_gateway.routers.dependencies.
            app.dependency_overrides[dependencies.get_provider_registry] = lambda: registry

            transport = httpx.ASGITransport(app=app, raise_app_exceptions=True)
            async with _loopback_http_client(transport=transport, base_url="http://gateway.test") as client:
                response = await _post_with_deadline(
                    client,
                    path=GATEWAY_PATH,
                    payload=_valid_gateway_request(),
                    headers={
                        "Authorization": "Bearer loopback-test-token",
                        "X-Omi-Service-Caller": "backend",
                    },
                )
                if _status_class(response.status_code) != "2xx":
                    raise OracleFailure("gateway did not return a successful status class")
                response_body = response.json()
                if not isinstance(response_body, dict):
                    raise OracleFailure("gateway returned a non-object response")
                response_schema_keys = tuple(sorted(response_body))
                if response_schema_keys != EXPECTED_GATEWAY_RESPONSE_KEYS:
                    raise OracleFailure("gateway response schema changed unexpectedly")
                upstream.events.append("gateway_response")

                # An external caller cannot change the provider target. The router
                # rejects this unknown field before the provider terminal path runs.
                redirect_response = await _post_with_deadline(
                    client,
                    path=GATEWAY_PATH,
                    payload={**_valid_gateway_request(), "upstream_url": upstream.base_url},
                    headers={
                        "Authorization": "Bearer loopback-test-token",
                        "X-Omi-Service-Caller": "backend",
                    },
                )
                if _status_class(redirect_response.status_code) != "4xx":
                    raise OracleFailure("gateway accepted an incoming upstream target")
                redirect_body = redirect_response.json()
                error = redirect_body.get("error") if isinstance(redirect_body, dict) else None
                error_class = error.get("code") if isinstance(error, dict) else None
                if error_class != "invalid_request":
                    raise OracleFailure("gateway used an unexpected redirect rejection class")
                if upstream.request_count != 1:
                    raise OracleFailure("incoming upstream target reached the provider terminal path")
                upstream.events.append("redirect_rejected")

                expected_events = ["upstream_request", "upstream_response", "gateway_response", "redirect_rejected"]
                if upstream.events != expected_events:
                    raise OracleFailure("gateway and provider terminal event ordering changed")

                return {
                    "oracle": "replay-llm-gateway-fake-upstream",
                    "endpoint_path": upstream.endpoint_path,
                    "event_order": upstream.events,
                    "request_schema_keys": upstream.request_schema_keys,
                    "response_schema_keys": response_schema_keys,
                    "status_classes": ["2xx", "4xx"],
                    "error_classes": [error_class],
                    "provider_request_count": upstream.request_count,
                    "bounded_round_trip": "within_5_seconds",
                }
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        if registry is not None:
            await registry.aclose()


def run_oracle() -> dict[str, Any]:
    """Run the gateway against its controlled loopback upstream."""

    with _temporary_environment(
        {
            "OMI_LLM_GATEWAY_SERVICE_TOKEN": "loopback-test-token",
            "OPENAI_API_KEY": "loopback-test-key",
        }
    ), _bounded_evidence_logging(), _LoopbackOpenAI() as upstream:
        return asyncio.run(_run_gateway_oracle(upstream))


def main() -> int:
    try:
        evidence = run_oracle()
    except Exception as error:
        print(f"Replay LLM gateway fake-upstream oracle failed: {type(error).__name__}")
        return 1
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
