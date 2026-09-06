from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
import json
import re
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
import httpx
import os
from fastapi.responses import JSONResponse, StreamingResponse

from llm_gateway.gateway.accounting import (
    AccountingContext,
    AttemptTrace,
    ProviderResponseMetadata,
    UsageStatus,
    cache_requested_for_openai_request,
    encode_jit_gateway_receipt,
    image_usage,
    jit_gateway_receipt_for_trace,
    jit_gateway_receipt_sse_frame,
    openai_usage_from_sse_payload,
)
from llm_gateway.gateway.accounting_sink import schedule_attempt_trace
from llm_gateway.gateway.auth import ServiceAuthDependency
from llm_gateway.gateway.config_loader import GatewayConfig
from llm_gateway.gateway.credentials import (
    CredentialContext,
    build_byok_credential_context,
    build_omi_managed_credential_context,
    parse_forwarded_byok_headers,
)
from llm_gateway.gateway.errors import (
    GatewayError,
    GatewayErrorCode,
    GatewayInvalidRouteConfigError,
    GatewayInvalidRequestError,
)
from llm_gateway.gateway.executor import (
    ProviderRegistry,
    jit_reservation_units,
    reserve_jit_attempt,
    settle_jit_attempt,
    execute_chat_completion,
    _map_provider_failure,  # type: ignore[reportPrivateUsage]  # shared gateway failure mapper
    output_budget_for,
    provider_request_for,
    selected_serving_route,
    selected_serving_route_artifact_id,
    selected_route_is_lkg,
    selected_route_serving_class,
)
from llm_gateway.gateway.metrics import (
    observe_error,
    observe_request_rejection,
    observe_route_result,
    observe_success,
    report_observation_failure,
    time_request,
)
from llm_gateway.gateway.output_budget import OutputBudgetDecision, completion_size_bucket, output_budget_bucket
from llm_gateway.gateway.providers import ProviderFailure
from llm_gateway.gateway.jit_budget import JITAttemptReservation
from llm_gateway.gateway.request_context import JITBudgetHeaders, jit_budget_headers_for, request_id_for
from llm_gateway.gateway.resolver import ResolvedRoute, is_lkg_eligible, resolve_chat_completion_route
from llm_gateway.gateway.schemas import FailureClass, RouteArtifact, RouteServingClass
from llm_gateway.gateway.sse import SSEEvent, SSEEventDecoder
from llm_gateway.routers.dependencies import get_gateway_config, get_provider_registry

router = APIRouter()
_image_generation_client: httpx.AsyncClient | None = None

# The provider throttled the caller's own key. These reach the router as a
# credential failure, but they are not a bad credential: answering 401 tells
# callers the key is invalid and makes a transient failure look permanent.
_THROTTLED_FAILURE_CLASSES = frozenset({FailureClass.BYOK_RATE_LIMIT, FailureClass.BYOK_QUOTA})
# Keep CRLF atomic: without the atomic group, the regex engine can backtrack
# from ``\r\n`` to ``\r`` + ``\n`` and split a multi-line SSE event at its
# first line ending.
_SSE_FRAME_BOUNDARY = re.compile(br'(?>\r\n|\r|\n){2}')


