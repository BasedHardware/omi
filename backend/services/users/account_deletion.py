from __future__ import annotations

import logging

import time
from typing import Any, Callable, Literal, TypedDict, cast

from database import vector_db
from database import users as users_db
from database.action_items import get_action_item_ids
from database.conversations import get_conversation_ids
from database.memories import get_memory_ids
from database.screen_activity import get_screen_activity_ids
from database.vector_db import (
    delete_action_item_vectors_batch,
    delete_conversation_vectors_batch,
    delete_memory_vectors_batch,
    delete_screen_activity_vectors,
    delete_transcript_chunk_vectors_batch,
)
from utils import stripe as stripe_utils
from utils.cloud_tasks import enqueue_account_deletion_wipe, is_account_deletion_dispatch_enabled
from utils.executors import cleanup_executor, submit_with_context
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth
from utils.memory.canonical_memory_adapter import purge_canonical_derived_user_data
from utils.other.storage import delete_all_conversation_recordings
from utils.twilio_service import delete_user_caller_ids_strict as delete_user_caller_ids

logger = logging.getLogger(__name__)


class PurgeFailure(TypedDict):
    operation: str
    error: str


class PurgeResult(TypedDict):
    required_failures: list[PurgeFailure]
    best_effort_failures: list[PurgeFailure]


def purge_derived_user_data(uid: str) -> PurgeResult:
    """Purge a user's derived data outside Firestore.

    Required failures must block the Firestore wipe because those IDs are
    stored in Firestore and may become unrecoverable after ``delete_user_data``.
    Best-effort failures are safe to retry independently or leave behind.
    """
    result: PurgeResult = {'required_failures': [], 'best_effort_failures': []}

    def record_failure(
        kind: Literal['required_failures', 'best_effort_failures'], operation: str, error: Exception
    ) -> None:
        result[kind].append({'operation': operation, 'error': sanitize(str(error))})

    def require_deleted_count(operation: str, expected: int, deleted: int | None):
        if expected and isinstance(deleted, int) and deleted < expected:
            raise RuntimeError(f'{operation} only deleted {deleted}/{expected} records')

    def require_vector_index(operation: str):
        if vector_db.index is None:
            raise RuntimeError(f'Pinecone index not initialized for {operation}')

    try:
        conversation_ids = get_conversation_ids(uid)
        if conversation_ids:
            require_vector_index('conversation_vectors')
            delete_conversation_vectors_batch(uid, conversation_ids)
    except Exception as e:
        record_failure('required_failures', 'conversation_vectors', e)
        logger.error(f'delete_account purge conversation vectors failed for {uid}: {sanitize(str(e))}')

    try:
        conversation_ids = get_conversation_ids(uid)
        if conversation_ids:
            require_vector_index('transcript_chunk_vectors')
            delete_transcript_chunk_vectors_batch(uid, conversation_ids, raise_on_failure=True)
    except Exception as e:
        record_failure('required_failures', 'transcript_chunk_vectors', e)
        logger.error(f'delete_account purge transcript chunk vectors failed for {uid}: {sanitize(str(e))}')

    try:
        memory_ids = get_memory_ids(uid)
        if memory_ids:
            require_vector_index('memory_vectors')
            deleted = delete_memory_vectors_batch(uid, memory_ids)
            require_deleted_count('memory_vectors', len(memory_ids), deleted)
    except Exception as e:
        record_failure('required_failures', 'memory_vectors', e)
        logger.error(f'delete_account purge memory vectors failed for {uid}: {sanitize(str(e))}')

    try:
        action_item_ids = get_action_item_ids(uid)
        if action_item_ids:
            require_vector_index('action_item_vectors')
            delete_action_item_vectors_batch(uid, action_item_ids)
    except Exception as e:
        record_failure('required_failures', 'action_item_vectors', e)
        logger.error(f'delete_account purge action item vectors failed for {uid}: {sanitize(str(e))}')

    try:
        screen_activity_ids = get_screen_activity_ids(uid)
        if screen_activity_ids:
            require_vector_index('screen_activity_vectors')
            delete_screen_activity_vectors(uid, screen_activity_ids)
    except Exception as e:
        record_failure('required_failures', 'screen_activity_vectors', e)
        logger.error(f'delete_account purge screen activity vectors failed for {uid}: {sanitize(str(e))}')

    try:
        delete_all_conversation_recordings(uid)
    except Exception as e:
        record_failure('required_failures', 'conversation_recordings', e)
        logger.error(f'delete_account purge recordings failed for {uid}: {sanitize(str(e))}')

    try:
        purge_canonical_derived_user_data(uid)
    except Exception as e:
        record_failure('required_failures', 'canonical_derived_data', e)
        logger.error(f'delete_account purge canonical vectors failed for {uid}: {sanitize(str(e))}')

    return result


