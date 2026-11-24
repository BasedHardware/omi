"""One named task and one renewable transaction lease per owner.

Markers are durable obligations. Dispatch failure never clears one; the sweeper
retries it. Switching admission off does not stop existing obligations.
"""

from database import conversations_v3_leases as leases

from database import conversations_v3_processing as writers

from database import conversations_v3_backfill_runs as backfill_runs

from database import conversations_v3_rederive as rederive_store

import asyncio
from collections.abc import Collection
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from google.cloud.firestore_v1 import FieldFilter

from config.conversations_v3 import (
    DEFAULT_BOUNDARY_SECONDS,
    HISTORICAL_SITDOWN_TIMING,
    SPEECH_LANDED_FIELD,
    boundary_seconds,
    live_title_enabled,
    stretch_cohesion_enabled,
)
from utils.conversations.v3.triggers import enqueue, changed
from utils.conversations.v3.renewal import renew_until_done, leased_work
from database import conversations as conversations_db, conversations_v3 as store, conversations_v3_fence as fence
from models.conversation import Conversation
from models.conversation_enums import ConversationStatus
from models.finalization_owner import FinalizationOwnedElsewhere, python_owns_finalization
from utils.conversations.v3 import (
    Conflict,
    outline,
    planner,
    models,
    metrics,
    policy,
    visibility,
    context,
)
from utils.conversations.v3 import refinement, preview_wakes
from utils.conversations.v3.word_floor import MIN_TASK_WORDS, has_unspaced_script, text_word_count
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.meeting_treatment import deduplicated_transcribed_speech_seconds
from utils.executors import run_blocking, db_executor, llm_executor, postprocess_executor, storage_executor
from utils.observability.fallback import record_fallback

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
        'rederive_live_open',
        'rederive_live_boundary',
        'rederive_live_outline_failed',
        'rederive_live_coverage',
        'rederive_live_donor_tasks',
        'rederive_live_range_overflow',
        'rederive_live_timing',
        'rederive_live_landing_unknown',
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
        if isinstance(conversation, Conversation) and not conversation.python_finalization_owned:
            raise FinalizationOwnedElsewhere()
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
        if current is not None and not python_owns_finalization(current):
            raise FinalizationOwnedElsewhere()
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


def _match(window, existing, used, *, preferred=None):
    start, end = window['lines'][0]['start'], window['lines'][-1]['end']
    published = window.get('_published_ids', ())
    candidates = [
        r
        for r in existing.values()
        if r['id'] not in used and (r['id'] not in published or r.get('deleted'))
        # A live re-derive's protected rows keep their own lines; they never absorb a window.
        and not r.get('_v3_protected')
        and r.get('started_at')
        and r.get('finished_at')
        and r['started_at'] <= end
        and r['finished_at'] >= start
    ]
    # Published claimants are assigned by the planner. Time matching is the fallback
    # for live rows, legacy rows without claims or playback, and deletion tombstones.
    return min(candidates, key=lambda r: (r['id'] != preferred, r['started_at'])) if candidates else None


def _backfill_runs(window, recordings):
    """The backfill runs whose donors contributed this window (live builder passes included), in line order."""
    found = []
    for line in window['lines']:
        source = recordings.get(line['conversation_id']) or {}
        run = source.get('_v3_backfill_run') or source.get('v3_backfill_run')
        if run and run not in found:
            found.append(run)
    return found


