"""Bounded per-provider live-STT connection-attempt counters.

Both connect paths record here: the legacy fixed-order walk in
``utils.stt.streaming.connect_stt_socket_with_fallback`` and the configured
chain in ``utils.stt.live_chain``. The 2026-09-26 incident left
``omi_stt_leg_attempts_total`` empty in prod because only the configured chain
(which was off) emits it; this counter is emitted on every connect path so a
leg-error alert can never again read a permanently empty series.

Labels are closed sets: provider tokens bounded by the stream-close vocabulary,
and an ``error_class`` folded from the bounded failure reasons both paths
already compute. Raw vendor messages never reach a label.
"""

from __future__ import annotations

from typing import Optional

from utils.metrics import OMI_STT_PROVIDER_CONNECT_TOTAL
from utils.stt.stream_close import STT_STREAM_CLOSE_PROVIDERS, bounded_stream_close_provider

CONNECT_SUCCESS = 'success'
CONNECT_FAILURE = 'failure'

# Bounded error classes for failed provider connects.
ERROR_CLASS_BUDGET = 'budget'
ERROR_CLASS_AUTH = 'auth'
ERROR_CLASS_SERVER_ERROR = 'server_error'
ERROR_CLASS_TIMEOUT = 'timeout'
ERROR_CLASS_CAPABILITY = 'capability'
ERROR_CLASS_OTHER = 'other'
ERROR_CLASS_NONE = 'none'

STT_CONNECT_ERROR_CLASSES = frozenset(
    {
        ERROR_CLASS_BUDGET,
        ERROR_CLASS_AUTH,
        ERROR_CLASS_SERVER_ERROR,
        ERROR_CLASS_TIMEOUT,
        ERROR_CLASS_CAPABILITY,
        ERROR_CLASS_OTHER,
        ERROR_CLASS_NONE,
    }
)

# The bounded failure reasons both connect paths already produce (legacy
# ``_fallback_failure_reason`` / chain ``failure_reason`` vocabulary, plus the
# typed stream-close shapes that can surface at the liveness grace), folded
# onto the alert-facing error class.
_REASON_ERROR_CLASS = {
    'quota': ERROR_CLASS_BUDGET,
    'budget': ERROR_CLASS_BUDGET,
    'provider_budget_exhausted': ERROR_CLASS_BUDGET,
    'auth': ERROR_CLASS_AUTH,
    'provider_auth_rejected': ERROR_CLASS_AUTH,
    'timeout': ERROR_CLASS_TIMEOUT,
    'provider_5xx': ERROR_CLASS_SERVER_ERROR,
    'server_error': ERROR_CLASS_SERVER_ERROR,
    'provider_429': ERROR_CLASS_SERVER_ERROR,
    'modulate_serve_error': ERROR_CLASS_SERVER_ERROR,
    'config_incomplete': ERROR_CLASS_CAPABILITY,
    'capability_mismatch': ERROR_CLASS_CAPABILITY,
    'capacity_full': ERROR_CLASS_CAPABILITY,
    'allocation_rejected': ERROR_CLASS_CAPABILITY,
}


def connect_error_class(reason: Optional[str]) -> str:
    """Fold a bounded connect-failure reason onto the closed error-class set."""

    label = (reason or '').strip().lower()
    return _REASON_ERROR_CLASS.get(label, ERROR_CLASS_OTHER)


def record_stt_provider_connect(*, provider: str, outcome: str, reason: Optional[str] = None) -> None:
    """Increment ``omi_stt_provider_connect_total``. Never raises.

    ``outcome`` is ``success`` or ``failure``; ``reason`` is the bounded
    failure vocabulary (ignored for successes, which carry ``none``).
    """

    try:
        error_class = ERROR_CLASS_NONE if outcome == CONNECT_SUCCESS else connect_error_class(reason)
        OMI_STT_PROVIDER_CONNECT_TOTAL.labels(
            provider=bounded_stream_close_provider(provider),
            outcome=outcome if outcome in (CONNECT_SUCCESS, CONNECT_FAILURE) else CONNECT_FAILURE,
            error_class=error_class,
        ).inc()
    except Exception:
        pass


def initialize_stt_provider_connect_children() -> None:
    """Pre-create the success/failure children for every known provider.

    A counter series only exists after its first increment; touching ``labels``
    instantiates the child at 0 without counting a phantom attempt, so a
    provider that has never failed is queryable (and the emitter provably
    alive) from process start. Never raises.
    """

    try:
        for provider in sorted(STT_STREAM_CLOSE_PROVIDERS):
            for outcome in (CONNECT_SUCCESS, CONNECT_FAILURE):
                OMI_STT_PROVIDER_CONNECT_TOTAL.labels(
                    provider=provider,
                    outcome=outcome,
                    error_class=ERROR_CLASS_NONE if outcome == CONNECT_SUCCESS else ERROR_CLASS_OTHER,
                )
    except Exception:
        pass
