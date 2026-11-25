"""Per-owner v3 repair: plan, estimate, run and undo backfill runs.

A run re-derives one owner's legacy pendant/phone conversations in [since, until) through the live
v3 builder and notes path (service.reconcile(derive=True) and service._process). The operator plans
it (backend/scripts/conversations_v3_backfill.py), which writes the run ledger and a start marker;
the five-minute sweep starts it once CONVERSATIONS_V3_BACKFILL=on, and each partition then runs as a
task on the dedicated backfill queue, one at a time per owner. Undo restores the legacy rows exactly
and removes the derived copies. A ``rederive-live`` run instead replans the owner's finished live v3
windows from their sealed sources after a planner fix; its undo restores every row it changed,
created or retired from the run's priors. Runbook: backend/docs/runbooks/conversations-v3.md.
"""

import hashlib
import logging
import os
import time
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone

from config.conversations_v3 import HISTORICAL_SITDOWN_TIMING, max_window_seconds, stretch_cohesion_enabled
from database import conversations as conversations_db
from database import conversations_v3 as store
from database import conversations_v3_backfill_runs as runs
from database import conversations_v3_leases as leases
from database import conversations_v3_rederive as rederive_store
from utils.cloud_tasks import enqueue_named_task
from utils.conversations.v3 import Conflict, outline, planner, policy, service, visibility
from utils.conversations.v3.triggers import task_base
from utils.conversations.v3.word_floor import MIN_TASK_WORDS
from utils.executors import db_executor, run_blocking

logger = logging.getLogger(__name__)

# Rows per partition at plan time. A resumed or re-derived partition also loads its derived copies,
# and the loader refuses more than store.LIMIT (128) documents, so plan well under half of it.
PARTITION_ROWS = 48
# A live re-derive partition reads sources and rows together (conversations_v3_rederive.REDERIVE_LIVE_LIMIT is 256) and
# rewrites only claims on its sources, so it plans larger partitions: fewer forced cuts in a busy day.
LIVE_MODE = runs.LIVE_MODE
LIVE_PARTITION_ROWS = 192
# A step (outline pass plus notes) stops taking new notes work this long after it started; the
# route timeout and the Cloud Tasks dispatch deadline are both 25 minutes.
STEP_SECONDS = 20 * 60
OWNERSHIP_RECHECK_SECONDS = 60 * 60
DEFAULT_QUEUE = 'conversations-v3-backfill'
STARTS_PER_SWEEP = 20

# Cost model for the dry-run estimate: the gateway card openai.gpt-6-luna.2026-09-22 (USD per million
# tokens) and planning token sizes per call. Actual spend comes from gateway usage, never from this.
INPUT_USD_PER_MILLION = 0.10
OUTPUT_USD_PER_MILLION = 0.60
TOKENS_PER_WORD = 1.4
OUTLINE_TOKENS = {'in': 1100, 'out': 350}
NOTES_TOKENS = {'in': 5000, 'out': 1500}
SHORT_TASKS_TOKENS = {'in': 1500, 'out': 250}
# Long conversations take the agentic notes path, capped per conversation (notes_agent_policy).
AGENT_MIN_WORDS = 1500
AGENT_MAX_USD = 0.02


class BackfillRetry(Exception):
    """The step could not run now (owner busy); the task is retried by the queue."""


def _utc(value):
    return outline.utc(value)


