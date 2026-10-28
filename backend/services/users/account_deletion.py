from __future__ import annotations

from database.messaging import MessagingStore

import asyncio
import logging
from threading import Event
import time
from datetime import datetime, timezone
from typing import Any, Callable, Literal, TypedDict, cast

from firebase_admin import auth as firebase_auth

from database import vector_db
from database.sync_jobs import renew_job_run_lock
from database import _client as database_client
from database.legal_holds import (
    acquire_destructive_operation,
    assert_account_deletion_permitted,
    finish_destructive_operation,
)
from database.dev_api_key import delete_dev_key, get_dev_keys_for_user
from database.mcp_api_key import delete_mcp_key, get_mcp_keys_for_user
from database.mcp_oauth import delete_user_oauth_credentials
from database import account_deletion_grace as deletion_grace_db
from database import account_deletion_marker as deletion_marker_db
from database import users as users_db
from database import processing_backlog as processing_backlog_db
from database.action_items import get_action_item_ids
from database.conversations import get_conversation_ids, get_conversation_photos
from database.screen_activity import get_screen_activity_ids
from database import frame_requests as frame_requests_db
from database.vector_db import (
    delete_action_item_vectors_batch,
    delete_conversation_vectors_batch,
    delete_memory_vectors_batch,
    delete_screen_activity_vectors,
    delete_transcript_chunk_vectors_batch,
)
from utils import stripe as stripe_utils
from utils.cloud_tasks import (
    assert_inline_account_deletion_permitted,
    enqueue_account_deletion_wipe,
    is_account_deletion_dispatch_enabled,
)
from utils.executors import cleanup_executor, db_executor, run_blocking, start_background_task, submit_with_context
from utils.log_sanitizer import sanitize
from utils.observability.fallback import record_fallback
from utils.other import endpoints as auth
from utils.memory.canonical_memory_adapter import purge_canonical_derived_user_data
from utils.memory.memory_service import MemoryService
from utils.memory.memory_system import delete_canonical_memory_maintenance_registry_entry
from utils.other.storage import delete_all_conversation_recordings, delete_all_user_storage_objects
from utils.retrieval.frame_request_storage import (
    delete_all_frame_request_pixels_for_user,
    delete_frame_request_pixels_for_user,
)
from utils.twilio_service import delete_user_caller_ids_strict as delete_user_caller_ids
from utils.integration_telemetry import emit_posthog_event
from services.users.agent_vm_account_cleanup import delete_agent_vm_for_account
from config.account_deletion_grace import (
    account_deletion_grace_enabled,
    account_deletion_grace_window,
    account_deletion_grace_window_days,
)
from utils.sync.cap_hold import read_held_audio_summary

logger = logging.getLogger(__name__)


class PurgeFailure(TypedDict):
    operation: str
    error: str


class PurgeResult(TypedDict):
    required_failures: list[PurgeFailure]
    best_effort_failures: list[PurgeFailure]
    vectors_deleted: int
    recordings_deleted: int


ACCOUNT_DELETION_WIPE_COMPLETED = 'Account Deletion Wipe Completed'
ACCOUNT_DELETION_WIPE_FAILED = 'Account Deletion Wipe Failed'


def _historical_memory_ids(uid: str) -> list[str]:
    """Enumerate historical provider identities through the universal owner."""

    return MemoryService().list_historical_memory_ids(uid)


def _delete_memory_maintenance_registry(uid: str) -> None:
    """Remove the content-free global inventory marker during account wipe."""

    delete_canonical_memory_maintenance_registry_entry(uid, db_client=database_client.get_data_plane_firestore_client())


def delete_account_credentials(uid: str) -> None:
    """Revoke UID-bearing credentials that live outside users/{uid}."""
    for key in get_dev_keys_for_user(uid):
        delete_dev_key(uid, key.id)
    for key in get_mcp_keys_for_user(uid):
        delete_mcp_key(uid, key.id)
    delete_user_oauth_credentials(uid)


