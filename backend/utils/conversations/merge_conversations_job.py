"""Lifecycle-owned durable merge coordinator; reconciliation survives mode-off."""

import asyncio
import logging
from typing import Any, Callable

from database import conversation_merge_jobs as store
from utils.executors import db_executor, lifecycle_executor, run_blocking, start_background_task
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


class MergeLeaseLost(RuntimeError):
    pass


def admit(uid: str, conversation_ids: list[str], reprocess: bool, *, firestore_client: Any = None) -> dict | None:
    return store.admit(uid, conversation_ids, reprocess, firestore_client=firestore_client)


def schedule(job: dict, add_background_task: Callable[..., Any]) -> None:
    """Offer the exact admitted generation to the configured transport first."""
    from utils.cloud_tasks import enqueue_listen_finalization_job, listen_finalization_binding

    job_id, generation = job['job_id'], job['dispatch_generation']
    if all(listen_finalization_binding().values()):
        try:
            enqueue_listen_finalization_job(job_id, generation)
            return
        except Exception as error:
            # An ambiguous enqueue may have delivered the task. Only one of
            # the two transports can claim this durable generation.
            logger.warning('event=conversation_merge_dispatch outcome=fallback exception_type=%s', type(error).__name__)
    add_background_task(run, job_id, generation)


def checkpoint(job_id: str, epoch: int, phase: str | None = None) -> None:
    if not store.renew(job_id, epoch, phase=phase):
        raise MergeLeaseLost('merge lease is no longer current')


async def run(job_id: str, generation: int | None = None) -> str:
    job = await run_blocking(db_executor, store.claim, job_id, generation=generation)
    if job is None:
        return 'fenced'
    if job.get('account_pending_deletion'):
        return 'account_pending_deletion'
    epoch = job['lease_epoch']
    stop = asyncio.Event()

    async def renew() -> None:
        while True:
            try:
                await asyncio.wait_for(stop.wait(), timeout=30)
                return
            except asyncio.TimeoutError:
                if not await run_blocking(db_executor, store.renew, job_id, epoch):
                    return

    heartbeat = start_background_task(renew(), name='merge_job_lease')
    try:
        from utils.conversations.merge_conversations import perform_merge_async

        if job.get('phase') == 'source_cleanup':
            completed = await run_blocking(lifecycle_executor(job['uid']), resume_source_cleanup, job)
        else:
            completed = await run_blocking(
                lifecycle_executor(job['uid']),
                perform_merge_async,
                job['uid'],
                job['conversation_ids'],
                reprocess=job['reprocess'],
                merge_job_id=job_id,
                merge_lease_epoch=epoch,
                merge_target_id=job['merge_target_id'],
            )
        if completed:
            return 'completed' if await run_blocking(db_executor, store.finish, job_id, epoch) else 'fenced'
        return 'recovery_pending'
    finally:
        stop.set()
        await heartbeat


def reconcile(job_id: str, *, firestore_client: Any = None) -> str:
    job = store.begin_recovery(job_id, firestore_client=firestore_client)
    if job is None:
        return 'fenced'
    if job.get('account_pending_deletion'):
        return 'account_pending_deletion'
    if job['recovery'] == 'resume_cleanup':
        from utils.cloud_tasks import enqueue_listen_finalization_job

        enqueue_listen_finalization_job(job_id, job['dispatch_generation'])
        return 'cleanup_requeued'
    if job['recovery'] == 'manual':
        record_fallback(
            component='other',
            from_mode='conversation_merge',
            to_mode='manual_recovery',
            reason='other',
            outcome='degraded',
        )
        return 'manual_recovery'
    # Never release sources before provisional target retraction succeeds.
    from utils.conversations.merge_conversations import cleanup_failed_merge_target

    completed_steps: set[str] = set()
    if not cleanup_failed_merge_target(job['uid'], job['merge_target_id'], rollback_step=completed_steps.add):
        return 'cleanup_pending'
    return (
        'rolled_back'
        if store.finish_recovery(
            job_id, job['lease_epoch'], cleanup_steps=completed_steps, firestore_client=firestore_client
        )
        else 'fenced'
    )


def resume_source_cleanup(job: dict) -> bool:
    """Replay only sealed source cleanup: no transcription or paid notes call."""
    from database import conversations
    from utils.conversations import merge_conversations
    from utils.notification_dispatch import dispatch_merge_completed

    owner, target = job['uid'], job['merge_target_id']
    checkpoint(job['job_id'], job['lease_epoch'])
    survivor = conversations.get_conversation(owner, target)
    if not survivor or survivor.get('deleted'):
        raise MergeLeaseLost('merge survivor unavailable; retain remaining sources')
    for cid in job['conversation_ids']:
        checkpoint(job['job_id'], job['lease_epoch'])
        source = conversations.get_conversation(owner, cid)
        if source is None:
            continue
        if source.get('merge_job_id') != job['job_id'] or source.get('transcript_corrections_moved_to') != target:
            raise MergeLeaseLost('merge source binding changed; retain it')
        merge_conversations.delete_merged_source(owner, cid, target)
    dispatch_merge_completed(owner, target, job['conversation_ids'])
    return True


def retract_go_merge_source(job_id: str, generation: int, epoch: int, index: int) -> bool:
    """Reuse authoritative derived-data cleanup while Go retains source custody."""
    from database.sync_jobs import release_job_run_lock, try_acquire_job_run_lock
    from utils.account_cutover.access import should_skip_background_account_mutation
    from utils.conversations.merge_conversations import retract_sync_bridge_source

    # Serialize duplicate HTTP deliveries across replicas. The durable lease
    # is rechecked inside the receiver after acquiring this lock.
    lock_key = f'go-merge-retraction:{job_id}'
    token = try_acquire_job_run_lock(lock_key)
    if not token:
        return False
    try:
        source = store.resolve_go_cleanup_source(job_id, generation, epoch, index)
        if source is None or should_skip_background_account_mutation(source[0]):
            return False
        owner, conversation, target, already_retracted = source
        if already_retracted:
            return True
        retract_sync_bridge_source(owner, conversation)
        receipt = store.resolve_go_cleanup_source(
            job_id, generation, epoch, index, retracted_source=(owner, conversation, target)
        )
        return receipt == (owner, conversation, target, True)
    finally:
        release_job_run_lock(lock_key, token)