def plan_partitions(meta, since, until, *, max_rows=PARTITION_ROWS, historical_sitdown=False):
    """Cut [since, until) into partitions of at most max_rows documents, at recorded silence.

    A cut is placed at the last gap of at least five minutes (outline.SILENCE, the live hard window
    boundary), so no live stretch spans two partitions. Only a gap-free run longer than max_rows is
    cut at its largest gap; that partition is marked forced_cut and the run reports the count.
    Historical sit-down plans require a 900-second boundary and refuse forced cuts.
    """
    gap_seconds = HISTORICAL_SITDOWN_TIMING[0] if historical_sitdown else outline.SILENCE.total_seconds()
    rows = sorted((r for r in meta if r.get('started_at')), key=lambda r: _utc(r['started_at']))
    if (
        historical_sitdown
        and len(rows) > max_rows
        and any(not r.get('finished_at') or _utc(r['finished_at']) < _utc(r['started_at']) for r in rows)
    ):
        raise Conflict('rederive_live_boundary')
    partitions, current, gaps = [], [], []
    end = None
    for row in rows:
        start = _utc(row['started_at'])
        gap = (start - end).total_seconds() if end is not None else float('inf')
        if len(current) >= max_rows:
            silent = [i for i in range(1, len(current)) if gaps[i] >= gap_seconds]
            forced = not silent and gap < gap_seconds
            if forced and historical_sitdown:
                raise Conflict('rederive_live_boundary')
            if gap >= gap_seconds:
                cut = len(current)
            elif silent:
                cut = silent[-1]
            else:
                cut = max(range(1, len(current)), key=lambda i: gaps[i]) if len(current) > 1 else len(current)
            partitions.append({'rows': current[:cut], 'forced_cut': forced})
            current, gaps = current[cut:], gaps[cut:]
        current.append(row)
        gaps.append(gap)
        end = max(end or start, _utc(row.get('finished_at')) or start)
    if current:
        partitions.append({'rows': current, 'forced_cut': False})
    planned = []
    for index, part in enumerate(partitions):
        planned.append(
            {
                'since': since if index == 0 else _utc(part['rows'][0]['started_at']),
                'until': _utc(partitions[index + 1]['rows'][0]['started_at']) if index + 1 < len(partitions) else until,
                'documents': len(part['rows']),
                'forced_cut': part['forced_cut'],
                'status': 'pending',
            }
        )
    return planned or [{'since': since, 'until': until, 'documents': 0, 'forced_cut': False, 'status': 'pending'}]


def classify_window(meta):
    """Counts for the operator: legacy candidates and what stays legacy, with the reason.

    Metadata carries no transcript, so a candidate whose transcript is unreadable (or that no window
    claims) is only found by the builder; the estimate's `sources` is the loaded donor count.
    """
    counts = {
        'documents': len(meta),
        'legacy_candidates': 0,
        'skipped_private': 0,
        'skipped_discarded': 0,
        'skipped_imported': 0,
        'skipped_locked': 0,
        'skipped_other_source': 0,
        'skipped_not_completed': 0,
        'already_backfilled': 0,
        'live_v3': 0,
    }
    for raw in meta:
        if raw.get('deleted') or raw.get('sync_merged_into'):
            continue
        if raw.get('v3_backfill_run'):
            counts['already_backfilled'] += 1
        elif raw.get('recording') or raw.get('v3_derived'):
            counts['live_v3'] += 1
        elif raw.get('source') not in store.BACKFILL_SOURCES:
            counts['skipped_other_source'] += 1
        elif raw.get('status') != 'completed':
            counts['skipped_not_completed'] += 1
        elif raw.get('data_protection_level') == 'private':
            counts['skipped_private'] += 1
        elif raw.get('discarded'):
            counts['skipped_discarded'] += 1
        elif raw.get('imported'):
            counts['skipped_imported'] += 1
        elif raw.get('is_locked'):
            counts['skipped_locked'] += 1
        elif store.backfill_legacy_source(raw):
            counts['legacy_candidates'] += 1
    return counts


def _usd(tokens_in, tokens_out):
    return tokens_in / 1e6 * INPUT_USD_PER_MILLION + tokens_out / 1e6 * OUTPUT_USD_PER_MILLION


def estimate_partition(uid, partition, run_id, *, rederive=False, now=None):
    """Read-only: load the partition exactly as the builder will and price its model calls.

    Windows are known only after the outline, so each silence-bounded stretch is priced as one
    window: an upper bound on notes for split stretches is not attempted. Writes nothing.
    """
    now = now or datetime.now(timezone.utc)
    recordings, _existing, _cache = store.load_derive(
        uid, since=partition['since'], until=partition['until'], run_id=run_id, rederive=rederive
    )
    eligible = [r for r in recordings.values() if policy.builder_eligible(r)]
    groups = outline.stretches(eligible, now, max_window=timedelta(seconds=max_window_seconds()))
    est = {
        'sources': len(eligible),
        'stretches': len(groups),
        'outline_calls': len(groups),
        'notes_calls': 0,
        'agent_notes': 0,
        'short_task_calls': 0,
        'no_model_windows': 0,
        'manual_end_sources': sum(1 for r in eligible if r.get('v3_manual_end')),
        'wearer_labelled_sources': sum(
            1 for r in eligible if any(s.get('is_user') is True for s in r.get('transcript_segments') or [])
        ),
        'language_sources': sum(1 for r in eligible if r.get('language')),
        'words': 0,
        'usd': 0.0,
    }
    for group in groups:
        words = planner.word_count(group['lines'])
        est['words'] += words
        est['usd'] += _usd(OUTLINE_TOKENS['in'] + words * TOKENS_PER_WORD, OUTLINE_TOKENS['out'])
        if words >= visibility.MIN_HOME_WORDS or (group.get('manual_end') and words > 0):
            est['notes_calls'] += 1
            if sum(len(line['text'].split()) for line in group['lines']) >= AGENT_MIN_WORDS:
                est['agent_notes'] += 1
                est['usd'] += AGENT_MAX_USD
            else:
                est['usd'] += _usd(NOTES_TOKENS['in'] + words * TOKENS_PER_WORD, NOTES_TOKENS['out'])
        elif words >= MIN_TASK_WORDS:
            est['short_task_calls'] += 1
            est['usd'] += _usd(SHORT_TASKS_TOKENS['in'] + words * TOKENS_PER_WORD, SHORT_TASKS_TOKENS['out'])
        else:
            est['no_model_windows'] += 1
    return est


