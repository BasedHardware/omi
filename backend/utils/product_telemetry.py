"""One lazy, fail-open server capture client; no content or raw identity properties.

Credential admission stays family-scoped: product/integration/extraction use
POSTHOG_PROJECT_API_KEY (legacy POSTHOG_API_KEY only when project is absent),
billing uses POSTHOG_BILLING_API_KEY, and MCP uses POSTHOG_EVENTS_API_KEY.
An absent/invalid family key disables that family: no cross-family fallback.
In particular, project=disabled plus a valid billing key enables billing only.
One synchronous SDK is shared, with each capture's key bound under a lock.
Flag-only clients retain separate credentials and never emit events.
"""

from __future__ import annotations

import importlib
import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from threading import BoundedSemaphore, Lock
from typing import Any, Mapping, Optional

from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)
_posthog_client: Optional[Any] = None
_injected_client: Optional[Any] = None
_client_lock = Lock()
_invalid_key_logged = False
_context: ContextVar[Mapping[str, Any]] = ContextVar('server_product_telemetry', default={})
SOURCE_PLATFORMS = frozenset({'macos', 'ios', 'android', 'windows', 'web', 'mcp', 'server', 'unknown'})
BUILD_CHANNELS = frozenset(
    {
        'stable',
        'beta',
        'dev',
        'production',
        'testflight',
        'app_store',
        'appstore',
        'debug',
        'release',
        'canary',
        'unknown',
    }
)
_CAPTURE_KEYS = ('POSTHOG_PROJECT_API_KEY', 'POSTHOG_EVENTS_API_KEY', 'POSTHOG_BILLING_API_KEY', 'POSTHOG_API_KEY')
BILLING_EVENTS = frozenset(
    {
        'Billing Subscription Started',
        'Billing Subscription Churned',
        'Billing Subscription Cancellation Scheduled',
        'Billing Subscription Plan Changed',
    }
)

MCP_EVENTS = frozenset({'MCP Active', 'MCP Tool Call', 'MCP Tool Use Succeeded'})


def _capture_project_key(event: str) -> Optional[str]:
    """Resolve only the owning family's configuration; invalid is not absent."""
    global _invalid_key_logged
    if event in BILLING_EVENTS:
        raw = os.getenv('POSTHOG_BILLING_API_KEY')
    elif event in MCP_EVENTS:
        raw = os.getenv('POSTHOG_EVENTS_API_KEY')
    else:
        raw = os.getenv('POSTHOG_PROJECT_API_KEY') or os.getenv('POSTHOG_API_KEY')
    key = raw.strip() if raw else ''
    if key.startswith('phc_'):
        return key
    if key and not _invalid_key_logged:
        _invalid_key_logged = True
        logger.warning('server telemetry disabled: invalid family project key')
    return None


def normalize_source_platform(value: Any) -> str:
    value = value.strip().lower() if isinstance(value, str) else ''
    return value if value in SOURCE_PLATFORMS else 'unknown'


@contextmanager
def product_telemetry_context(*, headers: Mapping[str, str]):
    """Request-scoped, non-authoritative client metadata; never trust exclusion headers."""
    token = _context.set(
        {
            'source_platform': normalize_source_platform(headers.get('x-app-platform')),
            'build_channel': headers.get('x-build-channel')
            or headers.get('x-app-build-channel')
            or headers.get('x-release-channel'),
        }
    )
    try:
        yield
    finally:
        _context.reset(token)


def bind_websocket_telemetry_context(headers: Mapping[str, str]) -> None:
    # The async listen dependency and handler share one connection-scoped task.
    _context.set(
        {
            'source_platform': normalize_source_platform(headers.get('x-app-platform')),
            'build_channel': headers.get('x-build-channel')
            or headers.get('x-app-build-channel')
            or headers.get('x-release-channel'),
        }
    )


def _roster_contains(name: str, uid: str) -> bool:
    # Owner-supplied UID rosters only, never email/domain inference or network IO.
    return uid in {value.strip() for value in os.getenv(name, '').split(',') if value.strip()}


def server_event_properties(uid: str, properties: Mapping[str, Any]) -> dict[str, Any]:
    """Enrich the emitter's closed dictionary, rejecting raw IDs and content.

    Explicit source metadata wins over request context (e.g. a background
    conversation was captured on a different device than the current viewer).
    Missing roster membership is unknown, never proof of external status.
    """
    forbidden = {
        'uid',
        'user_id',
        'distinct_id',
        'email',
        'ip',
        'user_agent',
        'content',
        'text',
        'query',
        'arguments',
        'result',
        'token',
        'transcript',
        'prompt',
    }
    safe = {
        key: value
        for key, value in properties.items()
        if (key not in forbidden and not key.endswith(('_id', '_ids'))) or key == '$insert_id'
    }
    # Experiment names are code-owned enum dimensions, not person/device IDs.
    # Preserve the existing experiment dashboard contract without admitting IDs
    # from arbitrary future callers.
    experiment = properties.get('experiment_id')
    if isinstance(experiment, str) and experiment in {
        'EXP-001-day3-reengagement',
        'EXP-002-desktop-identity-memory-v1',
    }:
        safe['experiment_id'] = experiment
    context = _context.get()
    source = next(
        (
            properties[key]
            for key in ('source_platform', 'client_platform', 'app_platform', 'platform')
            if properties.get(key) is not None
        ),
        context.get('source_platform'),
    )
    safe['source_platform'] = normalize_source_platform(source)
    safe['emitter'] = 'server'
    safe['environment'] = os.getenv('OMI_ENV_STAGE') or os.getenv('ENVIRONMENT') or 'unknown'
    channel = properties.get('build_channel', context.get('build_channel'))
    safe.pop('build_channel', None)
    if isinstance(channel, str) and channel.strip().lower() in BUILD_CHANNELS:
        safe['build_channel'] = channel.strip().lower()
    if type(safe.get('internal')) is not bool:
        safe.pop('internal', None)
    if _roster_contains('POSTHOG_INTERNAL_UIDS', uid):
        safe['internal'] = True
    synthetic = uid == 'omi-release-probe' or uid.startswith('cfc_')
    safe['test'] = synthetic or _roster_contains('POSTHOG_TEST_UIDS', uid) or safe.get('test') is True
    return safe


