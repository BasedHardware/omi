"""Low-cardinality telemetry and structured logs for provider integrations."""

import importlib
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

logger = logging.getLogger(__name__)

SYNC_ATTEMPTED = 'Integration Sync Attempted'
SYNC_SUCCEEDED = 'Integration Sync Succeeded'
SYNC_FAILED = 'Integration Sync Failed'
AUTH_REFRESH_ATTEMPTED = 'Integration Auth Refresh Attempted'
AUTH_REFRESH_SUCCEEDED = 'Integration Auth Refresh Succeeded'
AUTH_REFRESH_FAILED = 'Integration Auth Refresh Failed'

GOOGLE_CALENDAR = 'Google Calendar'
X = 'X'

_POSTHOG_CLIENT: Optional[Any] = None
_POSTHOG_DISABLED = False


@dataclass(frozen=True)
class IntegrationTelemetryContext:
    integration_name: str
    operation: str
    uid: Optional[str] = None
    app_platform: Optional[str] = None
    app_version: Optional[str] = None
    app_build: Optional[str] = None
    sync_source: Optional[str] = None


def emit_sync_attempted(context: IntegrationTelemetryContext) -> None:
    _emit(telemetry_event_name=SYNC_ATTEMPTED, context=context, status='attempted')


def emit_sync_succeeded(
    context: IntegrationTelemetryContext,
    *,
    item_count: Optional[int] = None,
    memories_created: Optional[int] = None,
) -> None:
    extra = {}
    if item_count is not None:
        extra['item_count'] = _bucket_count(item_count)
    if memories_created is not None:
        extra['memories_created'] = _bucket_count(memories_created)
    _emit(telemetry_event_name=SYNC_SUCCEEDED, context=context, status='succeeded', extra=extra)


def emit_sync_failed(context: IntegrationTelemetryContext, error: Any, *, provider_status_code: Any = None) -> None:
    status_code = _provider_status_code(error, provider_status_code)
    _emit(
        telemetry_event_name=SYNC_FAILED,
        context=context,
        status='failed',
        error=error,
        provider_status_code=status_code,
        retryable=_is_retryable(error, status_code),
    )


def emit_auth_refresh_attempted(context: IntegrationTelemetryContext) -> None:
    _emit(telemetry_event_name=AUTH_REFRESH_ATTEMPTED, context=context, status='attempted')


def emit_auth_refresh_succeeded(context: IntegrationTelemetryContext) -> None:
    _emit(telemetry_event_name=AUTH_REFRESH_SUCCEEDED, context=context, status='succeeded')


def emit_auth_refresh_failed(
    context: IntegrationTelemetryContext, error: Any, *, provider_status_code: Any = None
) -> None:
    status_code = _provider_status_code(error, provider_status_code)
    _emit(
        telemetry_event_name=AUTH_REFRESH_FAILED,
        context=context,
        status='failed',
        error=error,
        provider_status_code=status_code,
        retryable=_is_retryable(error, status_code),
    )