def new_run_id(now=None):
    now = now or datetime.now(timezone.utc)
    return now.strftime('%Y%m%dT%H%M%SZ') + '-' + os.urandom(3).hex()


def create_run(
    uid,
    *,
    since,
    until,
    mode,
    operator,
    code_sha,
    partitions,
    estimate,
    counts,
    historical_sitdown=False,
    run_id=None,
    firestore_client=None,
):
    """Write the planned run and its start marker; the sweep starts it when the switch is on."""
    run_id = run_id or new_run_id()
    record = {
        'mode': mode,
        'since': since,
        'until': until,
        'operator': operator,
        'code_sha_planned': code_sha,
        'partitions': partitions,
        'estimate': estimate,
        'counts': counts,
        'forced_cuts': sum(1 for p in partitions if p.get('forced_cut')),
    }
    if historical_sitdown:
        if mode != LIVE_MODE or record['forced_cuts']:
            raise Conflict('rederive_live_timing')
        record['historical_timing'] = list(HISTORICAL_SITDOWN_TIMING)
    if not runs.create_run(uid, run_id, record, firestore_client=firestore_client):
        raise ValueError('backfill_run_exists')
    runs.mark_start(uid, run_id, firestore_client=firestore_client)
    return run_id


def _task_id(uid, run_id, index, phase, seq, gen):
    owner = hashlib.sha256(uid.encode()).hexdigest()[:16]
    return f'conversations-v3-backfill-{owner}-{run_id}-g{gen}-{index}-{phase}-{seq}'


def enqueue_step(uid, run_id, index, phase='derive', seq=0, gen=0, *, schedule_at=None):
    """Named per run, resume generation, partition, phase and drain sequence: a redelivery dedupes."""
    enqueue_named_task(
        os.getenv('CONVERSATIONS_V3_BACKFILL_QUEUE', DEFAULT_QUEUE),
        task_base() + '/v1/conversations-v3/backfill',
        _task_id(uid, run_id, index, phase, seq, gen),
        {'uid': uid, 'run_id': run_id, 'partition': index, 'phase': phase},
        schedule_at=schedule_at,
    )


def next_partition(run):
    partitions = run.get('partitions') or []
    return next((i for i, p in enumerate(partitions) if p.get('status') != 'committed'), None)


def resume_run(uid, run_id, *, firestore_client=None):
    """Re-arm a stalled (retries exhausted), blocked or never-started run from its first unfinished partition."""
    resumable = {'planned', 'running', 'blocked'}
    run = runs.get_run(uid, run_id, firestore_client=firestore_client)
    if run is None or run.get('status') not in resumable:
        return {'outcome': 'not_resumable', 'status': (run or {}).get('status')}
    index = next_partition(run)
    if index is None:
        return {'outcome': 'nothing_left'}
    part = (run.get('partitions') or [])[index]
    updated = runs.update_run(
        uid,
        run_id,
        status='planned',
        partition=(index, {'status': 'pending'}) if part.get('status') == 'blocked' else None,
        patch={'resumes': int(run.get('resumes') or 0) + 1},
        expect=resumable,
        firestore_client=firestore_client,
    )
    if not updated:
        return {'outcome': 'not_resumable'}
    if run.get('mode') == LIVE_MODE:
        # A partition's attempt re-checks the rows it loads; this also reaches copies of rows gone since.
        rederive_store.drop_stale_priors(uid, run_id, firestore_client=firestore_client)
    runs.mark_start(uid, run_id, firestore_client=firestore_client)
    return {'outcome': 'resumed', 'partition': index}


