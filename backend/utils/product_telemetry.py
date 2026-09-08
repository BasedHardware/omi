"""Fail-open PostHog emission for privacy-safe backend product events."""

from __future__ import annotations

import importlib
import logging
import os
from typing import Any, Mapping, Optional

from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

_posthog_client: Optional[Any] = None
_posthog_disabled = False


def emit_product_event(*, uid: str, event: str, properties: Mapping[str, Any]) -> None:
    """Emit a bounded product event without changing the owning operation."""

    if not uid:
        return
    client = _get_posthog_client()
    if client is None:
        record_fallback(
            component='other',
            from_mode='posthog',
            to_mode='none',
            reason='config_incomplete',
            outcome='degraded',
        )
        return
    safe_properties = {key: value for key, value in properties.items() if value is not None}
    safe_properties['environment'] = os.getenv('OMI_ENV_STAGE') or os.getenv('ENVIRONMENT') or 'unknown'
    try:
        client.capture(distinct_id=uid, event=event, properties=safe_properties)
    except Exception as error:
        logger.warning('product telemetry emit failed event=%s error_type=%s', event, type(error).__name__)
        record_fallback(
            component='other',
            from_mode='posthog',
            to_mode='none',
            reason='other',
            outcome='degraded',
        )


def _get_posthog_client() -> Optional[Any]:
    global _posthog_client, _posthog_disabled
    if _posthog_disabled:
        return None
    if _posthog_client is not None:
        return _posthog_client
    api_key = os.getenv('POSTHOG_PROJECT_API_KEY') or os.getenv('POSTHOG_API_KEY')
    if not api_key:
        _posthog_disabled = True
        return None
    try:
        module = importlib.import_module('posthog')
        client_class = getattr(module, 'Posthog')
        _posthog_client = client_class(
            project_api_key=api_key,
            host=os.getenv('POSTHOG_HOST', 'https://app.posthog.com'),
        )
    except Exception as error:
        logger.warning('product telemetry unavailable error_type=%s', type(error).__name__)
        _posthog_disabled = True
        return None
    return _posthog_client


def set_product_telemetry_client_for_tests(client: Optional[Any]) -> None:
    global _posthog_client, _posthog_disabled
    _posthog_client = client
    _posthog_disabled = client is None
