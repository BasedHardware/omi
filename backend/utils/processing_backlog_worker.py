"""Bounded, fenced explicit-choice worker; reuses the held-audio receipt machinery."""

import asyncio
import logging
import time
from typing import Any

from anyio import from_thread
from google.cloud import firestore
from database import processing_backlog as store, conversations as conversations_db
from models.conversation import Conversation
from utils import funded_processing
from utils.processing_backlog import choose, is_active
from utils.conversations.process_conversation import process_conversation
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.executors import db_executor, postprocess_executor, run_blocking, start_background_task
from utils.sync import cap_hold, cap_hold_recovery
from config.rate_card import recording_units_per_hour

logger = logging.getLogger(__name__)
PAGE = 10


def _page(uid, kind, cursor):
    if kind == 'audio':
        collection = cap_hold.holds(uid)
        query = collection.where('state', 'in', ['held']).order_by('listed_at', direction=firestore.Query.DESCENDING)
        field = 'listed_at'
    else:
        collection = store.items(uid)
        query = collection.order_by('started_at', direction=firestore.Query.DESCENDING)
        field = 'started_at'
    if cursor:
        query = query.start_after({field: cursor['at'], '__name__': collection.document(cursor['id'])})
    return [(kind, snap) for snap in query.limit(PAGE).stream()]


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
        'queued_at': row.get('created_at' if kind == 'audio' else 'queued_at', 0),
    }


def _process_text(uid, identity):
    row = conversations_db.get_conversation(uid, identity)
    if row is None or row.get('deleted'):
        # Deleted captures never get recreated. Repair a stale sibling queue.
        store.remove(uid, identity)
        return True
    if not row.get('processing_deferred'):
        store.remove(uid, identity)
        return True
    lease = store.claim_item(uid, identity)
    if lease is None:
        return False
    try:
        with funded_processing.admission_scope():
            result = process_conversation(
                uid, row.get('language') or 'en', Conversation(**row), trigger=ProcessingTrigger.BACKLOG_CHOICE
            )
        return not result.processing_deferred
    finally:
        store.release_item(uid, identity, lease)


async def _process(uid, item):
    if item['kind'] == 'text':
        return await run_blocking(postprocess_executor, _process_text, uid, item['id'])
    snap = await run_blocking(db_executor, cap_hold.holds(uid).document(item['id']).get)
    if not snap.exists or (snap.to_dict() or {}).get('state') == 'purged':
        return True
    return await cap_hold_recovery.recover_selected(uid, snap)


async def run(uid: str, *, continuation: bool = False):
    if not funded_processing.enabled():
        return
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

    continuation = False
    fence_lost = asyncio.Event()

    async def renew():
        while True:
            await asyncio.sleep(60)
            if not await save({'lease_until': time.time() + 1800}):
                fence_lost.set()
                return

    heartbeat = start_background_task(renew(), name='processing_backlog_lease')
    try:
        reserved = job.get('reserved') or {}
        # A reserved application attempt keeps its identity over crashes and
        # cooldowns. Never debit the user's chosen estimate twice.
        if reserved:
            if not await _process(uid, reserved):
                return
            if not await save({'reserved': {}}):
                return
        pages = await run_blocking(db_executor, _page, uid, 'audio', job.get('cursor_audio'))
        pages += await run_blocking(db_executor, _page, uid, 'text', job.get('cursor_text'))
        candidates = sorted(
            (_candidate(kind, snap) for kind, snap in pages), key=lambda row: (row['at'], row['id']), reverse=True
        )[:PAGE]
        for item in candidates:
            if fence_lost.is_set() or not funded_processing.enabled() or job['period'] != funded_processing.period_id():
                return
            remaining = job.get('remaining')
            cursor = {'at': item['at'], 'id': item['id']}
            updates: dict[str, Any] = {'cursor_' + item['kind']: cursor, 'lease_until': time.time() + 1800}
            if item['queued_at'] > job['cutoff'] or remaining is not None and item['units'] > remaining:
                if not await save(updates):
                    return
                continue
            current = await run_blocking(db_executor, funded_processing.allowance, uid)
            actual_remaining, _ = funded_processing.capacity(current)
            if not current.managed or actual_remaining is not None and item['units'] > actual_remaining:
                if not await save(updates):
                    return
                continue
            updates.update(reserved=item, remaining=None if remaining is None else max(0, remaining - item['units']))
            if not await save(updates):
                return
            if not await _process(uid, item):
                return
            if not await save({'reserved': {}}):
                return
        if len(candidates) == PAGE:
            continuation = True
        else:
            await save({'state': 'waiting_choice'})
    except Exception as exc:
        logger.warning('event=processing_backlog outcome=deferred exception_type=%s', type(exc).__name__)
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
        await save({'lease_until': 0})
    if continuation:
        start_background_task(run(uid, continuation=True), name='processing_backlog_continuation')


async def _schedule(uid):
    start_background_task(run(uid), name='processing_backlog')


def kick(uid: str):
    if not funded_processing.enabled():
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        from_thread.run(_schedule, uid)
    else:
        start_background_task(run(uid), name='processing_backlog')


def upgrade(uid: str, request_key: str):
    """Only payment intent calls this; monthly renewal/reset never creates intent."""
    if choose(uid, request_key=request_key, automatic=True) is not None:
        kick(uid)


async def upgrade_async(uid: str, request_key: str):
    if await run_blocking(db_executor, choose, uid, request_key=request_key, automatic=True) is not None:
        kick(uid)


cap_hold_recovery.register_backlog_runner(run)