def purge_derived_user_data(uid: str) -> PurgeResult:
    """Purge a user's derived data outside Firestore.

    Required failures must block the Firestore wipe because those IDs are
    stored in Firestore and may become unrecoverable after ``delete_user_data``.
    Best-effort failures are safe to retry independently or leave behind.
    """
    result: PurgeResult = {
        'required_failures': [],
        'best_effort_failures': [],
        'vectors_deleted': 0,
        'recordings_deleted': 0,
    }

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
            result['vectors_deleted'] += len(conversation_ids)
    except Exception as e:
        record_failure('required_failures', 'conversation_vectors', e)
        logger.error(f'delete_account purge conversation vectors failed for {uid}: {sanitize(str(e))}')

    try:
        conversation_ids = get_conversation_ids(uid)
        if conversation_ids:
            require_vector_index('transcript_chunk_vectors')
            result['vectors_deleted'] += (
                delete_transcript_chunk_vectors_batch(uid, conversation_ids, raise_on_failure=True) or 0
            )
    except Exception as e:
        record_failure('required_failures', 'transcript_chunk_vectors', e)
        logger.error(f'delete_account purge transcript chunk vectors failed for {uid}: {sanitize(str(e))}')

    try:
        # The service owns the historical physical-ID inventory. Canonical
        # provider identities are purged by the canonical derived-data closure
        # below, while the recursive Firestore wipe removes items, overrides,
        # evidence, journals, and task sidecars under users/{uid}.
        memory_ids = _historical_memory_ids(uid)
        if memory_ids:
            require_vector_index('memory_vectors')
            deleted = delete_memory_vectors_batch(uid, memory_ids)
            require_deleted_count('memory_vectors', len(memory_ids), deleted)
            result['vectors_deleted'] += deleted or 0
    except Exception as e:
        record_failure('required_failures', 'memory_vectors', e)
        logger.error(f'delete_account purge memory vectors failed for {uid}: {sanitize(str(e))}')

    try:
        action_item_ids = get_action_item_ids(uid)
        if action_item_ids:
            require_vector_index('action_item_vectors')
            delete_action_item_vectors_batch(uid, action_item_ids)
            result['vectors_deleted'] += len(action_item_ids)
    except Exception as e:
        record_failure('required_failures', 'action_item_vectors', e)
        logger.error(f'delete_account purge action item vectors failed for {uid}: {sanitize(str(e))}')

    try:
        screen_activity_ids = get_screen_activity_ids(uid)
        if screen_activity_ids:
            require_vector_index('screen_activity_vectors')
            delete_screen_activity_vectors(uid, screen_activity_ids)
            result['vectors_deleted'] += len(screen_activity_ids)
    except Exception as e:
        record_failure('required_failures', 'screen_activity_vectors', e)
        logger.error(f'delete_account purge screen activity vectors failed for {uid}: {sanitize(str(e))}')

    try:
        result['recordings_deleted'] = delete_all_conversation_recordings(uid) or 0
    except Exception as e:
        record_failure('required_failures', 'conversation_recordings', e)
        logger.error(f'delete_account purge recordings failed for {uid}: {sanitize(str(e))}')

    try:
        # The recordings helper covers the historical recordings bucket. The
        # owner-prefix sweep covers private-cloud chunks/audio/merged/playback,
        # speech-profile objects, and chat uploads that are not represented by
        # the Firestore ID inventories below.
        delete_all_user_storage_objects(uid)
    except Exception as e:
        record_failure('required_failures', 'owner_storage_objects', e)
        logger.error(f'delete_account purge owner storage failed for {uid}: {sanitize(str(e))}')

    try:
        # Firestore metadata is removed by the recursive user wipe below, but
        # referenced pixels live in GCS and would otherwise become orphaned.
        photo_storage_ids = []
        for conversation_id in get_conversation_ids(uid):
            for photo in get_conversation_photos(uid, conversation_id) or []:
                if isinstance(photo, dict) and isinstance(photo.get('storage_id'), str) and photo.get('storage_id'):
                    photo_storage_ids.append(str(photo['storage_id']))
        frame_storage_ids = frame_requests_db.list_all_frame_request_storage_ids(uid)
        orphan_storage_ids = frame_requests_db.list_all_frame_upload_orphan_storage_ids(uid)
        deletion_outbox_storage_ids = frame_requests_db.list_all_frame_deletion_outbox_storage_ids(uid)
        delete_frame_request_pixels_for_user(
            uid,
            list(
                dict.fromkeys(photo_storage_ids + frame_storage_ids + orphan_storage_ids + deletion_outbox_storage_ids)
            ),
        )
        # Metadata inventories can be incomplete after a crashed request. The
        # authoritative prefix sweep below removes both temporary and
        # conversation-lifetime frame objects and verifies absence.
        delete_all_frame_request_pixels_for_user(uid)
    except Exception as e:
        record_failure('required_failures', 'frame_request_pixels', e)
        logger.error(f'delete_account purge frame request pixels failed for {uid}: {sanitize(str(e))}')

    try:
        canonical_result = purge_canonical_derived_user_data(
            uid, db_client=database_client.get_data_plane_firestore_client()
        )
        vector_ids = canonical_result.get('vector_ids', [])
        if isinstance(vector_ids, list):
            result['vectors_deleted'] += len(cast(list[object], vector_ids))
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