async def start_planned():
    """Sweep hook: dispatch the first partition of planned runs. Inert while the switch is off."""
    from config.conversations_v3 import backfill_enabled

    if not backfill_enabled():
        return 0
    started = 0
    try:
        starts = await run_blocking(db_executor, runs.pending_starts, STARTS_PER_SWEEP)
    except Exception as error:
        logger.warning('event=v3_backfill_start outcome=retry exception_type=%s', type(error).__name__)
        return 0
    for start in starts:
        uid, run_id = start['uid'], start['run_id']
        try:
            run = await run_blocking(db_executor, runs.get_run, uid, run_id)
            index = next_partition(run) if run and run.get('status') == 'planned' else None
            if run is not None and index is not None:
                gen = int(run.get('resumes') or 0)
                await run_blocking(db_executor, enqueue_step, uid, run_id, index, 'derive', 0, gen)
                started += 1
            await run_blocking(db_executor, runs.clear_start, uid, run_id)
        except Exception as error:
            # The marker stays for the next sweep; a backfill dispatch fault never fails the live sweep.
            logger.warning('event=v3_backfill_start outcome=retry exception_type=%s', type(error).__name__)
    return started


async def run_step(uid, run_id, index, phase):
    """One task: derive a partition (once) and drain its notes; chain the next step."""
    deadline = time.monotonic() + STEP_SECONDS
    run = await run_blocking(db_executor, runs.get_run, uid, run_id)
    if run is None:
        return {'outcome': 'unknown_run'}
    if run.get('status') in runs.STOPPED:
        return {'outcome': run['status']}
    partitions = run.get('partitions') or []
    if not 0 <= index < len(partitions):
        return {'outcome': 'unknown_partition'}
    part = partitions[index]
    # The copies this partition recorded (its ledger, or this step's report once it derives).
    prior_ids = part.get('prior_ids')
    gen = int(run.get('resumes') or 0)
    active = {'planned', 'running'}
    sha = os.getenv('OMI_BACKEND_RELEASE_SHA', '')
    if phase == 'derive' and part.get('status') in {'pending', 'deriving'}:
        historical_timing = run.get('historical_timing')
        if not await run_blocking(
            db_executor,
            runs.update_run,
            uid,
            run_id,
            status='running',
            partition=(index, {'status': 'deriving', 'code_sha': sha}),
            expect=active,
        ):
            return {'outcome': 'stopped'}
        report = {}
        outcome = await service.reconcile(
            uid,
            derive=True,
            since=_utc(part['since']),
            until=_utc(part['until']),
            run_id=run_id,
            rederive=run.get('mode') == 'rederive',
            live=run.get('mode') == LIVE_MODE,
            historical_timing=historical_timing,
            internal_end=index + 1 < len(partitions),
            report=report,
        )
        if outcome == 'busy':
            raise BackfillRetry('backfill_owner_busy')
        if outcome != 'committed':
            await run_blocking(
                db_executor,
                runs.update_run,
                uid,
                run_id,
                status='blocked',
                partition=(index, {'status': 'blocked', 'reason': report.get('blocked_reason') or outcome}),
                expect=active,
            )
            return {'outcome': 'blocked', 'reason': report.get('blocked_reason') or outcome}
        await run_blocking(
            db_executor,
            runs.update_run,
            uid,
            run_id,
            partition=(index, {'status': 'notes', **report}),
            expect=active,
        )
        part = {**part, 'status': 'notes'}
        prior_ids = report.get('prior_ids')
    if part.get('status') == 'committed' and run.get('status') in active:
        # Redelivery after the commit: the successor's dispatch may have failed. Its name is fixed, so
        # dispatching again is a no-op when it already went out.
        successor = next_partition(run)
        if successor is not None and partitions[successor].get('status') == 'pending':
            await run_blocking(db_executor, enqueue_step, uid, run_id, successor, 'derive', 0, gen)
        return {'outcome': 'committed', 'redelivered': True}
    if part.get('status') != 'notes':
        return {'outcome': part.get('status')}

    async def keep_going():
        current = await run_blocking(db_executor, runs.get_run, uid, run_id)
        return bool(current) and current.get('status') not in runs.STOPPED

    drained = await service.drain_backfill(
        uid, deadline=deadline, after=part.get('notes_scan_after'), keep_going=keep_going
    )
    fields = {
        'notes_processed': int(part.get('notes_processed') or 0) + drained['processed'],
        'notes_failed': int(part.get('notes_failed') or 0) + drained['failed'],
        'notes_remaining': drained['remaining'],
    }
    previous_seq = int(part.get('drain_seq') or 0)
    if drained['remaining']:
        seq = previous_seq + 1
        if 'scan_after' in drained:
            fields['notes_scan_after'] = drained['scan_after']
        if not await run_blocking(
            db_executor,
            runs.update_run,
            uid,
            run_id,
            partition=(index, {**fields, 'drain_seq': seq}),
            expect=active,
            expected_drain_seq=previous_seq,
        ):
            return {'outcome': 'stopped', 'remaining': drained['remaining']}
        # Keep the partition open through handback without rapid task churn when all debt is foreign.
        schedule = {}
        if not drained.get('scan_pending') and drained.get('ownership_blocked') == drained['remaining']:
            schedule['schedule_at'] = int(time.time()) + OWNERSHIP_RECHECK_SECONDS
        await run_blocking(db_executor, enqueue_step, uid, run_id, index, 'drain', seq, gen, **schedule)
        return {'outcome': 'draining', 'remaining': drained['remaining']}
    last = index + 1 >= len(partitions)
    if run.get('mode') == LIVE_MODE:
        # The partition's notes are settled: anything that changes these rows from here on is not the
        # run's, and undo refuses to overwrite it.
        await run_blocking(db_executor, rederive_store.record_baselines, uid, run_id, prior_ids)
    if not await run_blocking(
        db_executor,
        runs.update_run,
        uid,
        run_id,
        status='committed' if last else None,
        partition=(index, {**fields, 'status': 'committed'}),
        expect=active,
        expected_drain_seq=previous_seq,
    ):
        return {'outcome': 'stopped', 'remaining': 0}
    if not last:
        await run_blocking(db_executor, enqueue_step, uid, run_id, index + 1, 'derive', 0, gen)
    return {'outcome': 'committed', 'last': last}


