"""Bounded, fenced explicit-choice worker; reuses the held-audio receipt machinery."""

import asyncio
from functools import partial
from datetime import datetime, timezone
from enum import Enum
import logging
import time
from typing import Any

from google.cloud import firestore
from database import processing_backlog as store, conversations as conversations_db
from models.conversation import Conversation
from utils import funded_processing
from utils.processing_backlog import choose, is_active
from utils.conversations.process_conversation import process_conversation
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.executors import db_executor, postprocess_executor, storage_executor, run_blocking
from utils.sync import cap_hold, cap_hold_recovery, cap_hold_reservations, cap_work_budget
from config.rate_card import recording_units_per_hour
from config.stt_cap_dispatch import hold_lane, recovery_cohort_admits

logger = logging.getLogger(__name__)
PAGE = 10


class AttemptOutcome(Enum):
    COMPLETE = 'complete'
    DEFERRED = 'deferred'
    RETRY = 'retry'


def _page(uid, kind, cursor):
    if kind == 'audio':
        collection = cap_hold.holds(uid)
        query = collection.where('state', 'in', ['held', 'staging', 'sealing']).order_by(
            'listed_at', direction=firestore.Query.DESCENDING
        )
        field = 'listed_at'
    else:
        collection = store.items(uid)
        query = collection.order_by('started_at', direction=firestore.Query.DESCENDING)
        field = 'started_at'
    # Mapping cursors do not make the SDK append the document-name order.
    # Both fields must reach RunQuery to avoid skipping a timestamp's siblings.
    query = query.order_by('__name__', direction=firestore.Query.DESCENDING)
    if cursor:
        query = query.start_after({field: cursor['at'], '__name__': collection.document(cursor['id'])})
    return [(kind, snap) for snap in query.limit(PAGE).stream()]


def _timestamp(value):
    if isinstance(value, datetime):
        # Older manifests can contain Firestore timestamps, including naive UTC.
        return (value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)).timestamp()
    return float(value or 0)


def _candidate(kind, snap) -> dict[str, Any]:
    row = snap.to_dict() or {}
    at = row.get('listed_at' if kind == 'audio' else 'started_at', 0)
    units = (
        cap_hold.remaining_seconds(row) * float(recording_units_per_hour('batch')) / 3600
        if kind == 'audio'
        else row.get('units', 0)
    )
    return {
        'kind': kind,
        'id': snap.id,
        'at': at,
        'units': max(0, units),
        'state': row.get('state'),
        'queued_at': row.get('created_at' if kind == 'audio' else 'queued_at', 0),
    }


def _process_text(uid, identity) -> AttemptOutcome:
    row = conversations_db.get_conversation(uid, identity)
    if row is None or row.get('deleted'):
        # Deleted captures never get recreated. Repair a stale sibling queue.
        store.remove(uid, identity)
        return AttemptOutcome.COMPLETE
    if not row.get('processing_deferred'):
        store.remove(uid, identity)
        return AttemptOutcome.COMPLETE
    lease = store.claim_item(uid, identity)
    if lease is None:
        return AttemptOutcome.RETRY
    try:
        result = process_conversation(
            uid, row.get('language') or 'en', Conversation(**row), trigger=ProcessingTrigger.BACKLOG_CHOICE
        )
        return AttemptOutcome.DEFERRED if result.processing_deferred else AttemptOutcome.COMPLETE
    finally:
        store.release_item(uid, identity, lease)


async def _selected(uid, item) -> bool | None:
    if item['kind'] == 'text':
        return funded_processing.enabled(uid, 'batch')
    try:
        snap = await run_blocking(db_executor, cap_hold.holds(uid).document(item['id']).get)
        return not snap.exists or await cap_hold_recovery.selected_for_recovery(uid, snap.to_dict() or {})
    except Exception as error:
        logger.warning('event=processing_backlog outcome=scope_deferred exception_type=%s', type(error).__name__)
        return None


