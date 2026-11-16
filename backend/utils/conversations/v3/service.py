"""One named task and one renewable transaction lease per owner.

Markers are durable obligations. Dispatch failure never clears one; the sweeper
retries it. Switching admission off does not stop existing obligations.
"""

from database import conversations_v3_leases as leases

from database import conversations_v3_processing as writers

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps

from google.cloud.firestore_v1 import FieldFilter

from utils.conversations.v3.triggers import enqueue, changed
from utils.conversations.v3.renewal import renew_until_done, leased_work
from database import conversations as conversations_db, conversations_v3 as store, conversations_v3_fence as fence
from models.conversation import Conversation
from models.conversation_enums import ConversationStatus
from utils.conversations.v3 import outline, planner, models, metrics, policy, visibility, context
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.executors import run_blocking, db_executor, llm_executor, postprocess_executor, storage_executor

logger = logging.getLogger(__name__)


def recording_short_path(fn):
    @wraps(fn)
    def guarded(uid, language_code, conversation, *args, **kwargs):
        if not policy.flag(conversation, 'recording'):
            if policy.flag(conversation, 'v3_derived') and not fence.current():
                from utils.conversations.v3.processing import run_external

                return run_external(fn, uid, language_code, conversation, *args, **kwargs)
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


async def reconcile(uid, *, on_open=False, conversation_id=None, derive=False, _pass=0):
    token = await run_blocking(db_executor, leases.acquire, uid, 'builder')
    if token is None:
        metrics.RECONCILES.labels('busy').inc()
        return 'busy'
    try:
        recordings, existing, cached = await run_blocking(
            db_executor,
            store.load_derive if derive else store.load,
            uid,
            **({'conversation_id': conversation_id} if on_open and conversation_id else {})
        )
        now = datetime.now(timezone.utc)
        eligible = [
            r
            for r in recordings.values()
            if r
            and r.get('recording')
            and not r.get('deleted')
            and not r.get('sync_merged_into')
            and r.get('data_protection_level') != 'private'
            and r.get('started_at')
            and not r.get('_v3_unreadable')
        ]
        groups = outline.stretches(eligible, now)
        if on_open and conversation_id:
            target = existing.get(conversation_id)
            if target is None:
                return 'stored'
            ids = set(target.get('v3_recording_ids') or [])
            groups = [
                g
                for g in groups
                if any(l['conversation_id'] in ids for l in g['lines'])
                and g['lines'][0]['start'] <= target['finished_at']
                and g['end'] >= target['started_at']
            ]
            if not groups:
                return 'stored'
        # Keep a bounded cache; every fingerprint is checked even for finished stretches.
        saved = {row['fingerprint']: row for row in cached}
        outlines, cache = [], []
        background = await run_blocking(db_executor, context.outline_sources, uid, groups)
        for group in groups:
            await run_blocking(db_executor, leases.renew, uid, 'builder', token)
            messages = outline.messages(group, timezone.utc)
            messages.append(
                (
                    'human',
                    context.outline_block(
                        group, background, [entry['title'] for entries in outlines for entry in entries]
                    ),
                )
            )
            # Resume evidence is part of the cache key too.
            if outlines:
                previous = outlines[-1][-1]
                messages.append(('human', 'Preceding conversation: ' + previous['title'] + '\n' + previous['line']))
            fingerprint = context.cache_key(group, messages)
            hit = saved.get(fingerprint)
            if hit:
                entries = hit['entries']
            elif group['finished'] or on_open:
                if await run_blocking(db_executor, store.outline_attempt, uid, token, fingerprint):
                    metrics.MODEL_CALLS.labels('outline').inc()
                    content = await leased_work(uid, 'builder', token, llm_executor, models.outline, uid, messages)
                    try:
                        entries = outline.parse(content, group)
                    except (ValueError, KeyError, TypeError):
                        entries = outline.fallback(group)
                        entries = [{**entry, '_outline_failed': True} for entry in entries]
                        metrics.RECONCILES.labels('outline_fallback').inc()
                else:
                    entries = [{**entry, '_outline_failed': True} for entry in outline.fallback(group)]
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
                cache.append({'fingerprint': fingerprint, 'entries': entries})
        rows, used = [], set()
        windows = planner.preserve_finished_windows(planner.windows(groups, outlines), existing, recordings)
        await run_blocking(db_executor, visibility.hydrate_recognition, uid, recordings, windows)
        for window in windows:
            # An affirmative transcription failure is terminal even before the silence deadline.
            if any(policy.transcription_failed(recordings[line['conversation_id']]) for line in window['lines']):
                window['finished'] = True
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
            promoted = bool(
                prior
                and not row.get('home_hidden')
                and (
                    row.get('manual_end')
                    and not prior.get('manual_end')
                    or prior.get('kind') == 'background'
                    and row['kind'] == 'conversation'
                )
            )
            if promoted:
                row['summary_covers_through'] = None
            rewrite = bool(
                prior is not None
                and was_ended
                and planner.late_rewrite(
                    previous_words=before,
                    new_words=new_words,
                    ended_at=prior['finished_at'],
                    now=now,
                    rewrites=prior.get('v3_rewrites', 0),
                )
            )
            if rewrite:
                # The old summary no longer covers the window: without this the covered-summary guard
                # returns the previous notes and the only automatic rewrite is spent on nothing.
                row['summary_covers_through'] = None
            if prior is not None and was_ended and not rewrite and not promoted:
                row['status'] = prior['status']
                row['tile_state'] = prior.get('tile_state', 'done')
            transcription_failed = any(
                policy.transcription_failed(recordings[l['conversation_id']]) for l in window['lines']
            )
            waiting = not transcription_failed and any(
                policy.transcription_pending(recordings[l['conversation_id']]) for l in window['lines']
            )
            if ended and waiting:
                row['tile_state'] = 'transcribing'
                row['v3_process_pending'] = False
                await run_blocking(db_executor, enqueue, uid, at=now + timedelta(minutes=1))
            if (
                ended
                and not waiting
                and (not was_ended or rewrite or promoted or (prior or {}).get('tile_state') == 'transcribing')
            ):
                row['v3_process_pending'] = True
                row['v3_rewrites'] = int((prior or {}).get('v3_rewrites') or 0) + int(rewrite)
            if ended and (not was_ended or rewrite or promoted or (prior or {}).get('tile_state') == 'transcribing'):
                if not row.get('is_locked') and (transcription_failed or window.get('_outline_failed')):
                    row.update(
                        await run_blocking(
                            db_executor,
                            writers.failure_patch,
                            reason='transcription' if transcription_failed else 'outline',
                        )
                    )
            rows.append(row)
        await run_blocking(db_executor, leases.renew, uid, 'builder', token)
        await run_blocking(
            db_executor, _commit, uid, token, recordings, existing, rows, cache[-128:], clear_pending=not on_open
        )
        for group in groups:
            if not group['finished']:
                # A different minute than the currently executing task avoids
                # Cloud Tasks' completed-name dedupe swallowing the continuation.
                await run_blocking(
                    db_executor, enqueue, uid, at=max(group['end'] + outline.SILENCE, now + timedelta(minutes=1))
                )
        for row in rows:
            prior = existing.get(row['id']) or {}
            if (
                not row.get('home_hidden')
                and row.get('home_hidden_reason') == 'wearer_recognition_uncertain'
                and (prior.get('home_hidden') or prior.get('home_hidden_reason') != 'wearer_recognition_uncertain')
            ):
                metrics.UNCERTAIN_SHOWN.inc()
            if row['id'] not in existing:
                metrics.VISIBLE_LATENCY.observe(max(0, (now - row['started_at']).total_seconds()))
        metrics.RECONCILES.labels('committed').inc()
    except Exception:
        metrics.RECONCILES.labels('error').inc()
        raise
    finally:
        await run_blocking(db_executor, leases.release, uid, 'builder', token)
    if on_open:
        await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + timedelta(minutes=1))
        return 'committed'
    await drain_processing(uid)
    if not derive and await run_blocking(db_executor, has_pending, uid):
        if _pass < 2:
            await reconcile(uid, _pass=_pass + 1)
        else:
            await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + timedelta(minutes=1))
    return 'committed'