def historical_stretches(eligible, now, *, since, until, internal_end=False):
    """Build settled stretches and verify the partition edge using actual speech bounds."""
    silence_gap, lock_delay = (timedelta(seconds=value) for value in HISTORICAL_SITDOWN_TIMING)
    for row in eligible:
        if any(str(segment.get('text') or '').strip() for segment in row.get('transcript_segments') or ()):
            landed = row.get(SPEECH_LANDED_FIELD)
            if not isinstance(landed, datetime) or landed.utcoffset() is None:
                raise Conflict('rederive_live_landing_unknown')
    groups = outline.stretches(eligible, now, silence_gap=silence_gap, lock_delay=lock_delay, settle_on_landing=True)
    # Metadata finished_at can lag a late transcript. Reserve a full silence gap on the left
    # of an internal seam and verify the right side starts at or after it.
    latest = until - silence_gap if internal_end else until
    if any(group['lines'][0]['start'] < since or group['end'] > latest for group in groups):
        raise Conflict('rederive_live_boundary')
    if any(not group['locked'] for group in groups):
        raise Conflict('rederive_live_open')
    return groups


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
    live=False,
    historical_timing=None,
    internal_end=False,
    report=None,
    _pass=0,
):
    """One builder pass. ``derive`` is one planned backfill partition ([since, until), one owner).

    A derive pass applies every live planning, visibility and notes rule; it differs only in its
    inputs (legacy donors instead of v3_pending recordings), in stamping rows ``backfilled`` and in
    queueing notes on its own marker, drained by the backfill task instead of the live queue.
    ``live`` (with ``derive``) replans the owner's finished live windows from their sealed sources:
    see rederive_store.load_live_rederive and _live_outcome. An explicit historical timing
    receipt opts that repair into the serving sit-down profile.
    """
    report = {} if report is None else report
    key = store.BACKFILL_LEASE if derive else 'builder'
    blocked = None
    moved = set()
    deferred: dict[str, datetime] = {}
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
        cohesion = stretch_cohesion_enabled()
        silence_seconds, lock_seconds = boundary_seconds(cohesion=cohesion and not derive)
        if historical_timing is not None:
            if (
                not (derive and live)
                or not isinstance(historical_timing, (tuple, list))
                or tuple(historical_timing) != HISTORICAL_SITDOWN_TIMING
                or boundary_seconds(cohesion=cohesion) != HISTORICAL_SITDOWN_TIMING
            ):
                raise Conflict('rederive_live_timing')
            silence_seconds, lock_seconds = HISTORICAL_SITDOWN_TIMING
        if derive and live:
            recordings, existing, cached, skipped = await run_blocking(
                db_executor, rederive_store.load_live_rederive, uid, since=since, until=until, run_id=run_id
            )
            report.update(skipped)
        elif derive:
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
        custom_timing = (silence_seconds, lock_seconds) != (DEFAULT_BOUNDARY_SECONDS, DEFAULT_BOUNDARY_SECONDS)
        silence_gap, lock_delay = timedelta(seconds=silence_seconds), timedelta(seconds=lock_seconds)
        if historical_timing is not None:
            groups = historical_stretches(eligible, now, since=since, until=until, internal_end=internal_end)
        else:
            groups = outline.stretches(
                eligible, now, silence_gap=silence_gap, lock_delay=lock_delay, settle_on_landing=custom_timing
            )
        if live and not all(group['finished'] for group in groups):
            # Speech within five minutes of now is still the live builder's; refuse before any paid call.
            raise Conflict('rederive_live_open')
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
        preview_prefix = f'{silence_seconds}:'
        scoped_preview_keys = {f"{preview_prefix}{group['key']}" for group in groups} if custom_timing else set()
        previews = {row['preview_key']: row for row in cached if row.get('preview_key', '').startswith(preview_prefix)}
        unmatched_previews = {key: row for key, row in previews.items() if key not in scoped_preview_keys}
        consumed_previews = set()
        outlines, cache = [], []
        background = await run_blocking(db_executor, context.outline_sources, uid, groups)
        for group in groups:
            await run_blocking(db_executor, leases.renew, uid, key, token)
            messages = outline.messages(group, timezone.utc, cohesion=cohesion, silence_gap=silence_gap)
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
            preview_key = f"{preview_prefix}{group['key']}" if custom_timing else None
            preview = previews.get(preview_key) if preview_key else None
            if preview_key and preview is None and hit is None:
                matched_key = outline.matching_preview(group, unmatched_previews)
                if matched_key is not None:
                    preview = unmatched_previews.pop(matched_key)
                    consumed_previews.add(matched_key)
            preview_fields = {}
            if hit:
                entries = hit['entries']
                report['outline_cache_hits'] = report.get('outline_cache_hits', 0) + 1
            elif preview is not None:
                entries = outline.reuse_preview(group, preview)
                report['outline_cache_hits'] = report.get('outline_cache_hits', 0) + 1
            elif group['outline_ready'] or on_open:
                if await run_blocking(db_executor, store.outline_attempt, uid, token, fingerprint, **keyed):
                    metrics.MODEL_CALLS.labels('outline').inc()
                    report['outline_calls'] = report.get('outline_calls', 0) + 1
                    try:
                        content = await leased_work(uid, key, token, llm_executor, models.outline, uid, messages)
                    except RuntimeError as error:
                        if str(error) != 'v3_lease_lifetime_exhausted':
                            raise
                        content = ''
                    try:
                        entries = outline.parse(content, group)
                        if preview_key and not group['locked']:
                            preview_fields = {
                                'preview_key': preview_key,
                                'anchors': outline.preview_anchors(group, entries),
                            }
                            await run_blocking(
                                db_executor,
                                store.save_outline,
                                uid,
                                token,
                                fingerprint,
                                entries,
                                key=key,
                                preview=preview_fields,
                            )
                        else:
                            await run_blocking(
                                db_executor, store.save_outline, uid, token, fingerprint, entries, **keyed
                            )
                    except (ValueError, KeyError, TypeError):
                        entries = outline.fallback(group)
                        entries = [{**entry, '_outline_failed': True} for entry in entries]
                        metrics.RECONCILES.labels('outline_fallback').inc()
                else:
                    entries = [{**entry, '_outline_failed': True} for entry in outline.fallback(group)]
            else:
                # First speech is visible before either the title preview or the outline is ready.
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
            if group['outline_ready'] or on_open or preview is not None:
                if preview_key and not group['locked'] and not any(e.get('_outline_failed') for e in entries):
                    preview_fields = {'preview_key': preview_key, 'anchors': outline.preview_anchors(group, entries)}
                cache.append({'fingerprint': fingerprint, 'entries': entries, **preview_fields})

        if custom_timing and on_open:
            replaced = {row['fingerprint'] for row in cache}
            replaced_previews = scoped_preview_keys | consumed_previews
            cache = [
                row
                for row in cached
                if row.get('preview_key') not in replaced_previews and row['fingerprint'] not in replaced
            ] + cache

        preferred = conversation_id if on_open and custom_timing else None
        refine_locked = (
            custom_timing
            and not (derive or on_open)
            and not any(row.get('v3_pending') and row.get('v3_manual_end') for row in eligible)
        )

        eligible_ids = {row['id'] for row in eligible}
        unavailable = {
            row['id']: row
            for row in existing.values()
            if not (derive or on_open)
            and row.get('v3_unlocked')
            and not row.get('deleted')
            and not eligible_ids.intersection(row.get('v3_recording_ids') or ())
        }

        async def plan():
            # One ownership index per plan (adoption can add rows before a replan), shared by the
            # two-hour cap and both projections below.
            ownership = planner.Ownership(existing, recordings)
            proposed = planner.windows(
                groups,
                outlines,
                cohesion=cohesion,
                silence_gap=silence_gap,
                defer_topic_lock=custom_timing,
                ownership=ownership,
            )
            merge = refinement.candidate(proposed, existing, recordings) if refine_locked else None
            if merge and await run_blocking(db_executor, store.merge_donors_have_tasks, uid, merge[1]['_v3_absorbed']):
                merge = None
            reserved = set()
            candidates = proposed
            if merge is not None:
                index, merged = merge
                reserved = {merged['id'], *merged['_v3_absorbed']}
                candidates = proposed[:index] + proposed[index + 1 :]
            windows = planner.preserve_finished_windows(
                candidates, existing, recordings, protect_provisional=custom_timing, ownership=ownership
            )
            if reserved.intersection(window.get('existing_id') for window in windows):
                merge = None
                reserved.clear()
                windows = planner.preserve_finished_windows(
                    proposed, existing, recordings, protect_provisional=custom_timing, ownership=ownership
                )
            # A retained finished conversation owns its id by claim evidence; a fresh window that sorts
            # before it (late speech overlapping its start) must not time-match the same id. Two planned
            # rows with one id each re-add the source's held claims, doubling them every pass until the
            # recording outgrows Firestore's 1 MiB document limit (document_too_large).
            rows = []
            used = (
                reserved
                | unavailable.keys()
                | {window['existing_id'] for window in windows if window.get('existing_id')}
            )
            used.update(
                row['id'] for row in existing.values() if row.get('v3_refined') and row.get('v3_claims_transferred_to')
            )
            locked_ids = (
                {row['id'] for row in existing.values() if not planner.is_unlocked(row) and not row.get('deleted')}
                if custom_timing
                else set()
            )
            taken = set()
            allocated = {}
            await run_blocking(db_executor, visibility.hydrate_recognition, uid, recordings, windows)
            for window in windows:
                # An affirmative transcription failure is terminal even before the silence deadline.
                transcription_failed = any(
                    policy.transcription_failed(recordings[line['conversation_id']]) for line in window['lines']
                )
                if transcription_failed:
                    window['finished'] = True
                # A preview cannot take over a locked card by time matching alone.
                deferred_lock = (
                    custom_timing
                    and not transcription_failed
                    and (not window['finished'] or window.get('_defer_lock', False))
                )
                excluded = used | locked_ids if deferred_lock else used
                prior = existing.get(window.get('existing_id')) or _match(
                    window, existing, excluded, preferred=preferred
                )
                if live and window.get('_outline_failed') and not (prior or {}).get('_v3_protected'):
                    # A repair never replaces windows with the fallback outline's failed tiles; retry later.
                    raise Conflict('rederive_live_outline_failed')
                if prior:
                    used.add(prior['id'])
                opening = on_open and prior and prior['id'] == conversation_id and custom_timing
                if opening:
                    window['finished'] = True
                    deferred_lock = False
                if deferred_lock:
                    window['_title_preview'] = True
                row = planner.build(uid, window, recordings, prior, allocated=allocated)
                if opening and prior and planner.is_unlocked(prior):
                    row['v3_open_locked'] = True
                row.pop('v3_unlocked', None)
                if deferred_lock:
                    row['v3_unlocked'] = True
                    lock_end = window.get('_lock_end', row['finished_at'])
                    row['_v3_preview_due_at'] = max(lock_end + lock_delay, now + RACE_RETRY)
                published_ids = window.get('_published_ids', ())
                if not prior and (row['id'] in excluded | taken or row['id'] in published_ids):
                    first = window['lines'][0]['conversation_id']
                    seed = f"v3:{uid}:{row['started_at'].isoformat()}:{first}"
                    blocked_ids = excluded | taken | set(published_ids)
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
                if live:
                    row['v3_rederive_live_run'] = run_id
                if prior and prior.get('deleted'):
                    continue
                before = planner.word_count((prior or {}).get('transcript_segments') or [])
                new_words = max(0, planner.word_count(row['transcript_segments']) - before)
                ended = window['finished'] and not deferred_lock
                was_ended = prior and not planner.is_unlocked(prior)
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
                if promoted and custom_timing and prior:
                    covers = prior.get('summary_covers_through')
                    if covers and covers >= row['finished_at']:
                        promoted = False
                if promoted:
                    row['summary_covers_through'] = None
                rewrite = bool(
                    prior is not None
                    and was_ended
                    and not custom_timing
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
            if merge is not None:
                rows.append(merge[1])
            rows.extend(planner.unavailable_preview(row, recordings) for row in unavailable.values())
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
        retire, commit_recordings, commit_existing, priors = {}, recordings, existing, []
        if live:
            rows, retire, touched, sources, priors, outcome = _live_outcome(
                rows, existing, recordings, since=since, until=until, run_id=run_id
            )
            donors = [cid for cid, patch in retire.items() if patch.get('sync_merged_into')]
            if donors and await run_blocking(db_executor, store.merge_donors_have_tasks, uid, donors):
                raise Conflict('rederive_live_donor_tasks')
            report.update(outcome)
            commit_existing = {cid: existing[cid] for cid in touched if cid in existing}
            commit_recordings = {rid: recordings[rid] for rid in sources}
        try:
            if live:
                # The undo ledger is durable before the commit that changes its rows.
                # A stopped attempt's copies are of rows this partition loads again (or they are gone).
                stale = sorted({*existing, *(entry['id'] for entry in priors)})
                await run_blocking(db_executor, rederive_store.drop_stale_priors, uid, run_id, stale)
                await run_blocking(db_executor, backfill_runs.save_priors, uid, run_id, priors)
            await run_blocking(db_executor, leases.renew, uid, key, token)
            moved = await run_blocking(
                db_executor,
                _commit,
                uid,
                token,
                commit_recordings,
                commit_existing,
                rows,
                cache[-128:],
                clear_pending=not on_open,
                remove=remove,
                retire=retire,
                key=key,
            )
        except Exception:
            if live:
                # Copies of rows this attempt did not write go, whatever failed; a resume records them
                # again. If this cleanup fails too, the partition stays unfinished until resume or undo.
                await run_blocking(db_executor, rederive_store.drop_unwritten_priors, uid, run_id, priors)
            raise
        report.update(
            sources=len(eligible),
            windows=len(rows),
            rows_new=sum(1 for row in rows if row['id'] not in existing),
            rows_removed=len(remove),
            # A live run's loader already counted unclaimed live speech; its legacy meaning is donors.
            **({} if live else {'sources_unclaimed': len(unclaimed)}),
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
            if not (group['locked'] if custom_timing else group['finished']):
                # A different minute than the currently executing task avoids
                # Cloud Tasks' completed-name dedupe swallowing the continuation.
                delay = lock_delay if group['outline_ready'] else min(silence_gap, lock_delay)
                settle_from = group.get('settle_from', group['end'])
                await run_blocking(db_executor, enqueue, uid, at=max(settle_from + delay, now + timedelta(minutes=1)))
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
        if not derive and not on_open and live_title_enabled():
            for row in rows:
                if policy.live_title_candidate(row) and not row.get(policy.LIVE_TITLE_STATE):
                    await _maybe_publish_live_title(uid, key, token, row)
        metrics.RECONCILES.labels('committed').inc()
        deferred = preview_wakes(rows, recordings)
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
    pending = (
        await run_blocking(db_executor, has_pending, uid, deferred)
        if deferred
        else await run_blocking(db_executor, has_pending, uid)
    )
    if pending:
        if _pass < 2:
            return await reconcile(uid, _pass=_pass + 1)
        else:
            await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + timedelta(minutes=1))
    return 'committed'


async def _maybe_publish_live_title(uid, key, token, row):
    try:
        revision = row.get('sync_content_revision')
        segments = row.get('transcript_segments') or []
        if revision is None or deduplicated_transcribed_speech_seconds(segments) < 180:
            return
        args = (uid, token, row['id'], revision)
        if await run_blocking(db_executor, store.write_live_title_preview, *args):
            title = await leased_work(uid, key, token, llm_executor, models.live_title, uid, segments)
            if title and live_title_enabled():
                await run_blocking(db_executor, store.write_live_title_preview, *args, title=title)
    except Exception as error:
        logger.warning('event=v3_live_title exception_type=%s', type(error).__name__)
        record_fallback(component='other', from_mode='none', to_mode='none', reason='other', outcome='degraded')


def _held_claims(recordings, cid):
    """(recording id, list position, claim) for every claim the loaded sources hold for one row."""
    return [
        (rid, index, claim)
        for rid, recording in recordings.items()
        for index, claim in enumerate(recording.get('claims') or [])
        if isinstance(claim, dict) and claim.get('conversation_id') == cid
    ]


def _speech(row):
    return [(s.get('id'), s.get('start'), s.get('end'), s.get('text')) for s in row.get('transcript_segments') or []]


def _spoken(row):
    """Each stored segment of a row by recorded clock: (segment id, text, absolute start to 10 ms)."""
    keys = set()
    for s in row.get('transcript_segments') or []:
        try:
            at = row['started_at'] + timedelta(seconds=float(s.get('start') or 0))
        except (TypeError, ValueError, KeyError):
            continue
        keys.add((s.get('id'), ' '.join(str(s.get('text') or '').split()), round(at.timestamp(), 2)))
    return keys


def _same_window(row, original, held):
    """The rebuilt window has the stored row's speech, bounds, claims and Home decision: leave it alone."""
    if any(
        row.get(k) != original.get(k)
        for k in ('started_at', 'finished_at', 'kind', 'home_hidden', 'home_hidden_reason', 'manual_end')
    ):
        return False
    if _speech(row) != _speech(original):
        return False
    before = {}
    for rid, _index, claim in held:
        before.setdefault(rid, []).append((claim.get('start'), claim.get('end')))
    after = {rid: [(c['start'], c['end']) for c in spans] for rid, spans in row['_v3_claims'].items() if spans}
    return {k: sorted(v) for k, v in before.items()} == {k: sorted(v) for k, v in after.items()}


def _survivor(original, planned):
    """The rebuilt window that absorbed most of a retired row's time (earliest on a tie), if any."""
    start, end = original.get('started_at'), original.get('finished_at')
    best, best_overlap = None, None
    for row in sorted(planned, key=lambda r: r['started_at']):
        overlap = (min(end, row['finished_at']) - max(start, row['started_at'])).total_seconds()
        touches = overlap > 0 or row['started_at'] <= start <= row['finished_at']
        if touches and (best_overlap is None or overlap > best_overlap):
            best, best_overlap = row['id'], overlap
    return best


def _stored_bytes(value):
    """Mirrors rederive_store.stored_bytes, kept here so the async reconcile path stays pure."""
    return len(json.dumps(value, default=str).encode())


def _retire_patch(survivor, run_id, prior):
    """A retired live row becomes a sync bridge to the window that absorbed it.

    Deleted and discarded hide it everywhere a merged-away conversation is hidden, reads by id follow
    ``sync_merged_into`` to the survivor, and dropping ``v3_derived`` keeps every v3 planning read
    (closure claims, time queries, adoption) from treating it as a deletion tombstone.
    """
    return {
        'deleted': True,
        'discarded': True,
        # Owes no summary: the debt query must not keep selecting a row its repair refuses.
        'summary_due_at': None,
        'sync_merged_into': survivor,
        'v3_derived': False,
        'v3_rederive_live_run': run_id,
        # As a sync merge's absorbed row: its claims went to the survivor, so deleting the bridge later
        # releases nothing of the survivor's, and cached copies see the redirect.
        'v3_claims_transferred_to': survivor,
        'sync_content_revision': int(prior.get('sync_content_revision') or 0) + 1,
    }


def _live_outcome(rows, existing, recordings, *, since, until, run_id):
    """Turn a live re-derive's planned rows into what it writes, retires and records for undo.

    Protected rows are never written. A rebuilt window equal to its stored row is not written (no
    notes re-run). A rebuilt window keeps the id of the earliest row it absorbs (service._match);
    every other eligible row it absorbs is retired into it. Returns (rows to write, retire patches,
    touched row ids, recordings to commit, undo priors, ledger counts).
    """
    protected = {cid for cid, row in existing.items() if row.get('_v3_protected')}
    eligible = {cid: row for cid, row in existing.items() if cid not in protected}
    planned = [row for row in rows if row['id'] not in protected]
    for row in planned:
        if row['status'] == 'in_progress':
            raise Conflict('rederive_live_open')
        if row['started_at'] < since or row['finished_at'] > until:
            raise Conflict('rederive_live_boundary')
    unchanged = {
        row['id']
        for row in planned
        if row['id'] in eligible
        and _same_window(row, eligible[row['id']]['_v3_original'], _held_claims(recordings, row['id']))
    }
    # Nothing a row said may disappear: every eligible row's speech is in a rebuilt or protected row.
    kept_speech = set().union(*(_spoken(row) for row in planned), *(_spoken(existing[cid]) for cid in protected))
    before_speech = set().union(*(_spoken(prior['_v3_original']) for prior in eligible.values()))
    if before_speech - kept_speech:
        raise Conflict('rederive_live_coverage')
    planned_ids = {row['id'] for row in planned}
    retire, kept = {}, 0
    for cid, prior in eligible.items():
        if cid in planned_ids:
            continue
        survivor = _survivor(prior['_v3_original'], planned)
        if survivor is None:
            # No rebuilt window covers its time: nothing absorbed it, so it stays as it is.
            kept += 1
            continue
        retire[cid] = _retire_patch(survivor, run_id, prior['_v3_raw'])
    # The survivor lists its bridges (sync_merged_from), as a sync merge does: deleting it purges them.
    # The list lands in the final batch with the retirements, never before the bridges exist.
    merged_from = {}
    for cid, patch in retire.items():
        donors = merged_from.setdefault(patch['sync_merged_into'], set())
        donors.add(cid)
        donors.update(eligible[cid]['_v3_raw'].get('sync_merged_from') or [])
    lineage = {}
    for row in planned:
        if row['id'] in merged_from:
            had = (eligible.get(row['id']) or {}).get('_v3_raw', {}).get('sync_merged_from') or []
            lineage[row['id']] = {'sync_merged_from': sorted({*had, *merged_from[row['id']]})}
    write = [row for row in planned if row['id'] not in unchanged or row['id'] in merged_from]
    touched = {row['id'] for row in write} | set(retire)
    sources = {rid for row in write for rid in row.get('v3_recording_ids') or []} & recordings.keys()
    sources |= {
        rid
        for rid, recording in recordings.items()
        if any(isinstance(c, dict) and c.get('conversation_id') in touched for c in recording.get('claims') or [])
    }
    for rid in sources:
        recording = recordings[rid]
        claims = [
            c
            for c in recording.get('claims') or []
            if not (isinstance(c, dict) and c.get('conversation_id') in touched)
        ]
        claims += [{'conversation_id': row['id'], **span} for row in write for span in row['_v3_claims'].get(rid) or []]
        stored = recording.get('_v3_stored_bytes', 0)
        after = stored - recording.get('_v3_stored_claims_bytes', 0) + _stored_bytes(claims)
        if after > stored and after > rederive_store.SOURCE_MAX_BYTES:
            # Growing a source past the document limit fails every retry; block before any write.
            raise Conflict('document_too_large')
    if len(sources) + 2 * len(retire) + len(lineage) + 2 > store.BATCH_MAX_WRITES:
        # Reserve a write for each retirement and its task-link marker, plus the lineage, row and lease.
        raise Conflict('backfill_partition_budget')
    new_sources = {row['id']: set(row.get('v3_recording_ids') or []) for row in write}
    priors = []
    for cid in sorted(touched):
        prior = eligible.get(cid)
        if prior is not None and prior['_v3_raw'].get('v3_rederive_live_run') == run_id:
            # Already this run's (a resumed partition): its first prior is the one undo restores.
            continue
        held = _held_claims(recordings, cid)
        entry = {
            'id': cid,
            'sources': sorted(new_sources.get(cid, set()) | {rid for rid, _i, _c in held}),
            'claims': [{'recording_id': rid, 'index': index, 'claim': claim} for rid, index, claim in held],
        }
        if prior is None:
            entry['created'] = True
        else:
            entry['raw'] = prior['_v3_raw']
        if cid in retire:
            entry['retired_into'] = retire[cid]['sync_merged_into']
        if _stored_bytes(entry) > rederive_store.SOURCE_MAX_BYTES:
            # The prior holds the whole stored row; one that cannot be written leaves no exact undo.
            raise Conflict('document_too_large')
        priors.append(entry)
    counts = {
        'windows_after': len(planned),
        'visible_after': sum(1 for row in planned if not row.get('home_hidden')),
        'rows_unchanged': len(unchanged),
        'rows_rebuilt': sum(1 for row in write if row['id'] in eligible),
        'rows_created': sum(1 for row in write if row['id'] not in eligible),
        'rows_retired': len(retire),
        'rows_kept_unabsorbed': kept,
        'priors_recorded': len(priors),
        # The partition's settle step baselines these rows' copies by id rather than listing the run's;
        # a resumed partition's rows the failed attempt already wrote keep their first copy.
        'prior_ids': sorted(touched),
        'segments_checked': len(before_speech),
    }
    return write, {**retire, **lineage}, touched, sources, priors, counts


def _commit(
    uid, token, recordings, existing, rows, cache, *, clear_pending=True, remove=(), retire=None, key='builder'
):
    from google.api_core.exceptions import InvalidArgument

    from utils.conversations import lifecycle

    try:
        return lifecycle.commit_v3_projection(
            uid,
            token,
            recordings,
            existing,
            rows,
            cache,
            clear_pending=clear_pending,
            remove=remove,
            retire=retire,
            key=key,
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
        if row is None or not python_owns_finalization(row):
            continue
        token = await run_blocking(db_executor, leases.acquire, uid, 'summary-' + row['id'])
        if token is None:
            await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + timedelta(minutes=1))
            continue
        try:
            await _process_leased(uid, row, token)
        except FinalizationOwnedElsewhere:
            continue
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

    if not row or not python_owns_finalization(row):
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
    texts = [s.get('text') or '' for s in row.get('transcript_segments') or []]
    words = sum(map(text_word_count, texts))
    below_minimum = words < MIN_TASK_WORDS
    passive = row.get('kind') in {'media', 'background'}
    manual = policy.manual_intent(row)
    notes = False
    if passive or (not manual and below_minimum):
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
    word_floor_outcomes = None
    if not (passive or manual or row.get('backfilled') or row.get('v3_rewrites')) and any(
        map(has_unspaced_script, texts)
    ):
        legacy_below = sum(len(text.split()) for text in texts) < MIN_TASK_WORDS
        word_floor_outcomes = (legacy_below, below_minimum)
    writers.settle_processing(
        uid,
        row['id'],
        token,
        row.get('sync_content_revision'),
        row['finished_at'],
        notes=notes,
        content_hash=writers.processing_hash(row),
        word_floor_outcomes=word_floor_outcomes,
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
            if not python_owns_finalization(doc.to_dict() or {}):
                continue
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
BACKFILL_SCAN_MAX_PAGES = 8


async def drain_backfill(uid, *, deadline, after=None, keep_going=None, concurrency=BACKFILL_NOTES_CONCURRENCY):
    """Notes for backfilled rows, through the same _process as live, a few at a time until deadline.

    Returns counts; ``remaining`` > 0 asks the caller for a continuation task. ``keep_going`` is
    checked before each chunk so an undo stops new notes work.
    """
    counts: dict[str, Any] = {'processed': 0, 'failed': 0, 'retry': 0, 'busy': 0, 'remaining': 0}
    pages_left = BACKFILL_SCAN_MAX_PAGES

    async def scan(cursor):
        nonlocal pages_left
        foreign = 0
        while pages_left and time.monotonic() < deadline:
            pages_left -= 1
            page = await run_blocking(
                db_executor, store.pending_backfill_processing, uid, after=cursor, deadline=deadline
            )
            if page is None:
                break
            pending, next_cursor = page
            rows = [row for row in pending if python_owns_finalization(row)]
            foreign += len(pending) - len(rows)
            if rows or not pending or next_cursor is None:
                return rows, cursor, foreign, False
            cursor = next_cursor
        return [], cursor, foreign, True

    rows, cursor, foreign, paused = await scan(after)

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
    if rows:
        pending, tail_cursor, tail_foreign, paused = await scan(cursor)
        # Earlier skipped rows still owe notes. A rescan of the actionable
        # page may see the same foreign rows, so combine counts conservatively.
        foreign = max(foreign, tail_foreign) if cursor != after else tail_foreign
        rows, cursor = pending, tail_cursor
    # A suffix scan cannot certify that the skipped prefix is empty. At the
    # end of the suffix, wrap to the head on the delayed continuation.
    foreign = max(foreign, int(cursor is not None))
    counts['remaining'] = max(len(rows) + foreign, int(paused))
    counts['ownership_blocked'] = foreign
    counts['scan_pending'] = paused
    next_cursor = cursor if paused or rows else None
    if next_cursor != after:
        counts['scan_after'] = next_cursor
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


def has_pending(uid: str, deferred: Collection[str] = ()) -> bool:
    # One beyond the deferred sources is enough to find any newly owed work.
    pending = (
        store.user_conversations(store.get_firestore_client(), uid)
        .where(filter=FieldFilter('v3_pending', '==', True))
        .limit(len(deferred) + 1)
        .stream()
    )
    return any(doc.id not in deferred for doc in pending)
