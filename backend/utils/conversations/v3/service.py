"""One named task and one renewable transaction lease per owner.

Markers are durable obligations. Dispatch failure never clears one; the sweeper
retries it. Switching admission off does not stop existing obligations.
"""

import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from google.cloud.firestore_v1 import FieldFilter

from utils.conversations.v3.triggers import mark_new, enqueue, changed, conversations_v3_enabled
from database import conversations as conversations_db, conversations_v3 as store, conversations_v3_fence as fence
from utils.conversations.v3.errors import Conflict
from models.conversation import Conversation
from models.conversation_enums import ConversationStatus
from utils.cloud_tasks import enqueue_named_task
from utils.conversations.v3 import outline, planner, models, metrics
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.executors import run_blocking, db_executor, llm_executor, postprocess_executor, storage_executor
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def recording_short_path(fn):
    @wraps(fn)
    def guarded(uid, language_code, conversation, *args, **kwargs):
        if not getattr(conversation, 'recording', False):
            if getattr(conversation, 'v3_derived', False) and not fence.current():
                token = store.acquire(uid, 'summary-' + conversation.id)
                if not token:
                    raise RuntimeError('v3_summary_busy')
                try:
                    with fence.writer(uid, conversation.id, token), models.notes_mode(uid):
                        return fn(uid, language_code, conversation, *args, **kwargs)
                finally:
                    store.release(uid, 'summary-' + conversation.id, token)
            return fn(uid, language_code, conversation, *args, **kwargs)
        # Import the lifecycle owner lazily: lifecycle also calls this module at
        # intake. No model, entitlement, notes, derived side effect or webhook.
        from utils.conversations import lifecycle
        from utils.conversations.process_conversation import DerivedEffectsDisposition

        if kwargs.get('derived_effects_disposition_observer'):
            kwargs['derived_effects_disposition_observer'](DerivedEffectsDisposition.TERMINAL_NO_DERIVED_EFFECTS)

        persisted = lifecycle.complete(uid, conversation.id)
        current = conversations_db.get_conversation(uid, conversation.id)
        if current and current.get('status') == 'completed':
            persisted = True
        if persisted:
            changed(
                uid,
                conversation.id,
                manual_end=kwargs.get('trigger') is not None
                and getattr(kwargs['trigger'], 'value', '') == 'client_finalize',
            )
            conversation.status = ConversationStatus.completed
        if kwargs.get('persistence_observer'):
            kwargs['persistence_observer'](persisted)
        return conversation

    return guarded


def _match(window, existing, used):
    start, end = window['lines'][0]['start'], window['lines'][-1]['end']
    candidates = [
        r
        for r in existing.values()
        if r['id'] not in used
        and r.get('started_at')
        and r.get('finished_at')
        and r['started_at'] <= end
        and r['finished_at'] >= start
    ]
    # First resulting split retains the live id. Deleted targets also retain
    # their identity, so rebuilds cannot resurrect a deleted time window.
    return min(candidates, key=lambda r: r['started_at']) if candidates else None


