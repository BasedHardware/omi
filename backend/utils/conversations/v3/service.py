"""One named task and one renewable transaction lease per owner.

Markers are durable obligations. Dispatch failure never clears one; the sweeper
retries it. Switching admission off does not stop existing obligations.
"""

from database import conversations_v3_leases as leases

from database import conversations_v3_processing as writers

import asyncio
import hashlib
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from uuid import NAMESPACE_URL, uuid5

from google.cloud.firestore_v1 import FieldFilter

from config.conversations_v3 import stretch_cohesion_enabled
from utils.conversations.v3.triggers import enqueue, changed
from utils.conversations.v3.renewal import renew_until_done, leased_work
from database import conversations as conversations_db, conversations_v3 as store, conversations_v3_fence as fence
from models.conversation import Conversation
from models.conversation_enums import ConversationStatus
from utils.conversations.v3 import Conflict, outline, planner, models, metrics, policy, visibility, context
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.executors import run_blocking, db_executor, llm_executor, postprocess_executor, storage_executor

logger = logging.getLogger(__name__)

# Live capture keeps appending to its recording while a pass runs, so the commit's revision fence
# loses these races routinely. They answer the task and wake the owner again at the next minute
# (one coalesced named task per owner-minute) instead of burning Cloud Tasks attempts on a 500.
RACES = frozenset({'source_changed', 'lease_lost'})
RACE_RETRY = timedelta(minutes=1)

# Conflicts that fail identically until the data or code changes. Other races (summary/processing
# source changes) stay retryable errors.
BLOCKED = frozenset(
    {
        'target_exists',
        'target_deleted',
        'multiple_open_conversations',
        'v3_source_closure_budget',
        'v3_derived_budget',
        'recording_decode_unavailable',
        'account_deletion',
        'document_too_large',
        'request_too_large',
        'backfill_partition_budget',
        'remove_not_backfilled',
        'rederive_mixed_runs',
        'backfill_source_unreadable',
    }
)


# A blocked owner's earlier passes may have committed windows that still owe notes; draining them is
# safe for every reason except a pending account deletion.
NO_DRAIN = frozenset({'account_deletion'})


def owner_tag(uid):
    return hashlib.sha256(str(uid).encode()).hexdigest()[:12]


def redacted_cause(error):
    """The blocking error's cause: its type, plus the size limit and byte counts for a Firestore size error.

    Never the raw message: Firestore names the document path (owner and conversation ids).
    """
    cause = getattr(error, '__cause__', None)
    if cause is None:
        return '-'
    text = str(cause)
    # Pure string checks (store.size_error's markers): this runs on the event loop.
    kind = 'document' if store.DOCUMENT_TOO_LARGE in text else 'request' if store.REQUEST_TOO_LARGE in text else None
    if not kind:
        return type(cause).__name__
    sizes = ','.join(re.findall(r'\(?(\d+) bytes', text)) or '-'
    return f'{type(cause).__name__} limit={kind} bytes={sizes}'


async def _drain_blocked(uid, reason):
    if reason in NO_DRAIN:
        return
    try:
        await drain_processing(uid)
    except Exception as error:
        logger.warning('v3 reconcile blocked drain failed exception_type=%s', type(error).__name__)


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
    published = window.get('_published_ids', ())
    candidates = [
        r
        for r in existing.values()
        if r['id'] not in used
        and (r['id'] not in published or r.get('deleted'))
        and r.get('started_at')
        and r.get('finished_at')
        and r['started_at'] <= end
        and r['finished_at'] >= start
    ]
    # Published claimants are assigned by the planner. Time matching is the fallback
    # for live rows, legacy rows without claims or playback, and deletion tombstones.
    return min(candidates, key=lambda r: r['started_at']) if candidates else None


def _backfill_runs(window, recordings):
    """The backfill runs whose donors contributed this window (live builder passes included), in line order."""
    found = []
    for line in window['lines']:
        source = recordings.get(line['conversation_id']) or {}
        run = source.get('_v3_backfill_run') or source.get('v3_backfill_run')
        if run and run not in found:
            found.append(run)
    return found


