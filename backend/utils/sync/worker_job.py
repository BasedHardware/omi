"""One isolated backfill execution process. The parent owns sequencer heartbeats.

No HTTP request budget or budget-replacement enqueue exists on this path.
"""

import asyncio
import json
import logging
import os
import sys

from omi_logging import configure_logging

configure_logging(service='sync-backfill-worker')
logger = logging.getLogger(__name__)

_KEY_CREDENTIAL_ENV = ('SERVICE_ACCOUNT_JSON', 'GOOGLE_APPLICATION_CREDENTIALS', 'FIREBASE_AUTH_CREDENTIALS_PATH')


def drop_blank_credential_env() -> None:
    # The chart blanks these so a runtime secret cannot supply a key file. google-auth
    # reads a set-but-empty GOOGLE_APPLICATION_CREDENTIALS as a file path and fails, so
    # unset them before any client is built and let ADC use Workload Identity.
    for key in _KEY_CREDENTIAL_ENV:
        if key in os.environ and not os.environ[key].strip():
            del os.environ[key]


drop_blank_credential_env()

from database.batch_privacy_attempt import with_batch_privacy_attempt
from utils.sync.worker_client import ControlClient


def bootstrap() -> None:
    from database.google_credentials import customer_data_project
    from utils.staging_fence import assert_staging_isolation

    assert_staging_isolation(force=True)
    if os.environ.get('OMI_ENV_STAGE') != 'prod' or not customer_data_project():
        raise RuntimeError('worker needs explicit stage and customer data project')
    drop_blank_credential_env()
    if any(os.getenv(key) for key in _KEY_CREDENTIAL_ENV):
        raise RuntimeError('worker requires attached Workload Identity, not key credentials')
    import firebase_admin
    from utils.env_loader import firebase_admin_options
    from utils.firebase_admin_runtime import install_firebase_auth_mutation_guard, install_google_adc_guard
    from utils.rollout_cohorts import configure_rollout_runtime

    install_google_adc_guard()
    install_firebase_auth_mutation_guard()
    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(options=firebase_admin_options())
    configure_rollout_runtime()


def identity(lease: dict) -> dict:
    payload = lease['payload']
    return {
        'uid': payload['uid'],
        'job_id': payload['job_id'],
        'epoch': payload['sequencer_epoch'],
        'token': lease['token'],
    }


async def renew_run(job_id: str, token: str, stop: asyncio.Event, owner: asyncio.Task) -> None:
    from database import sync_jobs
    from utils.executors import db_executor, run_blocking

    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), sync_jobs.RUN_LOCK_HEARTBEAT_SECONDS)
            return
        except TimeoutError:
            pass
        try:
            async with asyncio.timeout(20):
                accepted = await run_blocking(db_executor, sync_jobs.renew_job_run_lock, job_id, token)
        except Exception:
            accepted = False
        if not accepted:
            # Cancellation preserves the lock; the parent kills the whole job
            # process before fallback, including any detached executor leaves.
            owner.cancel()
            return


async def cleanup_terminal(payload: dict, job: dict) -> None:
    from database import sync_dead_letters, sync_ledger
    from utils.executors import db_executor, run_blocking
    from utils.sync.backfill import release_backfill_slot
    from utils.sync.job_retry_policy import terminal_repeat_failure_kwargs
    from utils.sync.pipeline import delete_staged_blobs_async

    uid, job_id = payload['uid'], payload['job_id']
    if job['status'] in ('failed', 'partial_failure'):
        await run_blocking(
            db_executor,
            sync_dead_letters.ensure_dead_letter_confirmed,
            job_id,
            uid=uid,
            conversation_id=job.get('conversation_id'),
            failure_code=job.get('reason_code') or 'unknown',
        )
        if payload.get('content_id'):
            await run_blocking(
                db_executor,
                sync_ledger.release_sync_content_claim_after_job_retired,
                uid,
                payload['content_id'],
                job_id,
                **terminal_repeat_failure_kwargs(job),
            )
    else:
        await delete_staged_blobs_async(
            payload['raw_blob_paths'], uid=uid, content_id=payload.get('content_id'), job_id=job_id
        )
    await run_blocking(db_executor, release_backfill_slot, uid, job_id)


