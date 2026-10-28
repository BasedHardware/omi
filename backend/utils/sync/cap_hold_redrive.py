"""Scheduler-owned awaited redrive; persisted choice and worker leases own work."""

import asyncio
import logging
import os
import time
from typing import Any, TypedDict

from database import cap_hold_redrive as store, users as users_db
from utils.executors import db_executor, run_blocking, start_background_task, storage_executor
from utils import funded_processing, processing_backlog_worker
from config.stt_cap_dispatch import execution_admission_configured, recovery_cohort_admits
from config.plan_catalog import PAID_PLAN_TYPES
from utils.observability.held_content import publish_fleet
from utils.sync import live_cap_staging

logger = logging.getLogger(__name__)

LEGACY_CHOICES_PAGE = 5
CHOICES_PAGE_CEILING = 8
OWNER_ITEMS_CEILING = 10
# Keep the refresh cadence below the held-content acceptance gate's 300-second
# maximum age, leaving 180 seconds for aggregation completion and scheduler delay.
FLEET_SNAPSHOT_MAX_AGE_SECONDS = 300.0
FLEET_SNAPSHOT_INTERVAL_SECONDS = 120.0
FLEET_SNAPSHOT_WAIT_CEILING = 300.0


class _SnapshotGate(TypedDict):
    inflight: bool
    attempt_at: float | None


# Process-local gate: one fleet aggregation at a time, no more often than the
# configured interval. None means no attempt has run yet, including on a newly
# started process whose monotonic clock is still below the interval.
_snapshot_gate: _SnapshotGate = {'inflight': False, 'attempt_at': None}


def enabled() -> bool:
    return os.getenv('CAP_HOLD_DURABLE_REDRIVE_ENABLED', 'true').lower() == 'true'


def _env_number(raw_value: str | None, default: float, *, low: float, high: float) -> float:
    try:
        value = float(raw_value or default)
    except ValueError:
        value = default
    return max(low, min(high, value))


def parallel_drain_enabled() -> bool:
    """Bounded multi-owner drain is on unless switched off; off restores 5x1."""
    return os.getenv('CAP_HOLD_REDRIVE_PARALLEL_DRAIN_ENABLED', 'true').lower() == 'true'


def choices_page() -> int:
    """Processing owners visited per sweep, bounded below the shared sync pool."""
    if not parallel_drain_enabled():
        return LEGACY_CHOICES_PAGE
    return int(_env_number(os.getenv('CAP_HOLD_REDRIVE_CHOICES_PAGE', ''), 8, low=1, high=CHOICES_PAGE_CEILING))


def owner_items() -> int:
    """Candidates one owner runs per rotation turn. Turns keep owners fair:
    every visited owner advances the same number of items before any peer
    gets another turn."""
    if not parallel_drain_enabled():
        return 1
    return int(_env_number(os.getenv('CAP_HOLD_REDRIVE_ITEMS_PER_OWNER', ''), 10, low=1, high=OWNER_ITEMS_CEILING))


def fleet_snapshot_enabled() -> bool:
    return os.getenv('CAP_HOLD_FLEET_SNAPSHOT_ENABLED', 'true').lower() == 'true'


def fleet_snapshot_interval() -> float:
    return _env_number(
        os.getenv('CAP_HOLD_FLEET_SNAPSHOT_MIN_INTERVAL_SECONDS', ''),
        FLEET_SNAPSHOT_INTERVAL_SECONDS,
        low=0.0,
        high=3600.0,
    )


def fleet_snapshot_wait() -> float:
    return _env_number(
        os.getenv('CAP_HOLD_FLEET_SNAPSHOT_WAIT_SECONDS', ''), 90.0, low=0.0, high=FLEET_SNAPSHOT_WAIT_CEILING
    )


def owner(snap: Any, collection: str) -> str | None:
    parts = snap.reference.path.split('/')
    if len(parts) != 4 or parts[0] != 'users' or parts[2] != collection:
        logger.warning('event=cap_hold_redrive outcome=invalid_owner_path')
        return None
    if collection == 'processing_backlog' and parts[3] != 'current':
        return None
    return parts[1]


