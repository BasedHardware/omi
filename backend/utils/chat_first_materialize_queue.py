"""Chat-first materialize drain: per-rejection isolation and batch failure signal.

HTTP 200 stays the client contract. A batch whose every intent is a hard
rejection still increments a failure counter so the run is not silent success.
"""

from __future__ import annotations

from typing import Callable, Iterable, List, TypeVar

from models.chat_first import ProactiveMaterializationRejectionOutcome
from utils.durable_queue_policy import ProcessOutcome, drain_isolated
from utils.metrics import CHAT_FIRST_PROACTIVE_TOTAL

_HARD_REJECTION_OUTCOMES = frozenset({'recorded', 'malformed'})
T = TypeVar('T')


def drain_materialize_rejections(
    rejections: Iterable[T],
    process_one: Callable[[T], ProcessOutcome],
) -> None:
    drain_isolated(list(rejections), process_one)


def record_all_hard_reject_batch(outcomes: List[ProactiveMaterializationRejectionOutcome]) -> bool:
    """Return True and increment the failure counter when every outcome is hard."""
    if not outcomes:
        return False
    if not all(outcome.outcome in _HARD_REJECTION_OUTCOMES for outcome in outcomes):
        return False
    CHAT_FIRST_PROACTIVE_TOTAL.labels(
        event='materialize_batch_rejected',
        source='materialization',
        reason='all_hard_reject',
    ).inc()
    return True