async def reconcile(uid, *, on_open=False, derive=False, _pass=0):
    token = await run_blocking(db_executor, store.acquire, uid, 'builder')
    if token is None:
        metrics.RECONCILES.labels('busy').inc()
        return 'busy'
    try:
        recordings, existing, cached = await run_blocking(db_executor, store.load_derive if derive else store.load, uid)
        now = datetime.now(timezone.utc)
        eligible = [
            r
            for r in recordings.values()
            if r
            and r.get('recording')
            and not r.get('deleted')
            and not r.get('sync_merged_into')
            and r.get('data_protection_level') != 'private'
        ]
        if not eligible and any(not r.get('deleted') and not r.get('sync_merged_into') for r in recordings.values()):
            raise Conflict('recording_not_readable')
        groups = outline.stretches(eligible, now)
        # Keep a bounded cache; every fingerprint is checked even for finished stretches.
        saved = {row['fingerprint']: row for row in cached}
        outlines, cache = [], []
        for group in groups:
            await run_blocking(db_executor, store.renew, uid, 'builder', token)
            hit = saved.get(group['fingerprint'])
            if hit:
                entries = hit['entries']
            elif group['finished'] or on_open:
                metrics.MODEL_CALLS.labels('outline').inc()
                messages = outline.messages(group, timezone.utc)
                if outlines:
                    messages.append(('human', 'Preceding conversation: ' + str(outlines[-1][-1])))
                content = await run_blocking(llm_executor, models.outline, uid, messages)
                entries = outline.parse(content, group)
            else:
                # First speech is visible without a paid call. Outline on open
                # or at the five-minute deadline provides the first real title.
                entries = [
                    {
                        'first_line': 1,
                        'title': '',
                        'line': '',
                        'kind': 'conversation',
                        'people': [],
                        'sections': [],
                        'emoji': '💬',
                    }
                ]
            outlines.append(entries)
            if group['finished'] or on_open:
                cache.append({'fingerprint': group['fingerprint'], 'entries': entries})
        rows, used = [], set()
        for window in planner.preserve_finished_windows(planner.windows(groups, outlines), existing, recordings):
            prior = existing.get(window.get('existing_id')) or _match(window, existing, used)
            if prior:
                used.add(prior['id'])
            row = planner.build(uid, window, recordings, prior)
            if derive:
                row['backfilled'] = True
            if prior and prior.get('deleted'):
                continue
            before = sum(len(s.get('text', '').split()) for s in (prior or {}).get('transcript_segments') or [])
            new_words = max(0, sum(len(s.get('text', '').split()) for s in row['transcript_segments']) - before)
            ended = window['finished']
            was_ended = prior and prior.get('status') != 'in_progress'
            rewrite = bool(
                was_ended
                and planner.late_rewrite(
                    previous_words=before,
                    new_words=new_words,
                    ended_at=prior['finished_at'],
                    now=now,
                    rewrites=prior.get('v3_rewrites', 0),
                )
            )
            if was_ended and not rewrite:
                row['status'] = prior['status']
                row['tile_state'] = prior.get('tile_state', 'done')
            waiting = any(recordings[l['conversation_id']].get('record_audio_partial') for l in window['lines'])
            if ended and waiting:
                row['tile_state'] = 'transcribing'
                row['v3_process_pending'] = False
                await run_blocking(db_executor, enqueue, uid, at=now + timedelta(minutes=1))
            if (
                ended
                and not waiting
                and (not was_ended or rewrite or (prior or {}).get('tile_state') == 'transcribing')
            ):
                row['v3_process_pending'] = True
                row['v3_rewrites'] = int((prior or {}).get('v3_rewrites') or 0) + int(rewrite)
            rows.append(row)
        await run_blocking(db_executor, store.renew, uid, 'builder', token)
        await run_blocking(db_executor, _commit, uid, token, recordings, existing, rows, cache[-128:])
        for group in groups:
            if not group['finished']:
                # A different minute than the currently executing task avoids
                # Cloud Tasks' completed-name dedupe swallowing the continuation.
                await run_blocking(
                    db_executor, enqueue, uid, at=max(group['end'] + outline.SILENCE, now + timedelta(minutes=1))
                )
        for row in rows:
            if row['id'] not in existing:
                metrics.VISIBLE_LATENCY.observe(max(0, (now - row['started_at']).total_seconds()))
        metrics.RECONCILES.labels('committed').inc()
    except Exception:
        metrics.RECONCILES.labels('error').inc()
        raise
    finally:
        await run_blocking(db_executor, store.release, uid, 'builder', token)
    await drain_processing(uid)
    if not derive and await run_blocking(db_executor, has_pending, uid):
        if _pass < 2:
            await reconcile(uid, _pass=_pass + 1)
        else:
            await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + timedelta(minutes=1))
    return 'committed'


def _commit(uid, token, recordings, existing, rows, cache):
    from utils.conversations import lifecycle

    lifecycle.commit_v3_projection(uid, token, recordings, existing, rows, cache)


async def drain_processing(uid):
    rows = await run_blocking(db_executor, pending_processing, uid)
    for row in rows:
        token = await run_blocking(db_executor, store.acquire, uid, 'summary-' + row['id'])
        if token is None:
            await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + timedelta(minutes=1))
            continue
        try:
            await run_blocking(postprocess_executor, _process, uid, row, token)
        finally:
            await run_blocking(db_executor, store.release, uid, 'summary-' + row['id'], token)


def pending_processing(uid):
    client = store.get_firestore_client()
    return [
        store._decode(uid, doc)
        for doc in store.collection(client, uid)
        .where(filter=FieldFilter('v3_process_pending', '==', True))
        .limit(store.LIMIT)
        .stream()
    ]


