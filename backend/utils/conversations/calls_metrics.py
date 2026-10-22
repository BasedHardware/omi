"""Content-free V4 comparisons; never user, name, text or conversation labels."""

import logging
from enum import StrEnum
from prometheus_client import Counter
from utils.observability.reasons import ReasonFamily, reason_label

logger = logging.getLogger(__name__)


class CallsRefactorOutcome(StrEnum):
    UNKNOWN = 'unknown'
    AGREE = 'agree'
    DISAGREE = 'disagree'
    ERROR = 'error'


COMPARISONS = Counter('omi_calls_refactor_shadow_total', 'V4 deterministic comparisons', ['check', 'outcome'])
_CHECKS = frozenset(
    (
        'call_metadata',
        'recap_timing',
        'recap_pending',
        'recap_no_recordings',
        'recap_failed',
        'recap_generated',
        'recap_generation',
        'recap_state_write',
        'action_admission',
        'stt_vocab',
    )
)


def observe(check: str, outcome: str, *, size: int | None = None) -> None:
    check = check if check in _CHECKS else 'unknown'
    outcome = reason_label(ReasonFamily.PARITY, outcome, CallsRefactorOutcome)
    COMPARISONS.labels(check=check, outcome=outcome).inc()
    logger.info(
        'event=refactor_shadow lane=V4 check=%s outcome=%s size=%s', check, outcome, size if size is not None else 0
    )