async def reconcile(
    uid,
    *,
    on_open=False,
    conversation_id=None,
    derive=False,
    since=None,
    until=None,
    run_id=None,
    rederive=False,
    report=None,
    _pass=0,
):
    """One builder pass. ``derive`` is one planned backfill partition ([since, until), one owner).

    A derive pass applies every live planning, visibility and notes rule; it differs only in its
    inputs (legacy donors instead of v3_pending recordings), in stamping rows ``backfilled`` and in
    queueing notes on its own marker, drained by the backfill task instead of the live queue.
    """
    report = {} if report is None else report
    key = store.BACKFILL_LEASE if derive else 'builder'
    blocked = None
    moved = set()
    # Live passes call the outline-cache writers exactly as before; only a backfill names its lease.
    keyed = {'key': key} if derive else {}
    if not on_open and not derive:
        backoff, parked = await run_blocking(db_executor, store.backoff_state, uid)
        if backoff and backoff > datetime.now(timezone.utc):
            metrics.RECONCILES.labels('backoff').inc()
            # Rows earlier passes committed still owe notes while the builder is parked.
            await _drain_blocked(uid, parked)
            return 'backoff'
    token = await run_blocking(db_executor, leases.acquire, uid, key)
    if token is None:
        metrics.RECONCILES.labels('busy').inc()
        return 'busy'
    try:
        if derive:
            recordings, existing, cached = await run_blocking(
                db_executor,
                store.load_derive,
                uid,
                since=since,
                until=until,
                run_id=run_id,
                rederive=rederive,
            )
        else:
            recordings, existing, cached = await run_blocking(
                db_executor,
                store.load,
                uid,
                **({'conversation_id': conversation_id} if on_open and conversation_id else {}),
            )
        now = datetime.now(timezone.utc)
        eligible = [r for r in recordings.values() if policy.builder_eligible(r)]
        cohesion = stretch_cohesion_enabled()
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
            await run_blocking(db_executor, leases.renew, uid, key, token)
            messages = outline.messages(group, timezone.utc, cohesion=cohesion)
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
                report['outline_cache_hits'] = report.get('outline_cache_hits', 0) + 1
            elif group['finished'] or on_open:
                if await run_blocking(db_executor, store.outline_attempt, uid, token, fingerprint, **keyed):
                    metrics.MODEL_CALLS.labels('outline').inc()
                    report['outline_calls'] = report.get('outline_calls', 0) + 1
                    content = await leased_work(uid, key, token, llm_executor, models.outline, uid, messages)
                    try:
                        entries = outline.parse(content, group)
                        await run_blocking(db_executor, store.save_outline, uid, token, fingerprint, entries, **keyed)
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

        async def plan():
            windows = planner.preserve_finished_windows(
                planner.windows(groups, outlines, cohesion=cohesion), existing, recordings
            )
            # A retained finished conversation owns its id by claim evidence; a fresh window that sorts
            # before it (late speech overlapping its start) must not time-match the same id. Two planned
            # rows with one id each re-add the source's held claims, doubling them every pass until the
            # recording outgrows Firestore's 1 MiB document limit (document_too_large).
            rows, used = [], {window['existing_id'] for window in windows if window.get('existing_id')}
            taken = set()
            allocated = {}
            await run_blocking(db_executor, visibility.hydrate_recognition, uid, recordings, windows)
            for window in windows:
                # An affirmative transcription failure is terminal even before the silence deadline.
                if any(policy.transcription_failed(recordings[line['conversation_id']]) for line in window['lines']):
                    window['finished'] = True
                prior = existing.get(window.get('existing_id')) or _match(window, existing, used)
                if prior:
                    used.add(prior['id'])
                row = planner.build(uid, window, recordings, prior, allocated=allocated)
                published_ids = window.get('_published_ids', ())
                if not prior and (row['id'] in used | taken or row['id'] in published_ids):
                    first = window['lines'][0]['conversation_id']
                    seed = f"v3:{uid}:{row['started_at'].isoformat()}:{first}"
                    blocked_ids = used | taken | set(published_ids)
                    # Preserve the recording-qualified ID when free. Same-clock windows can also
                    # share a recording, so probe deterministic suffixes in planner order.
                    identifier = str(uuid5(NAMESPACE_URL, seed))
                    suffix = 0
                    while identifier in blocked_ids:
                        suffix += 1
                        identifier = str(uuid5(NAMESPACE_URL, f'{seed}:{suffix}'))
                    row['id'] = identifier
                taken.add(row['id'])
                contributing = _backfill_runs(window, recordings)
                if derive and len(contributing) > 1:
                    # Undo is scoped to one run; a re-derive never merges rows that different runs own.
                    raise Conflict('rederive_mixed_runs')
                run = contributing[0] if contributing else None
                if derive or run:
                    # Historical windows never fan out (policy.created_eligible) and take no derived
                    # effects; a live pass over an interrupted backfill's donors keeps the stamp.
                    row['backfilled'] = True
                    if run:
                        row['v3_backfill_run'] = run
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
                    if not derive:
                        await run_blocking(db_executor, enqueue, uid, at=now + timedelta(minutes=1))
                if (
                    ended
                    and not waiting
                    and (not was_ended or rewrite or promoted or (prior or {}).get('tile_state') == 'transcribing')
                ):
                    row['v3_process_pending'] = True
                    row['v3_rewrites'] = int((prior or {}).get('v3_rewrites') or 0) + int(rewrite)
                if (
                    prior
                    and prior.get('home_hidden')
                    and not row.get('v3_process_pending')
                    and policy.created_eligible(row)
                ):
                    # Notes written while hidden; the window now shows on Home without a re-note,
                    # so this is its first visible completed moment and it owes the created fanout.
                    row['v3_created_pending'] = True
                if ended and (
                    not was_ended or rewrite or promoted or (prior or {}).get('tile_state') == 'transcribing'
                ):
                    if not row.get('is_locked') and (transcription_failed or window.get('_outline_failed')):
                        row.update(
                            await run_blocking(
                                db_executor,
                                writers.failure_patch,
                                reason='transcription' if transcription_failed else 'outline',
                            )
                        )
                if derive and row.get('v3_process_pending'):
                    # Same notes obligation, on the backfill's own marker: the live sweep and the live
                    # queue never pick up historical notes.
                    row['v3_process_pending'] = False
                    row['v3_backfill_process_pending'] = True
                rows.append(row)
                for rid, claims in row['_v3_claims'].items():
                    allocated.setdefault(rid, []).extend((claim['start'], claim['end']) for claim in claims)
            return rows

        rows = await plan()
        # A planned id that already exists outside the loaded closure is adopted as the prior once,
        # never overwritten and never retried in a loop (each replan may cost outline work).
        # Backfill never adopts: its rows are stamped backfilled and must not move a live conversation.
        unseen = [] if derive else [row['id'] for row in rows if row['id'] not in existing]
        adopted = await run_blocking(db_executor, store.adoptable, uid, unseen) if unseen else {}
        if adopted:
            metrics.ADOPTED.inc(len(adopted))
            logger.info('v3 reconcile adopted existing derived rows count=%d', len(adopted))
            existing.update(adopted)
            rows = await plan()
        planned = {row['id'] for row in rows}
        unclaimed = []
        if derive:
            # A legacy row no window claims (no usable lines after duplicate and deleted-span removal)
            # stays a visible legacy conversation: converting it would hide it with no replacement.
            claimed = {rid for row in rows for rid in row.get('v3_recording_ids') or []}
            unclaimed = [rid for rid, r in recordings.items() if '_v3_backfill_prior' in r and rid not in claimed]
            for rid in unclaimed:
                recordings.pop(rid)
        # A re-derive reuses prior ids; a prior copy no rebuilt window claims is retired with the commit.
        remove = [cid for cid in existing if cid not in planned] if derive and rederive else []
        await run_blocking(db_executor, leases.renew, uid, key, token)
        moved = await run_blocking(
            db_executor,
            _commit,
            uid,
            token,
            recordings,
            existing,
            rows,
            cache[-128:],
            clear_pending=not on_open,
            remove=remove,
            key=key,
        )
        report.update(
            sources=len(eligible),
            windows=len(rows),
            rows_new=sum(1 for row in rows if row['id'] not in existing),
            rows_removed=len(remove),
            sources_unclaimed=len(unclaimed),
            notes_queued=sum(1 for row in rows if row.get('v3_backfill_process_pending')),
            home_visible=sum(1 for row in rows if not row.get('home_hidden')),
        )
        if moved:
            # Live speech arrived during the pass: the snapshot's windows are committed and the moved
            # recordings stay owed. Wake the owner at the next minute instead of an immediate re-pass,
            # which would race the same live recording again.
            metrics.RACES.labels('source_moved').inc()
            await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + RACE_RETRY)
        for group in groups if not derive else ():
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
    except Conflict as error:
        reason = str(error)
        if reason in RACES and not derive:
            # Nothing committed, so every pending marker is still owed. Answer the task and wake the
            # owner at the next minute: a minute name the executing task cannot already hold, shared
            # with every other wake for that minute. Without a scheduled wake, fall back to a retry.
            try:
                await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + RACE_RETRY)
            except Exception as dispatch:
                metrics.RECONCILES.labels('dispatch_error').inc()
                metrics.RECONCILES.labels('error').inc()
                logger.warning('v3 reconcile race wake failed exception_type=%s', type(dispatch).__name__)
                raise error from dispatch
            metrics.RECONCILES.labels('raced').inc()
            metrics.RACES.labels(reason).inc()
            logger.info('v3 reconcile raced reason=%s', reason)
            return 'raced'
        if reason not in BLOCKED:
            metrics.RECONCILES.labels('error').inc()
            raise
        # A deterministic conflict fails identically on every retry: answer the task (no Cloud Tasks
        # retry storm through the shared queue) and back this owner off; v3_pending stays owed.
        metrics.RECONCILES.labels('blocked').inc()
        metrics.BLOCKED.labels(reason).inc()
        logger.warning(
            'v3 reconcile blocked reason=%s owner=%s cause=%s', reason, owner_tag(uid), redacted_cause(error)
        )
        report['blocked_reason'] = reason
        if not derive:
            # A backfill conflict must not park the owner's live builder.
            await run_blocking(db_executor, store.record_blocked, uid, token, reason)
        blocked = reason
    except Exception:
        metrics.RECONCILES.labels('error').inc()
        raise
    finally:
        await run_blocking(db_executor, leases.release, uid, key, token)
    if blocked is not None:
        if not derive and not on_open:
            # Windows earlier passes (or earlier batches) committed still owe their notes.
            await _drain_blocked(uid, blocked)
        return 'blocked'
    if on_open:
        await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + timedelta(minutes=1))
        return 'committed'
    if derive:
        # The backfill task drains its own notes marker within its deadline.
        return 'committed'
    await drain_processing(uid)
    if moved:
        return 'committed'
    if not derive and await run_blocking(db_executor, has_pending, uid):
        if _pass < 2:
            return await reconcile(uid, _pass=_pass + 1)
        else:
            await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + timedelta(minutes=1))
    return 'committed'