async def _release_excluded(uid, token, lease, period, item):
    manifest = None
    if item['kind'] == 'audio':
        snap = await run_blocking(db_executor, cap_hold.holds(uid).document(item['id']).get)
        if not snap.exists:
            return None
        manifest = snap.to_dict() or {}
        meta = await run_blocking(storage_executor, cap_hold.metadata, uid, manifest)
        lane = hold_lane(meta)
        if lane is None or funded_processing.enabled(uid, lane):
            return None
    elif item['kind'] != 'text' or funded_processing.enabled(uid, 'batch'):
        return None
    return await run_blocking(
        db_executor, store.release_undispatched_reservation, uid, token, lease, period, item, audio_manifest=manifest
    )


async def _process(uid, item) -> AttemptOutcome:
    if item['kind'] == 'text':
        if not funded_processing.enabled(uid, 'batch'):
            return AttemptOutcome.RETRY
        return await run_blocking(postprocess_executor, _process_text, uid, item['id'])
    snap = await run_blocking(db_executor, cap_hold.holds(uid).document(item['id']).get)
    if not snap.exists or (snap.to_dict() or {}).get('state') == 'purged':
        return AttemptOutcome.COMPLETE
    recovered = await cap_hold_recovery.recover_selected(uid, snap)
    return AttemptOutcome.COMPLETE if recovered else AttemptOutcome.RETRY


