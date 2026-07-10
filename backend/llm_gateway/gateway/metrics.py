from __future__ import annotations

import time
from prometheus_client import Counter, Histogram

from llm_gateway.gateway.errors import GatewayError
from llm_gateway.gateway.executor import ExecutorResult

REQUEST_LATENCY_SECONDS = Histogram(
    'llm_gateway_request_latency_seconds',
    'LLM gateway request latency by route selection and outcome',
    [
        'lane_id',
        'route_artifact_id',
        'provider',
        'model',
        'used_lkg',
        'fallback_used',
        'fallback_reason',
        'outcome',
        'error_class',
    ],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 40),
)

REQUESTS_TOTAL = Counter(
    'llm_gateway_requests_total',
    'LLM gateway requests by route selection and outcome',
    [
        'lane_id',
        'route_artifact_id',
        'provider',
        'model',
        'used_lkg',
        'fallback_used',
        'fallback_reason',
        'outcome',
        'error_class',
    ],
)


def observe_success(started_at: float, result: ExecutorResult) -> None:
    labels = _result_labels(result, outcome='success', error_class='none')
    REQUESTS_TOTAL.labels(**labels).inc()
    REQUEST_LATENCY_SECONDS.labels(**labels).observe(time.monotonic() - started_at)


def observe_error(
    started_at: float,
    *,
    lane_id: str,
    route_artifact_id: str,
    error: GatewayError,
) -> None:
    labels = {
        'lane_id': _bounded(lane_id),
        'route_artifact_id': _bounded(route_artifact_id),
        'provider': 'none',
        'model': 'none',
        'used_lkg': 'false',
        'fallback_used': 'false',
        'fallback_reason': _bounded(error.failure_class.value if error.failure_class is not None else 'none'),
        'outcome': 'error',
        'error_class': _bounded(error.code.value),
    }
    REQUESTS_TOTAL.labels(**labels).inc()
    REQUEST_LATENCY_SECONDS.labels(**labels).observe(time.monotonic() - started_at)


def time_request() -> float:
    return time.monotonic()


def _result_labels(result: ExecutorResult, *, outcome: str, error_class: str) -> dict[str, str]:
    return {
        'lane_id': _bounded(result.lane_id),
        'route_artifact_id': _bounded(result.selected_route_artifact_id),
        'provider': _bounded(result.selected_provider),
        'model': _bounded(result.selected_model),
        'used_lkg': _bool_label(result.used_lkg),
        'fallback_used': _bool_label(result.fallback_used),
        'fallback_reason': _bounded(result.fallback_reason.value if result.fallback_reason is not None else 'none'),
        'outcome': _bounded(outcome),
        'error_class': _bounded(error_class),
    }


def _bounded(value: str) -> str:
    normalized = value.strip().lower().replace(' ', '_')
    return normalized[:128] if normalized else 'unknown'


def _bool_label(value: bool) -> str:
    return 'true' if value else 'false'