def _undo_refused(uid, run_id, reason, firestore_client):
    runs.update_run(
        uid,
        run_id,
        patch={'undo': {'outcome': 'busy', 'reason': reason, 'at': datetime.now(timezone.utc)}},
        firestore_client=firestore_client,
    )
    return {'outcome': 'busy', 'reason': reason}


def _kept_by_deletion(donors, derived, kept):
    """Close the owner's deletions over the run: rows linked to a kept donor stay, and so do their donors.

    Restoring a donor the owner deleted a copy of would resurrect it; deleting a sibling copy that
    shares a kept donor would drop the rest of that speech from Home. Both stay as backfilled v3.
    """
    links = {d['id']: {c.get('conversation_id') for c in d.get('claims') or []} for d in donors}
    kept_donors, kept_rows = set(kept) & set(links), set()
    while True:
        rows = {
            r['id']
            for r in derived
            if kept_donors & set(r.get('v3_recording_ids') or [])
            or any(r['id'] in links.get(cid, ()) for cid in kept_donors)
        }
        more = {rid for r in derived if r['id'] in rows for rid in r.get('v3_recording_ids') or []}
        more = (more & set(links)) | {cid for cid, claimed in links.items() if claimed & rows}
        if rows <= kept_rows and more <= kept_donors:
            return kept_donors, kept_rows
        kept_rows |= rows
        kept_donors |= more


