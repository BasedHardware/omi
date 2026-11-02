"""Fenced run-lease helpers shared by the pipeline and the uid sequencer.

This module is the lightweight top-level seam for ledger completion: importing
``utils.sync.pipeline`` here would drag its heavy dependency graph (pydub,
numpy, providers) into every ``uid_sequencer`` importer, so the fenced
completion boundary — which only needs the database layer — lives on its own.
The pipeline re-exports these names, so catch sites and test seams keep
working unchanged.
"""

from __future__ import annotations

from typing import Dict

from database.sync_jobs import (
    FencedSyncJobMutation,
    delete_sync_job_run_lock_epoch,
    fenced_finalize_sync_job_from_durable_ledger,
    get_sync_job_run_lock_epoch,
)
from database.sync_ledger import (
    bind_sync_content_run_token,
    is_valid_completed_sync_content_result,
)


class SyncJobRunLeaseLost(RuntimeError):
    """A worker tried to write after its run token stopped owning the job."""


def _require_run_owner(mutation: FencedSyncJobMutation, *, job_id: str) -> Dict | None:
    """Turn a non-applied Redis CAS result into the worker's stop signal."""
    if mutation.applied:
        return mutation.job
    raise SyncJobRunLeaseLost(f'sync job run lease lost: job={job_id} outcome={mutation.outcome.value}')


def bind_or_converge_sync_ledger_completion(
    *,
    job_id: str,
    uid: str,
    content_id: str | None,
    run_lock_token: str | None,
) -> Dict | None:
    """Bind a live lease to the durable ledger or converge a proven completion.

    This synchronous DB-boundary helper is shared by Cloud Tasks, inline work,
    and stale polling. A higher epoch displaces an old owner before any decode,
    provider, ledger mutation, or stale failure can occur. A valid completion
    that landed just before lease replacement becomes the current Redis result
    through the caller's *current* fenced token rather than being overwritten
    as a failure.
    """
    if not content_id or run_lock_token is None:
        return None

    binding = bind_sync_content_run_token(
        uid,
        content_id,
        job_id,
        run_lock_token,
        get_sync_job_run_lock_epoch(run_lock_token),
    )
    if binding.bound:
        return None
    result = binding.result
    if not (
        binding.held
        and isinstance(result, dict)
        and result.get('held_audio') is True
        or binding.completed
        and is_valid_completed_sync_content_result(result)
    ):
        raise SyncJobRunLeaseLost(f'sync content ledger owner lost: job={job_id}')
    # Both surviving branches prove ``result`` is a dict: the held branch via
    # isinstance above, the completed branch via is_valid_completed_sync_content_result.
    assert isinstance(result, dict)

    finalized = _require_run_owner(
        fenced_finalize_sync_job_from_durable_ledger(job_id, run_lock_token, result), job_id=job_id
    )
    delete_sync_job_run_lock_epoch(job_id)
    return finalized
