"""One named task and one renewable transaction lease per owner.

Markers are durable obligations. Dispatch failure never clears one; the sweeper
retries it. Switching admission off does not stop existing obligations.
"""

from config.llm_spend import (
    background_outline_flex_enabled,
    outline_cache_prefix_enabled,
    v3_summary_first_open_gating_enabled,
)
from database import conversations_v3_leases as leases

from database import conversations_v3_processing as writers

from database import conversations_v3_backfill_runs as backfill_runs

from database import conversations_v3_rederive as rederive_store

import asyncio
from collections.abc import Collection
import hashlib
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from functools import partial, wraps
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from google.cloud.firestore_v1 import FieldFilter

from config import reliability_experiments
from config.conversations_v3 import (
    bounded_pending_enabled,
    DEFAULT_BOUNDARY_SECONDS,
    HISTORICAL_SITDOWN_TIMING,
    SPEECH_LANDED_FIELD,
    boundary_seconds,
    capture_continuity_enabled,
    live_title_enabled,
    manual_end_home_visible_enabled,
    max_window_seconds,
    settle_on_landing_enabled,
    size_quarantine_enabled,
    size_quarantine_filters,
    stretch_cohesion_enabled,
)
from utils.conversations.v3.triggers import enqueue, changed
from utils.conversations.v3.renewal import renew_until_done, leased_work
from database import conversations as conversations_db, conversations_v3 as store, conversations_v3_fence as fence
from database import batch_pipeline_purge, conversation_batch_purge_jobs as batch_purge_jobs, legal_holds
from database.firestore_write_probe import suspend_committed_write_count
from utils import cloud_tasks
from utils.other import storage
from models.conversation import Conversation
from models.conversation_enums import ConversationStatus
from models.finalization_owner import FinalizationOwnedElsewhere, python_owns_finalization
from utils.conversations.v3 import (
    Conflict,
    UnlockedPage,
    outline,
    planner,
    models,
    metrics,
    policy,
    visibility,
    context,
)
from utils.conversations.v3 import manual_cuts, refinement, preview_wakes, rederive_plan, summary_wake
from utils.conversations.v3 import finish_timeline
from utils.conversations.fragment_visibility import is_relevance_discarded
from utils.conversations.v3 import live_tail
from utils.conversations.v3 import capture_device
from utils.conversations.v3.word_floor import MIN_TASK_WORDS, has_unspaced_script, text_word_count
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.meeting_treatment import deduplicated_transcribed_speech_seconds
from utils.executors import run_blocking, db_executor, llm_executor, postprocess_executor, storage_executor
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)

# Live capture keeps appending to its recording while a pass runs, so the commit's revision fence
# loses these races routinely. They answer the task and wake the owner again at the next minute
# (one coalesced named task per owner-minute) instead of burning Cloud Tasks attempts on a 500.
OUTLINE_BACKGROUND_BUDGET_SECONDS = 110
OUTLINE_MIN_FLEX_BUDGET_SECONDS = 60
OUTLINE_PUBLICATION_RESERVE_SECONDS = 15
OUTLINE_PUBLICATION_DEADLINE = timedelta(hours=2)

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
        'backfill_native_finish_unsupported',
        'backfill_donor_unclaimed',
        'backfill_rederive_linked_claims',
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
    # Pure string checks on store's size markers (no store call): this runs on the event loop.
    big = store.DOCUMENT_TOO_LARGE in text or all(m in text for m in store.PROPERTY_TOO_LARGE)
    kind = 'document' if big else 'request' if store.REQUEST_TOO_LARGE in text else None
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
        metrics.safe_metric(
            lambda: logger.warning('v3 reconcile blocked drain failed exception_type=%s', type(error).__name__)
        )


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


def _revoked_native_window(row, recordings):
    binding = row.get(policy.NATIVE_MANUAL_BINDING)
    source = recordings.get(binding.get('recording_id')) if isinstance(binding, dict) else None
    return bool(
        source
        and row.get('v3_process_pending')
        and not row.get('v3_notes_written')
        and not row.get(policy.NATIVE_MANUAL_NOTES_VISIBILITY)
        and policy.native_manual_binding(source) != binding
    )


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
    groups = outline.stretches(
        eligible,
        now,
        silence_gap=silence_gap,
        lock_delay=lock_delay,
        settle_on_landing=True,
        max_window=timedelta(seconds=max_window_seconds()),
    )
    # Metadata finished_at can lag a late transcript. Reserve a full silence gap on the left
    # of an internal seam and verify the right side starts at or after it.
    latest = until - silence_gap if internal_end else until
    if any(group['lines'][0]['start'] < since or group['end'] > latest for group in groups):
        raise Conflict('rederive_live_boundary')
    if any(not group['locked'] for group in groups):
        raise Conflict('rederive_live_open')
    return groups


def _outline_flex_budget(group, flex_owner_deadline):
    if flex_owner_deadline is None or not group['finished'] or group['manual_end']:
        return 0
    seconds_to_publish = (group['end'] + OUTLINE_PUBLICATION_DEADLINE - datetime.now(timezone.utc)).total_seconds()
    return int(
        min(
            flex_owner_deadline - time.monotonic(),
            seconds_to_publish - OUTLINE_PUBLICATION_RESERVE_SECONDS,
        )
        * 1000
    )


async def _derive_outline(
    uid, key, token, group, messages, fingerprint, report, *, cohesion, silence_gap, preview_key, flex_owner_deadline
):
    keyed = {'key': key} if key != 'builder' else {}
    background_attempt = False

    def record_attempt():
        metrics.MODEL_CALLS.labels('outline').inc()
        report['outline_calls'] = report.get('outline_calls', 0) + 1

    async def claim_background_attempt():
        nonlocal background_attempt
        budget_ms = _outline_flex_budget(group, flex_owner_deadline)
        if budget_ms < OUTLINE_MIN_FLEX_BUDGET_SECONDS * 1000:
            return 0
        background_attempt = await run_blocking(
            db_executor, store.outline_attempt, uid, token, fingerprint, preemptible=True
        )
        if not background_attempt:
            return 0
        await run_blocking(db_executor, leases.require_current, uid, key, token)
        budget_ms = _outline_flex_budget(group, flex_owner_deadline)
        if budget_ms < OUTLINE_MIN_FLEX_BUDGET_SECONDS * 1000:
            return 0
        record_attempt()
        return budget_ms

    try:
        if outline_cache_prefix_enabled():
            # Keep the existing result-cache key across prompt and transport experiments.
            messages = (
                outline.messages(group, timezone.utc, cohesion=cohesion, silence_gap=silence_gap, cache_prefix=True)
                + messages[2:]
            )
        content = None
        if _outline_flex_budget(group, flex_owner_deadline) >= OUTLINE_MIN_FLEX_BUDGET_SECONDS * 1000:
            await run_blocking(
                db_executor,
                models.require_current_generated_compute,
                'conversation_v3_outline',
                uid=uid,
                provider='openai',
                allow_byok=False,
            )
            try:
                content = await models.background_outline(uid, messages, claim=claim_background_attempt)
            finally:
                if background_attempt:
                    await run_blocking(db_executor, leases.mark_llm_preemptible, uid, key, token, False)
        if content is None:
            if not await run_blocking(db_executor, store.outline_attempt, uid, token, fingerprint, **keyed):
                return [{**entry, '_outline_failed': True} for entry in outline.fallback(group)], {}
            record_attempt()
            content = await leased_work(uid, key, token, llm_executor, models.outline, uid, messages)
    except RuntimeError as error:
        if str(error) != 'v3_lease_lifetime_exhausted':
            raise
        content = ''

    preview_fields = {}
    try:
        entries = outline.parse(content, group)
        if preview_key and not group['locked']:
            preview_fields = {'preview_key': preview_key, 'anchors': outline.preview_anchors(group, entries)}
            await run_blocking(
                db_executor, store.save_outline, uid, token, fingerprint, entries, key=key, preview=preview_fields
            )
        else:
            await run_blocking(db_executor, store.save_outline, uid, token, fingerprint, entries, **keyed)
        return entries, preview_fields
    except (ValueError, KeyError, TypeError):
        metrics.RECONCILES.labels('outline_fallback').inc()
        return [{**entry, '_outline_failed': True} for entry in outline.fallback(group)], preview_fields