async def _paid_first(choices: list[Any]) -> list[Any]:
    """Order this bounded page by the current valid subscription, without writes.

    The collection-group cursor still advances fairly across pages. Each page
    starts funded paid owners first; basic, missing and temporarily unreadable
    subscriptions remain eligible only through the worker's normal gates.
    """

    async def is_paid(snap: Any) -> bool:
        uid = owner(snap, 'processing_backlog')
        if uid is None or not recovery_cohort_admits(uid) or not funded_processing.enabled(uid):
            return False
        try:
            subscription = await run_blocking(db_executor, users_db.get_user_valid_subscription, uid, provision=False)
        except Exception as error:
            logger.warning(
                'event=cap_hold_redrive outcome=subscription_priority_deferred uid=%s exception_type=%s',
                uid,
                type(error).__name__,
                exc_info=True,
            )
            return False
        return subscription is not None and subscription.plan in PAID_PLAN_TYPES

    priorities = await asyncio.gather(*(is_paid(snap) for snap in choices))
    return [snap for snap, paid in zip(choices, priorities) if paid] + [
        snap for snap, paid in zip(choices, priorities) if not paid
    ]


async def _run_fleet_snapshot() -> None:
    try:
        publish_fleet(await run_blocking(db_executor, store.fleet_snapshot))
        logger.info('event=cap_hold_redrive outcome=fleet_snapshot_complete')
    except Exception as error:
        logger.warning('event=cap_hold_redrive outcome=fleet_snapshot_deferred exception_type=%s', type(error).__name__)
    finally:
        _snapshot_gate['inflight'] = False


def _schedule_fleet_snapshot() -> asyncio.Task[Any] | None:
    """Start the gauge aggregation beside the sweep, never ahead of its work."""
    if not fleet_snapshot_enabled():
        return None
    now = time.monotonic()
    last_attempt_at = _snapshot_gate['attempt_at']
    if _snapshot_gate['inflight'] or (
        last_attempt_at is not None and now - last_attempt_at < fleet_snapshot_interval()
    ):
        return None
    _snapshot_gate.update(inflight=True, attempt_at=now)
    return start_background_task(_run_fleet_snapshot(), name='cap_hold_fleet_snapshot')


async def _settle_fleet_snapshot(task: asyncio.Task[Any] | None) -> None:
    """Publish before the sweep returns when the aggregation fits its wait."""
    if task is None:
        return
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=fleet_snapshot_wait())
    except asyncio.TimeoutError:
        # The shielded aggregation keeps running under its own RPC budget; the
        # in-flight gate stops a second one piling up behind it.
        logger.warning('event=cap_hold_redrive outcome=fleet_snapshot_slow')


async def sweep() -> dict:
    if not enabled():
        return {'disabled': True}
    sweep_started = time.monotonic()
    snapshot_task = _schedule_fleet_snapshot()
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
        await _settle_fleet_snapshot(snapshot_task)
        logger.info(
            'event=cap_hold_redrive outcome=complete visited=0 sealed=%s duration_seconds=%.3f',
            counts['sealed'],
            time.monotonic() - sweep_started,
        )
        return counts

    started = time.monotonic()
    visited = set()
    items_per_turn = owner_items()

    async def visit(snap: Any, turn: int):
        uid = owner(snap, 'processing_backlog')
        if uid is None or not recovery_cohort_admits(uid) or not funded_processing.enabled(uid):
            return None
        try:
            # One bounded candidate batch per owner per round. A fast owner
            # cannot drain its candidates before its peers get a turn.
            more = await processing_backlog_worker.run(
                uid,
                continuation=turn > 0,
                max_items=items_per_turn,
                time_budget=max(0, 900 - (time.monotonic() - started)),
            )
            visited.add(uid)
            return snap if more else None
        except Exception as error:
            logger.warning(
                'event=cap_hold_redrive outcome=worker_deferred uid=%s exception_type=%s',
                uid,
                type(error).__name__,
                exc_info=True,
            )
            return None

    choices = await run_blocking(db_executor, store.discover, 'choices', limit=choices_page())
    choices = await _paid_first(choices)
    for turn in range(100):
        if not choices or time.monotonic() - started >= 900:
            break
        results = await asyncio.gather(*(visit(snap, turn) for snap in choices))
        choices = [snap for snap in results if snap is not None]
    counts['visited'] = len(visited)
    await _settle_fleet_snapshot(snapshot_task)
    logger.info(
        'event=cap_hold_redrive outcome=complete visited=%s sealed=%s duration_seconds=%.3f choices_page=%s owner_items=%s',
        counts['visited'],
        counts['sealed'],
        time.monotonic() - sweep_started,
        choices_page(),
        items_per_turn,
    )
    return counts
