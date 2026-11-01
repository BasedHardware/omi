"""Capture-mode retry caps for sync dispatch; the shared core lives in utils.capture.retry_cap."""

import logging
from typing import Any, Callable

from config import refactor_modes
from utils.capture.retry_cap import DECISIONS, MODE, RetryCap, observe, retry_cap

logger = logging.getLogger(__name__)
__all__ = ['DECISIONS', 'MODE', 'RetryCap', 'observe', 'retry_cap', 'dispatch_cap', 'reconcile_dispatch_cap']


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
