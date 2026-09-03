"""Firestore-touching durable-queue drain helpers and redrive.

Pure policy (outcomes, decide_attempt, drain_isolated, age helpers) lives in
``utils.durable_queue_policy`` so async callers can import it without the
async-blocker treating ``database.*`` as I/O. This module re-exports those
names for database-layer callers and owns the additive redrive patch.
Store-wide oldest-ready sampling lives in ``database.durable_queue_age``.
"""

from __future__ import annotations

from datetime import datetime

from utils.durable_queue_policy import (
    AttemptDecision,
    EnqueueDecision,
    IsolatedResult,
    OutcomeKind,
    ProcessOutcome,
    QueuePolicy,
    adopt_on_identity,
    backoff_seconds,
    decide_attempt,
    drain_isolated,
    drain_isolated_async,
    oldest_ready_age_seconds,
    ready_sort_key,
)


def redrive_patch(*, now: datetime) -> dict:
    """Additive fields to move a dead letter back to ready by identity."""
    return {
        'status': 'pending',
        'attempt_count': 0,
        'available_at': now,
        'dead_letter_reason': None,
        'last_error_text': None,
        'updated_at': now,
    }


__all__ = [
    'AttemptDecision',
    'EnqueueDecision',
    'IsolatedResult',
    'OutcomeKind',
    'ProcessOutcome',
    'QueuePolicy',
    'adopt_on_identity',
    'backoff_seconds',
    'decide_attempt',
    'drain_isolated',
    'drain_isolated_async',
    'oldest_ready_age_seconds',
    'ready_sort_key',
    'redrive_patch',
]
