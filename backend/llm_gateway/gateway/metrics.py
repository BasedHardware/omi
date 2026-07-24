from __future__ import annotations

import logging
import threading
import time
from typing import Protocol

from prometheus_client import Counter, Histogram

from llm_gateway.gateway.accounting import AccountingEvent
from llm_gateway.gateway.errors import GatewayError
from llm_gateway.gateway.output_budget import OutputBudgetDecision, output_budget_bucket
from llm_gateway.gateway.schemas import FailureClass, ProviderRejection

logger = logging.getLogger(__name__)

_OBSERVATION_WARNING_INTERVAL_SECONDS = 60.0
_observation_warning_lock = threading.Lock()
_last_observation_warning_at = 0.0

_REQUEST_LABELS = [
    'lane_id',
    'route_artifact_id',
    'provider',
    'model',
    'credential_source',
    'api_surface',
    'streaming',
    'phase',
    'used_lkg',
    'fallback_used',
    'fallback_reason',
    'outcome',
    'error_class',
    'provider_rejection',
    'budget_source',
    'output_budget',
    'completion_size',
    'finish_reason',
]

REQUEST_LATENCY_SECONDS = Histogram(
    'llm_gateway_request_latency_seconds',
    'LLM gateway request latency by route selection and terminal outcome',
    _REQUEST_LABELS,
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 40, 60, 120, 180, 300),
)

REQUESTS_TOTAL = Counter(
    'llm_gateway_requests_total',
    'LLM gateway requests by route selection and terminal outcome',
    _REQUEST_LABELS,
)

AUTH_REJECTIONS_TOTAL = Counter(
    'llm_gateway_auth_rejections_total',
    'LLM gateway service-auth rejections by bounded reason',
    ['reason'],
)

REQUEST_REJECTIONS_TOTAL = Counter(
    'llm_gateway_request_rejections_total',
    'LLM gateway request rejections before a route is selected',
    ['api_surface', 'error_class'],
)

STREAM_TTFB_SECONDS = Histogram(
    'llm_gateway_stream_ttfb_seconds',
    'Time to first non-empty stream chunk by bounded API surface, provider, and credential source',
    ['api_surface', 'provider', 'credential_source'],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 40, 60, 120),
)

ACCOUNTING_EVENTS_TOTAL = Counter(
    'llm_gateway_accounting_events_total',
    'LLM gateway accounting-event delivery by bounded provider and accounting state',
    ['api_surface', 'provider', 'payer', 'usage_status', 'cost_status', 'delivery'],
)


class ExecutorResultLike(Protocol):
    @property
    def lane_id(self) -> str: ...

    @property
    def selected_route_artifact_id(self) -> str: ...

    @property
    def selected_provider(self) -> str: ...

    @property
    def selected_model(self) -> str: ...

    @property
    def fallback_used(self) -> bool: ...

    @property
    def fallback_reason(self) -> FailureClass | None: ...

    @property
    def used_lkg(self) -> bool: ...

    @property
    def output_budget(self) -> OutputBudgetDecision: ...


def observe_success(
    started_at: float,
    result: ExecutorResultLike,
    *,
    credential_source: str,
    request_id: str,
    api_surface: str = 'openai_chat_completions',
    completion_size: str = 'unknown',
    finish_reason: str = 'unknown',
) -> None:
    observe_route_result(
        started_at,
        lane_id=result.lane_id,
        route_artifact_id=result.selected_route_artifact_id,
        provider=result.selected_provider,
        model=result.selected_model,
        credential_source=credential_source,
        used_lkg=result.used_lkg,
        fallback_used=result.fallback_used,
        fallback_reason=result.fallback_reason,
        outcome='success',
        error_class='none',
        request_id=request_id,
        api_surface=api_surface,
        streaming=False,
        phase='terminal',
        budget_source=result.output_budget.source,
        output_budget=output_budget_bucket(result.output_budget.max_completion_tokens),
        completion_size=completion_size,
        finish_reason=finish_reason,
    )


def observe_error(
    started_at: float,
    *,
    lane_id: str,
    route_artifact_id: str,
    error: GatewayError,
    credential_source: str,
    request_id: str,
    api_surface: str = 'openai_chat_completions',
    streaming: bool = False,
) -> None:
    observe_route_result(
        started_at,
        lane_id=lane_id,
        route_artifact_id=route_artifact_id,
        provider=error.provider,
        model=error.model,
        credential_source=credential_source,
        used_lkg=False,
        fallback_used=False,
        fallback_reason=error.failure_class,
        outcome='error',
        error_class=error.code.value,
        provider_rejection=error.provider_rejection,
        request_id=request_id,
        api_surface=api_surface,
        streaming=streaming,
        phase='before_output',
    )


