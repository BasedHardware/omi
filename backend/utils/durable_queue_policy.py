"""I/O-free durable-queue policy: outcomes, attempt budget, adopt, drain, age.

Async callers (pusher finalization) import this module instead of
``database.durable_queue`` so the async-blocker gate does not treat a pure
decision as Firestore I/O. Firestore-touching drain helpers and redrive live
in ``database.durable_queue``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Awaitable, Callable, Generic, Iterable, List, Optional, Sequence, TypeVar

T = TypeVar('T')

_MAX_ERROR_TEXT = 2000
_MAX_BACKOFF_EXPONENT = 30


class OutcomeKind(str, Enum):
    ACK = 'ack'
    RETRY = 'retry'
    REJECT = 'reject'


@dataclass(frozen=True)
class ProcessOutcome:
    kind: OutcomeKind
    error_text: Optional[str] = None
    reason: Optional[str] = None

    @staticmethod
    def ack() -> 'ProcessOutcome':
        return ProcessOutcome(OutcomeKind.ACK)

    @staticmethod
    def retry(error_text: str, reason: str = 'retryable') -> 'ProcessOutcome':
        return ProcessOutcome(OutcomeKind.RETRY, error_text=_bound_error(error_text), reason=reason)

    @staticmethod
    def reject(error_text: str, reason: str) -> 'ProcessOutcome':
        return ProcessOutcome(OutcomeKind.REJECT, error_text=_bound_error(error_text), reason=reason)


@dataclass(frozen=True)
class QueuePolicy:
    max_attempts: int = 5
    base_backoff_seconds: float = 1.0
    max_backoff_seconds: float = 1800.0


@dataclass(frozen=True)
class AttemptDecision:
    terminal: bool
    attempt_count: int
    available_at: Optional[datetime]
    error_text: str
    reason: str
    status: str


@dataclass(frozen=True)
class EnqueueDecision:
    adopted: bool


@dataclass(frozen=True)
class IsolatedResult(Generic[T]):
    item: T
    outcome: ProcessOutcome
    raised: bool


def _bound_error(text: str) -> str:
    return text[:_MAX_ERROR_TEXT]


def backoff_seconds(policy: QueuePolicy, attempt_count: int) -> float:
    exponent = min(max(attempt_count - 1, 0), _MAX_BACKOFF_EXPONENT)
    return min(policy.max_backoff_seconds, policy.base_backoff_seconds * (2**exponent))


def decide_attempt(
    *,
    attempt_count: int,
    outcome: ProcessOutcome,
    policy: QueuePolicy,
    now: datetime,
) -> AttemptDecision:
    """Map one failure onto retry-or-dead-letter. ``attempt_count`` includes this try."""
    if outcome.kind == OutcomeKind.ACK:
        raise ValueError('ack is not an attempt failure')
    if attempt_count < 1:
        raise ValueError('attempt_count must be at least 1')
    error_text = _bound_error(outcome.error_text or '')
    reason = outcome.reason or 'unspecified'
    terminal = outcome.kind == OutcomeKind.REJECT or attempt_count >= policy.max_attempts
    if terminal:
        return AttemptDecision(
            terminal=True,
            attempt_count=attempt_count,
            available_at=None,
            error_text=error_text,
            reason=reason,
            status='dead_letter',
        )
    return AttemptDecision(
        terminal=False,
        attempt_count=attempt_count,
        available_at=now + timedelta(seconds=backoff_seconds(policy, attempt_count)),
        error_text=error_text,
        reason=reason,
        status='retrying',
    )


def adopt_on_identity(*, existing_id: Optional[str], item_id: str) -> EnqueueDecision:
    """Collision on a stable item id is adopted. Never raise, never key on payload."""
    if not item_id:
        raise ValueError('item_id is required')
    if existing_id is None:
        return EnqueueDecision(adopted=False)
    if existing_id != item_id:
        raise ValueError('enqueue identity mismatch')
    return EnqueueDecision(adopted=True)


def ready_sort_key(
    *,
    priority: int = 0,
    available_at: object = None,
    created_at: object = None,
    item_id: str = '',
    enable_priority: bool = False,
) -> tuple[object, ...]:
    if enable_priority:
        return (priority, available_at, created_at, item_id)
    return (available_at, created_at, item_id)


def oldest_ready_age_seconds(created_ats: Sequence[Optional[datetime]], *, now: datetime) -> Optional[float]:
    ready: List[datetime] = []
    for created_at in created_ats:
        if created_at is None:
            continue
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        ready.append(created_at)
    if not ready:
        return None
    observed = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
    return max(0.0, (observed - min(ready)).total_seconds())


def drain_isolated(
    items: Iterable[T],
    process_one: Callable[[T], object],
) -> List[IsolatedResult[T]]:
    """Process each item independently. A raised or rejected item never stops the rest."""
    results: List[IsolatedResult[T]] = []
    for item in items:
        raised = False
        try:
            outcome = process_one(item)
        except Exception as exc:
            raised = True
            outcome = ProcessOutcome.reject(str(exc), reason='processor_exception')
        if not isinstance(outcome, ProcessOutcome):
            raised = True
            outcome = ProcessOutcome.reject('processor returned a non-outcome', reason='invalid_outcome')
        results.append(IsolatedResult(item=item, outcome=outcome, raised=raised))
    return results


async def drain_isolated_async(
    items: Iterable[T],
    process_one: Callable[[T], Awaitable[object]],
) -> List[IsolatedResult[T]]:
    results: List[IsolatedResult[T]] = []
    for item in items:
        raised = False
        try:
            outcome = await process_one(item)
        except Exception as exc:
            raised = True
            outcome = ProcessOutcome.reject(str(exc), reason='processor_exception')
        if not isinstance(outcome, ProcessOutcome):
            raised = True
            outcome = ProcessOutcome.reject('processor returned a non-outcome', reason='invalid_outcome')
        results.append(IsolatedResult(item=item, outcome=outcome, raised=raised))
    return results
