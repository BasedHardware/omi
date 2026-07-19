"""Raw Anthropic Messages API pass-through for agentic chat."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any, cast

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse

from llm_gateway.gateway.accounting import (
    AccountingContext,
    AttemptTrace,
    ProviderResponseMetadata,
    UsageStatus,
    anthropic_usage_from_response,
    cache_requested_for_anthropic_request,
    cache_write_ttl_for_anthropic_request,
)
from llm_gateway.gateway.accounting_sink import schedule_attempt_trace
from llm_gateway.gateway.auth import ServiceAuthDependency
from llm_gateway.gateway.config_loader import GatewayConfig
from llm_gateway.gateway.metrics import (
    observe_request_rejection,
    observe_route_result,
    report_observation_failure,
    time_request,
)
from llm_gateway.gateway.request_context import request_id_for
from llm_gateway.gateway.schemas import RouteArtifact, Surface
from llm_gateway.gateway.sse import SSEEventDecoder
from llm_gateway.routers.dependencies import get_gateway_config

router = APIRouter()

ANTHROPIC_MESSAGES_BASE_URL = 'https://api.anthropic.com/v1'
AUTO_LANE_PREFIX = 'omi:auto:'
ANTHROPIC_BETA_HEADER = 'anthropic-beta'
ANTHROPIC_VERSION_HEADER = 'anthropic-version'
DEFAULT_ANTHROPIC_VERSION = '2023-06-01'
DEFAULT_ANTHROPIC_BETA = 'token-efficient-tools-2025-02-19'

_anthropic_http_client: httpx.AsyncClient | None = None


@router.post('/v1/messages', response_model=None)
async def create_anthropic_message(
    request: Request,
    caller: ServiceAuthDependency,
    config: GatewayConfig = Depends(get_gateway_config),
) -> JSONResponse | StreamingResponse:
    started_at = time_request()
    request_id = request_id_for(request)
    try:
        request_body = await request.json()
    except ValueError as exc:
        _observe_anthropic_request_rejection(request_id, 'invalid_json')
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='request body must be valid JSON') from exc
    if not isinstance(request_body, dict):
        _observe_anthropic_request_rejection(request_id, 'invalid_body')
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='request body must be an object')

    body = cast(dict[str, Any], request_body)
    is_streaming = body.get('stream') is True
    try:
        route = _resolve_lane_route(config, body.get('model'))
        _validate_anthropic_capabilities(route, body)
    except HTTPException as exc:
        _observe_anthropic_request_rejection(request_id, f'http_{exc.status_code}')
        raise
    metric_context = _AnthropicMetricContext(
        started_at=started_at,
        lane_id=route.lane_id,
        route_artifact_id=route.route_artifact_id,
        provider=route.primary.provider,
        model=route.primary.model,
        credential_source=_anthropic_credential_source(request),
        request_id=request_id,
    )
    accounting_context = AccountingContext.create(
        request_id=request_id,
        caller=caller.name,
        user_uid=caller.user_uid,
        feature=_accounting_feature(caller, fallback=route.lane_id),
        api_surface='anthropic_messages',
        payer='byok' if _anthropic_credential_source(request) == 'service_forwarded_byok' else 'omi',
    )
    attempt_trace = AttemptTrace()
    body['model'] = route.primary.model
    body.update(route.provider_options)

    api_key = _resolve_anthropic_api_key(request)
    if not api_key:
        _observe_message_terminal(
            metric_context,
            outcome='error',
            error_class='invalid_config',
            phase='before_output',
            streaming=is_streaming,
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={'error': {'message': 'anthropic provider is not configured', 'type': 'api_error'}},
        )

    headers = _anthropic_forward_headers(request, api_key=api_key)
    if is_streaming:
        return await _streaming_anthropic_messages_response(
            body,
            headers=headers,
            metric_context=metric_context,
            accounting_context=accounting_context,
            attempt_trace=attempt_trace,
        )

    try:
        response = await _get_anthropic_http_client().post(
            f'{ANTHROPIC_MESSAGES_BASE_URL}/messages',
            json=body,
            headers=headers,
        )
    except asyncio.CancelledError:
        attempt_trace.record(
            provider='anthropic',
            configured_model=route.primary.model,
            route_artifact_id=route.route_artifact_id,
            fallback_reason=None,
            retry_ordinal=1,
            outcome='cancelled',
            error_class='client_cancelled',
            usage_status=UsageStatus.INDETERMINATE,
        )
        schedule_attempt_trace(accounting_context, attempt_trace)
        _observe_message_terminal(
            metric_context,
            outcome='cancelled',
            error_class='client_cancelled',
            phase='before_output',
        )
        raise
    except httpx.TimeoutException as exc:
        attempt_trace.record(
            provider='anthropic',
            configured_model=route.primary.model,
            route_artifact_id=route.route_artifact_id,
            fallback_reason=None,
            retry_ordinal=1,
            outcome='error',
            error_class='timeout_before_output',
            usage_status=UsageStatus.INDETERMINATE,
        )
        schedule_attempt_trace(accounting_context, attempt_trace)
        _observe_message_terminal(
            metric_context,
            outcome='error',
            error_class='timeout_before_output',
            phase='before_output',
        )
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail='anthropic request timed out') from exc
    except httpx.HTTPError as exc:
        attempt_trace.record(
            provider='anthropic',
            configured_model=route.primary.model,
            route_artifact_id=route.route_artifact_id,
            fallback_reason=None,
            retry_ordinal=1,
            outcome='error',
            error_class='transport_before_output',
            usage_status=UsageStatus.INDETERMINATE,
        )
        schedule_attempt_trace(accounting_context, attempt_trace)
        _observe_message_terminal(
            metric_context,
            outcome='error',
            error_class='transport_before_output',
            phase='before_output',
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail='anthropic transport failure') from exc

    if response.status_code >= 400:
        attempt_trace.record(
            provider='anthropic',
            configured_model=route.primary.model,
            route_artifact_id=route.route_artifact_id,
            fallback_reason=None,
            retry_ordinal=1,
            outcome='error',
            error_class=_provider_status_error_class(response.status_code),
            usage_status=UsageStatus.INDETERMINATE,
        )
        schedule_attempt_trace(accounting_context, attempt_trace)
        _observe_message_terminal(
            metric_context,
            outcome='error',
            error_class=_provider_status_error_class(response.status_code),
            phase='before_output',
        )
        return JSONResponse(status_code=response.status_code, content=_response_json_or_error(response))

    try:
        response_body = response.json()
    except ValueError:
        attempt_trace.record(
            provider='anthropic',
            configured_model=route.primary.model,
            route_artifact_id=route.route_artifact_id,
            fallback_reason=None,
            retry_ordinal=1,
            outcome='error',
            error_class='invalid_provider_response',
            usage_status=UsageStatus.INDETERMINATE,
        )
        schedule_attempt_trace(accounting_context, attempt_trace)
        _observe_message_terminal(
            metric_context,
            outcome='error',
            error_class='invalid_provider_response',
            phase='before_output',
        )
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={'error': {'message': 'invalid anthropic response', 'type': 'api_error'}},
        )

    response_metadata = (
        anthropic_usage_from_response(
            response_body,
            cache_requested=cache_requested_for_anthropic_request(body),
            cache_write_ttl=cache_write_ttl_for_anthropic_request(body),
        )
        if isinstance(response_body, Mapping)
        else ProviderResponseMetadata()
    )
    attempt_trace.record(
        provider='anthropic',
        configured_model=route.primary.model,
        route_artifact_id=route.route_artifact_id,
        fallback_reason=None,
        retry_ordinal=1,
        outcome='success',
        error_class='none',
        metadata=response_metadata,
    )
    schedule_attempt_trace(accounting_context, attempt_trace)
    _observe_message_terminal(metric_context, outcome='success', error_class='none', phase='terminal')
    return JSONResponse(status_code=response.status_code, content=response_body)


@dataclass(frozen=True)
class _AnthropicMetricContext:
    started_at: float
    lane_id: str
    route_artifact_id: str
    provider: str
    model: str
    credential_source: str
    request_id: str


def _resolve_lane_route(config: GatewayConfig, model: object) -> RouteArtifact:
    if not isinstance(model, str) or not model.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='model is required')
    lane_id = model.strip()
    if not lane_id.startswith(AUTO_LANE_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'only auto lanes are supported on /v1/messages: {lane_id}',
        )
    lane = config.lanes.get(lane_id)
    if lane is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'auto lane not found: {lane_id}')
    if lane.surface != Surface.ANTHROPIC_MESSAGES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'lane {lane_id} is not an anthropic messages lane',
        )
    route = config.route_artifacts.get(lane.active_route)
    if route is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f'active route missing for lane: {lane_id}',
        )
    provider_ref = route.primary
    if provider_ref.provider != 'anthropic':
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'lane {lane_id} is not an anthropic messages lane',
        )
    return route


def _validate_anthropic_capabilities(route: RouteArtifact, body: Mapping[str, Any]) -> None:
    if body.get('stream') is True and not route.capabilities.streaming:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='lane does not support streaming')
    if body.get('tools') and not route.capabilities.tools:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='lane does not support tools')


def _resolve_anthropic_api_key(request: Request) -> str | None:
    forwarded = request.headers.get('x-omi-byok-anthropic-key', '').strip()
    if forwarded:
        return forwarded
    configured = os.getenv('ANTHROPIC_API_KEY', '').strip()
    return configured or None


def _anthropic_credential_source(request: Request) -> str:
    return 'service_forwarded_byok' if request.headers.get('x-omi-byok-anthropic-key', '').strip() else 'omi_managed'


def _anthropic_forward_headers(request: Request, *, api_key: str) -> dict[str, str]:
    headers = {
        'x-api-key': api_key,
        ANTHROPIC_VERSION_HEADER: request.headers.get(ANTHROPIC_VERSION_HEADER, DEFAULT_ANTHROPIC_VERSION),
        'Content-Type': 'application/json',
    }
    beta = request.headers.get(ANTHROPIC_BETA_HEADER, DEFAULT_ANTHROPIC_BETA)
    if beta:
        headers[ANTHROPIC_BETA_HEADER] = beta
    return headers


async def _streaming_anthropic_messages_response(
    body: Mapping[str, Any],
    *,
    headers: Mapping[str, str],
    metric_context: _AnthropicMetricContext,
    accounting_context: AccountingContext | None = None,
    attempt_trace: AttemptTrace | None = None,
) -> JSONResponse | StreamingResponse:
    """Open the upstream stream before committing HTTP status.

    Upstream 4xx/5xx must be returned as JSON with the real status so gateway
    clients can fall back. Yielding the error body under an already-committed
    HTTP 200 breaks transport-failure detection.
    """
    try:
        stream_cm = _get_anthropic_http_client().stream(
            'POST',
            f'{ANTHROPIC_MESSAGES_BASE_URL}/messages',
            json=dict(body),
            headers=dict(headers),
        )
        response = await stream_cm.__aenter__()
    except asyncio.CancelledError:
        if attempt_trace is not None:
            attempt_trace.record(
                provider=metric_context.provider,
                configured_model=metric_context.model,
                route_artifact_id=metric_context.route_artifact_id,
                fallback_reason=None,
                retry_ordinal=1,
                outcome='cancelled',
                error_class='client_cancelled',
                usage_status=UsageStatus.INDETERMINATE,
            )
        if accounting_context is not None and attempt_trace is not None:
            schedule_attempt_trace(accounting_context, attempt_trace)
        _observe_message_terminal(
            metric_context,
            outcome='cancelled',
            error_class='client_cancelled',
            phase='before_output',
            streaming=True,
        )
        raise
    except httpx.TimeoutException as exc:
        if attempt_trace is not None:
            attempt_trace.record(
                provider=metric_context.provider,
                configured_model=metric_context.model,
                route_artifact_id=metric_context.route_artifact_id,
                fallback_reason=None,
                retry_ordinal=1,
                outcome='error',
                error_class='timeout_before_output',
                usage_status=UsageStatus.INDETERMINATE,
            )
        if accounting_context is not None and attempt_trace is not None:
            schedule_attempt_trace(accounting_context, attempt_trace)
        _observe_message_terminal(
            metric_context,
            outcome='error',
            error_class='timeout_before_output',
            phase='before_output',
            streaming=True,
        )
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail='anthropic request timed out') from exc
    except httpx.HTTPError as exc:
        if attempt_trace is not None:
            attempt_trace.record(
                provider=metric_context.provider,
                configured_model=metric_context.model,
                route_artifact_id=metric_context.route_artifact_id,
                fallback_reason=None,
                retry_ordinal=1,
                outcome='error',
                error_class='transport_before_output',
                usage_status=UsageStatus.INDETERMINATE,
            )
        if accounting_context is not None and attempt_trace is not None:
            schedule_attempt_trace(accounting_context, attempt_trace)
        _observe_message_terminal(
            metric_context,
            outcome='error',
            error_class='transport_before_output',
            phase='before_output',
            streaming=True,
        )
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail='anthropic transport failure') from exc

    if response.status_code >= 400:
        try:
            error_bytes = await response.aread()
        finally:
            try:
                if attempt_trace is not None:
                    attempt_trace.record(
                        provider=metric_context.provider,
                        configured_model=metric_context.model,
                        route_artifact_id=metric_context.route_artifact_id,
                        fallback_reason=None,
                        retry_ordinal=1,
                        outcome='error',
                        error_class=_provider_status_error_class(response.status_code),
                        usage_status=UsageStatus.INDETERMINATE,
                    )
                if accounting_context is not None and attempt_trace is not None:
                    schedule_attempt_trace(accounting_context, attempt_trace)
                _observe_message_terminal(
                    metric_context,
                    outcome='error',
                    error_class=_provider_status_error_class(response.status_code),
                    phase='before_output',
                    streaming=True,
                )
            finally:
                await stream_cm.__aexit__(None, None, None)
        return JSONResponse(status_code=response.status_code, content=_bytes_json_or_error(error_bytes))

    return StreamingResponse(
        _iter_open_anthropic_stream(
            stream_cm,
            response,
            metric_context=metric_context,
            accounting_context=accounting_context,
            attempt_trace=attempt_trace,
            cache_requested=cache_requested_for_anthropic_request(body),
            cache_write_ttl=cache_write_ttl_for_anthropic_request(body),
        ),
        media_type='text/event-stream',
    )


async def _iter_open_anthropic_stream(
    stream_cm: Any,
    response: Any,
    *,
    metric_context: _AnthropicMetricContext,
    accounting_context: AccountingContext | None = None,
    attempt_trace: AttemptTrace | None = None,
    cache_requested: bool = False,
    cache_write_ttl: str | None = None,
) -> AsyncIterator[bytes]:
    terminal_observed = False
    terminal_marker_seen = False
    saw_output = False
    ttfb_seconds: float | None = None
    decoder = SSEEventDecoder()
    provider_usage: dict[str, Any] = {}
    provider_response_id: str | None = None
    actual_model_version: str | None = None

    async def observe_terminal(*, outcome: str, error_class: str, phase: str) -> None:
        nonlocal terminal_observed
        if terminal_observed:
            return
        terminal_observed = True
        provider_response: dict[str, Any] = {
            'id': provider_response_id,
            'model': actual_model_version,
            'usage': provider_usage,
        }
        usage_metadata = anthropic_usage_from_response(
            provider_response,
            cache_requested=cache_requested,
            cache_write_ttl=cache_write_ttl,
        )
        if attempt_trace is not None:
            attempt_trace.record(
                provider=metric_context.provider,
                configured_model=metric_context.model,
                route_artifact_id=metric_context.route_artifact_id,
                fallback_reason=None,
                retry_ordinal=1,
                outcome=outcome,
                error_class=error_class,
                metadata=usage_metadata,
                usage_status=(
                    UsageStatus.CONFIRMED
                    if usage_metadata.usage is not None
                    else UsageStatus.NOT_REPORTED if outcome == 'success' else UsageStatus.INDETERMINATE
                ),
            )
        if accounting_context is not None and attempt_trace is not None:
            schedule_attempt_trace(accounting_context, attempt_trace)
        _observe_message_terminal(
            metric_context,
            outcome=outcome,
            error_class=error_class,
            phase=phase,
            streaming=True,
            ttfb_seconds=ttfb_seconds,
        )

    try:
        async for chunk in response.aiter_bytes():
            if not chunk:
                continue
            if not saw_output:
                saw_output = True
                ttfb_seconds = time_request() - metric_context.started_at
            for event in decoder.feed(chunk):
                event_payload = _event_payload(event.data)
                if event.event == 'message_start' and event_payload is not None:
                    message = event_payload.get('message')
                    if isinstance(message, Mapping):
                        provider_response_id = _optional_string(message.get('id'))
                        actual_model_version = _optional_string(message.get('model'))
                        raw_usage = message.get('usage')
                        if isinstance(raw_usage, Mapping):
                            provider_usage.update(dict(raw_usage))
                elif event.event == 'message_delta' and event_payload is not None:
                    raw_usage = event_payload.get('usage')
                    if isinstance(raw_usage, Mapping):
                        provider_usage.update(dict(raw_usage))
                if event.event == 'message_stop':
                    terminal_marker_seen = True
                    await observe_terminal(outcome='success', error_class='none', phase='terminal_marker')
                elif event.event == 'error':
                    await observe_terminal(
                        outcome='error',
                        error_class='provider_error_event',
                        phase='midstream' if saw_output else 'before_output',
                    )
            yield chunk
    except httpx.TimeoutException:
        await observe_terminal(
            outcome='error',
            error_class='timeout_midstream' if saw_output else 'timeout_before_output',
            phase='midstream' if saw_output else 'before_output',
        )
        yield b'event: error\ndata: {"type":"error","error":{"type":"timeout_error"}}\n\n'
    except httpx.HTTPError:
        await observe_terminal(
            outcome='error',
            error_class='transport_midstream' if saw_output else 'transport_before_output',
            phase='midstream' if saw_output else 'before_output',
        )
        yield b'event: error\ndata: {"type":"error","error":{"type":"api_error"}}\n\n'
    except ValueError:
        await observe_terminal(outcome='error', error_class='invalid_sse_frame', phase='midstream')
        raise
    except asyncio.CancelledError:
        await observe_terminal(
            outcome='cancelled',
            error_class='client_cancelled',
            phase='midstream' if saw_output else 'before_output',
        )
        raise
    except Exception:
        await observe_terminal(
            outcome='error',
            error_class='unexpected_midstream' if saw_output else 'unexpected_before_output',
            phase='midstream' if saw_output else 'before_output',
        )
        raise
    else:
        if not terminal_marker_seen:
            await observe_terminal(
                outcome='error',
                error_class='eof_before_terminal_marker' if saw_output else 'empty_stream_before_output',
                phase='midstream' if saw_output else 'before_output',
            )
    finally:
        try:
            await stream_cm.__aexit__(None, None, None)
        finally:
            if not terminal_observed:
                await observe_terminal(
                    outcome='cancelled',
                    error_class='consumer_abandoned_stream',
                    phase='midstream' if saw_output else 'before_output',
                )


def _observe_message_terminal(
    context: _AnthropicMetricContext,
    *,
    outcome: str,
    error_class: str,
    phase: str,
    streaming: bool = False,
    ttfb_seconds: float | None = None,
) -> None:
    try:
        observe_route_result(
            context.started_at,
            lane_id=context.lane_id,
            route_artifact_id=context.route_artifact_id,
            provider=context.provider,
            model=context.model,
            credential_source=context.credential_source,
            used_lkg=False,
            fallback_used=False,
            fallback_reason=None,
            outcome=outcome,
            error_class=error_class,
            request_id=context.request_id,
            api_surface='anthropic_messages',
            streaming=streaming,
            phase=phase,
            ttfb_seconds=ttfb_seconds,
        )
    except Exception:
        report_observation_failure(api_surface='anthropic_messages', request_id=context.request_id)


def _provider_status_error_class(status_code: int) -> str:
    if status_code in {401, 403}:
        return 'provider_auth'
    if status_code == 429:
        return 'provider_rate_limit'
    if status_code >= 500:
        return 'provider_5xx'
    return 'provider_4xx'


def _observe_anthropic_request_rejection(request_id: str, error_class: str) -> None:
    try:
        observe_request_rejection(
            api_surface='anthropic_messages',
            error_class=error_class,
            request_id=request_id,
        )
    except Exception:
        report_observation_failure(api_surface='anthropic_messages', request_id=request_id)


def _response_json_or_error(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        return {'error': {'message': 'invalid anthropic response', 'type': 'api_error'}}


def _bytes_json_or_error(body: bytes) -> object:
    if not body:
        return {'error': {'message': 'anthropic request failed', 'type': 'api_error'}}
    try:
        return json.loads(body)
    except ValueError:
        return {'error': {'message': 'invalid anthropic response', 'type': 'api_error'}}


def _accounting_feature(caller: ServiceAuthDependency, *, fallback: str) -> str:
    """Feature attribution comes only from an authenticated, bounded header."""
    return caller.usage_feature or fallback


def _event_payload(data: str) -> dict[str, Any] | None:
    try:
        value = json.loads(data)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _get_anthropic_http_client() -> httpx.AsyncClient:
    global _anthropic_http_client
    if _anthropic_http_client is None:
        _anthropic_http_client = httpx.AsyncClient(timeout=120.0)
    return _anthropic_http_client


async def close_anthropic_messages_client() -> None:
    global _anthropic_http_client
    if _anthropic_http_client is not None:
        await _anthropic_http_client.aclose()
        _anthropic_http_client = None
