"""Server-side v2 flag authority shared by admission and exclusive mentor dispatch."""

import importlib
import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from threading import Lock
from typing import Any

from config.proactivity_v2 import ProactivityDenied
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

FLAG_TTL_SECONDS = 300
ERROR_TTL_SECONDS = 60
MAX_CACHE_ENTRIES = 4096


@dataclass(frozen=True)
class _FlagResult:
    expires_at: float
    enabled: bool = False
    error_type: str = ''
    http_status: int | None = None


class ProactivityFlagUnavailable(ProactivityDenied):
    """Content-free cached failure; never retain an SDK exception/response."""

    def __init__(self, error_type: str, http_status: int | None):
        super().__init__('flag_unavailable')
        self.error_type = error_type
        self.http_status = http_status


_flag_cache: OrderedDict[str, _FlagResult] = OrderedDict()
_cache_lock = Lock()
# Fixed stripes coalesce same-user misses without holding the cache lock during
# network IO or growing an unbounded per-user lock map.
_lookup_locks = tuple(Lock() for _ in range(64))
_diagnostic_lock = Lock()
_next_warning_at = 0.0


def _log_flag_error(result: _FlagResult) -> None:
    global _next_warning_at
    with _diagnostic_lock:
        now = time.monotonic()
        if now < _next_warning_at:
            return
        _next_warning_at = now + ERROR_TTL_SECONDS
    logger.warning(
        'proactivity_v2_flag_unavailable error_type=%s http_status=%s',
        result.error_type,
        result.http_status if result.http_status is not None else 'unknown',
    )


def _error_result(exc: Exception, expires_at: float) -> _FlagResult:
    # PostHog 3.5.2 APIError uses .status; never stringify the exception (its
    # message can contain an upstream response). Only bounded scalar fields live
    # in this cache or its diagnostic log.
    error_type = ''.join(c for c in type(exc).__name__ if c.isascii() and (c.isalnum() or c == '_'))[:64]
    status = getattr(exc, 'status', None)
    if isinstance(status, str) and len(status) == 3 and status.isascii() and status.isdigit():
        status = int(status)
    http_status = status if type(status) is int and 100 <= status <= 599 else None
    return _FlagResult(expires_at, error_type=error_type or 'unknown', http_status=http_status)


@lru_cache(maxsize=1)
def flag_client() -> Any:
    # The shared backend key is intentionally disabled. Only this public token
    # grants v2 cohort lookup; never enable JIT flags or capture as a side effect.
    key = os.getenv('PROACTIVITY_V2_POSTHOG_TOKEN', '').strip()
    if not key.startswith('phc_'):
        raise ProactivityDenied('flag_unavailable')
    return importlib.import_module('posthog').Posthog(
        project_api_key=key,
        host=os.getenv('PROACTIVITY_V2_POSTHOG_HOST', '').strip() or 'https://us.posthog.com',
        send=False,
        sync_mode=True,
        feature_flags_request_timeout_seconds=2,
    )


def _cached_result(uid: str) -> _FlagResult | None:
    with _cache_lock:
        result = _flag_cache.get(uid)
        if result is not None and result.expires_at <= time.monotonic():
            del _flag_cache[uid]
            return None
        if result is not None:
            _flag_cache.move_to_end(uid)
        return result


def enabled(uid: str) -> bool:
    """Cache true/false for 300s and failures for 60s, failing closed on errors."""
    # Hits never wait for an unrelated user's in-flight lookup in the same stripe.
    result = _cached_result(uid)
    if result is None:
        with _lookup_locks[hash(uid) % len(_lookup_locks)]:
            result = _cached_result(uid)
            if result is None:
                now = time.monotonic()
                try:
                    variants = flag_client().get_feature_variants(uid)
                    if not isinstance(variants, dict):
                        raise ProactivityDenied('flag_unavailable')
                    result = _FlagResult(now + FLAG_TTL_SECONDS, enabled=variants.get('proactivity_v2') is True)
                except Exception as exc:
                    result = _error_result(exc, now + ERROR_TTL_SECONDS)
                with _cache_lock:
                    _flag_cache[uid] = result
                    _flag_cache.move_to_end(uid)
                    while len(_flag_cache) > MAX_CACHE_ENTRIES:
                        _flag_cache.popitem(last=False)
    if result.error_type:
        _log_flag_error(result)
        raise ProactivityFlagUnavailable(result.error_type, result.http_status)
    return result.enabled


def mentor_pipeline(uid: str) -> str:
    """Resolve one exclusive mentor lane using the admission flag client/cache."""
    pipeline = os.getenv('MENTOR_PIPELINE', 'legacy')
    if pipeline != 'cohort':
        return pipeline
    try:
        return 'v2' if enabled(uid) else 'legacy'
    except Exception:
        record_fallback(
            component='other',
            from_mode='mentor_cohort',
            to_mode='legacy',
            reason='other',
            outcome='recovered',
            log=logger,
        )
        return 'legacy'
