"""Loopback-only wire oracle for the LLM gateway streaming terminal path.

This is not a provider conformance suite. It drives the real FastAPI gateway,
route resolver, executor, OpenAI-compatible streaming provider, and
StreamingResponse against a controlled local fake upstream. The fake sends
synthetic SSE frames in deliberately fragmented HTTP chunks. Printed evidence
is restricted to endpoint/frame labels, schema keys, status/error classes,
timing bucket, and request count. It never retains prompt/completion/token
values, SSE payloads, headers, credentials, identifiers, or provider bodies.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import threading
import time
import warnings
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from unittest.mock import patch

# The pinned Starlette/httpx combination emits an import-time warning. The
# oracle's stdout is reserved for its structural evidence JSON.
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from starlette.testclient import TestClient

from llm_gateway.gateway.config_loader import load_gateway_config
from llm_gateway.gateway.executor import ProviderRegistry
from llm_gateway.gateway.providers import OpenAICompatibleChatCompletionProvider
from llm_gateway.gateway.sse import SSEEventDecoder
from llm_gateway.main import app
from llm_gateway.routers import dependencies

GATEWAY_PATH = "/v1/chat/completions"
LANE_ID = "omi:auto:chat-structured"
ROUND_TRIP_DEADLINE_SECONDS = 5.0
MAX_LOOPBACK_REQUEST_BYTES = 16 * 1024
EXPECTED_PROVIDER_REQUEST_KEYS = ("messages", "model", "reasoning_effort", "stream", "stream_options")

# Neither frame contains user content. The terminal frame needs synthetic usage
# fields only so the existing gateway terminal-usage path executes.
_SYNTHETIC_SSE = (
    b'data: {"choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}\n\n'
    b'data: {"choices":[{"index":0,"delta":{},"finish_reason":"stop"}],'
    b'"usage":{"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}}\n\n'
    b"data: [DONE]\n\n"
)
# Split inside SSE fields and frame boundaries; HTTP chunk framing preserves the
# deliberate upstream fragmentation for the real provider's incremental reader.
_SSE_FRAGMENTS = (
    _SYNTHETIC_SSE[:19],
    _SYNTHETIC_SSE[19:78],
    _SYNTHETIC_SSE[78:151],
    _SYNTHETIC_SSE[151:226],
    _SYNTHETIC_SSE[226:],
)


class OracleFailure(AssertionError):
    """A bounded structural assertion failed."""


@dataclass
class _LoopbackOpenAI:
    """Local streaming fake retaining only allowlisted structural evidence."""

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
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
                try:
                    if self.path.split("?", 1)[0] != upstream.endpoint_path:
                        raise OracleFailure("provider adapter used an unexpected upstream path")
                    upstream.events.append("upstream_request")
                    upstream.request_count += 1

                    content_length = int(self.headers.get("Content-Length", "0"))
                    if content_length <= 0 or content_length > MAX_LOOPBACK_REQUEST_BYTES:
                        raise OracleFailure("provider adapter sent an invalid request size")
                    request_body = json.loads(self.rfile.read(content_length))
                    if not isinstance(request_body, dict):
                        raise OracleFailure("provider adapter sent a non-object request")
                    upstream.request_schema_keys = tuple(sorted(request_body))
                    if upstream.request_schema_keys != EXPECTED_PROVIDER_REQUEST_KEYS:
                        raise OracleFailure("provider streaming request schema changed unexpectedly")
                    if request_body.get("stream") is not True:
                        raise OracleFailure("provider did not request streaming")
                    stream_options = request_body.get("stream_options")
                    if not isinstance(stream_options, dict) or stream_options.get("include_usage") is not True:
                        raise OracleFailure("provider did not request terminal usage")

                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Transfer-Encoding", "chunked")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    for fragment in _SSE_FRAGMENTS:
                        self.wfile.write(f"{len(fragment):X}\r\n".encode("ascii"))
                        self.wfile.write(fragment)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()
                    self.wfile.write(b"0\r\n\r\n")
                    self.wfile.flush()
                    self.close_connection = True
                    upstream.events.append("upstream_fragmented_sse")
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
    """Keep executable output inside the structural-evidence allowlist."""

    loggers = [logging.getLogger("llm_gateway.gateway.metrics"), logging.getLogger("httpx")]
    previous_levels = [logger.level for logger in loggers]
    for logger in loggers:
        logger.setLevel(logging.CRITICAL)
    try:
        yield
    finally:
        for logger, previous_level in zip(loggers, previous_levels):
            logger.setLevel(previous_level)


@contextmanager
def _loopback_egress_only() -> Iterator[None]:
    """Fail locally if this hermetic oracle attempts any non-loopback connect."""

    original_connect = socket.socket.connect

    def guarded_connect(sock: socket.socket, address: Any) -> Any:
        host = address[0] if isinstance(address, tuple) and address else ""
        if host not in {"127.0.0.1", "::1"}:
            raise OracleFailure("non-loopback socket egress was attempted")
        return original_connect(sock, address)

    with patch.object(socket.socket, "connect", guarded_connect):
        yield


def _streaming_enabled_gateway_config() -> Any:
    """Enable the existing stream capability for this test-owned dependency."""

    config = load_gateway_config(prod_mode=True)
    lane = config.lanes[LANE_ID]
    capabilities = lane.capabilities.model_copy(update={"streaming": True})
    streaming_lane = lane.model_copy(update={"capabilities": capabilities})
    route_artifacts = dict(config.route_artifacts)
    for route_id in (streaming_lane.active_route, streaming_lane.last_known_good):
        route_artifacts[route_id] = route_artifacts[route_id].model_copy(update={"capabilities": capabilities})
    lanes = dict(config.lanes)
    lanes[LANE_ID] = streaming_lane
    return config.model_copy(update={"lanes": lanes, "route_artifacts": route_artifacts})


def _valid_gateway_request() -> dict[str, object]:
    # Empty content proves only route handling and avoids prompt capture.
    return {
        "model": LANE_ID,
        "messages": [{"role": "user", "content": ""}],
        "stream": True,
    }


def _parse_client_frame_labels(body: bytes) -> tuple[list[str], list[tuple[str, ...]]]:
    """Normalize transport chunks and retain only frame labels and key sets."""

    decoder = SSEEventDecoder()
    labels: list[str] = []
    schema_key_sets: list[tuple[str, ...]] = []
    for event in decoder.feed(body):
        data = event.data.strip()
        if data == "[DONE]":
            labels.append("done")
            continue
        payload = json.loads(data)
        if not isinstance(payload, dict):
            raise OracleFailure("gateway emitted a non-object client data frame")
        schema_key_sets.append(tuple(sorted(payload)))
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise OracleFailure("gateway emitted a client frame without choices")
        if isinstance(payload.get("usage"), dict):
            if choices[0].get("finish_reason") is None:
                raise OracleFailure("terminal usage frame omitted its finish reason")
            labels.append("terminal_usage_finish")
        elif choices[0].get("finish_reason") is None:
            labels.append("nonterminal_data")
        else:
            raise OracleFailure("gateway emitted an unexpected terminal data frame")
    return labels, schema_key_sets


def _assert_semantic_stream_order(body: bytes) -> tuple[list[str], list[tuple[str, ...]]]:
    labels, schema_key_sets = _parse_client_frame_labels(body)
    if labels.count("done") != 1:
        raise OracleFailure("gateway did not emit exactly one done marker")
    if len(labels) < 3 or labels[-2:] != ["terminal_usage_finish", "done"]:
        raise OracleFailure("gateway terminal usage/finish and done ordering changed")
    if not all(label == "nonterminal_data" for label in labels[:-2]):
        raise OracleFailure("gateway emitted an unexpected nonterminal frame ordering")
    return labels, schema_key_sets


def _status_class(status_code: int) -> str:
    return f"{status_code // 100}xx"


def run_oracle() -> dict[str, Any]:
    """Exercise one bounded streaming round trip plus redirect rejection."""

    previous_overrides = dict(app.dependency_overrides)
    registry: ProviderRegistry | None = None
    try:
        with _temporary_environment(
            {
                "OMI_LLM_GATEWAY_SERVICE_TOKEN": "loopback-test-token",
                "OPENAI_API_KEY": "loopback-test-key",
            }
        ), _bounded_evidence_logging(), _LoopbackOpenAI() as upstream, _loopback_egress_only():
            registry = ProviderRegistry(
                {
                    "openai": OpenAICompatibleChatCompletionProvider(base_url=upstream.base_url),
                }
            )
            app.dependency_overrides[dependencies.get_gateway_config] = _streaming_enabled_gateway_config
            app.dependency_overrides[dependencies.get_provider_registry] = lambda: registry

            with TestClient(app) as client:
                started_at = time.monotonic()
                response = client.post(
                    GATEWAY_PATH,
                    json=_valid_gateway_request(),
                    headers={
                        "Authorization": "Bearer loopback-test-token",
                        "X-Omi-Service-Caller": "backend",
                    },
                )
                if time.monotonic() - started_at > ROUND_TRIP_DEADLINE_SECONDS:
                    raise OracleFailure("gateway streaming round trip exceeded its bounded deadline")
                if _status_class(response.status_code) != "2xx":
                    raise OracleFailure("gateway streaming request did not return a successful status class")
                if not response.headers.get("content-type", "").startswith("text/event-stream"):
                    raise OracleFailure("gateway streaming response did not use text/event-stream")
                frame_order, frame_schema_key_sets = _assert_semantic_stream_order(response.content)
                upstream.events.append("gateway_stream_response")

                redirect_response = client.post(
                    GATEWAY_PATH,
                    json={**_valid_gateway_request(), "upstream_url": upstream.base_url},
                    headers={
                        "Authorization": "Bearer loopback-test-token",
                        "X-Omi-Service-Caller": "backend",
                    },
                )
                if _status_class(redirect_response.status_code) != "4xx":
                    raise OracleFailure("gateway accepted an inbound upstream target")
                redirect_body = redirect_response.json()
                error = redirect_body.get("error") if isinstance(redirect_body, dict) else None
                error_class = error.get("code") if isinstance(error, dict) else None
                if error_class != "invalid_request":
                    raise OracleFailure("gateway used an unexpected redirect rejection class")
                if upstream.request_count != 1:
                    raise OracleFailure("inbound upstream target reached the provider streaming path")
                upstream.events.append("redirect_rejected")

                expected_events = [
                    "upstream_request",
                    "upstream_fragmented_sse",
                    "gateway_stream_response",
                    "redirect_rejected",
                ]
                if upstream.events != expected_events:
                    raise OracleFailure("gateway and streaming provider event ordering changed")

                return {
                    "oracle": "replay-llm-streaming-wire-fidelity",
                    "endpoint_path": upstream.endpoint_path,
                    "event_order": upstream.events,
                    "frame_order": frame_order,
                    "provider_request_schema_keys": upstream.request_schema_keys,
                    "client_frame_schema_key_sets": sorted({keys for keys in frame_schema_key_sets}),
                    "status_classes": ["2xx", "4xx"],
                    "error_classes": [error_class],
                    "provider_request_count": upstream.request_count,
                    "bounded_round_trip": "within_5_seconds",
                }
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        if registry is not None:
            asyncio.run(registry.aclose())


def main() -> int:
    try:
        evidence = run_oracle()
    except Exception as error:
        print(f"Replay LLM streaming wire-fidelity oracle failed: {type(error).__name__}")
        return 1
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