async def _release_reconcile_lease(uid, key, token, *, primary_failed):
    try:
        await run_blocking(db_executor, leases.release, uid, key, token)
    except Exception as error:
        if not primary_failed:
            raise
        metrics.safe_metric(
            lambda: logger.warning('v3 reconcile lease release failed exception_type=%s', type(error).__name__)
        )


# The bounded load ladder as (pending, unlocked, total) seed ceilings: the full page, eight seeds, one seed of each
# kind, then one seed of either kind (the single lanes). A commit-time locked-closure batch cap re-enters at the
# next ceiling below the seeds the pass read, so a pass re-enters at most three times and parks at one seed.
SEED_CEILINGS = ((32, 8, 40), (8, 8, 16), (1, 1, 2), (1, 1, 1))


def _seed_limits(options):
    pending = options.get('pending_limit', 32)
    return pending, options.get('unlocked_limit', min(8, pending))


def _within(options, ceiling):
    pending, unlocked = _seed_limits(options)
    return pending <= ceiling[0] and unlocked <= ceiling[1] and pending + unlocked <= ceiling[2]


async def _load_live_batch(uid, token, parked, unlocked_page=None, seed_ceiling=None):
    """Reduce pending seeds without clipping any selected source's ownership closure.

    ``seed_ceiling`` is the retry after a commit-time locked-closure batch cap: only the ladder's attempts
    within that (pending, unlocked, total) ceiling run."""
    if parked in store.BOUNDED_RETRY_REASONS:
        # Spend a legacy park's one early attempt under this lease before any paid work.
        await run_blocking(db_executor, store.mark_bounded_attempt, uid, token)
    remembered = await run_blocking(db_executor, store.clear_terminal_pending, uid, token)
    budget_reasons = {'v3_derived_budget', 'v3_source_closure_budget'}
    sizes = (32, 8, 1)
    if parked == 'document_too_large' or remembered == 1:
        sizes = (1,)
    elif parked in budget_reasons or remembered == 8:
        sizes = (8, 1)
    attempts: list[dict[str, Any]] = [{'pending_limit': size} if size < 32 else {} for size in sizes]
    if unlocked_page is not None:
        # One pending and one unlocked seed can overflow together while each fits alone. Seed one lane at a
        # time, leading with the other lane on alternate minutes so neither starves the other.
        lanes = [{'pending_limit': 1, 'unlocked_limit': 0}, {'pending_limit': 0, 'unlocked_limit': 1}]
        attempts += lanes[::-1] if datetime.now(timezone.utc).minute % 2 else lanes
    if seed_ceiling is not None:
        attempts = [options for options in attempts if _within(options, seed_ceiling)]
        if not attempts:
            raise Conflict('v3_derived_budget')
    overflow = None
    for index, options in enumerate(attempts):
        try:
            extra = {'unlocked_page': unlocked_page} if unlocked_page is not None else {}
            result = await run_blocking(db_executor, store.load, uid, **options, **extra, lease_token=token)
        except Conflict as error:
            if index == len(attempts) - 1 or str(error) not in budget_reasons:
                raise
            overflow = error
            await run_blocking(db_executor, leases.renew, uid, 'builder', token)
        else:
            if _lane_without_seed(options, unlocked_page):
                # A lane with nothing of its own to load is not progress: the overflow still stands and
                # an empty commit would clear the park. Try the other lane, or park on the overflow.
                if index == len(attempts) - 1:
                    raise overflow or Conflict('v3_derived_budget')
                continue
            size = options.get('pending_limit', 32)
            if size < 32:
                lane = f" unlocked_limit={options['unlocked_limit']}" if 'unlocked_limit' in options else ''
                logger.info('event=v3_bounded_pending pending_limit=%d%s', size, lane)
            # Only a pass that seeded pending rows may change the remembered pending page.
            return (*result, size or None)
    raise AssertionError('bounded pending batch sizes are empty')


def _smaller_seed_ceiling(error, page, ceiling=None):
    """The next SEED_CEILINGS step after a commit-time locked-closure batch cap, or None to park.

    Chosen from the seeds of both kinds the pass actually read, so a page that held one seed parks without
    repeating the load and outline. It is strictly below the pass's own ceiling, so the retries cannot loop."""
    if not isinstance(error, store.LockedBatchCap) or page is None:
        return None
    pending, unlocked = page.seeds
    if pending + unlocked <= 1:
        return None
    following = SEED_CEILINGS[1] if pending > 8 else SEED_CEILINGS[2] if pending + unlocked > 2 else SEED_CEILINGS[3]
    if ceiling is not None and following[2] >= ceiling[2]:
        return None
    return following


_SIZE_ERROR_DOCUMENT = re.compile(r"/documents/users/[^/]+/conversations/([^/'\"\\\s]+)")


def size_error_document(error):
    """The conversation id a Firestore document-size rejection names, or None. Never logged: it holds ids.

    Pure string checks on store's size marker (no store call): this runs on the event loop.
    """
    text = str(error) if error is not None else ''
    match = _SIZE_ERROR_DOCUMENT.search(text) if store.DOCUMENT_TOO_LARGE in text else None
    return match.group(1) if match else None


def _size_quarantine(reason, pending_limit, page, commit, oversized):
    """The pending recordings a one-seed pass's rejected commit pins to its seed (SCA-2918), or ().

    A one-seed park otherwise re-seeds the same oldest recording every backoff and freezes the owner's
    whole backlog behind it. Quarantine needs positive attribution: Firestore must name the oversize
    document (``oversized``), and it must be the seed, a row the seed claims or feeds, or a source the
    commit writes for those rows. Nothing the load pulls in on its own (the open window and unlocked seeds)
    reaches, through claims, time neighbours and sources transitively, is charged to the seed: it loads on every pass, so
    quarantining seeds would only walk healthy ones into the same rejection. The set is the seed plus the
    pending sources the commit writes for the seed's rows: they would be seeded into the same rejection.
    Recordings only loaded alongside (time siblings of unrelated rows) are not set aside. ``commit`` is the
    (recordings, existing rows, planned rows) of the rejected commit.
    """
    if reason != 'document_too_large' or pending_limit != 1 or page is None or not size_quarantine_enabled():
        return ()
    if len(page.pending_ids) != 1 or oversized is None or not commit:
        return ()
    recordings, existing, planned = commit
    (seed,) = page.pending_ids
    reached = _reached(page.independent, recordings, existing, planned, page.neighbours)
    if seed not in recordings or oversized in reached:
        return ()
    rows = {c.get('conversation_id') for c in recordings[seed].get('claims') or [] if isinstance(c, dict)}
    rows |= {row['id'] for row in planned if seed in (row.get('v3_recording_ids') or ())}
    rows.discard(None)
    fed = {rid for row in planned if row['id'] in rows for rid in row.get('v3_recording_ids') or ()}
    members = {seed} | {
        rid
        for rid, recording in recordings.items()
        if rid in fed
        or any(isinstance(c, dict) and c.get('conversation_id') in rows for c in recording.get('claims') or [])
    }
    if oversized not in rows | members:
        return ()
    return (seed, *sorted(rid for rid in members - {seed} if recordings[rid].get('v3_pending')))


