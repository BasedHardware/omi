from __future__ import annotations

import logging

import time
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
from utils.executors import cleanup_executor, submit_with_context
from utils.log_sanitizer import sanitize
from utils.other import endpoints as auth
from utils.other.storage import delete_all_conversation_recordings
from utils.twilio_service import delete_user_caller_ids

logger = logging.getLogger(__name__)


def purge_derived_user_data(uid: str):
    """Best-effort purge of a user's derived data outside Firestore."""
    try:
        conversation_ids = get_conversation_ids(uid)
        if conversation_ids:
            delete_conversation_vectors_batch(uid, conversation_ids)
    except Exception as e:
        logger.error(f'delete_account purge conversation vectors failed for {uid}: {sanitize(str(e))}')

    try:
        conversation_ids = get_conversation_ids(uid)
        if conversation_ids:
            delete_transcript_chunk_vectors_batch(uid, conversation_ids)
    except Exception as e:
        logger.error(f'delete_account purge transcript chunk vectors failed for {uid}: {sanitize(str(e))}')

    try:
        memory_ids = get_memory_ids(uid)
        if memory_ids:
            delete_memory_vectors_batch(uid, memory_ids)
    except Exception as e:
        logger.error(f'delete_account purge memory vectors failed for {uid}: {sanitize(str(e))}')

    try:
        action_item_ids = get_action_item_ids(uid)
        if action_item_ids:
            delete_action_item_vectors_batch(uid, action_item_ids)
    except Exception as e:
        logger.error(f'delete_account purge action item vectors failed for {uid}: {sanitize(str(e))}')

    try:
        screen_activity_ids = get_screen_activity_ids(uid)
        if screen_activity_ids:
            delete_screen_activity_vectors(uid, screen_activity_ids)
    except Exception as e:
        logger.error(f'delete_account purge screen activity vectors failed for {uid}: {sanitize(str(e))}')

    try:
        delete_all_conversation_recordings(uid)
    except Exception as e:
        logger.error(f'delete_account purge recordings failed for {uid}: {sanitize(str(e))}')


def background_wipe_user_data(uid: str):
    try:
        # Twilio caller IDs first, while the phone_numbers subcollection still carries twilio_sid metadata.
        delete_user_caller_ids(uid)
        purge_derived_user_data(uid)
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
    else:
        try:
            users_db.mark_user_deletion_wipe_completed(uid)
        except Exception as e:
            logger.error(f'delete_account wipe status persist failed for {uid}: {sanitize(str(e))}')


def _persist_wipe_marker_with_retry(uid: str, max_attempts: int = 3, retry_delay: float = 0.5):
    """Persist the pending-deletion marker, retrying transient Firestore failures.

    Raises on persistent failure so the caller can surface the error to the user
    rather than proceeding to the irreversible Firebase user deletion without a
    durable recovery marker.
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
        f'Failed to persist deletion-wipe marker after {max_attempts} attempts for {uid}: {sanitize(str(last_err))}'
    )


def _cancel_wipe_marker_with_retry(uid: str, max_attempts: int = 3, retry_delay: float = 0.5):
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

    # Persist the pending-deletion marker FIRST, before any irreversible action
    # (Stripe cancel, Firebase user delete). Retry transient Firestore failures.
    # If the marker cannot be written, do NOT proceed — without it, a deploy/restart
    # that cancels the queued wipe leaves no recovery path for the user's data.
    _persist_wipe_marker_with_retry(uid)

    try:
        sub = users_db.get_user_subscription(uid)
        if sub and sub.stripe_subscription_id:
            canceled = stripe_utils.cancel_subscription(sub.stripe_subscription_id)
            if not canceled:
                logger.error(f'delete_account stripe cancel returned None for {uid}')
    except Exception as e:
        logger.error(f'delete_account subscription lookup failed for {uid}: {sanitize(str(e))}')

    try:
        auth.delete_account(uid)
    except Exception as e:
        err = str(e).upper()
        if 'USER_NOT_FOUND' in err or 'NO USER RECORD' in err:
            logger.info(f'delete_account firebase user already gone for {uid}')
        else:
            # Auth deletion failed — cancel the pending marker so the
            # reconciliation worker doesn't wipe data for a user whose
            # Firebase account still exists. Retry transient Firestore failures.
            _cancel_wipe_marker_with_retry(uid)
            raise

    submit_with_context(cleanup_executor, background_wipe_user_data, uid)

    return {'status': 'ok', 'message': 'Account deletion started'}


def reconcile_pending_deletion_wipes(limit: int = 100) -> dict[str, int]:
    """Re-enqueue account-deletion wipes that were cancelled or failed.

    Called by a periodic worker (cron, Cloud Scheduler, or startup hook) to drain
    the ``wipe_status in ('pending', 'failed', 'retrying')`` backlog left behind
    when a deploy or restart cancels in-process ``cleanup_executor`` futures
    before they start.

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
        if not uid:
            skipped += 1
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
        submit_with_context(cleanup_executor, background_wipe_user_data, uid)
        requeued += 1
        logger.info(f'delete_account reconciliation re-enqueued wipe for {uid}')

    if requeued:
        logger.info(f'delete_account reconciliation: re-enqueued {requeued}, skipped {skipped}')
    return {'requeued': requeued, 'skipped': skipped}