def _fallback(reason: str = 'other') -> None:
    record_fallback(component='other', from_mode='posthog', to_mode='none', reason=reason, outcome='degraded')


class _ServerCaptureClient:
    """One synchronous SDK, with ordinary capture offloaded to the owned pool.

    Billing and daily MCP markers call capture synchronously from their existing
    background workers so delivery failures are visible before settling claims.
    """

    def __init__(self, sdk: Any):
        self.sdk = sdk
        self.capture_lock = Lock()
        self.pending = BoundedSemaphore(1000)

    def _capture_with_key(self, api_key: str, kwargs: Mapping[str, Any]) -> Any:
        # The pinned SDK's synchronous _enqueue sends with self.api_key before
        # returning. Serialize binding + capture + restoration; no SDK queue or
        # flag evaluation may observe another family's credentials.
        with self.capture_lock:
            previous_key = self.sdk.api_key
            try:
                self.sdk.api_key = api_key
                return self.sdk.capture(**kwargs)
            finally:
                self.sdk.api_key = previous_key

    def capture(self, **kwargs: Any) -> Any:
        api_key = _capture_project_key(kwargs['event'])
        if api_key is None:
            return False
        if kwargs['event'] in BILLING_EVENTS or kwargs['event'] == 'MCP Tool Use Succeeded':
            return self._capture_with_key(api_key, kwargs)
        from utils.executors import postprocess_executor, submit_with_context

        if not self.pending.acquire(blocking=False):
            _fallback('enqueue_failed')
            return False

        def deliver() -> None:
            try:
                result = self._capture_with_key(api_key, kwargs)
                if result is False or (isinstance(result, tuple) and result[0] is False):
                    _fallback()
            except Exception as error:
                logger.warning('server telemetry delivery failed error_type=%s', type(error).__name__)
                _fallback()
            finally:
                self.pending.release()

        try:
            submit_with_context(postprocess_executor, deliver)
        except Exception:
            self.pending.release()
            raise
        return True


def get_server_posthog_client(event: str = '') -> Optional[Any]:
    global _posthog_client
    if _injected_client is not None:
        return _injected_client
    with _client_lock:
        api_key = _capture_project_key(event)
        if api_key is None:
            return None
        if _posthog_client is not None:
            return _posthog_client
        try:
            sdk = importlib.import_module('posthog').Posthog(
                project_api_key=api_key,
                host=os.getenv('POSTHOG_HOST', 'https://app.posthog.com'),
                sync_mode=True,
                timeout=2,
                max_retries=0,
            )
            _posthog_client = _ServerCaptureClient(sdk)
        except Exception as error:
            logger.warning('server telemetry unavailable error_type=%s', type(error).__name__)
        return _posthog_client


def emit_product_event(
    *,
    uid: str,
    event: str,
    properties: Mapping[str, Any],
    timestamp: Optional[datetime] = None,
    event_uuid: Optional[str] = None,
) -> bool:
    """Return capture acceptance; telemetry failures never fail the owning operation."""
    if not uid:
        return False
    try:
        client = get_server_posthog_client(event)
        if client is None:
            _fallback('config_incomplete')
            return False
        capture_args: dict[str, Any] = dict(
            distinct_id=uid, event=event, properties=server_event_properties(uid, properties)
        )
        if event_uuid:
            capture_args['uuid'] = event_uuid
        if timestamp is not None:
            capture_args['timestamp'] = timestamp
        if event in BILLING_EVENTS and properties.get('$insert_id'):
            capture_args['uuid'] = properties['$insert_id']
            if properties.get('occurred_at'):
                capture_args['timestamp'] = datetime.fromisoformat(properties['occurred_at'].replace('Z', '+00:00'))
        result = client.capture(**capture_args)
        return not (result is False or (isinstance(result, tuple) and result[0] is False))
    except Exception as error:
        logger.warning('product telemetry emit failed event=%s error_type=%s', event, type(error).__name__)
        _fallback()
        return False


def set_product_telemetry_client_for_tests(client: Optional[Any]) -> None:
    global _posthog_client, _injected_client, _invalid_key_logged
    _posthog_client = None
    _injected_client = client
    _invalid_key_logged = False
