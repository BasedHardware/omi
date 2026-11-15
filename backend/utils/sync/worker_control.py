"""Sequencer-backed pull RPC leaves. No application startup or pipeline imports."""

import secrets
from itertools import islice

from config import sync_backfill_worker as policy
from database import sync_backfill_sequencer as registry, sync_jobs
from utils.sync import legacy_dark, uid_sequencer

# Per API process, shared by its serial claim polls. A restart may revisit a
# page; owner/epoch transactions still decide ownership. Resume past filtered
# owners instead of scanning the whole collection or starving later pages.
_candidate_after: str | None = None
CANDIDATES_PER_POLL = 100


def claim() -> dict | None:
    global _candidate_after
    # This check precedes all persistence reads: idle fleets at zero do no IO.
    if policy.percent() == 0 or not registry.enabled():
        return None
    if not legacy_dark.sequencer_dispatch_allowed():
        return None
    if sync_jobs.get_sync_ledger_fence_mode() is not sync_jobs.SyncLedgerFenceMode.ACTIVE:
        return None
    scanned = 0
    for owner in islice(registry.worker_candidates(after_uid=_candidate_after), CANDIDATES_PER_POLL):
        scanned += 1
        uid = owner['uid']
        _candidate_after = uid
        if not policy.selected(uid) or not legacy_dark.sequencer_dispatch_allowed(uid=uid):
            continue
        token = secrets.token_urlsafe(32)
        epoch, job_id = owner.get('active_epoch'), owner.get('active_job_id')
        if type(epoch) is not int or not isinstance(job_id, str):
            continue
        payload = registry.claim_worker(uid, job_id, epoch, token)
        if payload is not None:
            return {'payload': payload, 'token': token, 'lease_seconds': registry.LEASE_SECONDS}
        return None  # At most one transaction (including its bounded retries).
    # A short page/EOF wraps on the next request. A full filtered page keeps
    # its cursor so the following poll can reach newly eligible later owners.
    if scanned < CANDIDATES_PER_POLL:
        _candidate_after = None
    return None


def heartbeat(uid: str, job_id: str, epoch: int, token: str) -> bool:
    # Intake rollback does not strand an accepted lease.
    return registry.renew_job(uid, job_id, epoch, worker_token=token)


def complete(uid: str, job_id: str, epoch: int, token: str) -> bool:
    job = sync_jobs.get_sync_job(job_id)
    if not job or job.get('uid') != uid or job.get('status') not in sync_jobs.TERMINAL_STATUSES:
        return False
    released = registry.finish_job(uid, job_id, epoch, job['status'], worker_token=token)
    if released:
        uid_sequencer.kick(uid)
    return released


def fail(uid: str, job_id: str, epoch: int, token: str) -> bool:
    if sync_jobs.sync_job_run_lock_present(job_id):
        return False  # A cancelled leaf is not proof of a stopped pipeline.
    return registry.fail_worker(uid, job_id, epoch, token)