@with_batch_privacy_attempt
async def execute(lease: dict, client: ControlClient) -> bool:
    from database import sync_jobs
    from database.account_deletion_marker import account_deletion_blocks_user_work
    from utils.account_cutover.access import should_skip_background_account_mutation
    from utils.executors import db_executor, run_blocking, start_background_task, storage_executor
    from utils.sync.ledger_completion import SyncJobRunLeaseLost, bind_or_converge_sync_ledger_completion
    from utils.sync.pipeline import download_staged_files, run_full_pipeline_background_async
    from utils.sync import minimal_redrive
    from models.conversation import ConversationSource
    from models.geolocation import Geolocation

    payload = lease['payload']
    uid, job_id = payload['uid'], payload['job_id']
    redrive_mode = minimal_redrive.parse_mode(payload)
    if redrive_mode and not minimal_redrive.enabled():
        logger.warning('event=sync_minimal_redrive outcome=refused reason=disabled')
        return False
    if (
        payload.get('lane') != 'backfill'
        or payload.get('ledger_fence_mode') != 'active'
        or payload.get('worker_eligible') is not True
        or await run_blocking(db_executor, sync_jobs.get_sync_ledger_fence_mode)
        is not sync_jobs.SyncLedgerFenceMode.ACTIVE
    ):
        return False
    run_token = await run_blocking(db_executor, sync_jobs.try_acquire_sync_job_run_lock, job_id)
    if not run_token:
        return False
    stop = asyncio.Event()
    renewer = None
    release = True
    try:
        # Revalidate the sequencer AFTER taking Redis. A claim reply can have
        # stalled while fallback advanced its epoch and completed another run.
        if not (await client.call('heartbeat', identity(lease))).get('accepted'):
            return False
        job = await run_blocking(db_executor, sync_jobs.get_sync_job, job_id)
        if (
            not job
            or job.get('uid') != uid
            or not await run_blocking(db_executor, sync_jobs.sync_job_uses_ledger_fence, job)
        ):
            return False
        if job['status'] in sync_jobs.TERMINAL_STATUSES:
            await cleanup_terminal(payload, job)
            return True
        if await run_blocking(db_executor, account_deletion_blocks_user_work, uid):
            return False
        if await run_blocking(db_executor, should_skip_background_account_mutation, uid):
            return False
        marked = await run_blocking(
            db_executor,
            sync_jobs.fenced_update_sync_job,
            job_id,
            run_token,
            {'execution_drive': 'pull'},
            allowed_current_statuses={'queued', 'processing'},
        )
        if not marked.applied:
            release = False
            return False
        owner_task = asyncio.current_task()
        assert owner_task is not None
        renewer = start_background_task(renew_run(job_id, run_token, stop, owner_task), name='sync-pull:run-lease')
        converged = await run_blocking(
            db_executor,
            bind_or_converge_sync_ledger_completion,
            job_id=job_id,
            uid=uid,
            content_id=payload.get('content_id'),
            run_lock_token=run_token,
        )
        if converged is None:
            if not await run_blocking(
                storage_executor, download_staged_files, payload['raw_blob_paths'], bounded_backfill=True
            ):
                return False  # Fallback retains the existing missing-source disposition.
            await run_full_pipeline_background_async(
                job_id,
                uid,
                payload['raw_blob_paths'],
                ConversationSource(payload.get('source') or 'omi'),
                bool(payload.get('should_lock')),
                f'syncing/{uid}/{job_id}',
                payload.get('conversation_id'),
                geolocation=Geolocation.deserialize_safe(payload.get('geolocation')),
                task_mode=True,
                sync_lane='backfill',
                content_id=payload.get('content_id'),
                run_lock_token=run_token,
                content_run_bound=True,
                ledger_fence_active=True,
                client_device_id=payload.get('client_device_id'),
                client_platform=payload.get('client_platform'),
                recording_session_id=payload.get('recording_session_id'),
                audio_start_seconds=payload.get('audio_start_seconds'),
                audio_end_seconds=payload.get('audio_end_seconds'),
                raw_capture_paths=payload.get('raw_capture_paths'),
                capture_evidence_claims=payload.get('capture_evidence_claims'),
                capture_received_at=payload.get('capture_received_at'),
                redrive_mode=redrive_mode or None,
            )
        job = await run_blocking(db_executor, sync_jobs.get_sync_job, job_id)
        if not job or job['status'] not in sync_jobs.TERMINAL_STATUSES:
            raise RuntimeError('pipeline returned without terminal state')
        await cleanup_terminal(payload, job)
        return True
    except (asyncio.CancelledError, SyncJobRunLeaseLost):
        release = False
        raise
    except Exception as error:
        # Never consume a Cloud Tasks attempt budget in the worker. A normal
        # failure hands the same durable job back to its existing fallback.
        job = await run_blocking(db_executor, sync_jobs.get_sync_job, job_id)
        if job and job['status'] not in sync_jobs.TERMINAL_STATUSES:
            mutation = await run_blocking(
                db_executor,
                sync_jobs.fenced_mark_job_queued_for_retry,
                job_id,
                run_token,
                int(job.get('attempt') or 0),
                'sync_worker_retry',
            )
            release = mutation.applied
        logger.warning('event=sync_pull_worker outcome=job_retry exception_type=%s', type(error).__name__)
        return False
    finally:
        stop.set()
        if renewer:
            await asyncio.wait_for(renewer, 25)
        if release:
            await run_blocking(db_executor, sync_jobs.release_job_run_lock, job_id, run_token)