def _purge_failures(purge_result: object) -> tuple[list[PurgeFailure], list[PurgeFailure]]:
    if not isinstance(purge_result, dict):
        return [], []
    result = cast(dict[str, object], purge_result)

    def failures(key: str) -> list[PurgeFailure]:
        value = result.get(key, [])
        if not isinstance(value, list):
            return []
        bounded: list[PurgeFailure] = []
        for item in cast(list[object], value):
            if not isinstance(item, dict):
                continue
            item_dict = cast(dict[str, object], item)
            bounded.append({'operation': str(item_dict.get('operation', 'unknown')), 'error': ''})
        return bounded

    return failures('required_failures'), failures('best_effort_failures')


# Service-level PostHog distinct_id only. Never re-identify a deleted Firebase UID
# as a person profile (success path runs after Auth + Firestore wipe).
_ACCOUNT_DELETION_TELEMETRY_DISTINCT_ID = 'omi-service:account-deletion'


def _emit_deletion_telemetry(uid: str, event: str, properties: dict[str, object]) -> None:
    logger.info(
        'account_deletion_telemetry event=%s duration_seconds=%s vectors_deleted=%s recordings_deleted=%s '
        'required_failure_count=%s best_effort_failure_count=%s failed_operations=%s retry_count=%s terminal=%s',
        event,
        properties.get('duration_seconds'),
        properties.get('vectors_deleted'),
        properties.get('recordings_deleted'),
        properties.get('required_failure_count'),
        properties.get('best_effort_failure_count'),
        properties.get('failed_operations'),
        properties.get('retry_count'),
        properties.get('terminal'),
    )
    # Drop any accidental uid-bearing keys; person processing is disabled so
    # completion/failure cannot recreate a profile for the deleted account.
    safe_properties = {key: value for key, value in properties.items() if key not in {'uid', 'user_id', 'distinct_id'}}
    safe_properties['$process_person_profile'] = False
    emit_posthog_event(_ACCOUNT_DELETION_TELEMETRY_DISTINCT_ID, event, safe_properties)


class DeletionBillingError(RuntimeError):
    def __init__(self, subscription_id: str | None, error: Exception):
        super().__init__(str(error))
        self.subscription_id = subscription_id


_DELETION_HEARTBEAT_INTERVAL_SECONDS = 60