def _process(uid, row, token):
    from utils.conversations import lifecycle
    from utils.conversations.process_conversation import process_conversation

    if not row or row.get('deleted') or row.get('is_locked'):
        return
    words = sum(len(s.get('text', '').split()) for s in row.get('transcript_segments') or [])
    if row.get('kind') in {'media', 'background'} or words < 20 or (row.get('backfilled') and words < 600):
        lifecycle.complete(uid, row['id'])
    else:
        persisted = []
        with fence.writer(uid, row['id'], token), models.notes_mode(uid):
            result = process_conversation(
                uid,
                row.get('language') or 'en',
                Conversation(**row),
                persistence_observer=persisted.append,
                **({'trigger': ProcessingTrigger.SILENT_BACKFILL} if row.get('backfilled') else {})
            )
        if not persisted or not persisted[-1] or getattr(result.status, 'value', result.status) != 'completed':
            raise RuntimeError('v3_processing_not_completed')
        metrics.SUMMARY_WRITES.labels('rewrite' if row.get('v3_rewrites') else 'first').inc()
    metrics.SUMMARY_LATENCY.observe(max(0, (datetime.now(timezone.utc) - row['finished_at']).total_seconds()))
    store.settle_processing(uid, row['id'], token, row.get('sync_content_revision'), row['finished_at'])


async def sweep():
    client = await run_blocking(db_executor, store.get_firestore_client)
    rows = await run_blocking(
        db_executor,
        lambda: list(
            client.collection_group('conversations')
            .where(filter=FieldFilter('v3_pending', '==', True))
            .limit(1000)
            .stream()
        ),
    )
    now = datetime.now(timezone.utc)
    users = set()
    for doc in rows:
        row = doc.to_dict() or {}
        since = row.get('v3_pending_since')
        if since and now - since >= timedelta(minutes=10):
            parts = doc.reference.path.split('/')
            if len(parts) == 4 and parts[0] == 'users':
                users.add(parts[1])
                metrics.PENDING_AGE.observe((now - since).total_seconds())
    for uid in users:
        await run_blocking(db_executor, enqueue, uid)
    processing = await run_blocking(
        db_executor,
        lambda: list(
            client.collection_group('conversations')
            .where(filter=FieldFilter('v3_process_pending', '==', True))
            .limit(1000)
            .stream()
        ),
    )
    for doc in processing:
        parts = doc.reference.path.split('/')
        if len(parts) == 4 and parts[0] == 'users' and parts[1] not in users:
            users.add(parts[1])
            await run_blocking(db_executor, enqueue, parts[1])
    purges = await run_blocking(
        db_executor,
        lambda: list(
            client.collection_group('conversations')
            .where(filter=FieldFilter('v3_audio_purge_pending', '==', True))
            .limit(1000)
            .stream()
        ),
    )
    for doc in purges:
        parts = doc.reference.path.split('/')
        if len(parts) == 4 and parts[0] == 'users':
            await run_blocking(storage_executor, purge_audio, parts[1], parts[3])
    return len(users)


async def backfill(uid):
    from config.conversations_v3 import backfill_enabled

    if not backfill_enabled():
        raise RuntimeError('backfill_disabled')
    return await reconcile(uid, derive=True)


def purge_audio(uid, rid):
    from utils.other.storage import delete_privacy_conversation_audio

    if store.claim_audio_purge(uid, rid):
        delete_privacy_conversation_audio(uid, rid)
        conversations_db.update_conversation(uid, rid, {'v3_audio_purge_pending': False, 'audio_files': []})


async def measure_legacy_users():
    client = await run_blocking(db_executor, store.get_firestore_client)
    since = datetime.now(timezone.utc) - timedelta(days=1)
    snapshots = await run_blocking(
        db_executor,
        lambda: list(
            client.collection_group('conversations')
            .where(filter=FieldFilter('source', 'in', ['omi', 'phone']))
            .where(filter=FieldFilter('created_at', '>=', since))
            .select(['source', 'created_at', 'recording', 'v3_derived'])
            .limit(10001)
            .stream()
        ),
    )
    if len(snapshots) > 10000:
        raise RuntimeError('legacy_user_measurement_truncated')
    latest = {}
    for snapshot in snapshots:
        row = snapshot.to_dict() or {}
        parts = snapshot.reference.path.split('/')
        if len(parts) != 4 or parts[0] != 'users' or row.get('v3_derived'):
            continue
        uid = parts[1]
        if uid not in latest or row['created_at'] > latest[uid]['created_at']:
            latest[uid] = row
    count = sum(not r.get('recording') for r in latest.values())
    metrics.NON_V3.set(count)
    return {'active_legacy_users': count, 'measured_at': datetime.now(timezone.utc).isoformat()}


def has_pending(uid):
    return (
        next(
            iter(
                store.collection(store.get_firestore_client(), uid)
                .where(filter=FieldFilter('v3_pending', '==', True))
                .limit(1)
                .stream()
            ),
            None,
        )
        is not None
    )
