"""Content-free, bounded media/noise observations."""

import logging

from prometheus_client import REGISTRY, Counter
from utils.observability.reasons import ReasonFamily, RefactorShadowOutcome, reason_label

logger = logging.getLogger(__name__)
_NAME = 'omi_media_noise_shadow_total'
SHADOW = getattr(REGISTRY, '_names_to_collectors', {}).get(_NAME) or Counter(
    _NAME, 'V2 media/noise comparisons and admission decisions.', ['check', 'outcome']
)
_CHECKS = frozenset(
    (
        'classification',
        'conversation',
        'media',
        'noise',
        'admission_live',
        'admission_sync',
        'notes',
        'daily_summary',
        'memories',
        'recap',
        'action_items',
        'boundary_write',
        'owner_memory_source',
        'owner_memory_segments',
    )
)


def observe(check: str, outcome: str) -> None:
    if check not in _CHECKS:
        raise ValueError('unknown media/noise check')
    SHADOW.labels(check=check, outcome=reason_label(ReasonFamily.PARITY, outcome, RefactorShadowOutcome)).inc()
    outcome = outcome if outcome in {member.value for member in RefactorShadowOutcome} else 'unknown'
    logger.info('event=refactor_shadow lane=V2 check=%s outcome=%s', check, outcome)


def observe_owner_memory_admission(total_segments: int, admitted_segments: int) -> None:
    """Serving-cohort attempts, not unique memories or labeled speaker accuracy.

    Reuse the exported bounded family. No account, conversation or voice ID is
    a metric label. Retries count as attempts; compare equal lookback windows.
    """
    observe('owner_memory_source', 'agree' if admitted_segments else 'disagree')
    SHADOW.labels(check='owner_memory_segments', outcome='agree').inc(admitted_segments)
    SHADOW.labels(check='owner_memory_segments', outcome='disagree').inc(total_segments - admitted_segments)
