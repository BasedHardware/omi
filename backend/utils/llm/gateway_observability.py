from __future__ import annotations

import logging
import os
import threading
import time

from utils.metrics import (
    LLM_GATEWAY_CHAT_EXTRACTION_COMPARISONS,
    LLM_GATEWAY_CHAT_EXTRACTION_REQUESTS,
    LLM_GATEWAY_DIRECT_EXCEPTION_REQUESTS,
)

logger = logging.getLogger(__name__)

LLM_GATEWAY_BACKEND_EVENT = 'llm_gateway_backend_event'
LLM_GATEWAY_OBSERVABILITY_LOGS_ENABLED_ENV = 'OMI_LLM_GATEWAY_OBSERVABILITY_LOGS_ENABLED'

_GATEWAY_MODE_SERVING = 'serving'
_GATEWAY_MODE_FALLBACK = 'fallback'
_GATEWAY_MODE_DIRECT_EXCEPTION = 'direct_exception'
_GATEWAY_MODE_SHADOW = 'shadow'

_LABEL_MAX_LENGTH = 128
_SAFE_LABEL_CHARS = frozenset('._:-')
_OBSERVATION_WARNING_INTERVAL_SECONDS = 60.0
_observation_warning_lock = threading.Lock()
_last_observation_warning_at = 0.0


def record_gateway_request_result(
    *,
    feature: str,
    outcome: str,
    reason: str,
    route: str = 'chat_structured',
    mode: str | None = None,
    request_id: str = 'unknown',
    credential_source: str = 'unknown',
) -> None:
    feature_label = _safe_label(feature)
    outcome_label = _safe_label(outcome)
    reason_label = _safe_label(reason)
    route_label = _safe_label(route)
    mode_label = _safe_label(mode or _mode_for_outcome(outcome))

    try:
        LLM_GATEWAY_CHAT_EXTRACTION_REQUESTS.labels(
            feature=feature_label,
            mode=mode_label,
            outcome=outcome_label,
            reason=reason_label,
        ).inc()
    except Exception:
        _report_observation_failure('request_metric')

    _log_gateway_event(
        kind='request_result',
        feature=feature_label,
        mode=mode_label,
        outcome=outcome_label,
        reason=reason_label,
        field='none',
        route=route_label,
        request_id=_safe_label(request_id),
        credential_source=_safe_label(credential_source),
    )


def record_direct_exception_surface(*, surface: str, reason: str = 'acknowledged') -> None:
    surface_label = _safe_label(surface)
    reason_label = _safe_label(reason)

    try:
        LLM_GATEWAY_DIRECT_EXCEPTION_REQUESTS.labels(surface=surface_label, reason=reason_label).inc()
    except Exception:
        _report_observation_failure('direct_exception_metric')

    try:
        LLM_GATEWAY_CHAT_EXTRACTION_REQUESTS.labels(
            feature=surface_label,
            mode=_GATEWAY_MODE_DIRECT_EXCEPTION,
            outcome='direct_exception',
            reason=reason_label,
        ).inc()
    except Exception:
        _report_observation_failure('request_metric')

    _log_gateway_event(
        kind='direct_exception',
        feature=surface_label,
        mode=_GATEWAY_MODE_DIRECT_EXCEPTION,
        outcome='direct_exception',
        reason=reason_label,
        field='none',
        route='direct',
        request_id='unknown',
        credential_source='unknown',
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
        _report_observation_failure('shadow_comparison_metric')

    _log_gateway_event(
        kind='shadow_comparison',
        feature=feature_label,
        mode=_GATEWAY_MODE_SHADOW,
        outcome=outcome_label,
        reason='none',
        field=field_label,
        route=route_label,
        request_id='unknown',
        credential_source='unknown',
    )


def _mode_for_outcome(outcome: str) -> str:
    normalized = outcome.strip().casefold()
    if normalized == 'success':
        return _GATEWAY_MODE_SERVING
    if normalized == 'fallback':
        return _GATEWAY_MODE_FALLBACK
    if normalized == 'skipped':
        return _GATEWAY_MODE_SHADOW
    if normalized == 'direct_exception':
        return _GATEWAY_MODE_DIRECT_EXCEPTION
    return normalized or _GATEWAY_MODE_SERVING


def _log_gateway_event(
    *,
    kind: str,
    feature: str,
    mode: str,
    outcome: str,
    reason: str,
    field: str,
    route: str,
    request_id: str,
    credential_source: str,
) -> None:
    if not _observability_logs_enabled():
        return

    try:
        logger.info(
            '%s kind=%s request_id=%s feature=%s mode=%s outcome=%s reason=%s field=%s route=%s '
            'credential_source=%s service=%s',
            LLM_GATEWAY_BACKEND_EVENT,
            _safe_label(kind),
            request_id,
            feature,
            _safe_label(mode),
            outcome,
            reason,
            field,
            route,
            credential_source,
            _service_label(),
        )
    except Exception:
        _report_observation_failure('structured_log')


def _report_observation_failure(stage: str) -> None:
    global _last_observation_warning_at
    now = time.monotonic()
    with _observation_warning_lock:
        if now - _last_observation_warning_at < _OBSERVATION_WARNING_INTERVAL_SECONDS:
            return
        _last_observation_warning_at = now
    try:
        logger.warning('llm_gateway_backend_observation_failed stage=%s', _safe_label(stage))
    except Exception:
        return


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
