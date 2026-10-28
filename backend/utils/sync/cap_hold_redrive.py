"""Scheduler-owned awaited redrive; persisted choice and worker leases own work."""

import asyncio
import logging
import os
import time
from typing import Any

from database import cap_hold_redrive as store
from utils.executors import db_executor, storage_executor, run_blocking
from utils import funded_processing, processing_backlog_worker
from config.stt_cap_dispatch import execution_admission_configured, recovery_cohort_admits
from utils.observability.held_content import publish_fleet
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
    try:
        snapshot = await run_blocking(db_executor, store.fleet_snapshot)
    except Exception as error:
        logger.warning('event=cap_hold_redrive outcome=fleet_snapshot_deferred exception_type=%s', type(error).__name__)
    else:
        publish_fleet(snapshot)
    counts = {'sealed': 0, 'visited': 0}
    staging = await run_blocking(db_executor, store.discover, 'staging')
    for snap in staging:
        uid = owner(snap, 'stt_cap_holds')
        if uid is None:
            continue
        try:
            if await run_blocking(storage_executor, live_cap_staging.seal, uid, snap.id, expired_only=True):
                counts['sealed'] += 1
        except Exception as error:
            logger.warning('event=cap_hold_redrive outcome=seal_deferred exception_type=%s', type(error).__name__)
    cleanup = await run_blocking(db_executor, store.discover, 'cleanup')
    for snap in cleanup:
        uid = owner(snap, 'stt_cap_holds')
        if uid is None:
            continue
        try:
            await run_blocking(storage_executor, live_cap_staging.cleanup, uid, snap.reference)
        except Exception as error:
            logger.warning('event=cap_hold_redrive outcome=cleanup_deferred exception_type=%s', type(error).__name__)
    if not execution_admission_configured():
        return counts

    started = time.monotonic()
    visited = set()

    async def visit(snap: Any, turn: int):
        uid = owner(snap, 'processing_backlog')
        if uid is None or not recovery_cohort_admits(uid) or not funded_processing.enabled(uid):
            return None
        try:
            # One newest-first candidate per owner per round. A fast owner
            # cannot drain its 100 candidates before its peers get a turn.
            more = await processing_backlog_worker.run(
                uid, continuation=turn > 0, max_items=1, time_budget=max(0, 900 - (time.monotonic() - started))
            )
            visited.add(uid)
            return snap if more else None
        except Exception as error:
            logger.warning('event=cap_hold_redrive outcome=worker_deferred exception_type=%s', type(error).__name__)
            return None

    choices = await run_blocking(db_executor, store.discover, 'choices')
    for turn in range(100):
        if not choices or time.monotonic() - started >= 900:
            break
        results = await asyncio.gather(*(visit(snap, turn) for snap in choices))
        choices = [snap for snap in results if snap is not None]
    counts['visited'] = len(visited)
    logger.info('event=cap_hold_redrive outcome=complete visited=%s sealed=%s', counts['visited'], counts['sealed'])
    return counts
