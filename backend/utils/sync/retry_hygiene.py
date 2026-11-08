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
    'running_cap_observed',
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
    # The legacy budget counts only deliveries since this epoch began
    # (dispatch_attempt_base), so a carried running-crash count never spends it.
    return retry_cap(uid, legacy_dispatch_attempts(owner) + 1, get_sync_tasks_max_attempts(), enforce=False)


def legacy_dispatch_attempts(owner: dict[str, Any]) -> int:
    """Dispatch attempts since the current epoch began; main's dispatching budget."""
    attempt = int(owner.get('dispatch_attempt') or 0)
    base = owner.get('dispatch_attempt_base')
    base = base if type(base) is int and 0 <= base <= attempt else 0
    return attempt - base


def running_expiries(owner: dict[str, Any]) -> int:
    """Running leases of the active job that expired without a run lock."""
    count = owner.get('running_expiries', 0)
    return count if type(count) is int and count >= 0 else 0


def running_cap(uid: str, owner: dict) -> RetryCap:
    """Running-state cap: the job began and its worker died, which is proven failure.

    Only class 1 (CAPTURE_RETRY_CAP_ENFORCED) may make it serve. Main never
    capped running owners, so the CAPTURE_COVERAGE_MODE serve mode or cohort
    must not turn it on while class 1 is off; then it only observes. It
    observes with coverage mode off too, so a lease that keeps expiring past
    the cap is never silent (see running_cap_observed).
    """
    return RetryCap(running_cap_reached(owner), retry_cap_enforced())


def running_cap_reached(owner: dict[str, Any]) -> bool:
    from utils.cloud_tasks import get_sync_tasks_max_attempts

    return running_expiries(owner) + 1 >= max(1, get_sync_tasks_max_attempts())


def running_cap_observed(owner: dict[str, Any]) -> None:
    """After a committed running-lease redrive: count one at-or-over-cap expiry class 1 did not enforce.

    The caller passes the pre-commit owner snapshot the reconciler decided on.
    Alert: omi-backlog-sync-running-cap-unenforced.
    """
    if owner.get('active_state') == 'dispatching' or not running_attempt_carry(owner):
        return
    if retry_cap_enforced() or not running_cap_reached(owner):
        return
    from utils.backlog_metrics import record_transition

    record_transition('sync_running_cap_observed')


def running_attempt_carry(owner: dict[str, Any]) -> bool:
    """Whether a running owner's lease expiry carries dispatch_attempt.

    Budget-deferral chains carry too: their own count (active_budget_deferrals)
    bounds deferrals, while running_expiries bounds crashes. A deferral that is
    still pending is not a crash; the caller passes that from the job's live
    deferred_until marker (see deferral_pending).
    """
    return sync_attempt_carry_enabled()


def deferral_pending(job: Any, now_seconds: float) -> bool:
    """A budget deferral's delayed replacement has not run yet (live marker)."""
    if not isinstance(job, dict):
        return False
    marker = job.get('deferred_until')
    return isinstance(marker, (int, float)) and not isinstance(marker, bool) and now_seconds < marker


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
    # (proven failure; the cap enforces only with CAPTURE_RETRY_CAP_ENFORCED on, default off).
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
