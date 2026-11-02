"""Sequencer-backed pull RPC leaves. No application startup or pipeline imports."""

import secrets

from config import sync_backfill_worker as policy
from database import sync_backfill_sequencer as registry, sync_jobs
from utils.sync import legacy_dark


def claim() -> dict | None:
    # This check precedes all persistence reads: idle fleets at zero do no IO.
    if policy.percent() == 0 or not registry.enabled():
        return None
    if sync_jobs.get_sync_ledger_fence_mode() is not sync_jobs.SyncLedgerFenceMode.ACTIVE:
        return None
    for owner in registry.worker_candidates():
        uid = owner['uid']
        if not policy.selected(uid) or not legacy_dark.sequencer_dispatch_allowed(uid=uid):
            continue
        token = secrets.token_urlsafe(32)
        epoch, job_id = owner.get('active_epoch'), owner.get('active_job_id')
        if type(epoch) is not int or not isinstance(job_id, str):
            continue
        payload = registry.claim_worker(uid, job_id, epoch, token)
        if payload is not None:
            return {'payload': payload, 'token': token, 'lease_seconds': registry.LEASE_SECONDS}
    return None


def heartbeat(uid: str, job_id: str, epoch: int, token: str) -> bool:
    # Intake rollback does not strand an accepted lease.
    return registry.renew_job(uid, job_id, epoch, worker_token=token)


def complete(uid: str, job_id: str, epoch: int, token: str) -> bool:
    job = sync_jobs.get_sync_job(job_id)
    if not job or job.get('uid') != uid or job.get('status') not in sync_jobs.TERMINAL_STATUSES:
        return False
    return registry.finish_job(uid, job_id, epoch, job['status'], worker_token=token)


def fail(uid: str, job_id: str, epoch: int, token: str) -> bool:
    if sync_jobs.sync_job_run_lock_present(job_id):
        return False  # A cancelled leaf is not proof of a stopped pipeline.
    return registry.fail_worker(uid, job_id, epoch, token)