def undo_run(uid, run_id, *, firestore_client=None):
    """Restore every legacy donor of a run exactly and remove its derived rows.

    Undo holds both the backfill and the live builder leases, so no pass commits (or stamps another
    row with this run) while it enumerates, restores and deletes. Donors are restored before copies
    are removed, so an interrupted undo can show a duplicate, never hide a conversation; it is
    idempotent and simply rerun. A donor whose backfilled copy the owner deleted is kept converted,
    with the copies it shares, so undo never resurrects a deletion; the ledger counts them.
    """
    run = runs.get_run(uid, run_id, firestore_client=firestore_client)
    if run is None:
        return {'outcome': 'unknown_run'}
    if run.get('mode') == LIVE_MODE:
        return undo_live_run(uid, run_id, firestore_client=firestore_client)
    if run.get('mode') == 'rederive':
        # A re-derive keeps each row's original run stamp; undo that run to remove its rows.
        return {'outcome': 'undo_the_original_run'}
    # 'undoing' is written first so in-flight drains stop (keep_going); a refusal records why.
    runs.update_run(uid, run_id, status='undoing', firestore_client=firestore_client)
    held = []
    try:
        for key, reason in ((store.BACKFILL_LEASE, 'backfill_pass_in_flight'), ('builder', 'live_builder_in_flight')):
            token = leases.acquire(uid, key, firestore_client=firestore_client)
            if token is None:
                return _undo_refused(uid, run_id, reason, firestore_client)
            held.append((key, token))
        token = held[0][1]

        def renew():
            for key, held_token in held:
                leases.renew(uid, key, held_token, firestore_client=firestore_client)

        docs = store.backfill_run_documents(uid, run_id, firestore_client=firestore_client)
        derived = [d for d in docs if d.get('v3_derived')]
        donors = [d for d in docs if not d.get('v3_derived')]
        if any(leases.held(uid, 'summary-' + d['id'], firestore_client=firestore_client) for d in derived):
            return _undo_refused(uid, run_id, 'notes_in_flight', firestore_client)
        kept_donors, kept_rows = _kept_by_deletion(
            donors, derived, {d['id'] for d in donors if store.deleted_after_backfill(d)}
        )
        restored = 0
        restore = [d['id'] for d in donors if d['id'] not in kept_donors]
        for start in range(0, len(restore), store.BACKFILL_UNDO_PAGE):
            count, late = store.restore_backfill_donors(
                uid, token, restore[start : start + store.BACKFILL_UNDO_PAGE], firestore_client=firestore_client
            )
            restored += count
            if late:
                # Deleted while undo ran: keep it and every copy it shares.
                kept_donors, kept_rows = _kept_by_deletion(donors, derived, kept_donors | set(late))
            renew()
        removed = 0
        remove = [d['id'] for d in derived if d['id'] not in kept_rows]
        for start in range(0, len(remove), store.BACKFILL_UNDO_PAGE):
            removed += store.delete_backfill_rows(
                uid, token, remove[start : start + store.BACKFILL_UNDO_PAGE], firestore_client=firestore_client
            )
            renew()
    finally:
        for key, held_token in held:
            leases.release(uid, key, held_token, firestore_client=firestore_client)
    result = {
        'donors_restored': restored,
        'rows_removed': removed,
        'donors_kept_deleted': len(kept_donors),
        'rows_kept_deleted': len(kept_rows),
    }
    runs.update_run(
        uid,
        run_id,
        status='undone',
        patch={'undo': {**result, 'at': datetime.now(timezone.utc)}},
        firestore_client=firestore_client,
    )
    return {'outcome': 'undone', **result}


# ---- live re-derive -------------------------------------------------------------------------------


def classify_live_window(meta):
    """Counts for the operator before a live re-derive: what the window holds, by metadata only."""
    counts = {
        'documents': len(meta),
        'live_sources': 0,
        'live_rows': 0,
        'live_rows_visible': 0,
        'backfilled_rows': 0,
        'legacy_rows': 0,
        'deleted': 0,
    }
    for raw in meta:
        if raw.get('deleted') or raw.get('sync_merged_into'):
            counts['deleted'] += 1
        elif raw.get('recording') and not raw.get('v3_derived'):
            counts['live_sources'] += 1
        elif raw.get('v3_derived') and raw.get('backfilled') and not raw.get('v3_rederive_live_run'):
            counts['backfilled_rows'] += 1
        elif raw.get('v3_derived'):
            counts['live_rows'] += 1
            counts['live_rows_visible'] += 0 if raw.get('home_hidden') else 1
        else:
            counts['legacy_rows'] += 1
    return counts


