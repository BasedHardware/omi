"""Per-owner v3 repair: plan, estimate, run and undo backfill runs.

A run re-derives one owner's legacy pendant/phone conversations in [since, until) through the live
v3 builder and notes path (service.reconcile(derive=True) and service._process). The operator plans
it (backend/scripts/conversations_v3_backfill.py), which writes the run ledger and a start marker;
the five-minute sweep starts it once CONVERSATIONS_V3_BACKFILL=on, and each partition then runs as a
task on the dedicated backfill queue, one at a time per owner. Undo restores the legacy rows exactly
and removes the derived copies. Runbook: backend/docs/runbooks/conversations-v3.md.
"""

import hashlib
import logging
import os
import time
from datetime import datetime, timezone

from database import conversations_v3 as store
from database import conversations_v3_backfill_runs as runs
from database import conversations_v3_leases as leases
from utils.cloud_tasks import enqueue_named_task
from utils.conversations.v3 import outline, policy, service
from utils.conversations.v3.triggers import task_base
from utils.executors import db_executor, run_blocking

logger = logging.getLogger(__name__)

# Rows per partition at plan time. A resumed or re-derived partition also loads its derived copies,
# and the loader refuses more than store.LIMIT (128) documents, so plan well under half of it.
PARTITION_ROWS = 48
# A step (outline pass plus notes) stops taking new notes work this long after it started; the
# route timeout and the Cloud Tasks dispatch deadline are both 25 minutes.
STEP_SECONDS = 20 * 60
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


def plan_partitions(meta, since, until, *, max_rows=PARTITION_ROWS):
    """Cut [since, until) into partitions of at most max_rows documents, at recorded silence.

    A cut is placed at the last gap of at least five minutes (outline.SILENCE, the live hard window
    boundary), so no live stretch spans two partitions. Only a gap-free run longer than max_rows is
    cut at its largest gap; that partition is marked forced_cut and the run reports the count.
    """
    rows = sorted((r for r in meta if r.get('started_at')), key=lambda r: _utc(r['started_at']))
    partitions, current, gaps = [], [], []
    end = None
    for row in rows:
        start = _utc(row['started_at'])
        gap = (start - end).total_seconds() if end is not None else float('inf')
        if len(current) >= max_rows:
            silent = [i for i in range(1, len(current)) if gaps[i] >= outline.SILENCE.total_seconds()]
            forced = not silent and gap < outline.SILENCE.total_seconds()
            if gap >= outline.SILENCE.total_seconds():
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
    groups = outline.stretches(eligible, now)
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
        words = sum(len(line['text'].split()) for line in group['lines'])
        est['words'] += words
        est['usd'] += _usd(OUTLINE_TOKENS['in'] + words * TOKENS_PER_WORD, OUTLINE_TOKENS['out'])
        if words >= 300 or (group.get('manual_end') and words > 0):
            est['notes_calls'] += 1
            if words >= AGENT_MIN_WORDS:
                est['agent_notes'] += 1
                est['usd'] += AGENT_MAX_USD
            else:
                est['usd'] += _usd(NOTES_TOKENS['in'] + words * TOKENS_PER_WORD, NOTES_TOKENS['out'])
        elif words >= 20:
            est['short_task_calls'] += 1
            est['usd'] += _usd(SHORT_TASKS_TOKENS['in'] + words * TOKENS_PER_WORD, SHORT_TASKS_TOKENS['out'])
        else:
            est['no_model_windows'] += 1
    return est


def new_run_id(now=None):
    now = now or datetime.now(timezone.utc)
    return now.strftime('%Y%m%dT%H%M%SZ') + '-' + os.urandom(3).hex()


def create_run(
    uid, *, since, until, mode, operator, code_sha, partitions, estimate, counts, run_id=None, firestore_client=None
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
    if not runs.create_run(uid, run_id, record, firestore_client=firestore_client):
        raise ValueError('backfill_run_exists')
    runs.mark_start(uid, run_id, firestore_client=firestore_client)
    return run_id


def _task_id(uid, run_id, index, phase, seq, gen):
    owner = hashlib.sha256(uid.encode()).hexdigest()[:16]
    return f'conversations-v3-backfill-{owner}-{run_id}-g{gen}-{index}-{phase}-{seq}'


def enqueue_step(uid, run_id, index, phase='derive', seq=0, gen=0):
    """Named per run, resume generation, partition, phase and drain sequence: a redelivery dedupes."""
    enqueue_named_task(
        os.getenv('CONVERSATIONS_V3_BACKFILL_QUEUE', DEFAULT_QUEUE),
        task_base() + '/v1/conversations-v3/backfill',
        _task_id(uid, run_id, index, phase, seq, gen),
        {'uid': uid, 'run_id': run_id, 'partition': index, 'phase': phase},
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
    gen = int(run.get('resumes') or 0)
    active = {'planned', 'running'}
    sha = os.getenv('OMI_BACKEND_RELEASE_SHA', '')
    if phase == 'derive' and part.get('status') in {'pending', 'deriving'}:
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

    drained = await service.drain_backfill(uid, deadline=deadline, keep_going=keep_going)
    fields = {
        'notes_processed': int(part.get('notes_processed') or 0) + drained['processed'],
        'notes_failed': int(part.get('notes_failed') or 0) + drained['failed'],
        'notes_remaining': drained['remaining'],
    }
    if drained['remaining']:
        seq = int(part.get('drain_seq') or 0) + 1
        if not await run_blocking(
            db_executor,
            runs.update_run,
            uid,
            run_id,
            partition=(index, {**fields, 'drain_seq': seq}),
            expect=active,
        ):
            return {'outcome': 'stopped', 'remaining': drained['remaining']}
        await run_blocking(db_executor, enqueue_step, uid, run_id, index, 'drain', seq, gen)
        return {'outcome': 'draining', 'remaining': drained['remaining']}
    last = index + 1 >= len(partitions)
    if await run_blocking(
        db_executor,
        runs.update_run,
        uid,
        run_id,
        status='committed' if last else None,
        partition=(index, {**fields, 'status': 'committed'}),
        expect=active,
    ):
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