def _emit(
    *,
    telemetry_event_name: str,
    context: IntegrationTelemetryContext,
    status: str,
    error: Any = None,
    provider_status_code: Any = None,
    retryable: Optional[bool] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    properties = _properties(
        context=context,
        status=status,
        error=error,
        provider_status_code=provider_status_code,
        retryable=retryable,
        extra=extra,
    )
    _log_structured(telemetry_event_name, context.uid, properties)

    client = _get_posthog_client()
    if client is None or not context.uid:
        return

    try:
        client.capture(distinct_id=context.uid, event=telemetry_event_name, properties=properties)
    except Exception as exc:
        logger.warning(
            'integration telemetry posthog_emit_failed event=%s error=%s', telemetry_event_name, type(exc).__name__
        )


def _properties(
    *,
    context: IntegrationTelemetryContext,
    status: str,
    error: Any,
    provider_status_code: Any,
    retryable: Optional[bool],
    extra: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    props: Dict[str, Any] = {
        'integration_name': context.integration_name,
        'provider': context.integration_name,
        'operation': context.operation,
        'status': status,
        'error_bucket': _error_bucket(error, provider_status_code),
        'provider_status_code': provider_status_code,
        'retryable': bool(retryable) if retryable is not None else False,
        'environment': os.getenv('OMI_ENV_STAGE') or os.getenv('ENVIRONMENT') or 'unknown',
    }
    optional = {
        'app_platform': context.app_platform,
        'app_version': context.app_version,
        'app_build': context.app_build,
        'sync_source': context.sync_source,
    }
    props.update({key: value for key, value in optional.items() if value})
    if extra:
        props.update(extra)
    return props


def _log_structured(event_name: str, uid: Optional[str], properties: Dict[str, Any]) -> None:
    logger.info(
        'integration_telemetry event=%s uid=%s provider=%s operation=%s status=%s error_bucket=%s '
        'provider_status_code=%s retryable=%s app_platform=%s app_version=%s environment=%s',
        event_name,
        uid or 'unknown',
        properties['provider'],
        properties['operation'],
        properties['status'],
        properties['error_bucket'],
        properties['provider_status_code'],
        properties['retryable'],
        properties.get('app_platform', 'unknown'),
        properties.get('app_version', 'unknown'),
        properties['environment'],
    )


def _get_posthog_client() -> Optional[Any]:
    global _POSTHOG_CLIENT, _POSTHOG_DISABLED
    if _POSTHOG_DISABLED:
        return None
    if _POSTHOG_CLIENT is not None:
        return _POSTHOG_CLIENT

    api_key = os.getenv('POSTHOG_PROJECT_API_KEY') or os.getenv('POSTHOG_API_KEY')
    if not api_key:
        _POSTHOG_DISABLED = True
        return None

    host = os.getenv('POSTHOG_HOST', 'https://app.posthog.com')
    try:
        posthog_module = importlib.import_module('posthog')
        posthog_client_cls = getattr(posthog_module, 'Posthog')
    except Exception as exc:
        logger.warning('integration telemetry posthog_import_failed error=%s', type(exc).__name__)
        _POSTHOG_DISABLED = True
        return None

    _POSTHOG_CLIENT = posthog_client_cls(project_api_key=api_key, host=host)
    return _POSTHOG_CLIENT


def _provider_status_code(error: Any, explicit_status_code: Any = None) -> Optional[int]:
    if explicit_status_code is not None:
        try:
            return int(explicit_status_code)
        except (TypeError, ValueError):
            return None
    status_code = getattr(error, 'status_code', None)
    if status_code is not None:
        try:
            return int(status_code)
        except (TypeError, ValueError):
            return None
    response = getattr(error, 'response', None)
    response_status_code = getattr(response, 'status_code', None) if response is not None else None
    if response_status_code is not None:
        try:
            return int(response_status_code)
        except (TypeError, ValueError):
            return None
    return None


def _error_bucket(error: Any, provider_status_code: Any) -> str:
    if error is None:
        return 'none'
    status_code = _provider_status_code(error, provider_status_code)
    text = str(error).lower()
    if status_code in {401, 403} or 'unauthorized' in text or 'authentication' in text or 'invalid_grant' in text:
        return 'oauth_unauthorized'
    if status_code == 429 or 'rate limit' in text or 'rate_limited' in text:
        return 'rate_limited'
    if status_code is not None and 500 <= status_code <= 599:
        return 'provider_5xx'
    if status_code is not None and 400 <= status_code <= 499:
        return 'bad_request'
    if isinstance(error, (httpx.TimeoutException, httpx.ConnectError, TimeoutError)) or text in {
        'timeout',
        'connect_error',
    }:
        return 'network'
    if text in {'not_connected', 'missing_token', 'missing_handle'}:
        return 'oauth_unauthorized'
    return 'unknown'


def _is_retryable(error: Any, provider_status_code: Optional[int]) -> bool:
    if provider_status_code in {408, 429, 500, 502, 503, 504}:
        return True
    if getattr(error, 'is_retryable', False):
        return True
    return isinstance(error, (httpx.TimeoutException, httpx.ConnectError, TimeoutError))


def _bucket_count(value: int) -> str:
    if value <= 0:
        return '0'
    if value <= 10:
        return '1_10'
    if value <= 100:
        return '11_100'
    if value <= 1000:
        return '101_1000'
    return '1000_plus'


def set_posthog_client_for_tests(client: Optional[Any]) -> None:
    global _POSTHOG_CLIENT, _POSTHOG_DISABLED
    _POSTHOG_CLIENT = client
    _POSTHOG_DISABLED = client is None
