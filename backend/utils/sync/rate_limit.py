"""Privacy-safe response and telemetry primitives for sync rate limits."""

import json
import re
import sys
from typing import Any, Dict, Optional

FAIR_USE_RATE_LIMIT_CODE = 'fair_use_restricted'
FAIR_USE_RATE_LIMIT_REASON = 'fair_use'
FAIR_USE_RATE_LIMIT_REASON_HEADER = 'X-Omi-Rate-Limit-Reason'

# A missing/invalid legacy restriction deadline must not create a retry storm.
# Retry hourly so clients still reconcile and self-heal without waiting forever.
DEFAULT_FAIR_USE_RETRY_AFTER_SECONDS = 60 * 60
MAX_FAIR_USE_RETRY_AFTER_SECONDS = 30 * 24 * 60 * 60

_PLATFORMS = frozenset({'android', 'ios', 'linux', 'macos', 'web', 'windows'})
_FAIR_USE_STAGES = frozenset({'none', 'warning', 'throttle', 'restrict'})
_CLASSIFIER_TYPES = frozenset(
    {'none', 'audiobook', 'podcast', 'prerecorded', 'tv_movie', 'commercial', 'unknown', 'free_exhausted'}
)
_SUBSCRIPTION_PLANS = frozenset({'basic', 'unlimited', 'operator', 'architect'})
_SUBSCRIPTION_STATUSES = frozenset({'active', 'inactive'})
_APP_VERSION_PATTERN = re.compile(r'^[0-9]{1,4}(?:\.[0-9]{1,6}){1,3}(?:\+[A-Za-z0-9._-]{1,32})?$')
_REQUEST_ID_PATTERN = re.compile(
    r'^(?:[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}'
    r'|[0-9a-fA-F]{32}/[0-9]{1,20}(?:;o=[01])?)$'
)
_UID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{1,128}$')
_REVISION_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$')


def bounded_fair_use_retry_after(value: object) -> int:
    """Return a positive, bounded retry interval; legacy missing deadlines retry hourly."""
    try:
        seconds = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_FAIR_USE_RETRY_AFTER_SECONDS
    return min(max(seconds, 1), MAX_FAIR_USE_RETRY_AFTER_SECONDS)


def fair_use_rate_limit_headers(retry_after: object, base_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers = dict(base_headers or {})
    headers[FAIR_USE_RATE_LIMIT_REASON_HEADER] = FAIR_USE_RATE_LIMIT_REASON
    headers['Retry-After'] = str(bounded_fair_use_retry_after(retry_after))
    return headers


def validated_correlation_id(value: object) -> Optional[str]:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if _REQUEST_ID_PATTERN.fullmatch(normalized) else None


def _validated_member(value: object, allowed: frozenset[str]) -> str:
    normalized = str(getattr(value, 'value', value) or '').strip().lower()
    return normalized if normalized in allowed else 'unknown'


def _validated_device_hash(value: object) -> str:
    if not isinstance(value, str):
        return 'unknown'
    normalized = value.strip().lower()
    return normalized if re.fullmatch(r'[a-f0-9]{8}', normalized) else 'unknown'


def _validated_app_version(value: object) -> str:
    if not isinstance(value, str):
        return 'unknown'
    normalized = value.strip()
    return normalized if _APP_VERSION_PATTERN.fullmatch(normalized) else 'unknown'


def _validated_pattern(value: object, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str):
        return 'unknown'
    normalized = value.strip()
    return normalized if pattern.fullmatch(normalized) else 'unknown'


def build_sync_rate_limit_event(
    *,
    uid: object,
    device_hash: object,
    app_platform: object,
    app_version: object,
    subscription_plan: object,
    subscription_status: object,
    fair_use_stage: object,
    classifier_type: object,
    retry_after: object,
    backend_revision: object,
    correlation_id: object,
) -> Dict[str, Any]:
    """Build a fixed-shape event containing only allowlisted or validated values."""
    return {
        'severity': 'WARNING',
        'message': 'sync_rate_limit_rejected',
        'event': 'sync_rate_limit_rejected',
        'uid': _validated_pattern(uid, _UID_PATTERN),
        'device_id_hash': _validated_device_hash(device_hash),
        'app_platform': _validated_member(app_platform, _PLATFORMS),
        'app_version': _validated_app_version(app_version),
        'reason_code': FAIR_USE_RATE_LIMIT_CODE,
        'subscription_plan': _validated_member(subscription_plan, _SUBSCRIPTION_PLANS),
        'subscription_status': _validated_member(subscription_status, _SUBSCRIPTION_STATUSES),
        'fair_use_stage': _validated_member(fair_use_stage, _FAIR_USE_STAGES),
        'classifier_type': _validated_member(classifier_type, _CLASSIFIER_TYPES),
        'retry_after': bounded_fair_use_retry_after(retry_after),
        'backend_revision': _validated_pattern(backend_revision, _REVISION_PATTERN),
        'correlation_id': validated_correlation_id(correlation_id) or 'unknown',
    }


def emit_sync_rate_limit_event(event: Dict[str, Any]) -> None:
    """Write one exact JSON object so Cloud Logging ingests it as jsonPayload."""
    sys.stdout.write(json.dumps(event, separators=(',', ':'), sort_keys=True) + '\n')
    sys.stdout.flush()