@router.post('/v1/chat/completions', response_model=None)
async def create_chat_completion(
    request: Request,
    caller: ServiceAuthDependency,
    config: GatewayConfig = Depends(get_gateway_config),
    provider_registry: ProviderRegistry = Depends(get_provider_registry),
) -> JSONResponse | StreamingResponse:
    started_at = time_request()
    resolved_route = None
    credential_source = 'unknown'
    is_streaming = False
    request_id = request_id_for(request)
    accounting_context: AccountingContext | None = None
    attempt_trace = AttemptTrace()
    try:
        request_body = await _request_json(request)
        try:
            jit_budget = jit_budget_headers_for(request, owner_uid=caller.user_uid)
            if jit_budget is not None and not caller.user_uid:
                raise ValueError('JIT budget requires authenticated owner attribution')
        except ValueError as exc:
            raise GatewayInvalidRequestError(str(exc), param='x-omi-jit-contract-version') from exc
        if jit_budget is not None:
            _apply_jit_request_budget(request_body, jit_budget)
        resolved_route = resolve_chat_completion_route(config, request_body)
        credentials = _resolve_credentials(request, caller)
        credential_source = credentials.source.value
        accounting_context = _accounting_context(
            request_id=request_id,
            caller=caller,
            api_surface='openai_chat_completions',
            payer='byok' if credentials.mode.value == 'byok' else 'omi',
            fallback_feature=resolved_route.lane.lane_id,
            jit_budget=jit_budget,
        )
        is_streaming = resolved_route.validated_request.forwarded_params.get('stream') is True
        if is_streaming:
            return await _streaming_response(
                resolved_route,
                credentials,
                provider_registry,
                started_at=started_at,
                request_id=request_id,
                accounting_context=accounting_context,
                attempt_trace=attempt_trace,
                max_provider_attempts=jit_budget.max_attempts if jit_budget is not None else None,
                jit_max_spend_micro_usd=jit_budget.max_spend_micro_usd if jit_budget is not None else None,
                jit_owner_uid=jit_budget.owner_uid if jit_budget is not None else None,
                jit_run_id=jit_budget.run_id if jit_budget is not None else None,
                jit_contract_version=jit_budget.contract_version if jit_budget is not None else None,
            )
        result = await execute_chat_completion(
            resolved_route,
            credentials,
            provider_registry,
            attempt_trace=attempt_trace,
            max_provider_attempts=jit_budget.max_attempts if jit_budget is not None else None,
            jit_max_spend_micro_usd=jit_budget.max_spend_micro_usd if jit_budget is not None else None,
            jit_run_id=jit_budget.run_id if jit_budget is not None else None,
            jit_contract_version=jit_budget.contract_version if jit_budget is not None else None,
            jit_owner_uid=jit_budget.owner_uid if jit_budget is not None else None,
        )
        schedule_attempt_trace(accounting_context, attempt_trace)
        _safe_observe(
            lambda: observe_success(
                started_at,
                result,
                credential_source=credential_source,
                request_id=request_id,
                completion_size=completion_size_bucket(_completion_character_count(result.response)),
                finish_reason=_response_finish_reason(result.response),
            ),
            request_id=request_id,
            api_surface='openai_chat_completions',
        )
        return JSONResponse(content=result.response, headers=_jit_receipt_headers(accounting_context, attempt_trace))
    except asyncio.CancelledError:
        if accounting_context is not None:
            schedule_attempt_trace(accounting_context, attempt_trace)
        if resolved_route is not None:
            route = selected_serving_route(resolved_route)
            _safe_observe(
                lambda: observe_route_result(
                    started_at,
                    lane_id=resolved_route.lane.lane_id,
                    route_artifact_id=route.route_artifact_id,
                    provider='none',
                    model='none',
                    credential_source=credential_source,
                    route_serving_class=selected_route_serving_class(resolved_route),
                    used_lkg=selected_route_is_lkg(resolved_route),
                    fallback_used=False,
                    fallback_reason=None,
                    outcome='cancelled',
                    error_class='client_cancelled',
                    request_id=request_id,
                    api_surface='openai_chat_completions',
                    streaming=is_streaming,
                    phase='before_output',
                ),
                request_id=request_id,
                api_surface='openai_chat_completions',
            )
        raise
    except GatewayError as exc:
        if accounting_context is not None:
            schedule_attempt_trace(accounting_context, attempt_trace)
        if resolved_route is not None:
            _safe_observe(
                lambda: observe_error(
                    started_at,
                    lane_id=resolved_route.lane.lane_id,
                    route_artifact_id=selected_serving_route_artifact_id(resolved_route),
                    error=exc,
                    credential_source=credential_source,
                    request_id=request_id,
                    streaming=is_streaming,
                    used_lkg=selected_route_is_lkg(resolved_route),
                    route_serving_class=selected_route_serving_class(resolved_route),
                ),
                request_id=request_id,
                api_surface='openai_chat_completions',
            )
        else:
            _safe_observe(
                lambda: observe_request_rejection(
                    api_surface='openai_chat_completions',
                    error_class=exc.code.value,
                    request_id=request_id,
                ),
                request_id=request_id,
                api_surface='openai_chat_completions',
            )
        return _error_response(exc)
    except Exception:
        if accounting_context is not None:
            schedule_attempt_trace(accounting_context, attempt_trace)
        if resolved_route is not None:
            route = selected_serving_route(resolved_route)
            _safe_observe(
                lambda: observe_route_result(
                    started_at,
                    lane_id=resolved_route.lane.lane_id,
                    route_artifact_id=route.route_artifact_id,
                    provider='none',
                    model='none',
                    credential_source=credential_source,
                    route_serving_class=selected_route_serving_class(resolved_route),
                    used_lkg=selected_route_is_lkg(resolved_route),
                    fallback_used=False,
                    fallback_reason=None,
                    outcome='error',
                    error_class='unexpected_internal',
                    request_id=request_id,
                    api_surface='openai_chat_completions',
                    streaming=is_streaming,
                    phase='before_output',
                ),
                request_id=request_id,
                api_surface='openai_chat_completions',
            )
        else:
            _safe_observe(
                lambda: observe_request_rejection(
                    api_surface='openai_chat_completions',
                    error_class='unexpected_internal',
                    request_id=request_id,
                ),
                request_id=request_id,
                api_surface='openai_chat_completions',
            )
        raise


