"""Capture-mode retry caps (dependency-free core).

Shadow decisions never consume or terminalize work. Kept free of Cloud Tasks and other sync-only
imports so the GPU batch worker image can use it (its dependency closure has no google-cloud-tasks).
"""

from dataclasses import dataclass
import logging

from prometheus_client import Counter

from config import refactor_modes

logger = logging.getLogger(__name__)
MODE = 'CAPTURE_COVERAGE_MODE'
DECISIONS = Counter('omi_capture_retry_cap_total', 'Bounded retry decisions', ['check', 'outcome'])


@dataclass(frozen=True)
class RetryCap:
    reached: bool
    serving: bool


def retry_cap(uid: str, attempts: int, maximum: int) -> RetryCap | None:
    if not refactor_modes.shadow_or_serve(MODE):
        return None
    return RetryCap(attempts >= max(1, maximum), refactor_modes.serving_for(MODE, uid))


def observe(check: str, decision: RetryCap | None) -> None:
    if decision is None:
        return
    outcome = (
        'quarantine' if decision.reached and decision.serving else 'would_quarantine' if decision.reached else 'retry'
    )
    try:
        DECISIONS.labels(check, outcome).inc()
        if not decision.serving:
            logger.info(
                'event=refactor_shadow lane=L1 check=%s outcome=%s would_quarantine=%s',
                check,
                'disagree' if decision.reached else 'agree',
                decision.reached,
            )
    except Exception:
        pass  # Telemetry cannot change the committed retry transition.
