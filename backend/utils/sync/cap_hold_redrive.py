"""Scheduler-owned awaited redrive; persisted choice and worker leases own work."""

import logging
import os

from database import cap_hold_redrive as store
from utils.executors import db_executor, storage_executor, run_blocking
from utils import funded_processing, processing_backlog_worker
from utils.sync import live_cap_staging

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return os.getenv('CAP_HOLD_DURABLE_REDRIVE_ENABLED', 'true').lower() == 'true'


async def sweep() -> dict:
    if not enabled():
        return {'disabled': True}
    counts = {'sealed': 0, 'visited': 0}
    for snap in await run_blocking(db_executor, store.discover, 'staging'):
        uid = snap.reference.parent.parent.id
        try:
            if await run_blocking(storage_executor, live_cap_staging.seal, uid, snap.id, expired_only=True):
                counts['sealed'] += 1
        except Exception as error:
            logger.warning('event=cap_hold_redrive outcome=seal_deferred exception_type=%s', type(error).__name__)
    for snap in await run_blocking(db_executor, store.discover, 'cleanup'):
        try:
            await run_blocking(
                storage_executor, live_cap_staging.cleanup, snap.reference.parent.parent.id, snap.reference
            )
        except Exception as error:
            logger.warning('event=cap_hold_redrive outcome=cleanup_deferred exception_type=%s', type(error).__name__)
    if not funded_processing.enabled():
        return counts
    for snap in await run_blocking(db_executor, store.discover, 'choices'):
        uid = snap.reference.parent.parent.id
        try:
            # One item per owner/request; no un-awaited self-respawn. The next
            # sweep reads the durable cursor/reservation even after SIGKILL.
            await processing_backlog_worker.run(uid, max_items=1)
            counts['visited'] += 1
        except Exception as error:
            logger.warning('event=cap_hold_redrive outcome=worker_deferred exception_type=%s', type(error).__name__)
    logger.info('event=cap_hold_redrive outcome=complete visited=%s sealed=%s', counts['visited'], counts['sealed'])
    return counts