def _quarantine_park(error, pending_limit, page):
    """record_blocked's quarantine argument for a blocked pass: empty unless its rejection is attributable."""
    commit = error.size_commit if isinstance(error, Conflict) else None
    found = _size_quarantine(str(error), pending_limit, page, commit, size_error_document(error.__cause__))
    return {'quarantine': found} if found else {}


def _reached(starts, recordings, existing, planned, neighbours=None):
    """Every loaded document ``starts`` reach through claims and time neighbours (recording -> row) and sources (row -> recording)."""
    rows = {**existing, **{row['id']: row for row in planned}}
    seen, frontier = set(), set(starts)
    while frontier:
        doc = frontier.pop()
        if doc in seen:
            continue
        seen.add(doc)
        claims = (recordings.get(doc) or {}).get('claims') or ()
        frontier.update(c.get('conversation_id') for c in claims if isinstance(c, dict) and c.get('conversation_id'))
        frontier.update((neighbours or {}).get(doc, ()))
        row = rows.get(doc) or {}
        frontier.update(row.get('v3_recording_ids') or ())
        frontier.update(p['recording_id'] for p in row.get('recording_pieces') or () if p.get('recording_id'))
    return seen


def _lane_without_seed(options, page):
    if 'unlocked_limit' not in options or page is None:
        return False
    return not page.seeds[0 if options['pending_limit'] else 1]


def _keeps_unselected_outlines(custom_timing, on_open, page):
    """A partial pass keeps the cached outlines of groups it did not select, including unvisited unlocked windows."""
    return bool(custom_timing and on_open) or bool(page is not None and page.remaining)


async def _wake_unvisited_unlocked(uid, page, token, scheduled_at=None):
    now = datetime.now(timezone.utc)
    if page is not None and page.remaining and (scheduled_at is None or scheduled_at <= now):
        # An omitted window may already be due. Its next scan cannot depend on
        # the selected groups' deadlines or on the presence of pending recordings.
        scheduled_at = now + timedelta(minutes=1)
        # The pass's lease token names the task, so an earlier same-minute wake cannot swallow it.
        await run_blocking(db_executor, enqueue, uid, at=scheduled_at, wake_key=token)
    return scheduled_at


async def _wake_after_backoff(uid, page, token):
    """A parked paged pass's unlocked windows carry no pending marker for the sweep to find, and its
    next-minute continuation lands inside the backoff. Wake the owner when the backoff ends."""
    if page is None:
        return
    until, _ = await run_blocking(db_executor, store.backoff_state, uid)
    at = max(until or datetime.now(timezone.utc), datetime.now(timezone.utc)) + timedelta(seconds=5)
    await run_blocking(db_executor, enqueue, uid, at=at, wake_key=token)


def _measure_reconcile_writes(run):
    @wraps(run)
    async def measured(*args, **kwargs):
        if kwargs.get('_pass', 0) or kwargs.get('_seed_ceiling'):  # The outer pass owns the whole chain.
            return await run(*args, **kwargs)
        caller = 'backfill' if kwargs.get('derive') else 'on_open' if kwargs.get('on_open') else 'builder'
        with metrics.measure_reconcile_writes(caller):
            return await run(*args, **kwargs)

    return measured


def _exclude_unclaimed_backfill_donors(recordings, rows, *, rederive):
    claimed = {rid for row in rows for rid in row.get('v3_recording_ids') or []}
    # Keep unclaimed legacy rows visible. Converting them would hide the speech without a replacement.
    unclaimed = [rid for rid, row in recordings.items() if '_v3_backfill_prior' in row and rid not in claimed]
    for rid in unclaimed:
        recordings.pop(rid)
    # Re-derive may retire the existing copy. A converted donor needs a replacement before that can happen.
    if rederive and any(rid not in claimed for rid, row in recordings.items() if row.get('_v3_derive')):
        raise Conflict('backfill_donor_unclaimed')
    return unclaimed


