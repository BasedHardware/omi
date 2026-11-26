"""Reliability experiment ``commit_wake``: a commit tells the serving backend which owner to project.

The GPU pump commits a result to its owner's log but has no projector: writing the result into the
conversation belongs to the serving backend, which learns of the commit only from its sweep (one page
per serving tick). With the experiment on, the pump's ``on_committed`` hook hands the owner id to
``CommitWakeSender``, which posts it to ``/v2/batch-pipeline/commit-wake`` on the serving backend, and
that endpoint asks ``wakes()`` for one targeted walk of the owner's log (the walk the provider route
already uses, ``Serving.drain_settled_async``).

The wake is a hint held in memory on both sides. Nothing durable changes: a wake that is dropped,
refused or lost with its process leaves the committed row exactly where the sweep finds it today,
and the walk passes the same predecessor, privacy and receipt fences as any other projection.

The worker side lives in ``commit_wake_sender`` (stdlib and the compute client only, so the GPU image
gains no dependency and imports nothing of the serving role); this module is the serving side.
"""

import logging

from utils.batch_pipeline.commit_wake_sender import (
    EXPERIMENT,
    FAILURE_LOG_EVERY,
    MAX_OWNERS_PER_CALL,
    MAX_PENDING_OWNERS,
    CommitWakeSender,
    enabled,
    sender_from_env,
)

# The experiment's one public surface: the worker half is re-exported beside the serving half.
__all__ = [
    'EXPERIMENT',
    'FAILURE_LOG_EVERY',
    'MAX_OWNERS_PER_CALL',
    'MAX_PENDING_OWNERS',
    'CommitWakeSender',
    'enabled',
    'request',
    'sender_from_env',
    'wakes',
]

logger = logging.getLogger(__name__)

# --- Serving side ---------------------------------------------------------------------------------

_wakes = None


def wakes():
    """Per-process owner wakes; created on first use so importing this module constructs nothing.

    The provider route's coalescer with no settle delay and no head-wait round: the worker has already
    committed, so the first walk runs at once, and a wake that arrives during a walk schedules exactly
    one more.
    """
    global _wakes
    if _wakes is None:
        from utils.batch_pipeline.provider_drain import OwnerDrainCoalescer

        _wakes = OwnerDrainCoalescer(_project_owner, head_wait=lambda: 0.0, delay=0.0)
    return _wakes


async def _project_owner(owner_id: str) -> None:
    from utils.batch_pipeline.serving import serving_for_stage
    from utils.executors import run_blocking, sync_executor
    from utils.sync.stage import current_stage

    service = await run_blocking(sync_executor, serving_for_stage, current_stage())
    await service.drain_settled_async(owner_id)


def request(owner_ids: list[str]) -> int:
    """Ask for one walk per admitted owner. Must be called on the event loop. Returns the owners accepted."""
    admitted = [owner_id for owner_id in owner_ids if enabled(owner_id)]
    if not admitted:
        return 0
    coalescer = wakes()
    for owner_id in admitted:
        coalescer.request(owner_id)
    logger.info('event=batch_commit_wake outcome=requested owners=%d', len(admitted))
    return len(admitted)