def _commit(uid, token, recordings, existing, rows, cache, *, clear_pending=True):
    from utils.conversations import lifecycle

    lifecycle.commit_v3_projection(uid, token, recordings, existing, rows, cache, clear_pending=clear_pending)


async def drain_processing(uid):
    rows = await run_blocking(db_executor, pending_processing, uid)
    for row in rows:
        if row is None:
            continue
        token = await run_blocking(db_executor, leases.acquire, uid, 'summary-' + row['id'])
        if token is None:
            await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + timedelta(minutes=1))
            continue
        try:
            worker = asyncio.create_task(run_blocking(postprocess_executor, _process, uid, row, token))
            keeper = asyncio.create_task(renew_until_done(uid, 'summary-' + row['id'], token, worker))
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                await asyncio.shield(worker)
                await keeper
                raise
            await keeper
        finally:
            await run_blocking(db_executor, leases.release, uid, 'summary-' + row['id'], token)


def pending_processing(uid):
    client = store.get_firestore_client()
    return [
        store.decode_row(uid, doc)
        for doc in store.user_conversations(client, uid)
        .where(filter=FieldFilter('v3_process_pending', '==', True))
        .limit(store.LIMIT)
        .stream()
    ]


def _process(uid, row, token):
    from utils.conversations import lifecycle
    from utils.conversations.process_conversation import process_conversation

    if not row:
        return
    if row.get('deleted') or row.get('is_locked'):
        writers.settle_processing(uid, row['id'], token, row.get('sync_content_revision'), None, skipped=True)
        return
    if policy.transcription_failed(row):
        writers.fail_processing(
            uid,
            row['id'],
            token,
            row.get('sync_content_revision'),
            content_hash=writers.processing_hash(row),
            retryable=bool(row.get('transcript_segments')),
        )
        return
    if not writers.begin_processing(uid, row, token):
        return
    words = sum(len(s.get('text', '').split()) for s in row.get('transcript_segments') or [])
    if row.get('kind') in {'media', 'background'} or (
        not policy.manual_intent(row) and (words < 20 or (row.get('backfilled') and words < 600))
    ):
        lifecycle.complete(uid, row['id'])
    else:
        persisted = []
        with fence.writer(uid, row['id'], token), models.notes_mode(uid):
            result = process_conversation(
                uid,
                row.get('language') or 'en',
                Conversation(**row),
                persistence_observer=persisted.append,
                trigger=(ProcessingTrigger.SILENT_BACKFILL if row.get('backfilled') else ProcessingTrigger.CAPTURE_END),
            )
        if getattr(result.status, 'value', result.status) == 'failed':
            writers.fail_processing(
                uid, row['id'], token, row.get('sync_content_revision'), content_hash=writers.processing_hash(row)
            )
            return
        if not persisted or not persisted[-1] or getattr(result.status, 'value', result.status) != 'completed':
            raise RuntimeError('v3_processing_not_completed')
        metrics.SUMMARY_WRITES.labels('rewrite' if row.get('v3_rewrites') else 'first').inc()
    metrics.SUMMARY_LATENCY.observe(max(0, (datetime.now(timezone.utc) - row['finished_at']).total_seconds()))
    writers.settle_processing(
        uid,
        row['id'],
        token,
        row.get('sync_content_revision'),
        row['finished_at'],
        content_hash=writers.processing_hash(row),
    )