def _required_failures_from_purge_result(purge_result: object) -> list[PurgeFailure]:
    if not isinstance(purge_result, dict):
        return []
    purge_result_dict = cast(dict[str, object], purge_result)
    required_failures_value = purge_result_dict.get('required_failures', [])
    if not isinstance(required_failures_value, list):
        return []
    required_failure_items = cast(list[object], required_failures_value)
    failures: list[PurgeFailure] = []
    for failure in required_failure_items:
        if not isinstance(failure, dict):
            continue
        failure_dict = cast(dict[str, object], failure)
        failures.append(
            {'operation': str(failure_dict.get('operation', 'unknown')), 'error': str(failure_dict.get('error', ''))}
        )
    return failures


def background_wipe_user_data(uid: str) -> bool:
    try:
        # Transition to ``running`` so the reconciler can distinguish a
        # genuinely orphaned ``pending`` marker (queued but never started)
        # from a wipe that is actively executing. Without this, a slow wipe
        # could be duplicate-claimed after the short ``pending`` stale window.
        users_db.mark_user_deletion_wipe_running(uid)
        # The durable marker and queue claim are the authority for every
        # irreversible step below. In particular, do not cancel billing or
        # remove Firebase Auth from the request thread: a queue NotFound must
        # leave an account usable and recoverable.
        _cancel_subscription_for_account_deletion(uid)
        try:
            auth.delete_account(uid)
        except Exception as e:
            err = str(e).upper()
            if 'USER_NOT_FOUND' in err or 'NO USER RECORD' in err:
                logger.info('delete_account worker observed Firebase Auth user already absent')
            else:
                raise
        # Twilio caller IDs first, while the phone_numbers subcollection still carries twilio_sid metadata.
        delete_user_caller_ids(uid)
        purge_result = purge_derived_user_data(uid)
        required_failures = _required_failures_from_purge_result(purge_result)
        if required_failures:
            failed_operations = ', '.join(failure['operation'] for failure in required_failures)
            raise RuntimeError(f'required derived purge failed: {failed_operations}')
        wipe_result = users_db.delete_user_data(uid)
        if wipe_result.get('status') != 'ok':
            raise RuntimeError('authoritative Firestore user-data wipe did not complete')
        logger.info('delete_account background wipe complete')
    except Exception as e:
        logger.error(f'delete_account background wipe failed for {uid}: {sanitize(str(e))}')
        # Mark the wipe as failed so a reconciliation worker can retry. Do NOT mark
        # completed — that would hide a partial wipe from the recovery path.
        try:
            users_db.mark_user_deletion_wipe_failed(uid)
        except Exception as persist_err:
            logger.error(f'delete_account wipe status persist failed for {uid}: {sanitize(str(persist_err))}')
        return False
    else:
        try:
            users_db.mark_user_deletion_wipe_completed(uid)
        except Exception as e:
            logger.error(f'delete_account wipe status persist failed for {uid}: {sanitize(str(e))}')
        return True


def enqueue_deletion_wipe(uid: str, wipe_job_id: str):
    """Dispatch the account-deletion wipe using the configured durable mechanism."""
    if is_account_deletion_dispatch_enabled() is True:
        enqueue_account_deletion_wipe(wipe_job_id)
        return
    # Inline dispatch is retained solely for deterministic local/dev/test
    # execution. Production startup rejects this mode before serving traffic.
    submit_with_context(cleanup_executor, background_wipe_user_data, uid)


def _mark_wipe_failed_after_enqueue_error(uid: str, error: Exception):
    try:
        users_db.mark_user_deletion_wipe_failed(uid)
    except Exception as persist_err:
        logger.error(
            f'delete_account enqueue failure status persist failed for {uid}: {sanitize(str(persist_err))}; '
            f'original enqueue error: {sanitize(str(error))}'
        )