async def _renew_deletion_wipe_lease(uid: str, token: str, stop: asyncio.Event, lost: Event) -> None:
    while not stop.is_set():
        try:
            if not await run_blocking(db_executor, renew_job_run_lock, f'account-deletion:{uid}', token):
                lost.set()
                return
            # Also heartbeat during a single long provider/Firestore operation.
            await run_blocking(db_executor, users_db.heartbeat_user_deletion_wipe, uid)
        except Exception as error:
            # Keep the Firestore freshness fence on a Redis outage. A later
            # successful renewal or lost-token result resolves lease ownership.
            logger.error('delete_account lease heartbeat failed: %s', sanitize(str(error)))
            try:
                await run_blocking(db_executor, users_db.heartbeat_user_deletion_wipe, uid)
            except Exception as heartbeat_error:
                logger.error('delete_account marker heartbeat failed: %s', sanitize(str(heartbeat_error)))
        try:
            await asyncio.wait_for(stop.wait(), timeout=_DELETION_HEARTBEAT_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass


async def run_deletion_wipe_with_lease(uid: str, retry_count: int, terminal: bool, token: str) -> bool:
    """Own renewal until the cleanup thread finishes, even if HTTP is cancelled."""

    async def run() -> bool:
        stop = asyncio.Event()
        lost = Event()
        heartbeat = start_background_task(
            _renew_deletion_wipe_lease(uid, token, stop, lost), name='account-deletion-lease'
        )
        try:
            return await run_blocking(cleanup_executor, background_wipe_user_data, uid, retry_count, terminal, lost)
        finally:
            stop.set()
            await heartbeat

    worker = start_background_task(run(), name='account-deletion-worker')
    return await asyncio.shield(worker)


def background_wipe_user_data(
    uid: str, retry_count: int = 0, terminal: bool = False, lease_lost: Event | None = None
) -> bool:
    started_at = time.monotonic()
    current_operation = 'wipe_running_marker'
    purge_result: object = {}
    deletion_gate_token = f'account-deletion:{uid}'
    deletion_gate_acquired = False

    def heartbeat() -> None:
        if lease_lost is not None and lease_lost.is_set():
            raise RuntimeError('account deletion run-lock lost')
        users_db.heartbeat_user_deletion_wipe(uid)

    try:
        # Acquire the same transaction gate used by the server-owned legal-hold
        # writer before any irreversible provider, Auth, storage, or Firestore
        # mutation. A hold and this acquisition therefore have one winner.
        current_operation = 'legal_hold_authority'
        acquire_destructive_operation(
            uid,
            kind='account_deletion',
            token=deletion_gate_token,
        )
        deletion_gate_acquired = True
        # Transition to ``running`` so the reconciler can distinguish a
        # genuinely orphaned ``pending`` marker (queued but never started)
        # from a wipe that is actively executing. Without this, a slow wipe
        # could be duplicate-claimed after the short ``pending`` stale window.
        users_db.mark_user_deletion_wipe_running(uid)
        # The durable marker and queue claim are the authority for every
        # irreversible step below. In particular, do not cancel billing or
        # remove Firebase Auth from the request thread: a queue NotFound must
        # leave an account usable and recoverable.
        current_operation = 'billing_subscription'
        heartbeat()
        # A late checkout/webhook could have created a subscription after the
        # grace admission check. Re-read Stripe at the irreversible boundary,
        # even when admission recorded an earlier successful cancellation.
        _cancel_subscription_for_account_deletion(uid)
        current_operation = 'agent_vm'
        heartbeat()
        delete_agent_vm_for_account(uid)
        current_operation = 'messaging_channels'
        heartbeat()
        MessagingStore().delete_account(uid)
        current_operation = 'api_credentials'
        heartbeat()
        delete_account_credentials(uid)
        current_operation = 'firebase_auth'
        heartbeat()
        try:
            auth.delete_account(uid)
        except Exception as e:
            err = str(e).upper()
            if 'USER_NOT_FOUND' in err or 'NO USER RECORD' in err:
                logger.info('delete_account worker observed Firebase Auth user already absent')
            else:
                raise
        users_db.mark_user_deletion_auth_deleted(uid)
        # Twilio caller IDs first, while the phone_numbers subcollection still carries twilio_sid metadata.
        current_operation = 'twilio_caller_ids'
        heartbeat()
        delete_user_caller_ids(uid)
        current_operation = 'derived_data'
        heartbeat()
        purge_result = purge_derived_user_data(uid)
        required_failures = _required_failures_from_purge_result(purge_result)
        if required_failures:
            failed_operations = ', '.join(failure['operation'] for failure in required_failures)
            raise RuntimeError(f'required derived purge failed: {failed_operations}')
        current_operation = 'firestore_user_data'
        heartbeat()
        wipe_result = users_db.delete_user_data(uid)
        if wipe_result.get('status') != 'ok':
            raise RuntimeError('authoritative Firestore user-data wipe did not complete')
        # Typesense is a serving surface, so its owner purge is part of
        # completion. The filter remains executable after Firestore deletion,
        # and propagating failures leaves the durable wipe retryable.
        current_operation = 'conversation_typesense_purge'
        heartbeat()
        purge_user_conversation_index(uid)
        current_operation = 'memory_maintenance_registry'
        heartbeat()
        _delete_memory_maintenance_registry(uid)
        logger.info('delete_account background wipe complete')
    except Exception as e:
        logger.error(f'delete_account background wipe failed for {uid}: {sanitize(str(e))}')
        if deletion_gate_acquired:
            try:
                finish_destructive_operation(
                    uid,
                    kind='account_deletion',
                    token=deletion_gate_token,
                    outcome='failed',
                )
            except Exception as gate_err:
                # An uncertain running gate intentionally remains fail-closed;
                # never pretend a hold can be placed while deletion outcome is
                # unknown.
                logger.error(f'delete_account legal-hold gate finalization failed for {uid}: {sanitize(str(gate_err))}')
        # Billing can restore access only while Auth is confirmed present.
        # A post-Auth failure retains the existing fenced reconciliation path.
        billing_parked = False
        if isinstance(e, DeletionBillingError):
            try:
                firebase_auth.get_user(uid)
                billing_parked = (
                    _retry_firestore_write(
                        lambda: users_db.mark_user_deletion_billing_failed(uid, e.subscription_id, sanitize(str(e))),
                        uid=uid,
                        fail_msg='delete_account billing failure status persist failed',
                        on_failure='raise',
                    )
                    is True
                )
            except firebase_auth.UserNotFoundError:
                pass
            except Exception as persist_err:
                logger.error(f'delete_account billing status persist failed for {uid}: {sanitize(str(persist_err))}')
        if not billing_parked:
            try:
                users_db.mark_user_deletion_wipe_failed(uid)
            except Exception as persist_err:
                logger.error(f'delete_account wipe status persist failed for {uid}: {sanitize(str(persist_err))}')
        required_failures, best_effort_failures = _purge_failures(purge_result)
        failed_operations = [failure['operation'] for failure in required_failures + best_effort_failures] or [
            current_operation
        ]
        _emit_deletion_telemetry(
            uid,
            ACCOUNT_DELETION_WIPE_FAILED,
            {
                'failed_operations': failed_operations,
                'retry_count': max(0, retry_count),
                'terminal': terminal,
            },
        )
        return False
    else:
        try:
            heartbeat()
            if users_db.mark_user_deletion_wipe_completed(uid) is False:
                logger.warning('delete_account completion deferred for outstanding provider cleanup')
                return False
        except Exception as e:
            logger.error(f'delete_account wipe status persist failed for {uid}: {sanitize(str(e))}')
            return False
        try:
            finish_destructive_operation(
                uid,
                kind='account_deletion',
                token=deletion_gate_token,
                outcome='completed',
            )
        except Exception as e:
            logger.error(f'delete_account legal-hold gate completion failed for {uid}: {sanitize(str(e))}')
            return False
        required_failures, best_effort_failures = _purge_failures(purge_result)
        purge_result_dict = purge_result
        _emit_deletion_telemetry(
            uid,
            ACCOUNT_DELETION_WIPE_COMPLETED,
            {
                'duration_seconds': round(time.monotonic() - started_at, 3),
                'vectors_deleted': purge_result_dict.get('vectors_deleted', 0),
                'recordings_deleted': purge_result_dict.get('recordings_deleted', 0),
                'required_failure_count': len(required_failures),
                'best_effort_failure_count': len(best_effort_failures),
                'failed_operations': [failure['operation'] for failure in required_failures + best_effort_failures],
            },
        )
        return True


def enqueue_deletion_wipe(uid: str, wipe_job_id: str):
    """Dispatch the account-deletion wipe using the configured durable mechanism."""
    if is_account_deletion_dispatch_enabled() is True:
        enqueue_account_deletion_wipe(wipe_job_id)
        return
    # Inline dispatch is retained solely for deterministic local/dev/test
    # execution, and may never reach production data whatever the stage says.
    assert_inline_account_deletion_permitted()
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
        sub = users_db.get_existing_user_subscription(uid)
        app_subscription_ids = stripe_utils.find_billable_app_subscription_ids(uid)
        for subscription_id in app_subscription_ids:
            stripe_utils.cancel_subscription_for_account_deletion(subscription_id)
        subscription_id = getattr(sub, 'stripe_subscription_id', None) if sub else None
        if subscription_id and subscription_id not in app_subscription_ids:
            stripe_utils.cancel_subscription_for_account_deletion(subscription_id)
    except Exception as error:
        raise DeletionBillingError(subscription_id, error) from error


def purge_user_conversation_index(uid: str) -> None:
    """Remove Typesense's owner documents; failures keep the wipe retryable."""
    from utils.conversations.typesense_index import purge_user_conversation_index as purge

    purge(uid, raise_on_failure=True)


def _run_immediate_deletion_steps(uid: str) -> None:
    """Cancel billing and revoke owner credentials before accepting deletion."""
    failures: list[Exception] = []
    try:
        _cancel_subscription_for_account_deletion(uid)
    except Exception as error:
        failures.append(error)
    try:
        firebase_auth.revoke_refresh_tokens(uid)
    except firebase_auth.UserNotFoundError:
        logger.info('delete_account immediate revocation observed Firebase Auth user already absent')
    except Exception as error:
        failures.append(error)
    try:
        delete_account_credentials(uid)
    except Exception as error:
        failures.append(error)
    if failures:
        raise failures[0]


def _account_deletion_result(status: str, wipe_at: datetime | None = None) -> dict[str, Any]:
    return {
        'status': 'ok',
        'message': 'Account deletion started',
        'pending_deletion': status == 'pending_deletion',
        'wipe_at': wipe_at if status == 'pending_deletion' else None,
    }


def _summary_count(value: Any) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError, OverflowError):
        return 0


