"""Privacy-safe, bounded L3 comparison receipts; never record packet contents."""

from __future__ import annotations

import logging
from prometheus_client import Counter

logger = logging.getLogger(__name__)
SHADOW = Counter('omi_notes_refactor_shadow_total', 'L3 deterministic shadow comparisons', ['check', 'outcome'])
RESULTS = Counter('omi_notes_refactor_results_total', 'L3 serving results', ['check', 'outcome'])


def shadow(check: str, outcome: str, **sizes: int) -> None:
    SHADOW.labels(check=check, outcome=outcome).inc()
    logger.info(
        'event=refactor_shadow lane=L3 check=%s outcome=%s sizes=%s',
        check,
        outcome,
        ','.join(f'{key}:{value}' for key, value in sorted(sizes.items())),
    )


def result(check: str, outcome: str) -> None:
    RESULTS.labels(check=check, outcome=outcome).inc()