def observe_route_result(
    started_at: float,
    *,
    lane_id: str,
    route_artifact_id: str,
    provider: str,
    model: str,
    credential_source: str,
    used_lkg: bool,
    fallback_used: bool,
    fallback_reason: FailureClass | str | None,
    outcome: str,
    error_class: str,
    request_id: str,
    api_surface: str,
    streaming: bool,
    phase: str,
    provider_rejection: ProviderRejection | str = ProviderRejection.NONE,
    ttfb_seconds: float | None = None,
    budget_source: str = 'none',
    output_budget: str = 'none',
    completion_size: str = 'unknown',
    finish_reason: str = 'unknown',
) -> None:
    labels = {
        'lane_id': _bounded(lane_id),
        'route_artifact_id': _bounded(route_artifact_id),
        'provider': _bounded(provider),
        'model': _bounded(model),
        'credential_source': _bounded(credential_source),
        'api_surface': _bounded(api_surface),
        'streaming': _bool_label(streaming),
        'phase': _bounded(phase),
        'used_lkg': _bool_label(used_lkg),
        'fallback_used': _bool_label(fallback_used),
        'fallback_reason': _enum_label(fallback_reason, default='none'),
        'outcome': _bounded(outcome),
        'error_class': _bounded(error_class),
        'provider_rejection': _provider_rejection_label(provider_rejection),
        'budget_source': _budget_source_label(budget_source),
        'output_budget': _output_budget_label(output_budget),
        'completion_size': _completion_size_label(completion_size),
        'finish_reason': _finish_reason_label(finish_reason),
    }
    REQUESTS_TOTAL.labels(**labels).inc()
    REQUEST_LATENCY_SECONDS.labels(**labels).observe(time.monotonic() - started_at)
    if streaming and ttfb_seconds is not None:
        STREAM_TTFB_SECONDS.labels(
            api_surface=labels['api_surface'],
            provider=labels['provider'],
            credential_source=labels['credential_source'],
        ).observe(ttfb_seconds)
    terminal_log = logger.warning if outcome == 'error' else logger.info
    terminal_log(
        'llm_gateway_terminal request_id=%s surface=%s streaming=%s phase=%s lane=%s route=%s provider=%s '
        'model=%s credential_source=%s outcome=%s error_class=%s failure_class=%s fallback_used=%s '
        'provider_rejection=%s '
        'budget_source=%s output_budget=%s completion_size=%s finish_reason=%s ttfb_seconds=%s',
        request_id,
        _bounded(api_surface),
        _bool_label(streaming),
        _bounded(phase),
        labels['lane_id'],
        labels['route_artifact_id'],
        labels['provider'],
        labels['model'],
        labels['credential_source'],
        labels['outcome'],
        labels['error_class'],
        labels['fallback_reason'],
        labels['fallback_used'],
        labels['provider_rejection'],
        labels['budget_source'],
        labels['output_budget'],
        labels['completion_size'],
        labels['finish_reason'],
        f'{ttfb_seconds:.6f}' if ttfb_seconds is not None else 'none',
    )


def observe_auth_rejection(reason: str) -> None:
    AUTH_REJECTIONS_TOTAL.labels(reason=_bounded(reason)).inc()


def observe_request_rejection(*, api_surface: str, error_class: str, request_id: str) -> None:
    surface_label = _bounded(api_surface)
    error_label = _bounded(error_class)
    REQUEST_REJECTIONS_TOTAL.labels(api_surface=surface_label, error_class=error_label).inc()
    logger.warning(
        'llm_gateway_request_rejected request_id=%s surface=%s error_class=%s',
        request_id,
        surface_label,
        error_label,
    )


def observe_accounting_event(event: AccountingEvent, *, delivery: str) -> None:
    """Observe accounting delivery without user, request, or model labels."""
    delivery_label = delivery if delivery in {'written', 'duplicate', 'failed', 'dropped'} else 'unknown'
    ACCOUNTING_EVENTS_TOTAL.labels(
        api_surface=_bounded(event.api_surface),
        provider=_bounded(event.provider),
        payer=_bounded(event.payer),
        usage_status=_bounded(event.usage_status.value),
        cost_status=_bounded(event.cost_status.value),
        delivery=delivery_label,
    ).inc()


def report_observation_failure(*, api_surface: str, request_id: str) -> None:
    """Rate-limit a payload-free warning when best-effort telemetry itself fails."""
    global _last_observation_warning_at
    now = time.monotonic()
    with _observation_warning_lock:
        if now - _last_observation_warning_at < _OBSERVATION_WARNING_INTERVAL_SECONDS:
            return
        _last_observation_warning_at = now
    try:
        logger.warning(
            'llm_gateway_observation_failed request_id=%s surface=%s',
            request_id,
            _bounded(api_surface),
        )
    except Exception:
        return


def time_request() -> float:
    return time.monotonic()


def _enum_label(value: object, *, default: str = 'unknown') -> str:
    raw_value = getattr(value, 'value', value)
    if raw_value is None:
        return default
    return _bounded(str(raw_value))


def _provider_rejection_label(value: object) -> str:
    raw_value = getattr(value, 'value', value)
    try:
        return ProviderRejection(str(raw_value)).value
    except ValueError:
        return ProviderRejection.OTHER_4XX.value


def _bounded(value: str) -> str:
    normalized = value.strip().lower().replace(' ', '_')
    return normalized[:128] if normalized else 'unknown'


def _budget_source_label(value: str) -> str:
    return value if value in {'none', 'caller', 'route_default'} else 'unknown'


def _output_budget_label(value: str) -> str:
    return (
        value
        if value
        in {'none', 'le_64', 'le_128', 'le_256', 'le_512', 'le_1024', 'le_2048', 'le_4096', 'le_8192', 'gt_8192'}
        else 'unknown'
    )


def _completion_size_label(value: str) -> str:
    return value if value in {'unknown', 'le_64', 'le_256', 'le_1024', 'le_4096', 'le_16384', 'gt_16384'} else 'unknown'


def _finish_reason_label(value: str) -> str:
    return value if value in {'unknown', 'stop', 'length', 'content_filter', 'tool_calls'} else 'unknown'


def _bool_label(value: bool) -> str:
    return 'true' if value else 'false'
