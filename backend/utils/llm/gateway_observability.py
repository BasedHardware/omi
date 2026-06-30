from __future__ import annotations

import logging
import os

from utils.metrics import LLM_GATEWAY_CHAT_EXTRACTION_COMPARISONS, LLM_GATEWAY_CHAT_EXTRACTION_REQUESTS

logger = logging.getLogger(__name__)

LLM_GATEWAY_BACKEND_EVENT = 'llm_gateway_backend_event'
LLM_GATEWAY_OBSERVABILITY_LOGS_ENABLED_ENV = 'OMI_LLM_GATEWAY_OBSERVABILITY_LOGS_ENABLED'

_LABEL_MAX_LENGTH = 128
_SAFE_LABEL_CHARS = frozenset('._:-')


def record_gateway_request_result(*, feature: str, outcome: str, reason: str, route: str = 'chat_structured') -> None:
    feature_label = _safe_label(feature)
    outcome_label = _safe_label(outcome)
    reason_label = _safe_label(reason)
    route_label = _safe_label(route)

    try:
        LLM_GATEWAY_CHAT_EXTRACTION_REQUESTS.labels(
            feature=feature_label,
            outcome=outcome_label,
            reason=reason_label,
        ).inc()
    except Exception:
        pass

    _log_gateway_event(
        kind='request_result',
        feature=feature_label,
        outcome=outcome_label,
        reason=reason_label,
        field='none',
        route=route_label,
    )


def record_gateway_shadow_comparison(*, feature: str, field: str, outcome: str, route: str = 'chat_structured') -> None:
    feature_label = _safe_label(feature)
    field_label = _safe_label(field)
    outcome_label = _safe_label(outcome)
    route_label = _safe_label(route)

    try:
        LLM_GATEWAY_CHAT_EXTRACTION_COMPARISONS.labels(
            feature=feature_label,
            field=field_label,
            outcome=outcome_label,
        ).inc()
    except Exception:
        pass

    _log_gateway_event(
        kind='shadow_comparison',
        feature=feature_label,
        outcome=outcome_label,
        reason='none',
        field=field_label,
        route=route_label,
    )


def _log_gateway_event(
    *,
    kind: str,
    feature: str,
    outcome: str,
    reason: str,
    field: str,
    route: str,
) -> None:
    if not _observability_logs_enabled():
        return

    logger.info(
        '%s kind=%s feature=%s outcome=%s reason=%s field=%s route=%s service=%s',
        LLM_GATEWAY_BACKEND_EVENT,
        _safe_label(kind),
        feature,
        outcome,
        reason,
        field,
        route,
        _service_label(),
    )


def _observability_logs_enabled() -> bool:
    value = os.getenv(LLM_GATEWAY_OBSERVABILITY_LOGS_ENABLED_ENV)
    if value is None:
        return True
    return value.strip().casefold() not in {'0', 'false', 'no', 'off'}


def _service_label() -> str:
    return _safe_label(os.getenv('K_SERVICE') or os.getenv('APP_NAME') or 'backend')


def _safe_label(value: object, *, default: str = 'unknown') -> str:
    text = str(value or '').strip().casefold()
    if not text:
        text = default
    normalized = ''.join(char if char.isalnum() or char in _SAFE_LABEL_CHARS else '_' for char in text)
    return (normalized or default)[:_LABEL_MAX_LENGTH]
