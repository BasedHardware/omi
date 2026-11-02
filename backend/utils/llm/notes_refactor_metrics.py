"""Privacy-safe, bounded L3 comparison receipts; never record packet contents."""

from __future__ import annotations

import logging
from enum import StrEnum
from utils.observability.reasons import ReasonFamily, reason_label
from prometheus_client import REGISTRY, Counter


class NotesRefactorOutcome(StrEnum):
    UNKNOWN = 'unknown'
    AGREE = 'agree'
    DISAGREE = 'disagree'
    ERROR = 'error'
    MINIMUM = 'minimum'
    REPAIRED = 'repaired'
    PASSED = 'passed'
    ACCEPTED_WITH_PROBLEMS = 'accepted_with_problems'


logger = logging.getLogger(__name__)


def _counter(name: str, documentation: str) -> Counter:
    # Re-imports (test harnesses that re-exec importers) must reuse the registered collector.
    try:
        return Counter(name, documentation, ['check', 'outcome'])
    except ValueError:
        return REGISTRY._names_to_collectors[name]  # type: ignore[return-value]


SHADOW = _counter('omi_notes_refactor_shadow_total', 'L3 deterministic shadow comparisons')
RESULTS = _counter('omi_notes_refactor_results_total', 'L3 serving results')


def shadow(check: str, outcome: str, **sizes: int) -> None:
    SHADOW.labels(check=check, outcome=reason_label(ReasonFamily.PARITY, outcome, NotesRefactorOutcome)).inc()
    logger.info(
        'event=refactor_shadow lane=L3 check=%s outcome=%s sizes=%s',
        check,
        outcome,
        ','.join(f'{key}:{value}' for key, value in sorted(sizes.items())),
    )


def result(check: str, outcome: str) -> None:
    RESULTS.labels(check=check, outcome=reason_label(ReasonFamily.PARITY, outcome, NotesRefactorOutcome)).inc()
