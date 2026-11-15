"""Ship-on durable pendant/phone disconnect and crash recovery."""

from __future__ import annotations

import logging
from typing import Any

from config.listen_quiet_finalization import enabled
from config.refactor_modes import quiet_empty_exit_enabled
from database.batch_pipeline_privacy import assert_batch_write_allowed
from database import conversation_quiet_checks as checks_db
from database.account_deletion_marker import account_deletion_blocks_user_work
from utils.account_cutover.access import should_skip_background_account_mutation
from utils.cloud_tasks import (
    enqueue_listen_finalization_job,
    is_listen_finalization_dispatch_configured,
    is_listen_finalization_dispatch_enabled,
)
from utils.conversations import lifecycle
from utils.conversations.finalization_failure import classify_finalization_failure
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


class EmptyExitChanged(RuntimeError):
    """Custody changed between evaluation and fenced deletion."""


def _empty_storage_proof(transaction: Any, uid: str, cid: str, *, firestore_client: Any = None) -> bool:
    from database._client import get_firestore_client
    from utils.other.storage import list_audio_chunks

    client = firestore_client if firestore_client is not None else get_firestore_client()
    try:
        assert_batch_write_allowed(client, transaction, uid, conversation_ids=(cid,), snapshots={})
        return not list_audio_chunks(
            uid, cid, max_count=4096, require_archive=True, include_raw=True, source_metadata=True
        )
    except Exception:
        # A failed/partial listing is never proof of absence.
        record_fallback(
            component='pusher',
            from_mode='quiet_empty_proof',
            to_mode='base_quiet_admission',
            reason='proof_refused',
            outcome='degraded',
            log=logger,
        )
        return False


def run(job_id: str, generation: int, *, firestore_client: Any = None) -> str:
    if not enabled():
        # Remove the due index so disabled checks cannot starve normal outbox
        # replay. Session setup/disconnect or the fallback scan can rearm later.
        checks_db.stop_quiet_check(job_id, generation, firestore_client=firestore_client)
        checks_db.ensure_quiet_check_progress(job_id, firestore_client=firestore_client)
        return 'disabled'
    if not is_listen_finalization_dispatch_enabled() or not is_listen_finalization_dispatch_configured():
        checks_db.ensure_quiet_check_progress(job_id, firestore_client=firestore_client)
        raise lifecycle.FinalizationDispatchUnavailable('quiet finalization dispatch is unavailable')
    proof_args = {}
    if quiet_empty_exit_enabled():
        proof_args['empty_storage_proof'] = lambda tx, uid, cid: _empty_storage_proof(
            tx, uid, cid, firestore_client=firestore_client
        )
    check = checks_db.evaluate_quiet_check(job_id, generation, firestore_client=firestore_client, **proof_args)
    if check['status'] not in {'ready', 'empty_ready', 'deferred'}:
        return check['status']
    if account_deletion_blocks_user_work(check['uid'], firestore_client=firestore_client):
        return 'account_pending_deletion'
    if should_skip_background_account_mutation(check['uid'], firestore_client=firestore_client):
        checks_db.stop_quiet_check(job_id, check['dispatch_generation'], firestore_client=firestore_client)
        return 'account_fenced'
    # Persisting and dispatching the successor before admission makes all crash
    # points retryable, including a crash just before the lifecycle transaction.
    _dispatch(check)
    if check['status'] == 'deferred':
        return 'deferred'
    if check['status'] == 'empty_ready':
        guards = {}
        if check.get('empty_exit') == 'proven_empty_storage':

            def guard(transaction, row):
                if row is None:
                    client = firestore_client
                    if client is None:
                        from database._client import get_firestore_client

                        client = get_firestore_client()
                    row = (
                        client.collection('users')
                        .document(check['uid'])
                        .collection('conversations')
                        .document(check['conversation_id'])
                        .get(transaction=transaction)
                        .to_dict()
                        or {}
                    )
                if (
                    not quiet_empty_exit_enabled()
                    or not checks_db.quiet_empty_candidate(row)
                    or not _empty_storage_proof(
                        transaction, check['uid'], check['conversation_id'], firestore_client=firestore_client
                    )
                ):
                    raise EmptyExitChanged()

            guards['transaction_guard'] = guard
        try:
            deleted = lifecycle.delete_empty_recording_conversation(
                check['uid'],
                check['conversation_id'],
                check.get('recording_session_id'),
                recovery_cutoff=check['recovery_cutoff'],
                require_expired_recording_lease=True,
                firestore_client=firestore_client,
                **guards,
            )
        except EmptyExitChanged:
            checks_db.stop_quiet_check(
                job_id,
                check['dispatch_generation'],
                failure_code='record_orphan_repair',
                firestore_client=firestore_client,
            )
            return 'deferred'
        if deleted:
            checks_db.stop_quiet_check(job_id, check['dispatch_generation'], firestore_client=firestore_client)
        elif quiet_empty_exit_enabled():
            # A failed empty admission has no attempt budget. Keep custody and
            # hand it to repair rather than repeatedly dispatching a refusal.
            checks_db.stop_quiet_check(
                job_id,
                check['dispatch_generation'],
                failure_code='record_orphan_repair',
                firestore_client=firestore_client,
            )
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
    except Exception as error:
        failure = classify_finalization_failure(error, check['conversation_id'])
        if failure.reason != DOCUMENT_SIZE_LIMIT:
            raise
        if not failure.conversation_at_size_limit:
            # The 400 names a different document: this admission can never
            # commit and closing this conversation would not shrink that
            # document. Retire the check as held (#23353) instead of answering
            # 5xx into an endless redelivery; the conversation is untouched.
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
            logger.warning(
                'event=quiet_finalization outcome=held reason=%s generation=%s document=%s',
                DOCUMENT_SIZE_LIMIT,
                generation,
                failure.document,
            )
            return DOCUMENT_SIZE_LIMIT
        # The row sits at Firestore's 1 MiB document ceiling: the finalization
        # binding grows the document, so every redelivery of this check fails
        # identically (the grpc_helpers InvalidArgument 400 group). Close it
        # through the lifecycle owner's in_progress terminal — the one write
        # the document still accepts — fenced by the check's own absolute
        # recovery cutoff, the instant the failed admission already proved the
        # row stale against, like the live listen path's _close_oversized.
        close = lifecycle.close_oversized_in_progress_conversation(
            check['uid'],
            check['conversation_id'],
            recovery_cutoff=check['recovery_cutoff'],
            firestore_client=firestore_client,
            recovery_fences=True,
        )
        logger.warning(
            'Quiet finalization hit the document size limit conversation=%s close=%s',
            check['conversation_id'],
            close,
        )
        if close not in {'closed', 'missing'}:
            # Any bounded refusal (an active writer, a row that shrank below
            # the ceiling, a new durable owner) leaves the check armed: each
            # changes what the next replay must do.
            return f'oversized_{close}'
        if close == 'closed':
            # Count the degraded terminal only when it was actually taken,
            # matching the live listen path's _close_oversized.
            record_fallback(
                component='pusher',
                from_mode='quiet_finalization_admission',
                to_mode='unstampable_terminal',
                reason=DOCUMENT_SIZE_LIMIT,
                outcome='degraded',
                log=logger,
            )
        # Terminal or gone. Retire the check — recording the size-limit code,
        # like the held path — so the reconciler cannot re-arm an admission
        # that can never commit.
        checks_db.stop_quiet_check(
            job_id,
            check['dispatch_generation'],
            failure_code=DOCUMENT_SIZE_LIMIT,
            firestore_client=firestore_client,
        )
        return f'oversized_{close}'
    return result['status']