async def _reconcile_outlines(
    uid,
    key,
    token,
    groups,
    cached,
    report,
    *,
    silence_seconds,
    silence_gap,
    cohesion,
    custom_timing,
    on_open,
    unlocked_page,
    retry_failed_outlines,
    flex_owner_deadline,
):
    # Keep a bounded cache; every fingerprint is checked even for finished stretches.
    if retry_failed_outlines:
        cached = [row for row in cached if not any(entry.get('_outline_failed') for entry in row['entries'])]
    saved = {row['fingerprint']: row for row in cached}
    preview_prefix = f'{silence_seconds}:'
    scoped_preview_keys = {f"{preview_prefix}{group['key']}" for group in groups} if custom_timing else set()
    previews = {row['preview_key']: row for row in cached if row.get('preview_key', '').startswith(preview_prefix)}
    unmatched_previews = {key: row for key, row in previews.items() if key not in scoped_preview_keys}
    consumed_previews = set()
    outlines, cache = [], []
    sources = await run_blocking(db_executor, context.outline_sources, uid, groups)
    for group in groups:
        await run_blocking(db_executor, leases.renew, uid, key, token)
        messages = outline.messages(group, timezone.utc, cohesion=cohesion, silence_gap=silence_gap)
        messages.append(
            (
                'human',
                context.outline_block(group, sources, [entry['title'] for entries in outlines for entry in entries]),
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
            entries, preview_fields = await _derive_outline(
                uid,
                key,
                token,
                group,
                messages,
                fingerprint,
                report,
                cohesion=cohesion,
                silence_gap=silence_gap,
                preview_key=preview_key,
                flex_owner_deadline=flex_owner_deadline,
            )
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
        outline_failed = any(entry.get('_outline_failed') for entry in entries)
        if (group['outline_ready'] or on_open or preview is not None) and (
            not retry_failed_outlines or not outline_failed
        ):
            if preview_key and not group['locked'] and not outline_failed:
                preview_fields = {'preview_key': preview_key, 'anchors': outline.preview_anchors(group, entries)}
            cache.append({'fingerprint': fingerprint, 'entries': entries, **preview_fields})

    if _keeps_unselected_outlines(custom_timing, on_open, unlocked_page):
        replaced = {row['fingerprint'] for row in cache}
        replaced_previews = scoped_preview_keys | consumed_previews
        cache = [
            row
            for row in cached
            if row.get('preview_key') not in replaced_previews and row['fingerprint'] not in replaced
        ] + cache
    return outlines, cache


def _home_visible(row):
    # The Home feed's row filters for a derived row (database/home_feed._visible), as the settle applies them.
    return (
        not row.get('sync_merged_into')
        and not is_relevance_discarded(row)
        and conversations_db.is_visible_conversation(row, hide_home=True, presentation=True)
    )


async def _after_projection(
    uid,
    key,
    token,
    groups,
    recordings,
    rows,
    existing,
    *,
    derive,
    on_open,
    moved,
    custom_timing,
    silence_gap,
    lock_delay,
    now,
):
    if moved:
        # Live speech arrived during the pass: the snapshot's windows are committed and the moved
        # recordings stay owed. Wake the owner at the next minute instead of an immediate re-pass,
        # which would race the same live recording again.
        metrics.safe_metric(lambda: metrics.RACES.labels('source_moved').inc())
        await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + RACE_RETRY)
    for group in groups if not derive else ():
        if not (group['locked'] if custom_timing else group['finished']):
            # A different minute than the currently executing task avoids
            # Cloud Tasks' completed-name dedupe swallowing the continuation.
            delay = lock_delay if group['outline_ready'] else min(silence_gap, lock_delay)
            settle_from = group.get('settle_from', group['end'])
            await run_blocking(db_executor, enqueue, uid, at=max(settle_from + delay, now + timedelta(minutes=1)))
    holds = [r[outline.HOLD_UNTIL] for r in recordings.values() if r.get(outline.HOLD_UNTIL) is not None]
    if holds and not derive:
        # A held manual-end cut applies when its wait ends, even if no transcript lands.
        metrics.safe_metric(lambda: metrics.FINISH_HELD.inc())
        await run_blocking(db_executor, enqueue, uid, at=max(min(holds), now + timedelta(minutes=1)))
    for row in rows:
        prior = existing.get(row['id']) or {}
        if (
            not row.get('home_hidden')
            and row.get('home_hidden_reason') == 'wearer_recognition_uncertain'
            and (prior.get('home_hidden') or prior.get('home_hidden_reason') != 'wearer_recognition_uncertain')
        ):
            metrics.safe_metric(lambda: metrics.UNCERTAIN_SHOWN.inc())
        if row['id'] not in existing:
            metrics.safe_metric(
                lambda: metrics.VISIBLE_LATENCY.observe(max(0, (now - row['started_at']).total_seconds()))
            )
        if not derive:
            # Finish timeline: this pass (begun at ``now``) is the first to commit the card as manually ended.
            finish_timeline.observe_card_finished(row, prior, pass_started=now, visible=_home_visible)
    if not derive and not on_open and live_title_enabled():
        for row in rows:
            if policy.live_title_candidate(row) and not row.get(policy.LIVE_TITLE_STATE):
                await _maybe_publish_live_title(uid, key, token, row)


async def _plan_projection(
    uid,
    groups,
    outlines,
    recordings,
    existing,
    unavailable,
    *,
    derive,
    live,
    on_open,
    conversation_id,
    custom_timing,
    refine_locked,
    cohesion,
    silence_gap,
    owner_cuts,
    now,
    lock_delay,
    run_id,
    first_open_gating,
):
    preferred = conversation_id if on_open and custom_timing else None
    revoked_native_ids = {
        cid for cid, row in existing.items() if not derive and _revoked_native_window(row, recordings)
    }
    settled_ids = {cid for cid, row in existing.items() if row.get(policy.NATIVE_MANUAL_SETTLED)}
    immutable = {cid: row for cid, row in existing.items() if cid not in revoked_native_ids and cid not in settled_ids}
    # One ownership index per plan (adoption can add rows before a replan), shared by the
    # two-hour cap and both projections below.
    ownership = planner.Ownership(immutable, recordings)
    proposed = planner.windows(
        groups,
        outlines,
        cohesion=cohesion,
        silence_gap=silence_gap,
        defer_topic_lock=custom_timing,
        ownership=ownership,
    )
    merge = refinement.candidate(proposed, immutable, recordings) if refine_locked else None
    if merge and await run_blocking(db_executor, store.merge_donors_have_tasks, uid, merge[1]['_v3_absorbed']):
        merge = None
    reserved = set()
    candidates = proposed
    if merge is not None:
        index, merged = merge
        reserved = {merged['id'], *merged['_v3_absorbed']}
        candidates = proposed[:index] + proposed[index + 1 :]
    windows = planner.preserve_finished_windows(
        candidates, immutable, recordings, protect_provisional=custom_timing, ownership=ownership
    )
    if reserved.intersection(window.get('existing_id') for window in windows):
        merge = None
        reserved.clear()
        windows = planner.preserve_finished_windows(
            proposed, immutable, recordings, protect_provisional=custom_timing, ownership=ownership
        )
    # A retained finished conversation owns its id by claim evidence; a fresh window that sorts
    # before it (late speech overlapping its start) must not time-match the same id. Two planned
    # rows with one id each re-add the source's held claims, doubling them every pass until the
    # recording outgrows Firestore's 1 MiB document limit (document_too_large).
    rows = []
    used = (
        reserved
        | settled_ids
        | unavailable.keys()
        | {window['existing_id'] for window in windows if window.get('existing_id')}
    )
    used.update(row['id'] for row in existing.values() if row.get('v3_refined') and row.get('v3_claims_transferred_to'))
    locked_ids = (
        {row['id'] for row in existing.values() if not planner.is_unlocked(row) and not row.get('deleted')}
        if custom_timing
        else set()
    ) - revoked_native_ids
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
            custom_timing and not transcription_failed and (not window['finished'] or window.get('_defer_lock', False))
        )
        excluded = used | locked_ids if deferred_lock else used
        prior = existing.get(window.get('existing_id')) or _match(window, existing, excluded, preferred=preferred)
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
        revoked_native = bool(prior and prior['id'] in revoked_native_ids)
        # A manual window that never produced notes may still be open by the natural clock.
        current_window = {**prior, 'status': 'in_progress'} if prior and revoked_native else prior
        row = planner.build(
            uid,
            window,
            recordings,
            current_window,
            allocated=allocated,
            manual_end_home_visible=manual_end_home_visible_enabled(),
        )
        if owner_cuts and row.get('manual_end') and not row.get(planner.CUT_FIELD):
            # Experiment end_open_conversation: remember the End that closed this conversation, so
            # speech recorded before it that lands later still belongs here (planner.Ownership).
            # Off there are no owner cuts and the field is never written.
            closed_by = planner.ending_cut(row['finished_at'], owner_cuts, silence_gap)
            if closed_by is not None:
                row[planner.CUT_FIELD] = closed_by
        if row.get('tile_state') == 'live' and reliability_experiments.any_enabled(
            uid, 'end_button_by_device', 'instant_live_text', 'vendor_recognizer_on_opened_app'
        ):
            # Experiments end_button_by_device, instant_live_text and vendor_recognizer_on_opened_app:
            # an open conversation names the app install behind its latest speech. With all off the
            # field is never written.
            capture_device.stamp(row, window['lines'], recordings)
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
        # Experiment live_words_cascade: the summary of a conversation a user End closed may already
        # have read its last words from the phone's live tail. Stored words landing afterwards are
        # first taken to be that same speech, so the rewrite rule below sees only what goes beyond
        # it. Off, or with no such credit on the conversation, the count is unchanged.
        unseen_words, tail_credit = live_tail.rewrite_words(prior, row, new_words, uid)
        if prior and prior.get(live_tail.CREDIT_FIELD) and tail_credit != prior[live_tail.CREDIT_FIELD]:
            row[live_tail.CREDIT_FIELD] = tail_credit
            # A summary pass still running read these words as tail: mark the landing, so its
            # settle stands instead of writing the notes again. A landing with unseen words drops
            # the mark, and that pass's settle fails as it always did.
            live_tail.mark_absorbed(row, prior, unseen_words)
            if tail_credit <= live_tail.SPENT_CREDIT:
                # Batch has landed the tail's speech: its words are no longer needed with the End.
                await run_blocking(db_executor, live_tail.forget, uid, prior.get(planner.CUT_FIELD))
            logger.info(
                'event=v3_live_tail outcome=credit new_words=%d unseen_words=%d credit_left=%d',
                new_words,
                unseen_words,
                tail_credit,
            )
        ended = window['finished'] and not deferred_lock
        if revoked_native:
            # The natural window, not the stale summary attempt, now owns scheduling.
            row['v3_process_pending'] = False
        was_ended = prior and not planner.is_unlocked(prior) and not revoked_native
        visibility_receipt = row.get(policy.NATIVE_MANUAL_NOTES_VISIBILITY)
        recovered_native_notes = bool(
            visibility_receipt
            and prior
            and prior.get('v3_process_pending')
            and not prior.get('v3_notes_written')
            and not row.get(policy.NATIVE_MANUAL_BINDING)
        )
        if recovered_native_notes:
            # The output committed while the proof was valid. Releasing its stale work
            # must not trigger a second model call because settlement was interrupted.
            row.update(
                v3_notes_written=True,
                v3_process_pending=False,
                summary_covers_through=visibility_receipt['finished_at'],
            )
        promoted = bool(
            prior
            and not row.get('home_hidden')
            and (
                row.get('manual_end')
                and not prior.get('manual_end')
                and not (window.get('native_manual_end') and prior.get('v3_notes_written'))
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
                new_words=unseen_words,
                ended_at=prior['finished_at'],
                now=now,
                rewrites=prior.get('v3_rewrites', 0),
            )
        )
        if rewrite:
            # The old summary no longer covers the window: without this the covered-summary guard
            # returns the previous notes and the only automatic rewrite is spent on nothing.
            row['summary_covers_through'] = None
        outline_recovered = (
            first_open_gating
            and on_open
            and prior
            and prior.get('v3_process_failure_reason') == 'outline'
            and not window.get('_outline_failed')
        )
        needs_processing = (
            not was_ended
            or rewrite
            or promoted
            or outline_recovered
            or (prior or {}).get('tile_state') == 'transcribing'
        )
        keep_prior_status = not needs_processing if first_open_gating else not (rewrite or promoted)
        if prior is not None and was_ended and keep_prior_status:
            row['status'] = prior['status']
            row['tile_state'] = 'done' if recovered_native_notes else prior.get('tile_state', 'done')
        waiting = not transcription_failed and any(
            policy.transcription_pending(recordings[l['conversation_id']]) for l in window['lines']
        )
        if ended and waiting and (not recovered_native_notes or rewrite):
            row['tile_state'] = 'transcribing'
            row['v3_process_pending'] = False
            if not derive:
                await run_blocking(db_executor, enqueue, uid, at=now + timedelta(minutes=1))
        if ended and not waiting and needs_processing:
            if outline_recovered:
                row.update(v3_process_failed=False, v3_process_failure_reason=None, summary_retryable=False)
            row['v3_process_pending'] = True
            row.pop('v3_process_retry_after', None)
            row['v3_rewrites'] = int((prior or {}).get('v3_rewrites') or 0) + int(rewrite)
        if (
            (recovered_native_notes or (prior and prior.get('home_hidden')))
            and not row.get('v3_process_pending')
            and policy.created_eligible(row)
        ):
            # Recovered settlement and first visibility of already-written notes both
            # owe created fanout without another model call.
            row['v3_created_pending'] = True
        if ended and needs_processing:
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


