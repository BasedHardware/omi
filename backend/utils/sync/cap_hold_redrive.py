"""Scheduler-owned awaited redrive; persisted choice and worker leases own work."""

import asyncio
import logging
import os
from typing import Any

from database import cap_hold_redrive as store
from utils.executors import db_executor, storage_executor, run_blocking
from utils import funded_processing, processing_backlog_worker
from config.stt_cap_dispatch import execution_admission_configured
from utils.sync import live_cap_staging

logger = logging.getLogger(__name__)


def enabled() -> bool:
    return os.getenv('CAP_HOLD_DURABLE_REDRIVE_ENABLED', 'true').lower() == 'true'


def owner(snap: Any, collection: str) -> str | None:
    parts = snap.reference.path.split('/')
    if len(parts) != 4 or parts[0] != 'users' or parts[2] != collection:
        logger.warning('event=cap_hold_redrive outcome=invalid_owner_path')
        return None
    if collection == 'processing_backlog' and parts[3] != 'current':
        return None
    return parts[1]


async def sweep() -> dict:
    if not enabled():
        return {'disabled': True}
    counts = {'sealed': 0, 'visited': 0}
    for snap in await run_blocking(db_executor, store.discover, 'staging'):
        uid = owner(snap, 'stt_cap_holds')
        if uid is None:
            continue
        try:
            if await run_blocking(storage_executor, live_cap_staging.seal, uid, snap.id, expired_only=True):
                counts['sealed'] += 1
        except Exception as error:
            logger.warning('event=cap_hold_redrive outcome=seal_deferred exception_type=%s', type(error).__name__)
    for snap in await run_blocking(db_executor, store.discover, 'cleanup'):
        uid = owner(snap, 'stt_cap_holds')
        if uid is None:
            continue
        try:
            await run_blocking(storage_executor, live_cap_staging.cleanup, uid, snap.reference)
        except Exception as error:
            logger.warning('event=cap_hold_redrive outcome=cleanup_deferred exception_type=%s', type(error).__name__)
    if not execution_admission_configured():
        return counts

    async def visit(snap: Any):
        uid = owner(snap, 'processing_backlog')
        if uid is None or not funded_processing.enabled(uid):
            return
        try:
            # Five concurrent owners share existing executors. Stop before the
            # next item/piece after 900s; in-flight IO keeps adapter timeouts.
            await processing_backlog_worker.run(uid, max_items=100, time_budget=900)
            counts['visited'] += 1
        except Exception as error:
            logger.warning('event=cap_hold_redrive outcome=worker_deferred exception_type=%s', type(error).__name__)

    await asyncio.gather(*(visit(snap) for snap in await run_blocking(db_executor, store.discover, 'choices')))
    logger.info('event=cap_hold_redrive outcome=complete visited=%s sealed=%s', counts['visited'], counts['sealed'])
    return counts
