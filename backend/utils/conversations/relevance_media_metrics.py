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
    )
)


def observe(check: str, outcome: str) -> None:
    if check not in _CHECKS:
        raise ValueError('unknown media/noise check')
    SHADOW.labels(check=check, outcome=reason_label(ReasonFamily.PARITY, outcome, RefactorShadowOutcome)).inc()
    outcome = outcome if outcome in {member.value for member in RefactorShadowOutcome} else 'unknown'
    logger.info('event=refactor_shadow lane=V2 check=%s outcome=%s', check, outcome)