@_measure_reconcile_writes
async def reconcile(
    uid,
    *,
    on_open=False,
    promote_llm=False,
    conversation_id=None,
    derive=False,
    since=None,
    until=None,
    run_id=None,
    rederive=False,
    live=False,
    historical_timing=None,
    internal_end=False,
    background=False,
    report=None,
    _pass=0,
    _seed_ceiling=None,
):
    """One builder pass. ``derive`` is one planned backfill partition ([since, until), one owner).

    A derive pass applies every live planning, visibility and notes rule; it differs only in its
    inputs (legacy donors instead of v3_pending recordings), in stamping rows ``backfilled`` and in
    queueing notes on its own marker, drained by the backfill task instead of the live queue.
    ``live`` (with ``derive``) replans the owner's finished live windows from their sealed sources:
    see rederive_store.load_live_rederive and rederive_plan.live_outcome. An explicit historical timing
    receipt opts that repair into the serving sit-down profile.
    """
    report = {} if report is None else report
    key = store.BACKFILL_LEASE if derive else 'builder'
    blocked = None
    parked = None
    moved = set()
    deferred: dict[str, datetime] = {}
    if not on_open and not derive:
        backoff, parked = await run_blocking(db_executor, store.backoff_state, uid)
        # A batch-cap retry (_seed_ceiling) belongs to a pass that already got past this gate. Its own early attempt
        # (mark_bounded_attempt) may have restored a park's future backoff, which must not stop the smaller load.
        if _seed_ceiling is None and backoff and backoff > datetime.now(timezone.utc):
            metrics.RECONCILES.labels('backoff').inc()
            # Rows earlier passes committed still owe notes while the builder is parked.
            with suspend_committed_write_count():
                await _drain_blocked(uid, parked)
            return 'backoff'
    first_open_gating = v3_summary_first_open_gating_enabled()
    flex_enabled = background_outline_flex_enabled()
    retry_failed_outlines = first_open_gating or flex_enabled
    flex_owner_deadline = (
        time.monotonic() + OUTLINE_BACKGROUND_BUDGET_SECONDS
        if background and flex_enabled and not (on_open or derive or internal_end)
        else None
    )
    promote = {'promote_llm': True} if on_open and promote_llm and flex_enabled and not derive else {}
    token = await run_blocking(db_executor, leases.acquire, uid, key, **promote)
    if token is None:
        metrics.RECONCILES.labels('busy').inc()
        return 'busy'
    primary_failed = False
    bounded_pending_limit = None
    smaller_seeds = None
    unlocked_page = None
    unlocked_wake = None
    try:
        # The reliability experiments below are read on this event loop, which answers from what was last
        # learned for the account. Learn it on a worker thread first, so a pass never misses a switch.
        await reliability_experiments.warm(uid)
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
        elif not on_open and bounded_pending_enabled():
            unlocked_page = UnlockedPage()
            recordings, existing, cached, bounded_pending_limit = await _load_live_batch(
                uid, token, parked, unlocked_page, _seed_ceiling
            )
        else:
            recordings, existing, cached = await run_blocking(
                db_executor,
                store.load,
                uid,
                **({'conversation_id': conversation_id} if on_open and conversation_id else {}),
                lease_token=token,
            )
        # The legacy backfill delete set must never depend on native Finish planning.
        if (
            derive
            and rederive
            and not live
            and (
                any(policy.NATIVE_MANUAL_READY in row for row in recordings.values())
                or any(
                    row.get(field)
                    for row in existing.values()
                    for field in (
                        policy.NATIVE_MANUAL_BINDING,
                        policy.NATIVE_MANUAL_NOTES_VISIBILITY,
                        policy.NATIVE_MANUAL_SETTLED,
                    )
                )
            )
        ):
            raise Conflict('backfill_native_finish_unsupported')
        if on_open and existing.get(conversation_id, {}).get(policy.NATIVE_MANUAL_SETTLED):
            return 'stored'
        now = datetime.now(timezone.utc)
        eligible = [r for r in recordings.values() if policy.builder_eligible(r)]
        custom_timing = (silence_seconds, lock_seconds) != (DEFAULT_BOUNDARY_SECONDS, DEFAULT_BOUNDARY_SECONDS)
        silence_gap, lock_delay = timedelta(seconds=silence_seconds), timedelta(seconds=lock_seconds)
        owner_cuts = []
        if historical_timing is not None:
            groups = historical_stretches(eligible, now, since=since, until=until, internal_end=internal_end)
        else:
            # Experiment end_open_conversation: owner-level End instants cut the live builder's stretches.
            # Off (the baseline) this reads nothing and passes no cuts. Backfill and re-derive do not read them.
            if not derive and manual_cuts.enabled(uid):
                owner_cuts = await run_blocking(db_executor, manual_cuts.load, uid, eligible)
            groups = outline.stretches(
                eligible,
                now,
                silence_gap=silence_gap,
                lock_delay=lock_delay,
                settle_on_landing=settle_on_landing_enabled(
                    custom_timing=custom_timing, cohesion=cohesion, derive=derive
                ),
                max_window=timedelta(seconds=max_window_seconds()),
                **({'manual_cuts': owner_cuts} if owner_cuts else {}),
                # Live passes only: backfill and re-derive keep their windowing (cuts there are long settled).
                continuity=capture_continuity_enabled() and not derive,
            )
        if live and any(not g['finished'] or (g.get('window_cap_end') and not g['locked']) for g in groups):
            # Speech within five minutes of now is still the live builder's; refuse before any paid call.
            raise Conflict('rederive_live_open')
        if not derive:
            for group in groups:
                if group.get('window_cap_end'):
                    # Later speech can keep refreshing the same recording's landing clock.
                    # The forced boundary settles the prefix independently of that clock.
                    group['locked'] = True
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
        outlines, cache = await _reconcile_outlines(
            uid,
            key,
            token,
            groups,
            cached,
            report,
            silence_seconds=silence_seconds,
            silence_gap=silence_gap,
            cohesion=cohesion,
            custom_timing=custom_timing,
            on_open=on_open,
            unlocked_page=unlocked_page,
            retry_failed_outlines=retry_failed_outlines,
            flex_owner_deadline=flex_owner_deadline,
        )

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

        plan = partial(
            _plan_projection,
            uid,
            groups,
            outlines,
            recordings,
            existing,
            unavailable,
            derive=derive,
            live=live,
            on_open=on_open,
            conversation_id=conversation_id,
            custom_timing=custom_timing,
            refine_locked=refine_locked,
            cohesion=cohesion,
            silence_gap=silence_gap,
            owner_cuts=owner_cuts,
            now=now,
            lock_delay=lock_delay,
            run_id=run_id,
            first_open_gating=first_open_gating,
        )

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
        unclaimed = _exclude_unclaimed_backfill_donors(recordings, rows, rederive=rederive) if derive else []
        # The commit removes unplanned prior copies only if they have no task or memory links.
        remove = [cid for cid in existing if cid not in planned] if derive and rederive else []
        removed_ids: set[str] = set()
        retire, commit_recordings, commit_existing, priors = {}, recordings, existing, []
        # An unmatched revoked tile keeps its ID for direct links, but no longer owns speech or work.
        settle = {
            cid: {
                'status': 'completed',
                'home_hidden': True,
                'v3_derived': False,
                'v3_unlocked': False,
                'v3_process_pending': False,
                'v3_created_pending': False,
                'tile_state': 'failed',
                'summary_retryable': False,
                'summary_due_at': None,
                'manual_end': False,
                policy.NATIVE_MANUAL_BINDING: None,
                policy.NATIVE_MANUAL_SETTLED: True,
                'sync_content_revision': int(prior.get('sync_content_revision') or 0) + 1,
            }
            for cid, prior in existing.items()
            if not (derive or on_open)
            and cid not in planned
            and not prior.get('deleted')
            and _revoked_native_window(prior, recordings)
        }
        if live:
            rows, retire, touched, sources, priors, outcome = rederive_plan.live_outcome(
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
            unlocked_wake = await _wake_unvisited_unlocked(uid, unlocked_page, token)
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
                removed_ids=removed_ids,
                retire=retire,
                key=key,
                bounded_pending_limit=bounded_pending_limit,
                unlocked_page=unlocked_page,
                **({'settle': settle} if settle else {}),
            )
        except Exception:
            if live:
                # Copies of rows this attempt did not write go, whatever failed; a resume records them
                # again. If this cleanup fails too, the partition stays unfinished until resume or undo.
                await run_blocking(db_executor, rederive_store.drop_unwritten_priors, uid, run_id, priors)
            raise
        if not derive and not on_open:
            # Experiment fast_end_feedback: a client waiting on an ended conversation is woken as soon as
            # it is committed with its outline, before its summary starts. Off, nothing is published.
            summary_wake.publish_committed(uid, rows, existing)
            cap_starts = {group['lines'][0]['start'] for group in groups if group['after_window_cap']}
            new_cap_starts = {row['started_at'] for row in rows if row['id'] not in existing} & cap_starts
            metrics.safe_metric(lambda: metrics.WINDOW_CAP_CUTS.inc(len(new_cap_starts)))
        report.update(
            sources=len(eligible),
            windows=len(rows),
            rows_new=sum(1 for row in rows if row['id'] not in existing),
            rows_removed=len(removed_ids),
            # A live run's loader already counted unclaimed live speech; its legacy meaning is donors.
            **({} if live else {'sources_unclaimed': len(unclaimed)}),
            notes_queued=sum(1 for row in rows if row.get('v3_backfill_process_pending')),
            home_visible=sum(1 for row in rows if not row.get('home_hidden')),
        )
        await _after_projection(
            uid,
            key,
            token,
            groups,
            recordings,
            rows,
            existing,
            derive=derive,
            on_open=on_open,
            moved=moved,
            custom_timing=custom_timing,
            silence_gap=silence_gap,
            lock_delay=lock_delay,
            now=now,
        )
        metrics.safe_metric(lambda: metrics.RECONCILES.labels('committed').inc())
        deferred = preview_wakes(rows, recordings)
    except Conflict as error:
        primary_failed = True
        reason = str(error)
        if reason in RACES and not derive:
            # Nothing committed, so every pending marker is still owed. Answer the task and wake the
            # owner at the next minute: a minute name the executing task cannot already hold, shared
            # with every other wake for that minute. Without a scheduled wake, fall back to a retry.
            try:
                await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + RACE_RETRY)
            except Exception as dispatch:
                metrics.safe_metric(lambda: metrics.RECONCILES.labels('dispatch_error').inc())
                metrics.safe_metric(lambda: metrics.RECONCILES.labels('error').inc())
                metrics.safe_metric(
                    lambda: logger.warning('v3 reconcile race wake failed exception_type=%s', type(dispatch).__name__)
                )
                raise error from dispatch
            metrics.safe_metric(lambda: metrics.RECONCILES.labels('raced').inc())
            metrics.safe_metric(lambda: metrics.RACES.labels(reason).inc())
            metrics.safe_metric(lambda: logger.info('v3 reconcile raced reason=%s', reason))
            primary_failed = False
            return 'raced'
        if reason not in BLOCKED:
            metrics.safe_metric(lambda: metrics.RECONCILES.labels('error').inc())
            raise
        smaller_seeds = None if on_open or derive else _smaller_seed_ceiling(error, unlocked_page, _seed_ceiling)
        if smaller_seeds is not None:
            # The locked-closure batch cap fails before any write, and fewer seeds of either kind may fit (Codex
            # P2s on #26443). Retry down the load ladder, pending and unlocked lanes alike; park at one seed.
            metrics.safe_metric(
                lambda: logger.info(
                    'event=v3_locked_closure_batches retry pending_limit=%d unlocked_limit=%d seeds=%d',
                    *smaller_seeds,
                )
            )
            primary_failed = False
        else:
            # A deterministic conflict fails identically on every retry: answer the task (no Cloud Tasks
            # retry storm through the shared queue) and back this owner off; v3_pending stays owed.
            metrics.safe_metric(lambda: metrics.RECONCILES.labels('blocked').inc())
            metrics.safe_metric(lambda: metrics.BLOCKED.labels(reason).inc())
            metrics.safe_metric(
                lambda: logger.warning(
                    'v3 reconcile blocked reason=%s owner=%s cause=%s', reason, owner_tag(uid), redacted_cause(error)
                )
            )
            report['blocked_reason'] = reason
            if not derive:
                # A backfill conflict must not park the owner's live builder.
                await run_blocking(
                    db_executor,
                    store.record_blocked,
                    uid,
                    token,
                    reason,
                    on_open=on_open,
                    **_quarantine_park(error, bounded_pending_limit, unlocked_page),
                )
            blocked = reason
            primary_failed = False
    except BaseException as error:
        primary_failed = True
        if isinstance(error, Exception):
            metrics.safe_metric(lambda: metrics.RECONCILES.labels('error').inc())
        raise
    finally:
        await _release_reconcile_lease(uid, key, token, primary_failed=primary_failed)
    if smaller_seeds is not None:
        # Nothing was written and pending is still owed; the lease is released, so the retry can take it.
        return await reconcile(
            uid,
            background=background,
            internal_end=internal_end,
            report=report,
            _pass=_pass,
            _seed_ceiling=smaller_seeds,
        )
    if blocked is not None:
        if not derive and not on_open:
            # Windows earlier passes (or earlier batches) committed still owe their notes.
            with suspend_committed_write_count():
                await _drain_blocked(uid, blocked)
            await _wake_after_backoff(uid, unlocked_page, token)
        return 'blocked'
    await _wake_unvisited_unlocked(uid, unlocked_page, token, unlocked_wake)
    if on_open:
        await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + timedelta(minutes=1))
        return 'committed'
    if derive:
        # The backfill task drains its own notes marker within its deadline.
        return 'committed'
    with suspend_committed_write_count():
        await drain_processing(uid)
    if moved:
        return 'committed'
    # Size-quarantined recordings stay pending for repair; they must not keep the owner's pass chain hot.
    skip = {*deferred, *(unlocked_page.quarantined if unlocked_page is not None else ())}
    pending = (
        await run_blocking(db_executor, has_pending, uid, skip)
        if skip
        else await run_blocking(db_executor, has_pending, uid)
    )
    if pending and _pass < 2:
        return await reconcile(uid, background=background, _pass=_pass + 1)
    if pending:
        await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + timedelta(minutes=1))
    return 'committed'


