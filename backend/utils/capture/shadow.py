"""Bounded capture refactor comparisons; no identifiers or speech in telemetry."""

from utils.observability.reasons import ReasonFamily, reason_label, RefactorShadowOutcome
import logging

from prometheus_client import Counter

logger = logging.getLogger(__name__)
SHADOW = Counter('omi_capture_dedupe_shadow_total', 'Capture dedupe shadow comparisons', ['path', 'outcome'])


def compare(path: str, outcome: str, *, lane: str = 'L1') -> None:
    SHADOW.labels(path=path, outcome=reason_label(ReasonFamily.PARITY, outcome, RefactorShadowOutcome)).inc()
    logger.info('event=refactor_shadow lane=%s check=%s outcome=%s', lane, path, outcome)
