"""Bounded counters for provider STT stream-close reasons.

Vendor error frames already carry a typed death reason. This module is the
closed label set those frames increment so budget/quota exhaustion is countable
without putting raw vendor messages on a metric label.
"""

from __future__ import annotations

from typing import Optional

from utils.metrics import OMI_STT_STREAM_CLOSE_TOTAL

PROVIDER_BUDGET_EXHAUSTED = 'provider_budget_exhausted'

STT_STREAM_CLOSE_PROVIDERS = frozenset({'soniox', 'modulate', 'deepgram', 'parakeet'})
STT_STREAM_CLOSE_REASONS = frozenset(
    {
        PROVIDER_BUDGET_EXHAUSTED,
        'soniox_idle_timeout',
        'soniox_rotation',
        'soniox_invalid_hint',
        'modulate_serve_error',
        'connection_lost',
    }
)


def bounded_stream_close_provider(provider: str) -> str:
    label = (provider or '').strip().lower()
    return label if label in STT_STREAM_CLOSE_PROVIDERS else 'unknown'


def bounded_stream_close_reason(reason: Optional[str]) -> str:
    label = (reason or '').strip().lower()
    return label if label in STT_STREAM_CLOSE_REASONS else 'connection_lost'


def record_stt_stream_close(*, provider: str, reason: Optional[str]) -> None:
    """Increment ``omi_stt_stream_close_total``. Never raises."""

    try:
        OMI_STT_STREAM_CLOSE_TOTAL.labels(
            provider=bounded_stream_close_provider(provider),
            reason=bounded_stream_close_reason(reason),
        ).inc()
    except Exception:
        pass
