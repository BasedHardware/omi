"""Ship-on durable pendant/phone disconnect and crash recovery."""

from __future__ import annotations

import logging
from typing import Any

from google.api_core.exceptions import InvalidArgument

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

DOCUMENT_SIZE_LIMIT = 'document_size_limit'


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
    if check['status'] not in {'ready', 'empty_ready', 'deferred'}:
        return check['status']
    if should_skip_background_account_mutation(check['uid'], firestore_client=firestore_client):
        checks_db.stop_quiet_check(job_id, check['dispatch_generation'], firestore_client=firestore_client)
        return 'account_fenced'
    # Persisting and dispatching the successor before admission makes all crash
    # points retryable, including a crash just before the lifecycle transaction.
    _dispatch(check)
    if check['status'] == 'deferred':
        return 'deferred'
    if check['status'] == 'empty_ready':
        deleted = lifecycle.delete_empty_recording_conversation(
            check['uid'],
            check['conversation_id'],
            check.get('recording_session_id'),
            recovery_cutoff=check['recovery_cutoff'],
            require_expired_recording_lease=True,
            firestore_client=firestore_client,
        )
        if deleted:
            checks_db.stop_quiet_check(job_id, check['dispatch_generation'], firestore_client=firestore_client)
        return 'empty_deleted' if deleted else 'deferred'
    CONVERSATION_ORPHANED_UNFINALIZED.inc()
    try:
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
    except InvalidArgument as error:
        # Imported at the call: unit suites stub database._client without this predicate.
        from database._client import is_document_size_limit_error

        if not is_document_size_limit_error(error):
            raise
        # The conversation row sits at Firestore's 1 MiB ceiling, so the
        # admission stamp can never be written: every reserved wake would fail
        # the same way (#23341). Retire the successor this run already
        # dispatched instead of answering 5xx into an endless retry; the
        # conversation itself is left untouched.
        checks_db.stop_quiet_check(
            job_id,
            check['dispatch_generation'],
            failure_code=DOCUMENT_SIZE_LIMIT,
            firestore_client=firestore_client,
        )
        record_fallback(
            component='conversation_finalization',
            from_mode='quiet_check',
            to_mode='held',
            reason=DOCUMENT_SIZE_LIMIT,
            outcome='exhausted',
            log=logger,
        )
        logger.warning('event=quiet_finalization outcome=held reason=%s generation=%s', DOCUMENT_SIZE_LIMIT, generation)
        return DOCUMENT_SIZE_LIMIT
    return result['status']