def _retry_firestore_write(
    fn: Callable[[], Any],
    *,
    uid: str,
    fail_msg: str,
    on_failure: Literal['raise', 'log'],
    max_attempts: int = 3,
    retry_delay: float = 0.5,
) -> Any:
    """Retry a transient Firestore write, then raise or log on persistent failure."""
    last_err: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if attempt < max_attempts - 1:
                time.sleep(retry_delay * (attempt + 1))
    assert last_err is not None
    msg = f'{fail_msg} after {max_attempts} attempts for {uid}: {sanitize(str(last_err))}'
    if on_failure == 'raise':
        raise Exception(msg)
    logger.critical(msg)


def _cancel_subscription_for_account_deletion(uid: str) -> None:
    subscription_id = None
    try:
        sub = users_db.get_user_subscription(uid)
        subscription_id = getattr(sub, 'stripe_subscription_id', None) if sub else None
        if not subscription_id:
            return
        canceled = stripe_utils.cancel_subscription(subscription_id)
        if not canceled:
            raise RuntimeError('stripe cancel returned no subscription')
    except Exception as e:
        raw_error = str(e)
        sanitized_error = sanitize(raw_error)
        if not isinstance(
            sanitized_error, str
        ):  # pyright: ignore[reportUnnecessaryIsInstance]  # tests stub sanitize with MagicMock
            sanitized_error = raw_error
        _retry_firestore_write(
            lambda: users_db.mark_user_deletion_billing_failed(uid, subscription_id, sanitized_error),
            uid=uid,
            fail_msg='delete_account billing failure status persist failed',
            on_failure='log',
        )
        logger.error(f'delete_account billing cancellation failed for {uid}: {sanitize(str(e))}')
        raise


def start_account_deletion(uid: str, reason: str | None = None, reason_details: str | None = None) -> dict[str, str]:
    if reason or reason_details:
        try:
            users_db.set_user_deletion_feedback(uid, reason, reason_details)
        except Exception as e:
            logger.info(f'delete_account feedback store failed: {sanitize(str(e))}')

    # Persist the authoritative, actionable intent before dispatch. This state
    # is enough for reconciliation to recover a failed queue handoff, while the
    # Cloud Tasks handler claim fences all destructive work. If either write or
    # dispatch fails, no Firebase Auth or billing mutation has happened.
    wipe_intent = _retry_firestore_write(
        lambda: users_db.mark_user_deletion_wipe_intent(uid),
        uid=uid,
        fail_msg='Failed to persist deletion-wipe intent',
        on_failure='raise',
    )
    wipe_job_id = wipe_intent.get('wipe_job_id') if isinstance(wipe_intent, dict) else None
    if not isinstance(wipe_job_id, str) or not wipe_job_id:
        raise RuntimeError('deletion-wipe intent did not persist a wipe_job_id')
    dispatch_claimed = wipe_intent.get('dispatch_claimed') is True if isinstance(wipe_intent, dict) else False
    if not dispatch_claimed:
        logger.info('delete_account joined existing durable deletion intent')
        return {'status': 'ok', 'message': 'Account deletion started'}

    # The pending marker is persisted before enqueue. A failed enqueue is
    # recorded as failed and is therefore independently recoverable by the
    # reconciler; queue delivery accelerates the wipe but is not its only
    # durability boundary.
    pending_transitioned = _retry_firestore_write(
        lambda: users_db.mark_user_deletion_wipe_started(uid, wipe_job_id),
        uid=uid,
        fail_msg='delete_account marker transition to pending failed',
        on_failure='raise',
    )
    if pending_transitioned is not True:
        # Another execution owns the durable authority. Do not move its marker
        # backwards or dispatch a duplicate task.
        logger.info('delete_account queue transition already owned by another request')
        return {'status': 'ok', 'message': 'Account deletion started'}

    try:
        enqueue_deletion_wipe(uid, wipe_job_id)
    except Exception as e:
        _mark_wipe_failed_after_enqueue_error(uid, e)
        logger.warning('delete_account queue acceleration failed; durable reconciliation will retry')
        # The actionable marker is committed. Queue dispatch is only an
        # acceleration path; reconciliation owns eventual completion.
        return {'status': 'ok', 'message': 'Account deletion started'}

    logger.info('delete_account accepted durable deletion intent and queue acceleration')
    return {'status': 'ok', 'message': 'Account deletion started'}


