"""Persistence-layer access to the shared fallback counter, without business imports."""

import logging

from prometheus_client import Counter

OMI_FALLBACK_TOTAL = Counter(
    'omi_fallback_total',
    'Fallback / resilience transitions by component, path, reason, and outcome',
    ['component', 'from_mode', 'to_mode', 'reason', 'outcome'],
)


def record_fallback(
    *, component: str, from_mode: str, to_mode: str, reason: str, outcome: str, log: logging.Logger
) -> None:
    # These cache labels were bucketed to 'other' by the higher-level recorder.
    # Keep that exported schema while allowing persistence to emit independently.
    try:
        OMI_FALLBACK_TOTAL.labels(
            component='other', from_mode=from_mode, to_mode=to_mode, reason='other', outcome=outcome
        ).inc()
    except Exception:
        pass
    try:
        log.warning(
            'omi_fallback_event component=%s from=%s to=%s reason=%s outcome=%s',
            'other',
            from_mode,
            to_mode,
            'other',
            outcome,
        )
    except Exception:
        pass
