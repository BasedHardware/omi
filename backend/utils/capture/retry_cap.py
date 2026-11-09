"""Capture-mode retry caps (dependency-free core).

Enforcement is OFF by default: the cap enforces for every uid only with
CAPTURE_RETRY_CAP_ENFORCED=true (see config/backlog_state_machine.py). With the
switch off (the default), the legacy CAPTURE_COVERAGE_MODE cohort decides, and
shadow decisions never consume or terminalize work. Kept free of Cloud Tasks and other sync-only
imports so the GPU batch worker image can use it (its dependency closure has no google-cloud-tasks).
"""

from dataclasses import dataclass
import logging

from prometheus_client import Counter

from config import refactor_modes
from config.backlog_state_machine import retry_cap_enforced

logger = logging.getLogger(__name__)
MODE = 'CAPTURE_COVERAGE_MODE'
DECISIONS = Counter('omi_capture_retry_cap_total', 'Bounded retry decisions', ['check', 'outcome'])


@dataclass(frozen=True)
class RetryCap:
    reached: bool
    serving: bool


def retry_cap(uid: str, attempts: int, maximum: int, *, enforce: bool = False) -> RetryCap | None:
    """``enforce=True`` (the batch lease-expiry cap) lets CAPTURE_RETRY_CAP_ENFORCED
    serve it for every uid. Every other caller, including main's sync dispatch
    cap, keeps the legacy CAPTURE_COVERAGE_MODE cohort decision unchanged."""
    enforced = enforce and retry_cap_enforced()
    if not enforced and not refactor_modes.shadow_or_serve(MODE):
        return None
    return RetryCap(attempts >= max(1, maximum), enforced or refactor_modes.serving_for(MODE, uid))


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
