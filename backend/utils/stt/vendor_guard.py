"""Typed quota errors, a per-endpoint circuit breaker, and vendor burn metrics.

Shared by ``utils.stt.pre_recorded`` (STT) and ``utils.stt.batch_language`` (LID);
imports nothing from those modules so both can import it without cycles.
"""

from collections import deque
import threading
import time

import httpx
from prometheus_client import Counter, Gauge

from config.prerecorded_vendor import vendor_fail_fast_enabled

MODULATE_PROVIDER = 'modulate'
ENDPOINT_STT = 'stt'
ENDPOINT_LID = 'lid'

QUOTA_HTTP_STATUSES = frozenset({401, 402, 403, 429})
QUOTA_BODY_MARKER = 'insufficient credits'

BREAKER_FAILURE_THRESHOLD = 5
BREAKER_WINDOW_SECONDS = 60.0
BREAKER_OPEN_SECONDS = 60.0

BREAKER_OPEN_GAUGE = Gauge(
    'omi_prerecorded_vendor_breaker_open',
    'Prerecorded vendor circuit breaker open (1) or closed (0)',
    ['provider', 'endpoint'],
)
VENDOR_AUDIO_SECONDS = Counter(
    'omi_prerecorded_vendor_audio_seconds_total',
    'Audio seconds sent to the prerecorded vendor per POST',
    ['provider', 'endpoint', 'outcome'],
)

_clock = time.monotonic


class ModulateQuotaError(RuntimeError):
    """Non-retryable vendor quota/auth rejection (401/402/403/429 or credits body).

    Stays a RuntimeError subclass with the historical 'Modulate transcription failed'
    prefix in raisers so existing callers and retryable-failure semantics are unchanged.
    """


def is_quota_error(exc: BaseException) -> bool:
    if not isinstance(exc, httpx.HTTPStatusError):
        return False
    response = getattr(exc, 'response', None)
    try:
        if response is not None and response.status_code in QUOTA_HTTP_STATUSES:
            return True
    except Exception:
        pass
    try:
        # The marker is matched, never echoed: bodies must not reach logs or exceptions.
        return response is not None and QUOTA_BODY_MARKER in (response.text or '').lower()
    except Exception:
        return False


class _EndpointBreaker:
    __slots__ = ('lock', 'failures', 'opened_at', 'trial_in_flight')

    def __init__(self):
        self.lock = threading.Lock()
        self.failures = deque()
        self.opened_at = None
        self.trial_in_flight = False

    def evict(self, now: float) -> None:
        while self.failures and now - self.failures[0] > BREAKER_WINDOW_SECONDS:
            self.failures.popleft()


_breakers: dict[str, _EndpointBreaker] = {}
_breakers_guard = threading.Lock()


def _breaker_for(endpoint: str) -> _EndpointBreaker:
    with _breakers_guard:
        state = _breakers.get(endpoint)
        if state is None:
            state = _breakers[endpoint] = _EndpointBreaker()
        return state


def _set_gauge(endpoint: str, value: int) -> None:
    try:
        BREAKER_OPEN_GAUGE.labels(MODULATE_PROVIDER, endpoint).set(value)
    except Exception:
        pass


def breaker_allows(endpoint: str) -> bool:
    """False while open; the first call after the open window acquires the single trial."""
    if not vendor_fail_fast_enabled():
        return True
    state = _breaker_for(endpoint)
    with state.lock:
        now = _clock()
        state.evict(now)
        if state.opened_at is None:
            return True
        if now - state.opened_at < BREAKER_OPEN_SECONDS:
            return False
        if state.trial_in_flight:
            return False
        state.trial_in_flight = True
        return True


def record_breaker_success(endpoint: str) -> None:
    if not vendor_fail_fast_enabled():
        return
    state = _breaker_for(endpoint)
    with state.lock:
        state.failures.clear()
        state.opened_at = None
        state.trial_in_flight = False
    _set_gauge(endpoint, 0)


def record_breaker_quota_error(endpoint: str) -> None:
    if not vendor_fail_fast_enabled():
        return
    state = _breaker_for(endpoint)
    with state.lock:
        now = _clock()
        state.failures.append(now)
        state.evict(now)
        if state.opened_at is not None or len(state.failures) >= BREAKER_FAILURE_THRESHOLD:
            # A failed half-open trial re-opens the breaker for another full window.
            state.opened_at = now
            state.trial_in_flight = False
    if state.opened_at is not None:
        _set_gauge(endpoint, 1)


def record_vendor_burn(endpoint: str, outcome: str, seconds: float) -> None:
    try:
        VENDOR_AUDIO_SECONDS.labels(MODULATE_PROVIDER, endpoint, outcome).inc(max(0.0, float(seconds or 0.0)))
    except Exception:
        pass


def reset_vendor_guard_for_tests() -> None:
    """Reset breaker state and zero the gauges; tests only."""
    with _breakers_guard:
        endpoints = list(_breakers)
        _breakers.clear()
    for endpoint in endpoints:
        _set_gauge(endpoint, 0)
