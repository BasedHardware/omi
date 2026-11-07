"""Capture-mode retry caps for sync dispatch; the shared core lives in utils.capture.retry_cap."""

import logging
from typing import Any, Callable

from config import refactor_modes
from config.backlog_state_machine import retry_cap_enforced, sync_attempt_carry_enabled
from utils.capture.retry_cap import DECISIONS, MODE, RetryCap, observe, retry_cap

logger = logging.getLogger(__name__)
__all__ = [
    'DECISIONS',
    'MODE',
    'RetryCap',
    'observe',
    'retry_cap',
    'dispatch_cap',
    'running_cap',
    'running_expiries',
    'reconcile_dispatch_cap',
]


def dispatch_cap(uid: str, owner: dict) -> RetryCap | None:
    """Dispatching-state cap: still the CAPTURE_COVERAGE_MODE cohort decision.

    A passed dispatch retry deadline is not evidence that work failed: a
    backlogged queue delivers late, so enforcing this count by default would
    fail runnable jobs (FC-queued-delivery-invalidated-by-redrive).
    """
    if not refactor_modes.shadow_or_serve(MODE):
        return None
    from utils.cloud_tasks import get_sync_tasks_max_attempts

    # dispatch_attempt is a zero-based task identity: initial dispatch is 0.
    return retry_cap(uid, int(owner.get('dispatch_attempt') or 0) + 1, get_sync_tasks_max_attempts(), enforce=False)


def running_expiries(owner: dict[str, Any]) -> int:
    """Running leases of the active job that expired without a run lock."""
    count = owner.get('running_expiries', 0)
    return count if type(count) is int and count >= 0 else 0


def running_cap(uid: str, owner: dict) -> RetryCap | None:
    """Running-state cap: the job began and its worker died, which is proven failure.

    Enforced for every uid by default (CAPTURE_RETRY_CAP_ENFORCED). Counts this
    expiry plus earlier ones, never dispatch retries of a delayed queue.
    """
    if not retry_cap_enforced() and not refactor_modes.shadow_or_serve(MODE):
        return None
    from utils.cloud_tasks import get_sync_tasks_max_attempts

    return retry_cap(uid, running_expiries(owner) + 1, get_sync_tasks_max_attempts())


def running_attempt_carry(owner: dict[str, Any]) -> bool:
    """Whether a running owner's lease expiry counts as a spent delivery.

    A budget-deferral chain keeps its own count (active_budget_deferrals) and its
    own terminal (budget_chain_exhausted), so it keeps the legacy reset.
    """
    deferrals = owner.get('active_budget_deferrals')
    budget_chain = isinstance(deferrals, int) and not isinstance(deferrals, bool) and deferrals > 0
    return not budget_chain and sync_attempt_carry_enabled()


def reconcile_dispatch_cap(
    uid: str,
    owner: dict[str, Any],
    epoch: int,
    current: Any,
    *,
    registry: Any,
    finalize: Callable[..., bool],
    kick: Callable[[], Any],
    lease_expired: bool = False,
) -> str | None:
    # A dispatching owner's retry deadline passed (cohort-gated cap), or (with
    # attempt carry on) a running job's lease expired without a run lock
    # (proven failure, cap enforced by default).
    if owner.get('active_state') == 'dispatching':
        check, decision = 'sequencer_dispatch', dispatch_cap(uid, owner)
    elif lease_expired and running_attempt_carry(owner):
        check, decision = 'sequencer_running', running_cap(uid, owner)
    else:
        return None
    observe(check, decision)
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
        if owner.get('active_state') != 'dispatching':
            from utils.backlog_metrics import record_transition

            record_transition('sync_running_cap_reached')
        kick()
        return 'dispatch_retry_cap_reached'
    return 'raced'
