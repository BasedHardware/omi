"""Privacy-safe, bounded L3 comparison receipts; never record packet contents."""

from __future__ import annotations

import logging
from enum import StrEnum
from utils.observability.reasons import ReasonFamily, reason_label
from prometheus_client import Counter


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
SHADOW = Counter('omi_notes_refactor_shadow_total', 'L3 deterministic shadow comparisons', ['check', 'outcome'])
RESULTS = Counter('omi_notes_refactor_results_total', 'L3 serving results', ['check', 'outcome'])


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