def _commit(uid, token, recordings, existing, rows, cache, *, clear_pending=True, remove=(), key='builder'):
    from google.api_core.exceptions import InvalidArgument

    from utils.conversations import lifecycle

    try:
        return lifecycle.commit_v3_projection(
            uid, token, recordings, existing, rows, cache, clear_pending=clear_pending, remove=remove, key=key
        )
    except InvalidArgument as error:
        # A document over Firestore's 1 MiB limit, or a commit request over its payload limit, fails the
        # same way on every retry; park the owner instead of cycling the shared queue with 500s.
        kind = store.size_error(error)
        if kind == 'document':
            raise Conflict('document_too_large') from error
        if kind == 'request':
            raise Conflict('request_too_large') from error
        raise


async def _process_leased(uid, row, token):
    worker = asyncio.create_task(run_blocking(postprocess_executor, _process, uid, row, token))
    keeper = asyncio.create_task(renew_until_done(uid, 'summary-' + row['id'], token, worker))
    try:
        await asyncio.shield(worker)
    except asyncio.CancelledError:
        await asyncio.shield(worker)
        await keeper
        raise
    await keeper


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
            await _process_leased(uid, row, token)
        finally:
            await run_blocking(db_executor, leases.release, uid, 'summary-' + row['id'], token)
    # Settled notes arm the conversation-created obligation; deliver after every summary lease is released.
    # Imported here: the webhook fanout's LLM/app graph must not join process_conversation's import graph,
    # which loads this module at import time (listen, pusher and sync all import it).
    from utils.conversations.v3 import created

    await created.deliver(uid)


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
    notes = False
    if row.get('kind') in {'media', 'background'} or (not policy.manual_intent(row) and words < 20):
        lifecycle.complete(uid, row['id'])
    else:
        notes = True
        persisted = []
        with fence.writer(uid, row['id'], token), models.notes_mode(uid):
            result = process_conversation(
                uid,
                row.get('language') or 'en',
                Conversation(**row),
                persistence_observer=persisted.append,
                # Backfilled rows take the live trigger so relevance, speaker and meeting context and the
                # short-clip floor match live notes; process_conversation withholds their derived effects.
                trigger=ProcessingTrigger.CAPTURE_END,
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
        notes=notes,
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


BACKFILL_NOTES_CONCURRENCY = 4
BACKFILL_NOTES_ATTEMPTS = 3


async def drain_backfill(uid, *, deadline, keep_going=None, concurrency=BACKFILL_NOTES_CONCURRENCY):
    """Notes for backfilled rows, through the same _process as live, a few at a time until deadline.

    Returns counts; ``remaining`` > 0 asks the caller for a continuation task. ``keep_going`` is
    checked before each chunk so an undo stops new notes work.
    """
    rows = [row for row in await run_blocking(db_executor, store.pending_backfill_processing, uid) if row]
    counts = {'processed': 0, 'failed': 0, 'retry': 0, 'busy': 0, 'remaining': 0}

    async def one(row):
        token = await run_blocking(db_executor, leases.acquire, uid, 'summary-' + row['id'])
        if token is None:
            counts['busy'] += 1
            return
        failed = False
        try:
            await _process_leased(uid, row, token)
        except Exception as error:
            failed = True
            logger.warning('event=v3_backfill_notes outcome=error exception_type=%s', type(error).__name__)
        finally:
            try:
                outcome = await run_blocking(
                    db_executor,
                    writers.settle_backfill_processing,
                    uid,
                    row['id'],
                    failed=failed,
                    max_attempts=BACKFILL_NOTES_ATTEMPTS,
                )
            finally:
                await run_blocking(db_executor, leases.release, uid, 'summary-' + row['id'], token)
        counts[{'settled': 'processed', 'absent': 'processed', 'failed': 'failed', 'retry': 'retry'}[outcome]] += 1

    for start in range(0, len(rows), concurrency):
        if time.monotonic() >= deadline or (keep_going is not None and not await keep_going()):
            break
        await asyncio.gather(*(one(row) for row in rows[start : start + concurrency]))
    left = await run_blocking(db_executor, store.pending_backfill_processing, uid)
    counts['remaining'] = len([row for row in left if row])
    return counts


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
