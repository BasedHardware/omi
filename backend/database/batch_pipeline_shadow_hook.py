"""A2 shadow seams and the hook for batch writers that commit outside ``Store.run`` (projection apply, purge).

Kept outside ``database.jobstore`` on purpose: required core metrics are import-light, and the job-store package
(Postgres store, outbox, migrations) is imported only when this process runs in shadow or index mode.
"""

from __future__ import annotations

import logging
import os
from typing import Iterable

from database.batch_pipeline_recovery_metrics import RECOVERY_COLLECTORS

logger = logging.getLogger(__name__)


def _shadow_mode(*, index_only: bool = False) -> bool:
    # Store-selection infrastructure config, not per-unit policy (baselined in the batch-stage env ratchet).
    mode = os.getenv('BATCH_JOBSTORE_MODE', 'firestore').strip().lower()
    return mode == 'index' if index_only else mode in {'shadow', 'index'}


def mirror_refresh(namespace: str, keys: Iterable[tuple[str, str]]) -> None:
    """After a commit outside ``Store.run``: re-copy ``keys`` [(table, key)] to the shadow. Never raises."""
    if not _shadow_mode():
        return
    try:
        from utils.staging_fence import jobstore_mirror_factory_admits

        if not jobstore_mirror_factory_admits(namespace):
            return
        import database.jobstore.dual_store as dual_store

        dual_store.mirror_refresh(namespace, list(keys))
    except Exception:
        logger.warning('event=jobstore_shadow op=refresh outcome=hook_error', exc_info=True)


def shadow_mode_enabled() -> bool:
    """Whether this process mirrors batch state into the Postgres shadow."""
    return _shadow_mode()


def purge_owner(namespace: str, uid: str) -> int:
    """A5, at the end of a batch purge: erase ``uid``'s Postgres copy to match the purged primary.

    Unlike ``mirror_refresh`` this RAISES: privacy erasure must not be best effort, and the purge that
    calls it is bounded and retried. Retained copies remain reachable with shadow mode and admission disabled.
    """
    import database.jobstore.dual_store as dual_store

    return dual_store.purge_owner(namespace, uid)


def shadow_parity_collectors() -> tuple:
    """Caller metrics in every mode; optional parity/convergence/index metrics in their modes.

    ``omi_jobstore_shadow_{parity,convergence}_*`` live in the default registry; a process that serves its own
    ``CollectorRegistry`` (the batch worker) must register them there or the series are never exported.
    Optional jobstore import failures keep the core caller collectors available.
    Core collectors are required; their import does not traverse caller utilities or jobstore.
    """
    if not _shadow_mode():
        return RECOVERY_COLLECTORS
    try:
        import database.jobstore.dual_store as dual_store

        from database.jobstore.serving_parity import SERVING_PARITY_TOTAL

        collectors = (
            *RECOVERY_COLLECTORS,
            SERVING_PARITY_TOTAL,
            dual_store.SHADOW_PARITY_TOTAL,
            dual_store.SHADOW_CONVERGENCE_TOTAL,
            dual_store.SHADOW_CONVERGENCE_SECONDS,
        )
        if _shadow_mode(index_only=True):
            from database.jobstore.index_store import INDEX_READS_TOTAL

            return (*collectors, INDEX_READS_TOTAL)
        return collectors
    except Exception:
        logger.warning('event=jobstore_shadow outcome=metrics_unavailable', exc_info=True)
        return RECOVERY_COLLECTORS


def shadow_from_env(primary):
    """The A2 seam: ``primary`` unchanged unless this process runs in shadow or index mode.

    In shadow mode it defers to ``database.jobstore.dual_store.shadow_from_env`` (which requires explicit namespace/context,
    a complete target and a driver); any failure there keeps the plain primary.
    """
    if not _shadow_mode():
        return primary
    try:
        import database.jobstore.dual_store as dual_store

        return dual_store.shadow_from_env(primary)
    except Exception:
        logger.warning('event=jobstore_shadow outcome=refused reason=seam_error', exc_info=True)
        return primary