async def _maybe_publish_live_title(uid, key, token, row):
    # Reliability experiment title_at_end: an open conversation is not named; the outline names it at its end.
    if reliability_experiments.enabled(reliability_experiments.TITLE_AT_END_FLAG_KEY, uid):
        return
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
        metrics.safe_metric(lambda: logger.warning('event=v3_live_title exception_type=%s', type(error).__name__))
        metrics.safe_metric(
            lambda: record_fallback(
                component='other', from_mode='none', to_mode='none', reason='other', outcome='degraded'
            )
        )


def _commit(
    uid,
    token,
    recordings,
    existing,
    rows,
    cache,
    *,
    clear_pending=True,
    remove=(),
    removed_ids=None,
    retire=None,
    settle=None,
    key='builder',
    bounded_pending_limit=None,
    unlocked_page=None,
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
            removed_ids=removed_ids,
            retire=retire,
            key=key,
            **({'settle': settle} if settle else {}),
            **({'bounded_pending_limit': bounded_pending_limit} if bounded_pending_limit is not None else {}),
            **({'unlocked_page': unlocked_page} if unlocked_page is not None else {}),
        )
    except InvalidArgument as error:
        # A document over Firestore's 1 MiB limit, or a commit request over its payload limit, fails the
        # same way on every retry; park the owner instead of cycling the shared queue with 500s.
        kind = store.size_error(error)
        if kind == 'document':
            conflict = Conflict('document_too_large')
            # What the rejected commit wrote, for the size quarantine's attribution.
            conflict.size_commit = (recordings, existing, rows)
            raise conflict from error
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
        raise
    finally:
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
        primary_failed = False
        try:
            # The pending scan can precede a foreground write that releases
            # this lease. Use its latest input and coverage to reuse the notes
            # while still running the remaining processing and derived effects.
            current = await run_blocking(db_executor, _load_processing_row, uid, row['id'])
            if current and current.get('v3_process_pending'):
                await _process_leased(uid, current, token)
        except FinalizationOwnedElsewhere:
            continue
        except Conflict as error:
            if str(error) != 'lease_lost':
                primary_failed = True
                raise
            try:
                await run_blocking(db_executor, enqueue, uid, at=datetime.now(timezone.utc) + RACE_RETRY)
            except BaseException:
                primary_failed = True
                raise
        except BaseException:
            primary_failed = True
            raise
        finally:
            await _release_reconcile_lease(uid, 'summary-' + row['id'], token, primary_failed=primary_failed)
    # Settled notes arm the conversation-created obligation; deliver after every summary lease is released.
    # Imported here: the webhook fanout's LLM/app graph must not join process_conversation's import graph,
    # which loads this module at import time (listen, pusher and sync all import it).
    from utils.conversations.v3 import created

    await created.deliver(uid)


