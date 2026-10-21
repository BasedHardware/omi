"""A2 shadow seams and the hook for batch writers that commit outside ``Store.run`` (projection apply, purge).

Kept outside ``database.jobstore`` on purpose: importing it costs one ``os`` lookup, and the job-store package
(Postgres store, outbox, migrations) is imported only when this process runs ``BATCH_JOBSTORE_MODE=shadow``.
"""

from __future__ import annotations

import logging
import os
from typing import Iterable

logger = logging.getLogger(__name__)


def _shadow_mode() -> bool:
    # Store-selection infrastructure config, not per-unit policy (baselined in the batch-stage env ratchet).
    return os.getenv('BATCH_JOBSTORE_MODE', 'firestore').strip().lower() == 'shadow'


def mirror_refresh(namespace: str, keys: Iterable[tuple[str, str]]) -> None:
    """After a commit outside ``Store.run``: re-copy ``keys`` [(table, key)] to the shadow. Never raises."""
    if not _shadow_mode():
        return
    try:
        from utils.staging_fence import jobstore_shadow_admits

        if not jobstore_shadow_admits(namespace):  # prod namespace outside the staging DB (L02-2)
            return
        import database.jobstore.dual_store as dual_store

        dual_store.mirror_refresh(namespace, list(keys))
    except Exception:
        logger.warning('event=jobstore_shadow op=refresh outcome=hook_error', exc_info=True)


def shadow_parity_collectors() -> tuple:
    """The A2 parity and convergence metrics for a process-private registry; empty outside shadow mode.

    ``omi_jobstore_shadow_{parity,convergence}_*`` live in the default registry; a process that serves its own
    ``CollectorRegistry`` (the batch worker) must register them there or the series are never exported.
    Never raises: a failed import keeps the worker serving its other metrics.
    """
    if not _shadow_mode():
        return ()
    try:
        import database.jobstore.dual_store as dual_store

        return (
            dual_store.SHADOW_PARITY_TOTAL,
            dual_store.SHADOW_CONVERGENCE_TOTAL,
            dual_store.SHADOW_CONVERGENCE_SECONDS,
        )
    except Exception:
        logger.warning('event=jobstore_shadow outcome=metrics_unavailable', exc_info=True)
        return ()


def shadow_from_env(primary):
    """The A2 seam: ``primary`` unchanged unless this process runs ``BATCH_JOBSTORE_MODE=shadow``.

    In shadow mode it defers to ``database.jobstore.dual_store.shadow_from_env`` (which still refuses prod,
    a missing setting or a missing driver); any failure there keeps the plain primary.
    """
    if not _shadow_mode():
        return primary
    try:
        import database.jobstore.dual_store as dual_store

        return dual_store.shadow_from_env(primary)
    except Exception:
        logger.warning('event=jobstore_shadow outcome=refused reason=seam_error', exc_info=True)
        return primary