def estimate_live_partition(uid, partition, run_id, *, now=None, historical_sitdown=False, internal_end=False):
    """Read-only preview of one live re-derive partition. Writes nothing and calls no model.

    Before counts are exact. After counts come from the real planner with one window per stretch
    (each stretch outlined as a single conversation), so ``windows_after`` is the fewest windows the
    run can make; the outline can split a stretch into more windows (each with at least 150 words, or
    the manual-end window), which adopt more rows, so the run retires at most about
    ``rows_retired_est`` (eligible rows minus the windows that adopt one). Spend is priced
    like a backfill: one outline per stretch, plus notes or tasks for every window after.
    """
    now = now or datetime.now(timezone.utc)
    recordings, existing, _cache, counts = rederive_store.load_live_rederive(
        uid, since=partition['since'], until=partition['until'], run_id=run_id
    )
    eligible = [r for r in recordings.values() if policy.builder_eligible(r)]
    if historical_sitdown:
        groups = service.historical_stretches(
            eligible, now, since=partition['since'], until=partition['until'], internal_end=internal_end
        )
    else:
        groups = outline.stretches(eligible, now, max_window=timedelta(seconds=max_window_seconds()))
    protected = {cid for cid, row in existing.items() if row.get('_v3_protected')}
    outlines = [outline.fallback(group) for group in groups]
    if historical_sitdown:
        ownership = planner.Ownership(existing, recordings)
        planned = planner.windows(
            groups,
            outlines,
            cohesion=True,
            silence_gap=timedelta(seconds=HISTORICAL_SITDOWN_TIMING[0]),
            defer_topic_lock=True,
            ownership=ownership,
        )
        windows = planner.preserve_finished_windows(
            planned, existing, recordings, protect_provisional=True, ownership=ownership
        )
    else:
        windows = planner.preserve_finished_windows(
            planner.windows(groups, outlines, cohesion=stretch_cohesion_enabled()), existing, recordings
        )
    # Retained windows belong to protected rows, which the run never writes.
    fresh = [w for w in windows if w.get('existing_id') not in protected]
    est = {
        'sources': len(eligible),
        'stretches': len(groups),
        'open_stretches': sum(1 for g in groups if not g['finished']),
        'rows_eligible': counts.get('rows_eligible', 0),
        'visible_before': counts.get('visible_before', 0),
        'windows_after': len(fresh),
        'visible_after': 0,
        'rows_retired_est': max(0, counts.get('rows_eligible', 0) - _adopting(fresh, existing, protected)),
        'protected': sum(v for k, v in counts.items() if k.startswith('protected_')),
        'sources_blocked': sum(v for k, v in counts.items() if k.startswith('sources_blocked_')),
        # A rebuilt window past the partition's edge blocks the run (rederive_live_boundary).
        'windows_crossing_edge': sum(
            1
            for w in fresh
            if w['lines'][0]['start'] < partition['since'] or w['lines'][-1]['end'] > partition['until']
        ),
        'outline_calls': len(groups),
        'notes_calls': 0,
        'agent_notes': 0,
        'short_task_calls': 0,
        'words': 0,
        'usd': 0.0,
    }
    for key, value in counts.items():
        if key.startswith(('protected_', 'sources_', 'skipped_')):
            est[key] = value
    for group in groups:
        words = planner.word_count(group['lines'])
        est['words'] += words
        est['usd'] += _usd(OUTLINE_TOKENS['in'] + words * TOKENS_PER_WORD, OUTLINE_TOKENS['out'])
    for window in fresh:
        own = planner.word_count(window['lines'])
        words = window.get('_stretch_words', own)
        manual = bool(window.get('manual_end'))
        hidden = window['finished'] and not manual and words < visibility.MIN_HOME_WORDS
        est['visible_after'] += 0 if hidden else 1
        if own >= visibility.MIN_HOME_WORDS or (manual and own > 0):
            est['notes_calls'] += 1
            if sum(len(line['text'].split()) for line in window['lines']) >= AGENT_MIN_WORDS:
                est['agent_notes'] += 1
                est['usd'] += AGENT_MAX_USD
            else:
                est['usd'] += _usd(NOTES_TOKENS['in'] + own * TOKENS_PER_WORD, NOTES_TOKENS['out'])
        elif own >= MIN_TASK_WORDS:
            est['short_task_calls'] += 1
            est['usd'] += _usd(SHORT_TASKS_TOKENS['in'] + own * TOKENS_PER_WORD, SHORT_TASKS_TOKENS['out'])
    return est


def _adopting(windows, existing, protected):
    """How many windows adopt an eligible row's id (service._match: earliest unused overlapping row)."""
    free = sorted(
        (row for cid, row in existing.items() if cid not in protected and row.get('started_at')),
        key=lambda row: row['started_at'],
    )
    used = set()
    for window in sorted(windows, key=lambda w: w['lines'][0]['start']):
        start, end = window['lines'][0]['start'], window['lines'][-1]['end']
        prior = next(
            (r for r in free if r['id'] not in used and r['started_at'] <= end and r['finished_at'] >= start), None
        )
        if prior is not None:
            used.add(prior['id'])
    return len(used)