async def sweep():
    client = await run_blocking(db_executor, store.get_firestore_client)
    now = datetime.now(timezone.utc)
    users = set()
    cursor = None
    while True:
        query = (
            client.collection_group('conversations')
            .where(filter=FieldFilter('v3_pending', '==', True))
            .where(filter=FieldFilter('v3_pending_since', '<=', now - timedelta(minutes=10)))
            .order_by('v3_pending_since')
            .order_by('__name__')
            .limit(1000)
        )
        if cursor is not None:
            query = query.start_after(cursor)
        rows = await run_blocking(db_executor, lambda: list(query.stream()))
        for doc in rows:
            row = doc.to_dict() or {}
            since = row['v3_pending_since']
            parts = doc.reference.path.split('/')
            if len(parts) == 4 and parts[0] == 'users':
                users.add(parts[1])
                metrics.PENDING_AGE.observe((now - since).total_seconds())
        if len(rows) < 1000:
            break
        cursor = rows[-1]
    for uid in users:
        await run_blocking(db_executor, enqueue, uid)
    cursor = None
    while True:
        query = (
            client.collection_group('conversations')
            .where(filter=FieldFilter('v3_process_pending', '==', True))
            .order_by('__name__')
            .limit(1000)
        )
        if cursor is not None:
            query = query.start_after(cursor)
        processing = await run_blocking(db_executor, lambda: list(query.stream()))
        for doc in processing:
            parts = doc.reference.path.split('/')
            if len(parts) == 4 and parts[0] == 'users' and parts[1] not in users:
                users.add(parts[1])
                try:
                    await run_blocking(db_executor, enqueue, parts[1])
                except Exception as exc:
                    logger.warning('event=v3_process_dispatch outcome=retry exception_type=%s', type(exc).__name__)
        if len(processing) < 1000:
            break
        cursor = processing[-1]
    cursor = None
    while True:
        query = (
            client.collection_group('conversations')
            .where(filter=FieldFilter('v3_audio_purge_pending', '==', True))
            .order_by('__name__')
            .limit(1000)
        )
        if cursor is not None:
            query = query.start_after(cursor)
        purges = await run_blocking(db_executor, lambda: list(query.stream()))
        for doc in purges:
            parts = doc.reference.path.split('/')
            retry_at = (doc.to_dict() or {}).get('v3_audio_purge_retry_after')
            if len(parts) == 4 and parts[0] == 'users' and (not retry_at or retry_at <= now):
                try:
                    await run_blocking(storage_executor, purge_audio, parts[1], parts[3])
                except Exception as exc:
                    logger.warning('event=v3_audio_purge outcome=retry exception_type=%s', type(exc).__name__)
                    try:
                        await run_blocking(
                            db_executor,
                            conversations_db.update_conversation,
                            parts[1],
                            parts[3],
                            {
                                'v3_audio_purge_pending': True,
                                'v3_audio_purge_retry_after': now + timedelta(minutes=5),
                                'v3_audio_purge_attempts': int(
                                    (doc.to_dict() or {}).get('v3_audio_purge_attempts') or 0
                                )
                                + 1,
                            },
                        )
                    except Exception as state_error:
                        # The original pending obligation still survives a failed retry-state write.
                        logger.warning(
                            'event=v3_audio_purge_retry_state outcome=pending exception_type=%s',
                            type(state_error).__name__,
                        )
        if len(purges) < 1000:
            break
        cursor = purges[-1]
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
                store.user_conversations(store.get_firestore_client(), uid)
                .where(filter=FieldFilter('v3_pending', '==', True))
                .limit(1)
                .stream()
            ),
            None,
        )
        is not None
    )
