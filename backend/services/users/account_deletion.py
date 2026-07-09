from __future__ import annotations

import logging

import time
from typing import Literal, TypedDict, cast

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
        try:
            users_db.mark_user_deletion_wipe_running(uid)
        except Exception as e:
            logger.warning(f'delete_account marker transition to running failed for {uid}: {sanitize(str(e))}')
        # Twilio caller IDs first, while the phone_numbers subcollection still carries twilio_sid metadata.
        delete_user_caller_ids(uid)
        purge_result = purge_derived_user_data(uid)
        required_failures = _required_failures_from_purge_result(purge_result)
        if required_failures:
            failed_operations = ', '.join(failure['operation'] for failure in required_failures)
            raise RuntimeError(f'required derived purge failed: {failed_operations}')
        users_db.delete_user_data(uid)
        logger.info(f'delete_account background wipe complete for {uid}')
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


def enqueue_deletion_wipe(uid: str):
    """Dispatch the account-deletion wipe using the configured durable mechanism."""
    if is_account_deletion_dispatch_enabled() is True:
        enqueue_account_deletion_wipe(uid)
        return
    submit_with_context(cleanup_executor, background_wipe_user_data, uid)


def _mark_wipe_failed_after_enqueue_error(uid: str, error: Exception):
    try:
        users_db.mark_user_deletion_wipe_failed(uid)
    except Exception as persist_err:
        logger.error(
            f'delete_account enqueue failure status persist failed for {uid}: {sanitize(str(persist_err))}; '
            f'original enqueue error: {sanitize(str(error))}'
        )


def _persist_wipe_intent_with_retry(uid: str, max_attempts: int = 3, retry_delay: float = 0.5) -> None:
    """Persist the non-actionable deletion intent, retrying transient Firestore failures.

    Writes ``wipe_status='deleting_auth'`` which the reconciler only recovers
    *after* verifying the Firebase auth user is actually gone. A crash or deploy
    between this write and ``auth.delete_account()`` therefore leaves a benign
    record that cannot trigger a premature data wipe for a user whose Firebase
    account still exists.

    Raises on persistent failure so the caller can surface the error to the user
    rather than proceeding to the irreversible Firebase user deletion without a
    durable recovery marker.
    """
    last_err = None
    for attempt in range(max_attempts):
        try:
            users_db.mark_user_deletion_wipe_intent(uid)
            return
        except Exception as e:
            last_err = e
            if attempt < max_attempts - 1:
                time.sleep(retry_delay * (attempt + 1))
    raise Exception(
        f'Failed to persist deletion-wipe intent after {max_attempts} attempts for {uid}: {sanitize(str(last_err))}'
    )


def _persist_wipe_marker_with_retry(uid: str, max_attempts: int = 3, retry_delay: float = 0.5) -> None:
    """Transition the marker to the actionable ``'pending'`` state after auth deletion is confirmed.

    Called only after ``auth.delete_account()`` has succeeded (or the user was
    already gone). Raises on persistent failure so callers do not enqueue or
    report success without an actionable wipe marker. A stale
    ``'deleting_auth'`` marker remains recoverable: the reconciler verifies the
    auth user is gone before re-enqueueing the wipe.
    """
    last_err = None
    for attempt in range(max_attempts):
        try:
            users_db.mark_user_deletion_wipe_started(uid)
            return
        except Exception as e:
            last_err = e
            if attempt < max_attempts - 1:
                time.sleep(retry_delay * (attempt + 1))
    raise Exception(
        f'delete_account marker transition to pending failed after {max_attempts} attempts for {uid}: '
        f'{sanitize(str(last_err))}'
    )


def _mark_billing_failed_with_retry(
    uid: str, subscription_id: str | None, error: Exception, max_attempts: int = 3, retry_delay: float = 0.5
) -> None:
    last_err = None
    raw_error = str(error)
    sanitized_error = sanitize(raw_error)
    if not isinstance(
        sanitized_error, str
    ):  # pyright: ignore[reportUnnecessaryIsInstance]  # tests stub sanitize with MagicMock
        sanitized_error = raw_error
    for attempt in range(max_attempts):
        try:
            users_db.mark_user_deletion_billing_failed(uid, subscription_id, sanitized_error)
            return
        except Exception as e:
            last_err = e
            if attempt < max_attempts - 1:
                time.sleep(retry_delay * (attempt + 1))
    logger.critical(
        f'delete_account billing failure status persist failed after {max_attempts} attempts for {uid}: '
        f'{sanitize(str(last_err))}; original billing error: {sanitized_error}'
    )


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
        _mark_billing_failed_with_retry(uid, subscription_id, e)
        logger.error(f'delete_account billing cancellation failed for {uid}: {sanitize(str(e))}')
        raise


def _cancel_wipe_marker_with_retry(uid: str, max_attempts: int = 3, retry_delay: float = 0.5) -> None:
    """Cancel the pending-deletion marker, retrying transient Firestore failures.

    Used when auth.delete_account() fails after the marker was already persisted.
    Escalates to a critical log (not an exception) if cancellation ultimately
    fails — the auth error still propagates to the caller, and the stale marker
    will age out naturally (pending → stale → retried by reconciler, by which
    point the auth user may be re-deleted).
    """
    last_err = None
    for attempt in range(max_attempts):
        try:
            users_db.cancel_user_deletion_wipe(uid)
            return
        except Exception as e:
            last_err = e
            if attempt < max_attempts - 1:
                time.sleep(retry_delay * (attempt + 1))
    logger.critical(
        f'delete_account marker CANCEL failed after {max_attempts} attempts for {uid}: '
        f'{sanitize(str(last_err))} — manual intervention may be needed to prevent '
        f'unwanted data wipe by the reconciliation worker.'
    )


def start_account_deletion(uid: str, reason: str | None = None, reason_details: str | None = None) -> dict[str, str]:
    if reason or reason_details:
        try:
            users_db.set_user_deletion_feedback(uid, reason, reason_details)
        except Exception as e:
            logger.info(f'delete_account feedback store failed: {sanitize(str(e))}')

    # Phase 1 — persist a NON-ACTIONABLE intent ('deleting_auth') before any
    # irreversible action. The reconciler only recovers stale 'deleting_auth'
    # records after verifying the Firebase auth user is gone, so a crash/deploy
    # between this write and the confirmed auth deletion cannot trigger a
    # premature data wipe for a user whose Firebase account still exists. Retry
    # transient Firestore failures; if the intent cannot be written, do NOT
    # proceed.
    _persist_wipe_intent_with_retry(uid)

    _cancel_subscription_for_account_deletion(uid)

    try:
        auth.delete_account(uid)
    except Exception as e:
        err = str(e).upper()
        if 'USER_NOT_FOUND' in err or 'NO USER RECORD' in err:
            logger.info(f'delete_account firebase user already gone for {uid}')
        else:
            # Auth deletion failed — cancel the intent so the record doesn't
            # linger in 'deleting_auth'. This is cosmetic cleanup, not a safety
            # requirement: the reconciler verifies the auth user is gone before
            # recovering any 'deleting_auth' record.
            _cancel_wipe_marker_with_retry(uid)
            raise

    # Phase 2 — auth deletion confirmed. Transition the marker to the
    # actionable 'pending' state before dispatching the durable wipe task.
    _persist_wipe_marker_with_retry(uid)

    try:
        enqueue_deletion_wipe(uid)
    except Exception as e:
        _mark_wipe_failed_after_enqueue_error(uid, e)
        raise

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
        try:
            enqueue_deletion_wipe(uid)
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