def _undo_groups(priors):
    """Priors that share a source restore together, so each source gets its exact claim list back."""
    parent = {}

    def find(key):
        parent.setdefault(key, key)
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key

    for entry in priors:
        row = ('row', entry['id'])
        find(row)
        for rid in set(entry.get('sources') or []) | {c['recording_id'] for c in entry.get('claims') or []}:
            parent[find(('source', rid))] = find(row)
    groups = {}
    for entry in priors:
        groups.setdefault(find(('row', entry['id'])), []).append(entry)
    return list(groups.values())


def undo_live_run(uid, run_id, *, firestore_client=None):
    """Restore every row a live re-derive changed, created or retired, exactly, from its priors.

    Same fences as a backfill undo: both builder leases, no notes in flight. Each group of rows that
    shares a source restores in one transaction (rows and their sources' claims together), so an
    interrupted undo is simply rerun. Refuses while a newer live re-derive restamped one of the rows
    (undo that one first) or after the owner deleted a rebuilt row (restoring would resurrect it).
    """
    runs.update_run(uid, run_id, status='undoing', firestore_client=firestore_client)
    held = []
    heartbeats = ExitStack()
    try:
        for key, reason in ((store.BACKFILL_LEASE, 'backfill_pass_in_flight'), ('builder', 'live_builder_in_flight')):
            token = leases.acquire(uid, key, firestore_client=firestore_client)
            if token is None:
                return _undo_refused(uid, run_id, reason, firestore_client)
            held.append((key, token))
            heartbeats.enter_context(
                leases.keepalive(uid, key, token, firestore_client=firestore_client, max_seconds=None)
            )

        def renew():
            for key, held_token in held:
                leases.renew(uid, key, held_token, firestore_client=firestore_client)

        # Copies of rows the run never stamped (a stopped attempt) restore nothing; they go first.
        rederive_store.drop_stale_priors(uid, run_id, firestore_client=firestore_client)
        priors = runs.list_priors(uid, run_id, firestore_client=firestore_client)
        if any(leases.held(uid, 'summary-' + e['id'], firestore_client=firestore_client) for e in priors):
            return _undo_refused(uid, run_id, 'notes_in_flight', firestore_client)
        payload_costs = {}
        blocker = rederive_store.live_undo_blocker(
            uid, run_id, priors, firestore_client=firestore_client, payload_costs=payload_costs
        )
        groups = _undo_groups(priors)
        if not blocker and not all(
            rederive_store.undo_group_fits(group, payload_costs=payload_costs) for group in groups
        ):
            # Each group restores in one transaction; one too large would fail midway on every retry.
            blocker = 'undo_group_too_large'
        if blocker:
            return _undo_refused(uid, run_id, blocker, firestore_client)
        totals = {'rows_restored': 0, 'rows_removed': 0, 'sources_repaired': 0}
        for group in groups:
            # A stopped heartbeat or a taken-over token must fail before restoration begins.
            renew()
            result = rederive_store.undo_live_rederive(uid, held, run_id, group, firestore_client=firestore_client)
            totals['rows_restored'] += result['rows_restored']
            totals['sources_repaired'] += result['sources_repaired']
            for cid in result['created']:
                # Already hidden with no claims; the deletion helper also erases its child collections.
                conversations_db.delete_conversation(uid, cid)
                totals['rows_removed'] += 1
        # Restored exactly: the copies of the owner's rows are no longer needed, so none are kept.
        renew()
        runs.drop_priors(uid, run_id, [e['id'] for e in priors], firestore_client=firestore_client)
    except store.Conflict as error:
        if str(error) not in {
            'undo_newer_run_first',
            'owner_deleted_rebuilt_row',
            'owner_edited_rebuilt_row',
            'account_deletion',
            'undo_source_missing',
            'undo_created_row_has_tasks',
            'undo_group_too_large',
            'undo_payload_unavailable',
            'undo_source_changed',
            'lease_lost',
        }:
            raise
        return _undo_refused(uid, run_id, str(error), firestore_client)
    finally:
        heartbeats.close()
        for key, held_token in held:
            leases.release(uid, key, held_token, firestore_client=firestore_client)
    result = {**totals, 'priors': len(priors)}
    runs.update_run(
        uid,
        run_id,
        status='undone',
        patch={'undo': {**result, 'at': datetime.now(timezone.utc)}},
        firestore_client=firestore_client,
    )
    return {'outcome': 'undone', **result}
