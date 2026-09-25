"""Decision-model surface for the LLM gateway (OpenRouter systemone, #14835).

One lane, ``omi:auto:jev-decisions``, pinned to one Jev version. The request is
``{"model": <lane>, "state": str, "questions": {...}}`` and the response is the
provider's typed answer body, passed through unchanged. The gateway owns the
OpenRouter credential, accounting, and metrics; backend callers never hold it.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from llm_gateway.gateway.accounting import AccountingContext, AttemptTrace
from llm_gateway.gateway.accounting_sink import schedule_attempt_trace
from llm_gateway.gateway.auth import ServiceAuthDependency
from llm_gateway.gateway.config_loader import GatewayConfig
from llm_gateway.gateway.errors import GatewayError
from llm_gateway.gateway.executor import ProviderRegistry, execute_systemone
from llm_gateway.gateway.metrics import (
    observe_error,
    observe_request_rejection,
    observe_route_result,
    report_observation_failure,
    time_request,
)
from llm_gateway.gateway.request_context import request_id_for
from llm_gateway.gateway.resolver import ResolvedSystemOneRoute, resolve_systemone_route
from llm_gateway.gateway.schemas import RouteServingClass
from llm_gateway.routers.dependencies import get_gateway_config, get_provider_registry
from llm_gateway.routers.openai_compatible import (
    _accounting_context,  # pyright: ignore[reportPrivateUsage]
    _error_response,  # pyright: ignore[reportPrivateUsage]
    _request_json,  # pyright: ignore[reportPrivateUsage]
    _resolve_credentials,  # pyright: ignore[reportPrivateUsage]
)

router = APIRouter()

API_SURFACE = 'openrouter_systemone'


@router.post('/v1/systemone', response_model=None)
async def create_systemone(
    request: Request,
    caller: ServiceAuthDependency,
    config: GatewayConfig = Depends(get_gateway_config),
    provider_registry: ProviderRegistry = Depends(get_provider_registry),
) -> JSONResponse:
    started_at = time_request()
    resolved: ResolvedSystemOneRoute | None = None
    credential_source = 'unknown'
    request_id = request_id_for(request)
    accounting_context: AccountingContext | None = None
    attempt_trace = AttemptTrace()
    try:
        request_body = await _request_json(request)
        resolved = resolve_systemone_route(config, request_body)
        credentials = _resolve_credentials(request, caller)
        credential_source = credentials.source.value
        accounting_context = _accounting_context(
            request_id=request_id,
            caller=caller,
            api_surface=API_SURFACE,
            payer='byok' if credentials.mode.value == 'byok' else 'omi',
            fallback_feature=resolved.lane.lane_id,
        )
        response = await execute_systemone(
            resolved,
            credentials,
            provider_registry,
            attempt_trace=attempt_trace,
        )
        schedule_attempt_trace(accounting_context, attempt_trace)
        _safe_observe(
            lambda: observe_route_result(
                started_at,
                lane_id=resolved.lane.lane_id,
                route_artifact_id=resolved.route.route_artifact_id,
                provider=resolved.route.primary.provider,
                model=resolved.route.primary.model,
                credential_source=credential_source,
                used_lkg=False,
                fallback_used=False,
                fallback_reason=None,
                outcome='success',
                error_class='none',
                request_id=request_id,
                api_surface=API_SURFACE,
                streaming=False,
                phase='terminal',
            ),
            request_id=request_id,
        )
        return JSONResponse(content=response)
    except GatewayError as exc:
        if accounting_context is not None:
            schedule_attempt_trace(accounting_context, attempt_trace)
        if resolved is not None:
            _safe_observe(
                lambda: observe_error(
                    started_at,
                    lane_id=resolved.lane.lane_id,
                    route_artifact_id=resolved.route.route_artifact_id,
                    error=exc,
                    credential_source=credential_source,
                    request_id=request_id,
                    api_surface=API_SURFACE,
                    route_serving_class=RouteServingClass.ACTIVE,
                ),
                request_id=request_id,
            )
        else:
            _safe_observe(
                lambda: observe_request_rejection(
                    api_surface=API_SURFACE,
                    error_class=exc.code.value,
                    request_id=request_id,
                ),
                request_id=request_id,
            )
        return _error_response(exc)
    except Exception:
        if accounting_context is not None:
            schedule_attempt_trace(accounting_context, attempt_trace)
        _safe_observe(
            lambda: observe_request_rejection(
                api_surface=API_SURFACE,
                error_class='unexpected_internal',
                request_id=request_id,
            ),
            request_id=request_id,
        )
        raise


def _safe_observe(fn: Any, *, request_id: str) -> None:
    """Emit metrics without risking request-handling failures."""
    try:
        fn()
    except Exception:
        report_observation_failure(api_surface=API_SURFACE, request_id=request_id)
