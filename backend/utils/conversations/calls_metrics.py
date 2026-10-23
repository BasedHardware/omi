"""Content-free V4 comparisons; never user, name, text or conversation labels."""

import logging
from enum import StrEnum
from typing import cast
from prometheus_client import Counter, REGISTRY
from utils.observability.reasons import ReasonFamily, reason_label

logger = logging.getLogger(__name__)


class CallsRefactorOutcome(StrEnum):
    UNKNOWN = 'unknown'
    AGREE = 'agree'
    DISAGREE = 'disagree'
    ERROR = 'error'


def _counter() -> Counter:
    try:
        return Counter('omi_calls_refactor_shadow_total', 'V4 deterministic comparisons', ['check', 'outcome'])
    except ValueError:
        # Prometheus has no public collector lookup; mirror the notes metrics reload seam.
        collectors = REGISTRY._names_to_collectors  # pyright: ignore[reportPrivateUsage]
        return cast(Counter, collectors['omi_calls_refactor_shadow_total'])


COMPARISONS = _counter()
_CHECKS = frozenset(
    (
        'call_metadata',
        'recap_timing',
        'recap_pending',
        'recap_not_generated',
        'recap_no_recordings',
        'recap_failed',
        'recap_generated',
        'recap_generation',
        'recap_state_write',
        'action_admission',
        'stt_vocab',
        'media_consumer',
    )
)


def observe(check: str, outcome: str, *, size: int | None = None) -> None:
    check = check if check in _CHECKS else 'unknown'
    COMPARISONS.labels(check=check, outcome=reason_label(ReasonFamily.PARITY, outcome, CallsRefactorOutcome)).inc()
    outcome = outcome if outcome in {member.value for member in CallsRefactorOutcome} else 'unknown'
    logger.info(
        'event=refactor_shadow lane=V4 check=%s outcome=%s size=%s', check, outcome, size if size is not None else 0
    )
