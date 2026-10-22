"""Content-free shadow decisions for lane L4."""

from utils.observability.reasons import ReasonFamily, reason_label, RefactorShadowOutcome
import logging

from prometheus_client import REGISTRY, Counter

logger = logging.getLogger(__name__)
_NAME = 'omi_lifecycle_refactor_shadow_total'
SHADOW = getattr(REGISTRY, '_names_to_collectors', {}).get(_NAME) or Counter(
    _NAME, 'Lane L4 shadow decisions.', ['check', 'outcome']
)


def observe(check: str, agrees: bool | None) -> None:
    outcome = 'error' if agrees is None else ('agree' if agrees else 'disagree')
    SHADOW.labels(check=check, outcome=reason_label(ReasonFamily.PARITY, outcome, RefactorShadowOutcome)).inc()
    logger.info('event=refactor_shadow lane=L4 check=%s outcome=%s', check, outcome)
