"""Narrow loopback Vertex broker for the isolated JIT QA stack.

Only this process receives development ADC. It exposes one authenticated
OpenAI-compatible chat endpoint and its provider constructs only Vertex
``aiplatform.googleapis.com`` requests. The general backend processes receive
neither ADC nor the host gcloud configuration.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import hmac
import os
import time
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
import google.auth
from google.auth.transport.requests import Request as GoogleAuthRequest

from llm_gateway.gateway.auth import ServiceCaller
from llm_gateway.gateway.credentials import build_omi_managed_credential_context
from llm_gateway.gateway.providers import ProviderFailure, VertexGeminiProvider
from llm_gateway.gateway.schemas import ProviderRef

MAX_REQUEST_BYTES = 5 * 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_TOKENS = 8_192
MAX_CONCURRENT_REQUESTS = 2
MAX_REQUESTS_PER_MINUTE = 30
DEFAULT_MODEL = "gemini-2.5-flash"
_provider: VertexGeminiProvider | None = None
_credentials = build_omi_managed_credential_context(ServiceCaller(name="backend"))
_in_flight = 0
_request_starts: deque[float] = deque()


def _service_token() -> str:
    token = os.environ.get("OMI_LLM_GATEWAY_SERVICE_TOKEN", "").strip()
    if len(token) < 32:
        raise RuntimeError("local Vertex gateway service token is not configured")
    return token


def _authorize(request: Request) -> None:
    supplied = request.headers.get("authorization", "")
    expected = f"Bearer {_service_token()}"
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid service authentication")
    if request.headers.get("x-omi-service-caller", "").strip().lower() != "backend":
        raise HTTPException(status_code=403, detail="service caller is not allowed")
    if any(name.lower().startswith("x-omi-byok-") for name in request.headers):
        raise HTTPException(status_code=400, detail="BYOK is not available in local JIT QA")


async def _request_payload(request: Request) -> dict[str, Any]:
    body = await request.body()
    if not body or len(body) > MAX_REQUEST_BYTES:
        raise HTTPException(status_code=413, detail="request body is empty or too large")
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="request body must be JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="request body must be an object")
    _reject_unsupported_surfaces(payload)
    bounded = dict(payload)
    _bound_output_budget(bounded)
    return bounded


def _bound_output_budget(payload: dict[str, Any]) -> None:
    values: list[int] = []
    for name in ("max_tokens", "max_completion_tokens"):
        value = payload.get(name)
        if value is None:
            continue
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise HTTPException(status_code=400, detail=f"{name} must be a positive integer")
        values.append(value)
    if len(values) == 2 and values[0] != values[1]:
        raise HTTPException(
            status_code=400,
            detail="max_tokens and max_completion_tokens must match",
        )
    requested = values[0] if values else MAX_OUTPUT_TOKENS
    payload["max_tokens"] = min(requested, MAX_OUTPUT_TOKENS)
    payload.pop("max_completion_tokens", None)

    extra_body = payload.get("extra_body")
    if extra_body not in (None, {}):
        raise HTTPException(
            status_code=422,
            detail="provider-specific options require deployed development",
        )


def _reserve_request_slot() -> None:
    global _in_flight
    now = time.monotonic()
    while _request_starts and now - _request_starts[0] >= 60:
        _request_starts.popleft()
    if _in_flight >= MAX_CONCURRENT_REQUESTS:
        raise HTTPException(status_code=429, detail="local Vertex concurrency limit")
    if len(_request_starts) >= MAX_REQUESTS_PER_MINUTE:
        raise HTTPException(status_code=429, detail="local Vertex rate limit")
    _request_starts.append(now)
    _in_flight += 1


def _release_request_slot() -> None:
    global _in_flight
    _in_flight = max(0, _in_flight - 1)


async def _bounded_stream(
    chunks: AsyncIterator[bytes | str],
) -> AsyncIterator[bytes | str]:
    response_bytes = 0
    async for chunk in chunks:
        encoded = chunk if isinstance(chunk, bytes) else chunk.encode("utf-8")
        response_bytes += len(encoded)
        if response_bytes > MAX_RESPONSE_BYTES:
            raise RuntimeError("local Vertex stream exceeded its response budget")
        yield chunk


def _reject_unsupported_surfaces(payload: dict[str, Any]) -> None:
    if payload.get("tools") or payload.get("tool_choice") not in (None, "none"):
        raise HTTPException(status_code=422, detail="tool calls require deployed development")
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("tool_calls"):
            raise HTTPException(status_code=422, detail="tool calls require deployed development")
        content = message.get("content")
        if isinstance(content, list) and any(
            not isinstance(part, dict) or part.get("type") != "text" for part in content
        ):
            raise HTTPException(status_code=422, detail="multimodal input requires deployed development")


def _get_provider() -> VertexGeminiProvider:
    global _provider
    if _provider is None:
        _provider = VertexGeminiProvider()
    return _provider


def _provider_ref() -> ProviderRef:
    model = os.environ.get("OMI_JIT_QA_VERTEX_MODEL", DEFAULT_MODEL).strip()
    if model != DEFAULT_MODEL:
        raise RuntimeError(f"local Vertex gateway model must remain {DEFAULT_MODEL}")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    if project != "based-hardware-dev":
        raise RuntimeError("local Vertex gateway requires the development GCP project")
    return ProviderRef(provider="gemini", model=model)


def _refresh_development_adc() -> None:
    credentials, detected_project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    if detected_project != "based-hardware-dev":
        raise RuntimeError("local Vertex gateway ADC resolved outside development")
    if getattr(credentials, "quota_project_id", None) != "based-hardware-dev":
        raise RuntimeError("local Vertex gateway ADC quota project is not development")
    credentials.refresh(GoogleAuthRequest())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _provider
    _service_token()
    _provider_ref()
    provider = _get_provider()
    try:
        yield
    finally:
        await provider.aclose()
        _provider = None


app = FastAPI(title="Omi JIT QA Vertex Gateway", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": "omi-jit-qa-vertex-gateway"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    _service_token()
    _provider_ref()
    # Health is not readiness: prove the isolated broker can still refresh its
    # dev credential so `up` cannot report a usable stack from labels alone.
    await asyncio.to_thread(_refresh_development_adc)
    return {"status": "ready", "service": "omi-jit-qa-vertex-gateway"}


@app.post("/v1/chat/completions", response_model=None)
async def chat_completions(request: Request) -> JSONResponse | StreamingResponse:
    _authorize(request)
    payload = await _request_payload(request)
    stream = payload.pop("stream", False) is True
    payload.pop("model", None)
    provider_ref = _provider_ref()
    provider = _get_provider()
    _reserve_request_slot()
    if stream:

        async def events():
            try:
                chunks = provider.stream_chat_completion(
                    payload,
                    provider_ref=provider_ref,
                    credentials=_credentials,
                    timeout_ms=150_000,
                )
                async for chunk in _bounded_stream(chunks):
                    yield chunk
            finally:
                _release_request_slot()

        return StreamingResponse(events(), media_type="text/event-stream")
    try:
        result = await provider.create_chat_completion(
            payload,
            provider_ref=provider_ref,
            credentials=_credentials,
            timeout_ms=150_000,
        )
        response = JSONResponse(content=dict(result.response))
        if len(response.body) > MAX_RESPONSE_BYTES:
            raise HTTPException(status_code=502, detail="Vertex response exceeded its byte budget")
        return response
    except ProviderFailure as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Vertex provider failure: {exc.failure_class.value}",
        ) from exc
    finally:
        _release_request_slot()


def provider_surface_names() -> frozenset[str]:
    """Auditable contract for the broker's only cloud-capable provider."""

    return frozenset({VertexGeminiProvider.__name__})


__all__ = ["app", "provider_surface_names"]