def _load_processing_row(uid, cid):
    snapshot = store.user_conversations(store.get_firestore_client(), uid).document(cid).get()
    return store.decode_row(uid, snapshot) if snapshot.exists else None


PROCESSING_SCAN_MAX_PAGES = 4


def pending_processing(uid):
    client = store.get_firestore_client()
    now = datetime.now(timezone.utc)
    query = (
        store.user_conversations(client, uid)
        .where(filter=FieldFilter('v3_process_pending', '==', True))
        .order_by('__name__')
        .limit(store.LIMIT)
    )
    due = []
    page = query
    # At most four pages (512 document reads), and at most 128 decoded results.
    for _ in range(PROCESSING_SCAN_MAX_PAGES):
        snapshots = list(page.stream())
        for doc in snapshots:
            data = doc.to_dict() or {}
            if policy.processing_due(data, now):
                due.append(store.decode_row(uid, doc, data=data))
                if len(due) == store.LIMIT:
                    return due
        if len(snapshots) < store.LIMIT:
            break
        page = query.start_after(snapshots[-1])
    return due


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
    backfill_prior = {} if row.get('backfilled') else None
    if writers.begin_processing(uid, row, token, backfill_prior=backfill_prior) is not True:
        return
    texts = [s.get('text') or '' for s in row.get('transcript_segments') or []]
    words = sum(map(text_word_count, texts))
    below_minimum = words < MIN_TASK_WORDS
    passive = row.get('kind') in {'media', 'background'}
    manual = policy.manual_intent(row)
    if finish_timeline.first_notes_attempt(row):
        finish_timeline.observe('notes_started', row)
    notes = False
    tail_words = None
    if passive or (not manual and below_minimum):
        lifecycle.complete(uid, row['id'])
    else:
        notes = True
        persisted = []

        def summary_persisted(current):
            # process_conversation reports its canonical write here, before folder assignment, memory
            # extraction and the other derived effects. Experiment fast_end_feedback shows the row as done
            # at that moment instead of after them; settle_processing below still owns the obligation.
            # Off, this is the baseline observer and nothing else is written.
            persisted.append(current)
            if current and reliability_experiments.enabled('fast_end_feedback', uid):
                try:
                    if writers.show_summary_stored(uid, row['id'], token):
                        logger.info('event=v3_summary_shown_early outcome=shown')
                        summary_wake.publish(uid, row['id'])
                except Exception as error:
                    logger.warning('event=v3_summary_shown_early outcome=error exception_type=%s', type(error).__name__)

        # Experiment live_words_cascade: the live words the phone showed before the End that closed this
        # conversation, less what stored text covers, follow the transcript in the notes prompt. Off, or
        # for a conversation no End closed, the text is empty and the prompt is the baseline.
        tail_text, tail_words, tail_since = live_tail.for_conversation(uid, row)
        if tail_words is not None:
            # The count is stamped before the notes are written, not when the pass settles: the batch
            # text for the same speech usually lands within seconds, while this pass is still running,
            # and the grouping pass must already find the count to know that speech is not new to the
            # notes. A pass that fails is run again and stamps again from what is uncovered then.
            try:
                writers.note_summary_tail(uid, row['id'], token, tail_words, tail_since)
            except Exception as error:
                logger.warning('event=v3_live_tail outcome=stamp_error exception_type=%s', type(error).__name__)
        summary_lease = None
        if not (manual or row.get('backfilled') or row.get('v3_unlocked') or policy.live_summary_target(row)):
            summary_lease = (row['id'], token, row.get('finished_at'))
        try:
            with (
                fence.writer(uid, row['id'], token, native_binding=row.get(policy.NATIVE_MANUAL_BINDING)),
                models.notes_mode(uid, backfilled=bool(row.get('backfilled')), background_lease=summary_lease),
                live_tail.summarising(tail_text),
            ):
                result = process_conversation(
                    uid,
                    row.get('language') or 'en',
                    Conversation(**row),
                    persistence_observer=summary_persisted,
                    # Backfilled rows take the live trigger so relevance, speaker and meeting context and the
                    # short-clip floor match live notes; process_conversation withholds their derived effects.
                    trigger=ProcessingTrigger.CAPTURE_END,
                )
                decline = fence.persistence_declined()
        except (models.BackfillNotesDeletionBlocked, models.BackfillNotesAdmissionTimeout):
            if backfill_prior is not None:
                writers.park_backfill_processing(uid, row['id'], token, backfill_prior)
            raise
        if decline is not None:
            writers.settle_processing(
                uid, row['id'], token, row.get('sync_content_revision'), None, skipped=True, decline=decline
            )
            return
        if getattr(result.status, 'value', result.status) == 'failed':
            writers.fail_processing(
                uid, row['id'], token, row.get('sync_content_revision'), content_hash=writers.processing_hash(row)
            )
            return
        if not persisted or not persisted[-1] or getattr(result.status, 'value', result.status) != 'completed':
            raise RuntimeError('v3_processing_not_completed')
        metrics.safe_metric(
            lambda: metrics.SUMMARY_WRITES.labels('rewrite' if row.get('v3_rewrites') else 'first').inc()
        )
    metrics.safe_metric(
        lambda: metrics.SUMMARY_LATENCY.observe(
            max(0, (datetime.now(timezone.utc) - row['finished_at']).total_seconds())
        )
    )
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
        # Experiment live_words_cascade: how many tail words this summary used, for the rewrite rule.
        tail_words=tail_words if notes and tail_words is not None else None,
    )
    # Experiment fast_end_feedback: a client waiting on this row (GET .../summary/wait) is woken again at
    # the end of the pass, for the passes that had no early summary write. Off, nothing is published.
    summary_wake.publish(uid, row['id'])