def _safe_observe(fn: Callable[[], None], *, request_id: str, api_surface: str) -> None:
    """Emit metrics without risking request-handling failures."""
    try:
        fn()
    except Exception:
        report_observation_failure(api_surface=api_surface, request_id=request_id)


async def _request_json(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except ValueError as exc:
        raise GatewayInvalidRequestError('request body must be valid JSON') from exc
    if not isinstance(body, dict):
        raise GatewayInvalidRequestError('request body must be an object')
    return cast(dict[str, Any], body)


def _resolve_credentials(request: Request, caller: ServiceAuthDependency) -> CredentialContext:
    forwarded = parse_forwarded_byok_headers(request.headers)
    if forwarded:
        return build_byok_credential_context(caller, forwarded)
    return build_omi_managed_credential_context(caller)


def _error_response(exc: GatewayError) -> JSONResponse:
    error: dict[str, object] = {
        'message': exc.message,
        'type': _error_type_for_code(exc.code, exc.failure_class),
        'param': exc.param,
        'code': exc.code.value,
    }
    if exc.failure_class is not None:
        # This is a bounded gateway-owned classifier, never an upstream body.
        # Backend composition boundaries need it to preserve intentional
        # credential policy without conflating distinct throttling failures.
        error['failure_class'] = exc.failure_class.value
    content: dict[str, object] = {'error': error}
    return JSONResponse(
        status_code=_status_code_for_error(exc),
        content=content,
    )


def _error_type_for_code(code: GatewayErrorCode, failure_class: FailureClass | None = None) -> str:
    """Map an internal error code to an OpenAI API error category.

    OpenAI distinguishes ``type`` (a broad error category) from ``code`` (the
    specific identifier). Without this distinction clients that categorize
    errors by ``type`` cannot classify them correctly.
    """
    if failure_class in _THROTTLED_FAILURE_CLASSES:
        return 'rate_limit_error'
    if code == GatewayErrorCode.CREDENTIAL_FAILURE:
        return 'authentication_error'
    if code in {
        GatewayErrorCode.INVALID_REQUEST,
        GatewayErrorCode.INVALID_ROUTE_CONFIG,
        GatewayErrorCode.UNSUPPORTED_MODEL,
        GatewayErrorCode.CAPABILITY_NOT_SUPPORTED,
        GatewayErrorCode.PROVIDER_REQUEST_REJECTED,
    }:
        return 'invalid_request_error'
    return 'api_error'


def _status_code_for_error(exc: GatewayError) -> int:
    if exc.failure_class in _THROTTLED_FAILURE_CLASSES:
        return 429
    if exc.code == GatewayErrorCode.MODEL_NOT_FOUND:
        return 404
    if exc.code in {
        GatewayErrorCode.INVALID_REQUEST,
        GatewayErrorCode.UNSUPPORTED_MODEL,
        GatewayErrorCode.CAPABILITY_NOT_SUPPORTED,
        GatewayErrorCode.PROVIDER_REQUEST_REJECTED,
    }:
        return 400
    if exc.code == GatewayErrorCode.CREDENTIAL_FAILURE:
        return 401
    if exc.code == GatewayErrorCode.INVALID_ROUTE_CONFIG:
        return 503
    if exc.code == GatewayErrorCode.PROVIDER_FAILURE:
        return 502
    return 500


@router.post('/v1/images/generations')
async def create_image_generation(request: Request, caller: ServiceAuthDependency):
    request_body = await _request_json(request)
    _normalize_image_request_defaults(request_body)
    request_id = request_id_for(request)
    context = _accounting_context(
        request_id=request_id,
        caller=caller,
        api_surface='openai_images_generations',
        payer='omi',
        fallback_feature='image_generation',
    )
    trace = AttemptTrace()
    api_key = os.getenv('OPENAI_API_KEY', '').strip()
    if not api_key:
        trace.record(
            provider='openai',
            configured_model=_string_request_value(request_body, 'model', default='unknown'),
            route_artifact_id=None,
            fallback_reason=None,
            retry_ordinal=1,
            outcome='error',
            error_class='invalid_config',
            usage_status=UsageStatus.INDETERMINATE,
        )
        schedule_attempt_trace(context, trace)
        return JSONResponse(
            status_code=503,
            content={'error': {'message': 'provider request failed: invalid_config', 'type': 'api_error'}},
        )
    try:
        response = await _get_image_generation_client().post(
            'https://api.openai.com/v1/images/generations',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json=request_body,
        )
        body = response.json()
        if response.status_code >= 400:
            trace.record(
                provider='openai',
                configured_model=_string_request_value(request_body, 'model', default='unknown'),
                route_artifact_id=None,
                fallback_reason=None,
                retry_ordinal=1,
                outcome='error',
                error_class=f'provider_http_{response.status_code}',
                usage_status=UsageStatus.INDETERMINATE,
            )
        else:
            trace.record(
                provider='openai',
                configured_model=_string_request_value(request_body, 'model', default='unknown'),
                route_artifact_id=None,
                fallback_reason=None,
                retry_ordinal=1,
                outcome='success',
                error_class='none',
                metadata=ProviderResponseMetadata(
                    usage=image_usage(
                        count=_int_request_value(request_body, 'n', default=1),
                        size=_string_request_value(request_body, 'size', default='auto'),
                        quality=_string_request_value(request_body, 'quality', default='auto'),
                    )
                ),
            )
        schedule_attempt_trace(context, trace)
        return JSONResponse(status_code=response.status_code, content=body)
    except (httpx.HTTPError, ValueError):
        trace.record(
            provider='openai',
            configured_model=_string_request_value(request_body, 'model', default='unknown'),
            route_artifact_id=None,
            fallback_reason=None,
            retry_ordinal=1,
            outcome='error',
            error_class='transport_or_invalid_response',
            usage_status=UsageStatus.INDETERMINATE,
        )
        schedule_attempt_trace(context, trace)
        return JSONResponse(
            status_code=502,
            content={'error': {'message': 'provider request failed', 'type': 'api_error'}},
        )


def _get_image_generation_client() -> httpx.AsyncClient:
    global _image_generation_client
    if _image_generation_client is None:
        _image_generation_client = httpx.AsyncClient(timeout=120.0)
    return _image_generation_client


async def close_image_generation_client() -> None:
    global _image_generation_client
    if _image_generation_client is not None:
        await _image_generation_client.aclose()
        _image_generation_client = None


async def _streaming_response(
    resolved_route: ResolvedRoute,
    credentials: CredentialContext,
    provider_registry: ProviderRegistry,
    *,
    started_at: float,
    request_id: str,
    accounting_context: AccountingContext,
    attempt_trace: AttemptTrace,
    max_provider_attempts: int | None = None,
    jit_max_spend_micro_usd: int | None = None,
    jit_owner_uid: str | None = None,
    jit_run_id: str | None = None,
    jit_contract_version: str | None = None,
) -> StreamingResponse:
    route = selected_serving_route(resolved_route)
    output_budget = output_budget_for(resolved_route, route)

    prepared = await _prepared_streaming_iterator(
        resolved_route,
        credentials,
        provider_registry,
        route,
        attempt_trace=attempt_trace,
        max_provider_attempts=max_provider_attempts,
        jit_max_spend_micro_usd=jit_max_spend_micro_usd,
        jit_owner_uid=jit_owner_uid,
        jit_run_id=jit_run_id,
        jit_contract_version=jit_contract_version,
    )
    async_iterator = _stream_with_terminal_metrics(
        prepared,
        resolved_route=resolved_route,
        credentials=credentials,
        route=route,
        started_at=started_at,
        request_id=request_id,
        output_budget=output_budget,
        accounting_context=accounting_context,
        attempt_trace=attempt_trace,
    )

    return StreamingResponse(async_iterator, media_type='text/event-stream')


@dataclass(frozen=True)
class _PreparedStream:
    first_chunk: bytes | None
    stream: AsyncIterator[bytes]
    provider: str
    model: str
    fallback_used: bool
    fallback_reason: str | None
    cache_requested: bool = False
    reservation: JITAttemptReservation | None = None


async def _prepared_streaming_iterator(
    resolved_route: ResolvedRoute,
    credentials: CredentialContext,
    provider_registry: ProviderRegistry,
    route: RouteArtifact,
    *,
    attempt_trace: AttemptTrace,
    max_provider_attempts: int | None = None,
    jit_max_spend_micro_usd: int | None = None,
    jit_owner_uid: str | None = None,
    jit_run_id: str | None = None,
    jit_contract_version: str | None = None,
) -> _PreparedStream:
    last_error: GatewayError | None = None
    first_failure: str | None = None
    for provider_ref in [route.primary, *route.fallbacks]:
        if max_provider_attempts is not None and len(attempt_trace.attempts) >= max_provider_attempts:
            raise GatewayInvalidRequestError('JIT provider attempt budget exhausted')
        reservation: JITAttemptReservation | None = None
        provider = provider_registry.provider_for(provider_ref.provider)
        if provider is None:
            raise GatewayInvalidRouteConfigError(f'provider is not supported for this route: {provider_ref.provider}')
        stream_chat_completion = getattr(provider, 'stream_chat_completion', None)
        if stream_chat_completion is None:
            continue
        provider_request = provider_request_for(resolved_route, provider_ref)
        _request_stream_usage(provider_request, provider_ref.provider)
        if jit_run_id is not None:
            try:
                units = jit_reservation_units(provider_request)
                reservation = await reserve_jit_attempt(
                    owner_uid=cast(str, jit_owner_uid),
                    run_id=jit_run_id,
                    contract_version=cast(str, jit_contract_version),
                    max_attempts=cast(int, max_provider_attempts),
                    max_spend_micro_usd=jit_max_spend_micro_usd or 50_000,
                    provider=provider_ref.provider,
                    model=provider_ref.model,
                    input_tokens=int(cast(int | str, units['input_tokens'])),
                    cached_input_tokens=int(cast(int | str, units['cached_input_tokens'])),
                    output_tokens=int(cast(int | str, units['output_tokens'])),
                    cache_write_tokens=int(cast(int | str, units['cache_write_tokens'])),
                    cache_ttl=cast(str | None, units['cache_ttl']),
                )
            except ValueError as exc:
                raise GatewayInvalidRequestError(str(exc)) from exc
            except Exception as exc:
                raise GatewayInvalidRequestError('JIT budget authority unavailable') from exc
            if reservation is None:
                raise GatewayInvalidRequestError('JIT provider attempt budget exhausted')
        stream = stream_chat_completion(
            provider_request,
            provider_ref=provider_ref,
            credentials=credentials,
            timeout_ms=route.timeouts.request_ms,
        )
        try:
            while True:
                first_chunk = await anext(stream)
                if first_chunk:
                    break
        except StopAsyncIteration:
            await settle_jit_attempt(
                reservation,
                provider=provider_ref.provider,
                model=provider_ref.model,
                metadata=None,
                status='failed',
            )
            return _PreparedStream(
                first_chunk=None,
                stream=stream,
                provider=provider_ref.provider,
                model=provider_ref.model,
                fallback_used=first_failure is not None,
                fallback_reason=first_failure,
                cache_requested=cache_requested_for_openai_request(provider_request),
            )
        except ProviderFailure as exc:
            await settle_jit_attempt(
                reservation,
                provider=provider_ref.provider,
                model=provider_ref.model,
                metadata=None,
                status='failed',
            )
            last_error = _map_provider_failure(exc, credentials, provider_ref)
            attempt_trace.record(
                provider=provider_ref.provider,
                configured_model=provider_ref.model,
                route_artifact_id=route.route_artifact_id,
                fallback_reason=first_failure,
                retry_ordinal=1,
                outcome='error',
                error_class=exc.failure_class.value,
                usage_status=UsageStatus.INDETERMINATE,
            )
            first_failure = first_failure or exc.failure_class.value
            if jit_run_id is not None:
                # A provider failure has unknown usage.  The reservation
                # authority blocks this run, so do not attempt a fallback that
                # would immediately spend around the blocked reservation.
                raise last_error
            if not is_lkg_eligible(route, exc.failure_class):
                raise last_error
            continue
        return _PreparedStream(
            first_chunk=first_chunk,
            stream=stream,
            provider=provider_ref.provider,
            model=provider_ref.model,
            fallback_used=first_failure is not None,
            fallback_reason=first_failure,
            cache_requested=cache_requested_for_openai_request(provider_request),
            reservation=reservation,
        )
    if last_error is not None:
        raise last_error
    raise GatewayInvalidRequestError('streaming provider adapter is not configured', param='stream')


async def _stream_with_terminal_metrics(
    prepared: _PreparedStream,
    *,
    resolved_route: ResolvedRoute,
    credentials: CredentialContext,
    route: RouteArtifact,
    started_at: float,
    request_id: str,
    output_budget: OutputBudgetDecision | None = None,
    accounting_context: AccountingContext | None = None,
    attempt_trace: AttemptTrace | None = None,
) -> AsyncIterator[bytes]:
    trace = attempt_trace or AttemptTrace()
    terminal_observed = False
    saw_output = prepared.first_chunk is not None
    terminal_marker_seen = False
    decoder = SSEEventDecoder()
    ttfb_seconds = time_request() - started_at if saw_output else None
    completion_characters = 0
    finish_reason = 'unknown'
    usage_metadata: ProviderResponseMetadata | None = None
    passthrough_buffer = b''
    terminal_settlement_ok = True
    output_budget = output_budget or OutputBudgetDecision(source='none', max_completion_tokens=None)

    async def observe_terminal(*, outcome: str, error_class: str, phase: str) -> bool:
        nonlocal terminal_observed, terminal_settlement_ok
        if terminal_observed:
            return terminal_settlement_ok
        terminal_observed = True
        settlement_ok = await settle_jit_attempt(
            prepared.reservation,
            provider=prepared.provider,
            model=prepared.model,
            metadata=usage_metadata if outcome == 'success' else None,
            status='succeeded' if outcome == 'success' else ('cancelled' if outcome == 'cancelled' else 'failed'),
        )
        terminal_settlement_ok = settlement_ok
        if outcome == 'success' and not settlement_ok:
            # The provider bytes may already be visible to the caller, but a
            # successful JIT receipt is only valid after durable settlement.
            outcome = 'error'
            error_class = 'jit_budget_settlement_failed'
            # Keep provider-observed usage for diagnostics and reconciliation;
            # the failed settlement still suppresses the success receipt below.
            usage_for_trace = usage_metadata
        else:
            # A provider may report usage or a response ID before an error or
            # client cancellation. Preserve those diagnostics, but mark their
            # completeness and cost as indeterminate below.
            usage_for_trace = usage_metadata
        # Per the PR behavioral contract, actual fallback requires a subsequent
        # successful provider/route.  Only stamp the actual-fallback labels when
        # the terminal outcome is success; an error or cancellation means the
        # failover did not complete, so dashboards and ad-hoc queries must not
        # count it as a completed failover.
        completed_fallback = prepared.fallback_used and outcome == 'success'
        trace.record(
            provider=prepared.provider,
            configured_model=prepared.model,
            route_artifact_id=route.route_artifact_id,
            fallback_reason=prepared.fallback_reason if completed_fallback else None,
            retry_ordinal=1,
            outcome=outcome,
            error_class=error_class,
            metadata=usage_for_trace,
            usage_status=(
                UsageStatus.CONFIRMED
                if outcome == 'success' and usage_for_trace is not None and usage_for_trace.usage is not None
                else UsageStatus.NOT_REPORTED if outcome == 'success' else UsageStatus.INDETERMINATE
            ),
        )
        if accounting_context is not None:
            schedule_attempt_trace(accounting_context, trace)
        _safe_observe(
            lambda: observe_route_result(
                started_at,
                lane_id=resolved_route.lane.lane_id,
                route_artifact_id=route.route_artifact_id,
                provider=prepared.provider,
                model=prepared.model,
                credential_source=credentials.source.value,
                route_serving_class=(
                    RouteServingClass.ACTUAL_FALLBACK
                    if completed_fallback
                    else selected_route_serving_class(resolved_route)
                ),
                used_lkg=selected_route_is_lkg(resolved_route),
                fallback_used=completed_fallback,
                fallback_reason=prepared.fallback_reason if completed_fallback else None,
                fallback_from_route_artifact_id=route.route_artifact_id if completed_fallback else None,
                fallback_to_route_artifact_id=route.route_artifact_id if completed_fallback else None,
                outcome=outcome,
                error_class=error_class,
                request_id=request_id,
                api_surface='openai_chat_completions',
                streaming=True,
                phase=phase,
                ttfb_seconds=ttfb_seconds,
                budget_source=output_budget.source,
                output_budget=output_budget_bucket(output_budget.max_completion_tokens),
                completion_size=completion_size_bucket(completion_characters),
                finish_reason=finish_reason,
            ),
            request_id=request_id,
            api_surface='openai_chat_completions',
        )
        return settlement_ok

    async def handle_events(frame_events: list[SSEEvent]) -> bool:
        nonlocal completion_characters, finish_reason, terminal_marker_seen, usage_metadata
        done_seen = False
        for event in frame_events:
            # SSEEvent is intentionally kept behind the decoder interface; the
            # runtime only relies on its stable data attribute here.
            data = event.data
            if data.strip() == '[DONE]':
                terminal_marker_seen = True
                done_seen = True
                await observe_terminal(outcome='success', error_class='none', phase='terminal_marker')
                continue
            payload = _stream_payload(data)
            if payload is not None:
                observed_usage = openai_usage_from_sse_payload(
                    payload,
                    cache_requested=prepared.cache_requested,
                )
                if observed_usage is not None:
                    usage_metadata = observed_usage
            completion_characters += _stream_completion_character_count(data)
            observed_finish_reason = _stream_finish_reason(data)
            if observed_finish_reason is not None:
                finish_reason = observed_finish_reason
        return done_seen

    async def process_jit_frame(raw_frame: bytes, *, force_boundary: bool = False) -> list[bytes]:
        normalized = raw_frame.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        if force_boundary and not normalized.endswith(b'\n\n'):
            normalized += b'\n\n'
        done_seen = await handle_events(decoder.feed(normalized))
        emitted: list[bytes] = []
        if done_seen and terminal_settlement_ok:
            receipt = (
                jit_gateway_receipt_for_trace(accounting_context, trace) if accounting_context is not None else None
            )
            if receipt is not None:
                emitted.append(jit_gateway_receipt_sse_frame(receipt))
        emitted.append(raw_frame)
        return emitted

    async def inspect_chunk(chunk: bytes) -> list[bytes]:
        nonlocal passthrough_buffer
        # Non-JIT callers must receive provider bytes unchanged.  The decoder
        # observes a copy of each chunk only for metrics and terminal state.
        if accounting_context is None or accounting_context.jit_run_id is None:
            await handle_events(decoder.feed(chunk))
            return [chunk]

        emitted: list[bytes] = []
        passthrough_buffer += chunk
        if len(passthrough_buffer) > 1024 * 1024:
            raise ValueError('SSE frame exceeds bounded decoder buffer')
        while True:
            boundary = _SSE_FRAME_BOUNDARY.search(passthrough_buffer)
            if boundary is None:
                break
            end = boundary.end()
            raw_frame = passthrough_buffer[:end]
            passthrough_buffer = passthrough_buffer[end:]
            emitted.extend(await process_jit_frame(raw_frame))
        return emitted

    if prepared.first_chunk is None:
        await observe_terminal(outcome='error', error_class='empty_stream_before_output', phase='before_output')
        return

    try:
        for emitted in await inspect_chunk(prepared.first_chunk):
            yield emitted
        async for chunk in prepared.stream:
            if chunk:
                for emitted in await inspect_chunk(chunk):
                    yield emitted
    except asyncio.CancelledError:
        await observe_terminal(
            outcome='cancelled',
            error_class='client_cancelled',
            phase='midstream' if saw_output else 'before_output',
        )
        raise
    except ProviderFailure as exc:
        await observe_terminal(
            outcome='error',
            error_class=f'{exc.failure_class.value}_midstream',
            phase='midstream',
        )
        raise
    except ValueError:
        await observe_terminal(outcome='error', error_class='invalid_sse_frame', phase='midstream')
        raise
    except Exception:
        await observe_terminal(outcome='error', error_class='transport_midstream', phase='midstream')
        raise
    else:
        if passthrough_buffer:
            # A provider may close after a valid data line without the usual
            # blank-line delimiter.  Inspect a synthetic delimiter while
            # yielding the original residual bytes unchanged.
            residual = passthrough_buffer
            passthrough_buffer = b''
            if accounting_context is not None and accounting_context.jit_run_id is not None:
                for emitted in await process_jit_frame(residual, force_boundary=True):
                    yield emitted
            else:
                await handle_events(decoder.feed(residual + b'\n\n'))
        if not terminal_marker_seen:
            await observe_terminal(outcome='error', error_class='eof_before_terminal_marker', phase='midstream')
    finally:
        if not terminal_observed:
            await observe_terminal(
                outcome='cancelled',
                error_class='consumer_abandoned_stream',
                phase='midstream' if saw_output else 'before_output',
            )


def _accounting_context(
    *,
    request_id: str,
    caller: ServiceAuthDependency,
    api_surface: str,
    payer: str,
    fallback_feature: str,
    jit_budget: JITBudgetHeaders | None = None,
) -> AccountingContext:
    feature = caller.usage_feature or fallback_feature
    return AccountingContext.create(
        request_id=request_id,
        caller=caller.name,
        user_uid=caller.user_uid,
        feature=feature.strip(),
        api_surface=api_surface,
        payer=payer,
        app_platform=caller.app_platform,
        jit_run_id=jit_budget.run_id if jit_budget is not None else None,
        jit_contract_version=jit_budget.contract_version if jit_budget is not None else None,
    )


def _jit_receipt_headers(context: AccountingContext, trace: AttemptTrace) -> dict[str, str]:
    """Return a receipt only for the explicit QA capability."""
    receipt = jit_gateway_receipt_for_trace(context, trace)
    if receipt is None:
        return {}
    return {'x-omi-jit-gateway-receipt': encode_jit_gateway_receipt(receipt)}


def _apply_jit_request_budget(request_body: dict[str, Any], budget: JITBudgetHeaders) -> None:
    """Apply a qualification-only output cap and conservative input preflight."""
    if _contains_jit_unsupported_modality(request_body):
        raise GatewayInvalidRequestError(
            'JIT qualification currently accepts text-only provider inputs',
            param='messages',
        )
    # A character-count heuristic underestimates non-ASCII text and ignores
    # tool/system fields. UTF-8 bytes are a conservative tokenizer-independent
    # upper bound (every token consumes at least one byte), so the QA gate
    # fails closed before a provider attempt rather than guessing low.
    estimated_input_tokens = len(json.dumps(request_body, separators=(',', ':'), ensure_ascii=False).encode('utf-8'))
    if estimated_input_tokens > budget.max_input_tokens:
        raise GatewayInvalidRequestError('JIT input budget exceeded', param='messages')
    has_output_limit = False
    for key in ('max_tokens', 'max_completion_tokens'):
        if key not in request_body or request_body[key] is None:
            # OpenAI treats the two fields as aliases.  Remove explicit nulls so
            # they cannot suppress the qualification ceiling or reach a
            # provider that coerces null unexpectedly.
            request_body.pop(key, None)
            continue
        value = request_body[key]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise GatewayInvalidRequestError('invalid JIT output token budget', param=key)
        request_body[key] = min(value, budget.max_output_tokens)
        has_output_limit = True
    if not has_output_limit:
        request_body['max_completion_tokens'] = budget.max_output_tokens


def _contains_jit_unsupported_modality(value: object) -> bool:
    """Reject image/audio payloads whose billable input envelope is not tokenized here."""
    if isinstance(value, Mapping):
        if value.get('type') in {'image_url', 'image', 'input_audio', 'audio'}:
            return True
        return any(_contains_jit_unsupported_modality(child) for child in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_jit_unsupported_modality(child) for child in value)
    return False


def _request_stream_usage(request: dict[str, Any], provider: str) -> None:
    """Request terminal usage from OpenAI-compatible providers at the gateway boundary."""
    if provider.strip().lower() not in {'openai', 'openrouter', 'perplexity'}:
        return
    existing = request.get('stream_options')
    options = dict(existing) if isinstance(existing, dict) else {}
    options['include_usage'] = True
    request['stream_options'] = options


def _string_request_value(request_body: dict[str, Any], key: str, *, default: str) -> str:
    value = request_body.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else default


def _int_request_value(request_body: dict[str, Any], key: str, *, default: int) -> int:
    value = request_body.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else default


def _normalize_image_request_defaults(request_body: dict[str, Any]) -> None:
    """Make documented image API defaults explicit for request and accounting parity."""
    request_body.setdefault('size', 'auto')
    request_body.setdefault('quality', 'auto')


def _completion_character_count(response: dict[str, Any]) -> int:
    choices = response.get('choices')
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return 0
    message = choices[0].get('message')
    if not isinstance(message, dict):
        return 0
    content = message.get('content')
    return len(content) if isinstance(content, str) else 0


def _response_finish_reason(response: dict[str, Any]) -> str:
    choices = response.get('choices')
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return 'unknown'
    return _normalize_finish_reason(choices[0].get('finish_reason'))


def _stream_completion_character_count(data: str) -> int:
    payload = _stream_payload(data)
    if payload is None:
        return 0
    choices = payload.get('choices')
    if not isinstance(choices, list):
        return 0
    character_count = 0
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        for field in ('delta', 'message'):
            value = choice.get(field)
            if isinstance(value, dict) and isinstance(value.get('content'), str):
                character_count += len(value['content'])
    return character_count


def _stream_finish_reason(data: str) -> str | None:
    payload = _stream_payload(data)
    if payload is None:
        return None
    choices = payload.get('choices')
    if not isinstance(choices, list):
        return None
    for choice in choices:
        if isinstance(choice, dict) and choice.get('finish_reason') is not None:
            return _normalize_finish_reason(choice.get('finish_reason'))
    return None


def _stream_payload(data: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(data)
    except (TypeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _normalize_finish_reason(value: object) -> str:
    normalized = str(value or '').strip().lower()
    if normalized in {'stop', 'length', 'content_filter', 'tool_calls'}:
        return normalized
    return 'unknown'