def _deletion_due_at(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def start_account_deletion(
    uid: str,
    reason: str | None = None,
    reason_details: str | None = None,
    *,
    grace: bool = False,
    erase_now: bool = False,
) -> dict[str, Any]:
    # Admission is also fenced before creating a durable deletion intent. This
    # keeps a newly-held account from entering the destructive queue at all;
    # the worker repeats the check because holds can change while queued.
    assert_account_deletion_permitted(uid)
    # Persist the authoritative intent before billing/session revocation. Grace
    # markers are not dispatchable until the stored deadline and the immediate
    # action receipt are both present. Immediate requests keep the established
    # durable queue claim and worker as the destructive executor.
    grace_window = account_deletion_grace_window()
    use_grace = account_deletion_grace_enabled() and grace and not erase_now and grace_window.total_seconds() > 0
    wipe_due_at: datetime | None = None
    if use_grace:
        wipe_due_at = datetime.now(timezone.utc) + grace_window
        wipe_intent = _retry_firestore_write(
            lambda: deletion_grace_db.mark_user_deletion_grace_intent(uid, wipe_due_at),
            uid=uid,
            fail_msg='Failed to persist deletion-grace intent',
            on_failure='raise',
        )
    else:
        promoted_intent = _retry_firestore_write(
            lambda: deletion_grace_db.promote_grace_to_immediate(uid),
            uid=uid,
            fail_msg='Failed to promote deletion-grace intent',
            on_failure='raise',
        )
        wipe_intent = promoted_intent or _retry_firestore_write(
            lambda: users_db.mark_user_deletion_wipe_intent(uid),
            uid=uid,
            fail_msg='Failed to persist deletion-wipe intent',
            on_failure='raise',
        )
    wipe_job_id = wipe_intent.get('wipe_job_id') if isinstance(wipe_intent, dict) else None
    if not isinstance(wipe_job_id, str) or not wipe_job_id:
        raise RuntimeError('deletion-wipe intent did not persist a wipe_job_id')
    if reason or reason_details:
        try:
            users_db.set_user_deletion_feedback(uid, reason, reason_details)
        except Exception as e:
            logger.info(f'delete_account feedback store failed: {sanitize(str(e))}')
    if use_grace:
        mode = wipe_intent.get('mode') if isinstance(wipe_intent, dict) else 'legacy'
        status = wipe_intent.get('wipe_status') if isinstance(wipe_intent, dict) else 'pending_deletion'
        joined_due_at = wipe_intent.get('wipe_due_at') if isinstance(wipe_intent, dict) else wipe_due_at
        if mode == 'legacy':
            logger.info('delete_account joined an existing immediate deletion intent')
            return _account_deletion_result(str(status or 'pending'), joined_due_at)
        if mode == 'created':
            # The marker fences every capture path before any provider calls.
            # Firebase Auth remains enabled so sign-in continues to resolve to
            # this uid; all ordinary requests receive the pending-deletion
            # fence while the status and restore routes remain available.
            _run_immediate_deletion_steps(uid)
            if deletion_grace_db.mark_user_deletion_grace_actions_complete(uid, wipe_job_id) is False:
                marker = deletion_marker_db.read_account_deletion_marker(uid) or {}
                if marker.get('wipe_status') != 'cancelled':
                    raise RuntimeError('deletion grace immediate steps could not be committed')
            status = (deletion_marker_db.read_account_deletion_marker(uid) or {}).get('wipe_status') or status
            joined_due_at = (deletion_marker_db.read_account_deletion_marker(uid) or {}).get(
                'wipe_due_at'
            ) or joined_due_at
        else:
            logger.info('delete_account joined existing grace-window deletion intent')
        return _account_deletion_result(str(status or 'pending_deletion'), joined_due_at)

    dispatch_claimed = wipe_intent.get('dispatch_claimed') is True if isinstance(wipe_intent, dict) else False
    if not dispatch_claimed:
        logger.info('delete_account joined existing durable deletion intent')
        return _account_deletion_result('pending')

    # User asked for immediate erasure (or the grace kill switch is off).
    # Keep billing/session revocation ahead of task dispatch, as in the grace
    # path, while retaining the existing durable worker as the wipe owner.
    _run_immediate_deletion_steps(uid)

    try:
        enqueue_deletion_wipe(uid, wipe_job_id)
    except Exception as e:
        _mark_wipe_failed_after_enqueue_error(uid, e)
        record_fallback(
            component='other',
            from_mode='cloud_tasks',
            to_mode='durable_reconciliation',
            reason='enqueue_failed',
            outcome='degraded',
            log=logger,
        )
        # The actionable marker is committed. Queue dispatch is only an
        # acceleration path; reconciliation owns eventual completion.
        return _account_deletion_result('pending')

    logger.info('delete_account accepted durable deletion intent and queue acceleration')
    return _account_deletion_result('pending')


def account_deletion_status(uid: str) -> dict[str, Any]:
    """Owner-facing deletion state and metadata-only loss summary."""
    marker = deletion_marker_db.read_account_deletion_marker(uid) or {}
    status = marker.get('wipe_status')
    wipe_at = marker.get('wipe_due_at') if status == 'pending_deletion' else None
    held = read_held_audio_summary(uid) or {}
    backlog = processing_backlog_db.read_processing_backlog_summary(uid) or {}
    return {
        'status': status,
        'pending_deletion': status == 'pending_deletion',
        'wipe_at': wipe_at,
        'grace_period_days': account_deletion_grace_window_days() if account_deletion_grace_enabled() else 0,
        'loss_summary': {
            'held_recordings': _summary_count(held.get('count')),
            'held_audio_seconds': _summary_count(held.get('seconds')),
            'backlog_conversations': _summary_count(backlog.get('count')),
            'backlog_seconds': _summary_count(backlog.get('seconds')),
        },
    }


def restore_account_deletion(uid: str) -> dict[str, Any]:
    """Restore the existing uid while the grace marker is still restorable."""
    marker = deletion_marker_db.read_account_deletion_marker(uid) or {}
    if marker.get('wipe_status') != 'pending_deletion':
        return {'status': 'not_pending', 'restored': False}
    if marker.get('grace_actions_complete') is not True:
        _run_immediate_deletion_steps(uid)
        deletion_grace_db.mark_user_deletion_grace_actions_complete(uid, str(marker.get('wipe_job_id') or ''))
    outcome = deletion_grace_db.restore_user_deletion(uid)
    return {
        'status': outcome,
        'restored': outcome == 'restored',
        'billing_cancelled': outcome == 'restored',
    }


def reconcile_pending_deletion_wipes(limit: int = 100) -> dict[str, int]:
    """Retry incomplete grace admission actions and re-enqueue due wipes.

    Called by a periodic worker (cron, Cloud Scheduler, or startup hook) to drain
    incomplete grace actions and the ``wipe_status in ('pending', 'failed', 'retrying')``
    backlog left behind when a durable task enqueue or worker execution failed.

    Also recovers stale legacy ``'deleting_auth'`` records. The worker owns
    Firebase Auth deletion, so the durable intent itself is sufficient recovery
    authority; new admissions atomically create ``pending`` instead.

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
        if record.get('wipe_status') == 'pending_deletion':
            if record.get('grace_actions_complete') is not True:
                job_id = record.get('wipe_job_id')
                if not isinstance(job_id, str) or not job_id:
                    skipped += 1
                    continue
                try:
                    _run_immediate_deletion_steps(uid)
                    actions_completed = deletion_grace_db.mark_user_deletion_grace_actions_complete(uid, job_id)
                except Exception as error:
                    logger.error(
                        'delete_account grace immediate-action retry failed for %s: %s', uid, sanitize(str(error))
                    )
                    skipped += 1
                    continue
                if actions_completed is not True:
                    skipped += 1
                    continue
            due_at = _deletion_due_at(record.get('wipe_due_at'))
            if due_at is None or due_at > datetime.now(timezone.utc):
                skipped += 1
                continue
        # ``deleting_auth`` is a legacy durable intent from the former
        # two-transaction admission path. The worker now owns Firebase Auth
        # deletion, so a stale legacy intent is safe to claim even when the
        # Auth user still exists.
        if record.get('wipe_status') == 'deleting_auth':
            logger.info(f'delete_account reconciliation recovering legacy deleting_auth intent for {uid}')
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
        if record.get('wipe_status') == 'running':
            _emit_deletion_telemetry(
                uid,
                ACCOUNT_DELETION_WIPE_FAILED,
                {'failed_operations': ['stale_running_wipe'], 'retry_count': 0, 'terminal': False},
            )
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
            # Reconciliation re-dispatches; it never executes. Calling the
            # mode-aware helper here made any inline process - a local run
            # against prod data - the wipe executor for every account it could
            # claim, which is how wipes ran outside the OIDC handler entirely.
            enqueue_account_deletion_wipe(wipe_job_id)
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