async def sweep():
    client = await run_blocking(db_executor, store.get_firestore_client)
    now = datetime.now(timezone.utc)
    users = set()
    stale: dict[str, set[str]] = {}
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
                stale.setdefault(parts[1], set()).add(parts[3])
                metrics.PENDING_AGE.observe((now - since).total_seconds())
        if len(rows) < 1000:
            break
        cursor = rows[-1]
    for uid, ids in stale.items():
        # Recordings set aside for size stay pending until repaired; they alone must not wake the owner
        # every sweep (SCA-2918). One lease read per stale owner, against the full stale-pending scan above.
        if size_quarantine_filters():
            try:
                held = await run_blocking(db_executor, store.size_quarantined, uid)
            except Exception as error:
                # One unreadable lease must not stop the sweep: treat the owner as not quarantined and wake it.
                logger.warning('event=v3_size_quarantine_read outcome=error exception_type=%s', type(error).__name__)
                record_fallback(
                    component='conversations_v3',
                    from_mode='size_quarantine_filter',
                    to_mode='unfiltered_wake',
                    reason='unavailable',
                    outcome='recovered',
                    log=logger,
                )
                held = frozenset()
            if ids <= held:
                continue
        users.add(uid)
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
            row = doc.to_dict() or {}
            if not python_owns_finalization(row) or not policy.processing_due(row, now):
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
    checked before each chunk so an undo stops new notes work, and so is the account-deletion marker:
    once deletion starts no transcript goes to the notes model (``account_deletion`` is set).
    """
    counts: dict[str, Any] = {'processed': 0, 'failed': 0, 'retry': 0, 'busy': 0, 'remaining': 0, 'account_deletion': 0}
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
        try:
            if await run_blocking(db_executor, store.account_deletion_blocks_user_work, uid, fresh=True):
                counts['account_deletion'] = 1
                return
            failed = False
            try:
                await _process_leased(uid, row, token)
            except models.BackfillNotesDeletionBlocked:
                counts['account_deletion'] = 1
                return
            except Exception as error:
                failed = True
                logger.warning('event=v3_backfill_notes outcome=error exception_type=%s', type(error).__name__)
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
        if (
            counts['account_deletion']
            or time.monotonic() >= deadline
            or (keep_going is not None and not await keep_going())
        ):
            break
        if await run_blocking(db_executor, store.account_deletion_blocks_user_work, uid, fresh=True):
            counts['account_deletion'] = 1
            break  # still count what remains owed below
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


# The account gate kind storage's audio-deletion helpers take; held here, theirs nests in it.
AUDIO_GATE_KIND = 'audio_conversation_deletion'


class AudioPurgeIntakesPending(RuntimeError):
    """The recording's batch-intake purge obligation has not run yet; the blobs wait for it."""


def _assert_erasure_permitted(uid):
    """The obligation runner's hold preflight; a held purge stays owed and the sweep re-checks it."""
    try:
        legal_holds.assert_account_deletion_permitted(uid)
    except legal_holds.LegalHoldActive:
        metrics.AUDIO_PURGES.labels('held').inc()
        raise


def purge_audio(uid, rid):
    """Erase a released recording. Custody intakes go before the blobs; any failure raises for the retry.

    Nothing is deleted under an active legal hold: the hold is checked before the
    claim, the inline intake purge runs under the account gate a synchronous user
    delete holds (its acquisition re-checks the hold), and every blob deletion runs
    under one audio-deletion gate, which a hold cannot overtake. Each step is
    idempotent and the pending bit clears last.
    """
    _assert_erasure_permitted(uid)
    claim = store.claim_audio_purge(
        uid, rid, defer_intake_purge=cloud_tasks.is_conversation_batch_purge_dispatch_configured()
    )
    if not claim:
        return
    if claim.custody_invalidated:
        metrics.AUDIO_PURGES.labels('custody_invalidated').inc()
    if claim.intakes == 'pending':
        metrics.AUDIO_PURGES.labels('intakes_pending').inc()
        raise AudioPurgeIntakesPending('record WAL intake purge obligation still armed')
    if claim.intakes == 'inline':
        # The same per-conversation purge a user delete runs (record_deletion) under the same gate,
        # for the recording and each retained donor; the claim wrote their tombstones.
        try:
            with legal_holds.destructive_operation_gate(uid, kind=batch_purge_jobs.GATE_KIND):
                for owner in (rid, *claim.donor_ids):
                    batch_pipeline_purge.purge_batch_owner(uid, conversation_id=owner)
        except legal_holds.LegalHoldActive:
            metrics.AUDIO_PURGES.labels('held').inc()
            raise
        except Exception:
            metrics.AUDIO_PURGES.labels('intakes_failed').inc()
            raise
    # One account gate spans every irreversible blob deletion: canonical packs, the recording's raw
    # prefixes and each donor's. Its acquisition re-checks the hold transactionally, and while it runs
    # place_legal_hold refuses, so no hold can land between the canonical and the prefix deletes.
    # The storage helpers' own audio gate nests in this one (same uid and kind) rather than releasing it.
    try:
        with legal_holds.destructive_operation_gate(uid, kind=AUDIO_GATE_KIND):
            if claim.donor_ids:
                # A merge target's retained donors served only this recording, as a user delete erases them:
                # their canonical packs with the recording's, then each donor's own prefixes.
                storage.delete_privacy_conversation_audio(uid, rid, source_ids=list(claim.donor_ids))
                for donor in claim.donor_ids:
                    storage.delete_conversation_audio_files(uid, donor)
            else:
                storage.delete_privacy_conversation_audio(uid, rid)
    except legal_holds.LegalHoldActive:
        metrics.AUDIO_PURGES.labels('held').inc()
        raise
    done = {'v3_audio_purge_pending': False, 'audio_files': []}
    if claim.donor_ids:
        # The donor list is the last identifier the erase needed; it goes with the pending bit.
        done[store.AUDIO_PURGE_DONORS_FIELD] = []
    conversations_db.update_conversation(uid, rid, done)
    metrics.AUDIO_PURGES.labels('erased').inc()


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
        .select(['v3_pending'])  # Only ids are needed: up to 65 for an owner holding a full quarantine.
        .limit(len(deferred) + 1)
        .stream()
    )
    return any(doc.id not in deferred for doc in pending)
