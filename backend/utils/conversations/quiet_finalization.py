"""Ship-on durable pendant/phone disconnect and crash recovery."""

from __future__ import annotations

import logging
from typing import Any

from config.listen_quiet_finalization import enabled
from database import conversation_quiet_checks as checks_db
from utils.account_cutover.access import should_skip_background_account_mutation
from utils.cloud_tasks import (
    enqueue_listen_finalization_job,
    is_listen_finalization_dispatch_configured,
    is_listen_finalization_dispatch_enabled,
)
from utils.conversations import lifecycle
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.metrics import CONVERSATION_ORPHANED_UNFINALIZED
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def _dispatch(check: dict[str, Any]) -> None:
    # Listen/GKE intentionally retains inline pusher finalization. Its check
    # is still durable; the Cloud Run reconciler owns the indexed wake when
    # this producer has no finalization queue binding.
    if not is_listen_finalization_dispatch_configured():
        return
    try:
        enqueue_listen_finalization_job(
            check['job_id'], check['dispatch_generation'], schedule_at=int(check['due_at'].timestamp()) + 1
        )
    except Exception as error:
        # The outbox's indexed due instant survives both enqueue failure and
        # process death. The existing bounded reconciler replays this check.
        record_fallback(
            component='pusher',
            from_mode='cloud_tasks',
            to_mode='durable_queued',
            reason='enqueue_failed',
            outcome='degraded',
            log=logger,
        )
        logger.warning('Quiet finalization wake failed type=%s', type(error).__name__)


def arm(
    uid: str, conversation_id: str, timeout: float, *, requires_byok: bool = False, firestore_client: Any = None
) -> None:
    if not enabled():
        return
    check = checks_db.arm_quiet_check(
        uid, conversation_id, timeout, requires_byok=requires_byok, firestore_client=firestore_client
    )
    if check is not None:
        _dispatch(check)


def run(job_id: str, generation: int, *, firestore_client: Any = None) -> str:
    if not enabled():
        # Remove the due index so disabled checks cannot starve normal outbox
        # replay. Session setup/disconnect or the fallback scan can rearm later.
        checks_db.stop_quiet_check(job_id, generation, firestore_client=firestore_client)
        return 'disabled'
    if not is_listen_finalization_dispatch_enabled() or not is_listen_finalization_dispatch_configured():
        raise lifecycle.FinalizationDispatchUnavailable('quiet finalization dispatch is unavailable')
    check = checks_db.evaluate_quiet_check(job_id, generation, firestore_client=firestore_client)
    if check['status'] not in {'ready', 'deferred'}:
        return check['status']
    if should_skip_background_account_mutation(check['uid'], firestore_client=firestore_client):
        checks_db.stop_quiet_check(job_id, check['dispatch_generation'], firestore_client=firestore_client)
        return 'account_fenced'
    # Persisting and dispatching the successor before admission makes all crash
    # points retryable, including a crash just before the lifecycle transaction.
    _dispatch(check)
    if check['status'] == 'deferred':
        return 'deferred'
    CONVERSATION_ORPHANED_UNFINALIZED.inc()
    result = lifecycle.request_finalization(
        check['uid'],
        check['conversation_id'],
        has_byok_keys=False,
        trigger=ProcessingTrigger.SERVER_RECOVERY,
        require_cloud_tasks=True,
        recovery_cutoff=check['recovery_cutoff'],
        require_expired_recording_lease=True,
        firestore_client=firestore_client,
    )
    return result['status']