async def run(lease: dict) -> int:
    import httpx
    from utils.sync.worker_client import WorkerClient, worker_endpoint

    base, audience = worker_endpoint()
    async with httpx.AsyncClient(timeout=httpx.Timeout(20, connect=3), follow_redirects=False) as http:
        return 0 if await execute(lease, WorkerClient(http, base, audience)) else 1


async def process_entry(lease: dict) -> None:
    try:
        status = await run(lease)
        # Normal isolated-child exit bypasses main's lifespan and Python atexit.
        # A controlled os._exit has no later grace: await settlement itself,
        # bounded by the parent's existing work deadline, not a lifespan wait.
        from database.pinecone_partition_state import drain_mutations
        from utils.executors import get_pinecone_shutdown_executor, run_blocking

        await run_blocking(get_pinecone_shutdown_executor(), drain_mutations)
        # This process deliberately never imports main's lifespan. Flush its
        # own buffered holds and tracked work before a normal child exit.
        # Lease loss/cancellation bypasses this path: the parent must first
        # terminate every executor leaf while the Redis fence is retained.
        from utils.executors import drain_background_tasks
        from utils.sync.cap_hold_lifecycle import flush_active

        await flush_active(timeout=30.0)
        await drain_background_tasks(timeout=10.0)
    except BaseException as error:
        logger.warning('event=sync_pull_worker outcome=job_process_stopped exception_type=%s', type(error).__name__)
        status = 2
    # Exit before asyncio's executor shutdown can join an abandoned leaf.
    os._exit(status)


def main() -> None:
    status = 2
    try:
        bootstrap()
        lease = json.loads(sys.stdin.buffer.read(1024 * 1024))
        asyncio.run(process_entry(lease))
    except BaseException as error:
        logger.warning('event=sync_pull_worker outcome=job_process_stopped exception_type=%s', type(error).__name__)
        status = 2
    # Every job has its own process group: terminating it also terminates
    # non-cancellable executor leaves. Never leave threads in a claimed tree.
    os._exit(status)


if __name__ == '__main__':
    main()