async def run(
    uid: str, *, continuation: bool = False, max_items: int = PAGE, time_budget: float | None = None
) -> bool | None:
    """True permits another round; false/None parks a blocked or inactive owner."""
    if not recovery_cohort_admits(uid) or not funded_processing.enabled(uid):
        return
    max_items = max(1, min(max_items, 100))
    if not continuation and not await run_blocking(db_executor, cap_hold.recovery_cooldown, uid):
        return
    job = await run_blocking(db_executor, store.read, uid)
    if not is_active(job):
        return
    token = job['token']
    lease = await run_blocking(db_executor, store.claim, uid, token, funded_processing.period_id())
    if lease is None:
        return

    async def save(updates):
        ok = await run_blocking(db_executor, store.checkpoint, uid, token, lease, updates)
        if ok:
            job.update(updates)
        return ok

    async def finish():
        try:
            # The transaction alone decides whether a durable reservation can
            # finish, or an already-authorized upgrade needs a new-token run.
            return await run_blocking(db_executor, store.finish, uid, token, lease, funded_processing.period_id())
        except Exception as exc:
            logger.warning('event=processing_backlog outcome=finish_deferred exception_type=%s', type(exc).__name__)
            return False

    async def attempt(item):
        # Executors and spawned callbacks inherit this UID/month grant. Later
        # model/STT dispatches must not silently adopt a reset allowance.
        with funded_processing.backlog_consent(uid, job['period']):
            outcome = await _process(uid, item)
        if outcome in (AttemptOutcome.COMPLETE, AttemptOutcome.DEFERRED):
            # A returned deferred result is known complete, unlike a busy lease
            # or an ambiguous application failure. Its queue row stays waiting.
            return await save({'reserved': {}})
        return False

    fence_lost = asyncio.Event()

    async def renew():
        while True:
            await asyncio.sleep(60)
            if not await save({'lease_until': time.time() + 1800}):
                fence_lost.set()
                return

    async def work(limit: int) -> bool:
        if cap_work_budget.exhausted():
            return False
        reserved = job.get('reserved') or {}
        # A reserved application attempt keeps its identity over crashes and
        # cooldowns. Never debit the user's chosen estimate twice.
        if reserved:
            if job['period'] != funded_processing.period_id():
                return False
            selected = await _selected(uid, reserved)
            if selected is None:
                return False
            if not selected:
                try:
                    released = await _release_excluded(uid, token, lease, job['period'], reserved)
                except Exception as error:
                    # A committed refund's response may be lost. Never finish
                    # from stale local state; the next visit rereads the choice.
                    logger.warning(
                        'event=processing_backlog outcome=release_deferred exception_type=%s', type(error).__name__
                    )
                    return False
                if released is None:
                    return False
                job.update(released)
            elif not await attempt(reserved):
                return False
            elif limit == 1:
                return True  # Resuming a reservation consumes this owner's turn.
        pages = await run_blocking(db_executor, _page, uid, 'audio', job.get('cursor_audio'))
        pages += await run_blocking(db_executor, _page, uid, 'text', job.get('cursor_text'))
        candidates = sorted(
            (_candidate(kind, snap) for kind, snap in pages),
            key=lambda row: (_timestamp(row['at']), row['id']),
            reverse=True,
        )[:limit]
        for item in candidates:
            if (
                cap_work_budget.exhausted()
                or fence_lost.is_set()
                or not funded_processing.enabled(uid)
                or job['period'] != funded_processing.period_id()
            ):
                return False
            remaining = job.get('remaining')
            cursor = {'at': item['at'], 'id': item['id']}
            updates: dict[str, Any] = {'cursor_' + item['kind']: cursor, 'lease_until': time.time() + 1800}
            if _timestamp(item['queued_at']) > _timestamp(job['cutoff']):
                if not await save(updates):
                    return False
                continue
            if not await _selected(uid, item):
                if not await save({**updates, 'scope_skipped': True}):
                    return False
                continue
            current = await run_blocking(db_executor, funded_processing.allowance, uid)
            if not current.managed:
                return await finish()
            if remaining is not None and item['units'] > remaining:
                if not await save(updates):
                    return False
                continue
            # An authorized pre-cutoff source must seal before we advance past
            # it or finish this choice. Its created_at/listed_at survive sealing.
            if item.get('state') in {'staging', 'sealing'}:
                return False
            actual_remaining, _ = funded_processing.capacity(current)
            if actual_remaining is not None:
                # Cap-hold units handed to batch are debited only at projection; their open
                # reservations stand in for that spend until the batch outcome is known.
                reserved_units = await run_blocking(
                    db_executor,
                    partial(
                        cap_hold_reservations.open_units,
                        uid,
                        job['period'],
                        status_reader=cap_hold_reservations.batch_status,
                    ),
                )
                # Re-read after settling: a projection that commits between the first allowance read
                # and open_units drops its reservation, so only a later read sees its usage. A commit
                # after open_units is counted twice, which under-admits (safe).
                current = await run_blocking(db_executor, funded_processing.allowance, uid)
                if not current.managed:
                    return await finish()
                actual_remaining, _ = funded_processing.capacity(current)
                if actual_remaining is not None:
                    actual_remaining = max(0.0, actual_remaining - reserved_units)
            if actual_remaining is not None and item['units'] > actual_remaining:
                if not await save(updates):
                    return False
                continue
            updates.update(reserved=item, remaining=None if remaining is None else max(0, remaining - item['units']))
            if not await save(updates):
                return False
            if not await attempt(item):
                return False
        if len(candidates) == limit:
            return True
        return await finish()

    continuation = False
    heartbeat = asyncio.create_task(renew(), name='processing_backlog_lease')
    try:
        with cap_work_budget.visit(time_budget):
            for offset in range(0, max_items, PAGE):
                continuation = await work(min(PAGE, max_items - offset))
                if not continuation or cap_work_budget.exhausted():
                    break
    except Exception as exc:
        logger.warning('event=processing_backlog outcome=deferred exception_type=%s', type(exc).__name__)
        continuation = await finish()
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
        try:
            await save({'lease_until': 0})
        except Exception as exc:
            logger.warning('event=processing_backlog outcome=release_deferred exception_type=%s', type(exc).__name__)
    # A productive page remains state=processing. The periodic durable sweep
    # owns continuation, including an authorized pending upgrade consumed above.
    return continuation


def upgrade(uid: str, request_key: str, *, intent_at):
    """Only payment intent calls this; monthly renewal/reset never creates intent."""
    choose(uid, request_key=request_key, automatic=True, intent_at=intent_at)


async def upgrade_async(uid: str, request_key: str, *, intent_at):
    await run_blocking(db_executor, choose, uid, request_key=request_key, automatic=True, intent_at=intent_at)


cap_hold_recovery.register_backlog_runner(run)
