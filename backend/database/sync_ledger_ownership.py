"""Pure ledger ownership checks shared by sync mutations and GPU batch fences.

Keep storage clients and sync orchestration out of this module so checking a
batch owner does not pull Cloud Tasks into the GPU worker import closure.
"""

from typing import Any, Dict

# Terminal batch_v1 ledger state: every failed unit is held with no recovery
# path left; projected siblings are published, the held span is counted.
BATCH_PARTIAL_STATUS = 'partial'


def ledger_owner_matches(
    existing: Dict[str, Any],
    job_id: str,
    run_token: str | None,
    run_epoch: int | None = None,
    *,
    allow_batch: bool = False,
) -> bool:
    """Return whether a worker still owns this ledger mutation boundary.

    Tokenless callers are admission/recovery exceptions only. They may mutate a
    claim that has never been bound, but can never overwrite a live worker that
    has recorded a run token.
    """
    if existing.get('dispatch_protocol') == 'batch_v1' and not allow_batch:
        return False
    # A batch partial is terminal for the client but still owned by its batch
    # job: recovery, operator redrive and the ordinary completion upgrade it.
    owned = {'processing', BATCH_PARTIAL_STATUS} if allow_batch else {'processing'}
    if existing.get('status') not in owned or existing.get('job_id') != job_id:
        return False
    bound_token = existing.get('ledger_run_token')
    bound_epoch = existing.get('ledger_run_epoch')
    if run_token is None:
        return bound_token is None and bound_epoch is None
    return bound_token == run_token and bound_epoch == run_epoch


def batch_projection_ledger_owner_matches(
    existing: Dict[str, Any],
    job_id: str,
    run_token: str | None,
    run_epoch: int | None,
) -> bool:
    """Explicit batch owner check; ordinary legacy mutations never use it."""
    return ledger_owner_matches(existing, job_id, run_token, run_epoch, allow_batch=True)
