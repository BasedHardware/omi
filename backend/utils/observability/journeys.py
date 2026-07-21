"""Closed, privacy-safe outcome metrics for real product traffic journeys."""

from __future__ import annotations

from datetime import datetime, timezone
from time import monotonic
from typing import Literal, cast

from utils.metrics import (
    OMI_CAPTURE_FINALIZATION_RECONCILIATIONS_TOTAL,
    OMI_JOURNEY_ACCEPTED_TOTAL,
    OMI_JOURNEY_LATENCY_SECONDS,
    OMI_JOURNEY_TERMINAL_TOTAL,
)

JourneyName = Literal['chat_response', 'pusher_session', 'live_transcription', 'capture_finalization']
JourneyOutcome = Literal['success', 'failure', 'cancelled', 'stale']
ReconciliationOutcome = Literal['requeued', 'enqueue_failed']

_JOURNEYS = frozenset({'chat_response', 'pusher_session', 'live_transcription', 'capture_finalization'})
_OUTCOMES = frozenset({'success', 'failure', 'cancelled', 'stale'})
_RECONCILIATION_OUTCOMES = frozenset({'requeued', 'enqueue_failed'})


def _journey(value: str) -> JourneyName:
    if value not in _JOURNEYS:
        raise ValueError(f'unknown journey: {value}')
    return cast(JourneyName, value)


def _outcome(value: str) -> JourneyOutcome:
    if value not in _OUTCOMES:
        raise ValueError(f'unknown journey outcome: {value}')
    return cast(JourneyOutcome, value)


def record_journey_accepted(journey: JourneyName) -> None:
    """Record an accepted journey after its authoritative durable/protocol boundary."""
    OMI_JOURNEY_ACCEPTED_TOTAL.labels(journey=_journey(journey)).inc()


def record_journey_terminal(journey: JourneyName, outcome: JourneyOutcome, elapsed_seconds: float) -> None:
    """Record exactly one terminal outcome and its elapsed time for one journey."""
    labels = {'journey': _journey(journey), 'outcome': _outcome(outcome)}
    OMI_JOURNEY_TERMINAL_TOTAL.labels(**labels).inc()
    OMI_JOURNEY_LATENCY_SECONDS.labels(**labels).observe(max(0.0, elapsed_seconds))


class JourneyAttempt:
    """In-process accepted journey with a one-shot terminal outcome."""

    def __init__(self, journey: JourneyName) -> None:
        self.journey: JourneyName = _journey(journey)
        self.started_at = monotonic()
        self._finished = False
        record_journey_accepted(self.journey)

    @property
    def finished(self) -> bool:
        return self._finished

    def finish(self, outcome: JourneyOutcome) -> None:
        if self._finished:
            return
        self._finished = True
        record_journey_terminal(self.journey, outcome, monotonic() - self.started_at)


def record_capture_finalization_terminal(outcome: JourneyOutcome, accepted_at: datetime | None) -> None:
    """Terminalize a durable capture job using its persisted acceptance time."""
    if accepted_at is None:
        # Legacy jobs can predate created_at. Keep the outcome visible without
        # fabricating a latency value.
        labels = {'journey': _journey('capture_finalization'), 'outcome': _outcome(outcome)}
        OMI_JOURNEY_TERMINAL_TOTAL.labels(**labels).inc()
        return
    if accepted_at.tzinfo is None:
        accepted_at = accepted_at.replace(tzinfo=timezone.utc)
    elapsed_seconds = (datetime.now(timezone.utc) - accepted_at).total_seconds()
    record_journey_terminal('capture_finalization', outcome, elapsed_seconds)


def record_capture_finalization_reconciliation(outcome: ReconciliationOutcome) -> None:
    """Record a bounded reconciliation event for stale capture work."""
    if outcome not in _RECONCILIATION_OUTCOMES:
        raise ValueError(f'unknown finalization reconciliation outcome: {outcome}')
    OMI_CAPTURE_FINALIZATION_RECONCILIATIONS_TOTAL.labels(outcome=outcome).inc()