def _is_auth_user_gone(uid: str) -> bool:
    """Check whether the Firebase auth user for ``uid`` no longer exists.

    Returns ``True`` if the user was already deleted (``USER_NOT_FOUND`` or
    equivalent). Returns ``False`` on any other error — fail safe so a transient
    Firebase outage does not trigger a data wipe for a user whose auth account
    may still exist.
    """
    try:
        auth.get_user(uid)
        return False
    except Exception as e:
        err = str(e).upper()
        if 'USER_NOT_FOUND' in err or 'NO USER RECORD' in err:
            return True
        # Indeterminate — do NOT treat as gone.
        logger.warning(f'delete_account auth-user-gone check indeterminate for {uid}: {sanitize(str(e))}')
        return False


def reconcile_pending_deletion_wipes(limit: int = 100) -> dict[str, int]:
    """Re-enqueue account-deletion wipes that were cancelled or failed.

    Called by a periodic worker (cron, Cloud Scheduler, or startup hook) to drain
    the ``wipe_status in ('pending', 'failed', 'retrying')`` backlog left behind
    when a durable task enqueue or worker execution failed.

    Also recovers stale ``'deleting_auth'`` records — markers where the deletion
    intent was written but never transitioned to ``'pending'`` (usually a crash
    or deploy after ``auth.delete_account()`` succeeded). For these records, the
    Firebase auth user is verified gone *before* claiming and re-enqueueing, so a
    transient Firebase outage or a record left by an in-progress deletion cannot
    trigger a premature data wipe for a user whose auth account still exists.

    Each wipe is atomically claimed via a Firestore transaction before
    re-enqueueing, so concurrent workers or overlapping scheduler runs cannot
    double-enqueue the same wipe.

    Returns a summary dict with counts of re-enqueued and skipped wipes.
    """
    requeued = 0
    skipped = 0
    try:
        pending = users_db.get_pending_deletion_wipes(limit=limit)
    except Exception as e:
        logger.error(f'delete_account reconciliation query failed: {sanitize(str(e))}')
        return {'requeued': 0, 'skipped': 0, 'error': 1}

    for record in pending:
        uid = record.get('uid')
        if uid is not None and not isinstance(uid, str):
            skipped += 1
            continue
        if not uid:
            skipped += 1
            continue
        # P1 recovery: a 'deleting_auth' record means the intent was written but
        # the marker was never transitioned to 'pending'. Verify the Firebase
        # auth user is actually gone before claiming it, so we never wipe data
        # for a user whose auth account may still exist.
        if record.get('wipe_status') == 'deleting_auth':
            if not _is_auth_user_gone(uid):
                skipped += 1
                logger.info(
                    f'delete_account reconciliation skipping deleting_auth record for {uid} — auth user still exists'
                )
                continue
        # Atomically claim the wipe to prevent concurrent re-enqueueing by
        # multiple workers. If the claim fails, another worker owns it.
        try:
            claimed_uid = users_db.claim_deletion_wipe(uid)
        except Exception as e:
            logger.error(f'delete_account reconciliation claim failed for {uid}: {sanitize(str(e))}')
            skipped += 1
            continue
        if claimed_uid is None:
            skipped += 1
            continue
        wipe_job_id = record.get('wipe_job_id')
        if not isinstance(wipe_job_id, str) or not wipe_job_id:
            try:
                wipe_job_id = users_db.ensure_deletion_wipe_job_id(uid)
            except Exception as e:
                logger.error(f'delete_account reconciliation job-id recovery failed for {uid}: {sanitize(str(e))}')
                _mark_wipe_failed_after_enqueue_error(uid, e)
                skipped += 1
                continue
        if not isinstance(wipe_job_id, str) or not wipe_job_id:
            error = RuntimeError('deletion-wipe job id missing after recovery')
            logger.error(f'delete_account reconciliation cannot dispatch {uid}: {error}')
            _mark_wipe_failed_after_enqueue_error(uid, error)
            skipped += 1
            continue
        try:
            enqueue_deletion_wipe(uid, wipe_job_id)
        except Exception as e:
            logger.error(f'delete_account reconciliation enqueue failed for {uid}: {sanitize(str(e))}')
            _mark_wipe_failed_after_enqueue_error(uid, e)
            skipped += 1
            continue
        requeued += 1
        logger.info(f'delete_account reconciliation re-enqueued wipe for {uid}')

    if requeued:
        logger.info(f'delete_account reconciliation: re-enqueued {requeued}, skipped {skipped}')
    return {'requeued': requeued, 'skipped': skipped}
