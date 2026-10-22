"""Capture-mode retry caps; shadow decisions never consume or terminalize work."""

from dataclasses import dataclass
import logging
from typing import Any, Callable

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


def dispatch_cap(uid: str, owner: dict) -> RetryCap | None:
    if not refactor_modes.shadow_or_serve(MODE):
        return None
    from utils.cloud_tasks import get_sync_tasks_max_attempts

    # dispatch_attempt is a zero-based task identity: initial dispatch is 0.
    return retry_cap(uid, int(owner.get('dispatch_attempt') or 0) + 1, get_sync_tasks_max_attempts())


def reconcile_dispatch_cap(
    uid: str,
    owner: dict[str, Any],
    epoch: int,
    current: Any,
    *,
    registry: Any,
    finalize: Callable[..., bool],
    kick: Callable[[], Any]
) -> str | None:
    if owner.get('active_state') != 'dispatching':
        return None
    decision = dispatch_cap(uid, owner)
    observe('sequencer_dispatch', decision)
    if decision is None or not decision.reached or not decision.serving:
        return None
    logger.error('event=sync_uid_sequencer action=sweep outcome=dispatch_retry_cap_reached')
    if not finalize(
        uid,
        owner['active_job_id'],
        epoch,
        now=current,
        failure_message='sync dispatch exhausted the attempt contract',
        reason_code='sync_dispatch_exhausted',
    ):
        registry.defer_owner(uid, registry.HEARTBEAT_SECONDS, now=current)
        return 'finalize_deferred'
    if registry.finish_expired_job(uid, owner['active_job_id'], epoch, 'dispatch_retry_cap_reached', now=current):
        kick()
        return 'dispatch_retry_cap_reached'
    return 'raced'
