"""Independent repair coordinator; private row inputs, aggregate outputs only.

Each row uses a disposable process. A stuck SDK/native call cannot consume a
slot indefinitely or share cloud clients with another row. Only an encrypted
maintenance frontier persists; no planner/apply semantics are reimplemented here.
"""

from collections import Counter, deque
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

from config import record_seal_repair as config
from utils.batch_pipeline.record_seal_reasons import PROOF_REASONS, TAIL_GAP_BUCKETS

MAX_ROWS = 1024
MAX_SCAN = 10000
DISPOSITIONS = frozenset(
    {
        'eligible',
        'sealed',
        'sealed_registered',
        'already_registered',
        'already_closed',
        'not_pending',
        'not_batch_owned',
        'upload_failed',
        'upload_failed_cleared',
        'upload_pending',
        'not_completed',
        'privacy_refused',
        'proof_refused',
        'read_error',
        'write_error',
        'state_changed',
        'unavailable',
        'budget_exhausted',
        'error',
        'unknown',
        'deferred',
        'disabled',
    }
)


@contextmanager
def silent_dependencies():
    """Also suppress native SDK output; never store provider errors or inputs."""
    logging.disable(logging.CRITICAL)
    sys.stdout.flush()
    sys.stderr.flush()
    saved = [os.dup(1), os.dup(2)]
    try:
        with open(os.devnull, 'wb') as sink:
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
        yield
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved[0], 1)
        os.dup2(saved[1], 2)
        for fd in saved:
            os.close(fd)


def repair_one(store, storage, artifacts, path, *, flags, inventory, budget, mode='apply', reason_out=None):
    """Fresh proof for every row, singleton canonical plan and same-digest apply."""
    from utils.batch_pipeline import record_seal_nojob as nojob, record_seal_repair as repair
    from utils.batch_pipeline.live import record_identity
    from utils.batch_pipeline.record_seal_sweeper import require_fresh_proof

    budget.check()
    proof = inventory()
    require_fresh_proof(proof)  # Required even for token-free rows.
    uid, cid = nojob.conversation_path(path)
    _, job_id = record_identity(uid, cid)
    job = store.run(lambda tx: tx.get('jobs', job_id))
    budget.check()
    plan: dict[str, Any]
    if job:
        plan = repair.plan_seals(
            store,
            [job_id],
            storage,
            artifacts,
            producer_proof=proof,
            check_budget=budget.check,
            repair_upload_failed=True,
        )
        apply = repair.apply_seals
    else:
        plan = nojob.plan_backfill(
            store, [path], storage, artifacts, server_flags=flags, producer_proof=proof, repair_upload_failed=True
        )
        apply = nojob.apply_backfill
    budget.check()
    entries = plan.get('entries', [])
    if len(entries) != 1:
        return 'unknown'
    disposition = entries[0].get('disposition')
    if reason_out is not None and entries[0].get('trimmed_divergent_overlaps'):
        reason_out['trimmed_divergent_overlaps'] = entries[0]['trimmed_divergent_overlaps']
    if disposition == 'proof_refused' and reason_out is not None:
        reason = entries[0].get('proof_reason')
        reason_out['proof_reason'] = reason if reason in PROOF_REASONS else 'other'
        if reason == 'tail_lagging':
            bucket = entries[0].get('tail_gap_bucket')
            reason_out['tail_gap_bucket'] = bucket if bucket in TAIL_GAP_BUCKETS else 'negative_or_unknown'
    if disposition != 'eligible' or mode == 'plan':
        return disposition if disposition in DISPOSITIONS else 'unknown'
    require_fresh_proof(proof)  # Tail downloads can exhaust the five-minute inventory window.
    budget.check()
    result = apply(store, plan, plan['plan_sha256'])
    if sum(result.values()) != 1 or len(result) != 1:
        return 'unknown'
    disposition = next(iter(result))
    return disposition if disposition in DISPOSITIONS else 'unknown'


def discover(
    client, *, budget, after=None, max_rows=MAX_ROWS, max_scan=MAX_SCAN, advance_rows=MAX_ROWS, selected_cursors=None
):
    """Page past closed rows; oldest finished first within each bounded pass.

    Both owners use the canonical record identity. Sync rows without a job are
    refused by the existing no-job planner (which only registers batch_live).
    Projection excludes transcript/content. Bounds are reported, never treated
    as an empty-backlog proof.
    """
    from google.cloud.firestore_v1 import FieldFilter

    rows, scanned, cursor = [], 0, after
    # Freeze each pass's upper finish boundary. Continuous newer inflow must
    # not prevent wrap and indefinitely starve the oldest refused rows.
    horizon = (after or {}).get('horizon') or datetime.now(timezone.utc)
    resume = None
    while scanned < max_scan and len(rows) < max_rows:
        budget.check()
        query = (
            client.collection_group('conversations')
            .where(filter=FieldFilter('record_lane_owner', 'in', ['batch_live_v1', 'batch_sync_v1']))
            .where(filter=FieldFilter('status', '==', 'completed'))
            .where(filter=FieldFilter('finished_at', '<=', horizon))
            .order_by('finished_at')
            .order_by('__name__')
            .select(('finished_at', 'record_audio_closed'))
            .limit(min(128, max_scan - scanned))
        )
        if cursor is not None:
            query = query.start_after(
                {'finished_at': cursor['finished_at'], '__name__': client.document(cursor['path'])}
            )
        page = list(query.stream(timeout=budget.timeout(), retry=None))
        budget.check()
        if not page:
            cursor = None  # Full pass exhausted: revisit refused rows on wrap.
            break
        for doc in page:
            scanned += 1
            data = doc.to_dict() or {}
            finished = data.get('finished_at')
            cursor = {'path': doc.reference.path, 'finished_at': finished, 'horizon': horizon}
            if not data.get('record_audio_closed') and isinstance(finished, datetime) and finished.tzinfo is not None:
                rows.append((doc.reference.path, max(0, int(time.time() - finished.timestamp()))))
                if selected_cursors is not None:
                    selected_cursors[doc.reference.path] = cursor
                if len(rows) <= advance_rows:
                    resume = cursor
                if len(rows) == max_rows:
                    break
        if len(page) < 128 and len(rows) < max_rows and scanned < max_scan:
            cursor = None
            break
    # Only the first worker group is guaranteed a turn before a global deadline.
    # Never wrap past a larger selected-but-deferred tail, even at end of scan.
    return rows, scanned >= max_scan or len(rows) >= max_rows, resume if len(rows) > advance_rows else cursor


class RowProcess(subprocess.Popen):
    """Own the row's session, including any ffmpeg decoder descendants."""

    def kill(self) -> None:
        try:
            os.killpg(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def launch_row(path, seconds, mode):
    script = Path(__file__).resolve().parents[2] / 'scripts/record_seal_repair_job.py'
    process = RowProcess(
        [sys.executable, str(script), '--row'],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    stdin = process.stdin
    if stdin is None:
        stop(process)
        raise RuntimeError('row input pipe unavailable')
    try:
        payload = json.dumps({'path': path, 'seconds': seconds, 'mode': mode}).encode()
        stdin.write(payload)
        stdin.close()
    except BaseException:
        stop(process)
        stdin.close()
        raise
    return process


def stop(process):
    # Also reap decoder descendants if the row leader already exited.
    process.kill()
    process.wait()
    process.stdout.close()


def coordinate(
    rows,
    *,
    workers,
    row_seconds,
    run_seconds,
    mode,
    launch=launch_row,
    clock=time.monotonic,
    pause=time.sleep,
    progress=lambda _: None,
    attempted=lambda _: None,
):
    """Bound total concurrency and wall time; reap every child, including on failure."""
    pending, active, counts, reasons = deque(rows), [], Counter(), Counter()
    gaps = Counter()
    started = clock()
    deadline = started + run_seconds
    max_age, sealed_age = 0, 0
    try:
        while pending or active:
            now = clock()
            if now >= deadline:
                counts['deferred'] += len(pending)
                pending.clear()
            while pending and len(active) < workers and now < deadline:
                path, age = pending.popleft()
                attempted(path)
                max_age = max(max_age, age)
                seconds = min(row_seconds, deadline - now)
                try:
                    process = launch(path, seconds, mode)
                    active.append((process, now + seconds, age))
                except Exception:
                    counts['error'] += 1
            for process, expires, age in active[:]:
                disposition = None
                reason = 'other'
                gap = 'negative_or_unknown'
                trimmed = 0
                if process.poll() is not None:
                    try:
                        payload = process.stdout.read(1025)
                        result = json.loads(payload) if len(payload) <= 1024 else {}
                        candidate = result.get('trimmed_divergent_overlaps', 0)
                        trimmed = candidate if type(candidate) is int and 0 <= candidate <= 4096 else 0
                        disposition = result.get('disposition')
                        candidate = result.get('proof_reason')
                        reason = candidate if candidate in PROOF_REASONS else 'other'
                        candidate = result.get('tail_gap_bucket')
                        gap = candidate if candidate in TAIL_GAP_BUCKETS else 'negative_or_unknown'
                    except Exception:
                        disposition = 'error'
                    if process.returncode != 0 or disposition not in DISPOSITIONS:
                        disposition = 'error'
                elif clock() >= expires:
                    disposition = 'budget_exhausted'
                if disposition:
                    stop(process)
                    active.remove((process, expires, age))
                    counts[disposition] += 1
                    if disposition == 'proof_refused':
                        reasons[reason] += 1
                        if reason == 'tail_lagging':
                            gaps[gap] += 1
                    age += max(0, int(clock() - started))
                    sealed = disposition in {'sealed', 'sealed_registered', 'upload_failed_cleared'}
                    if sealed:
                        sealed_age = max(sealed_age, age)
                    progress(
                        {
                            'event': 'record_seal_repair_row',
                            'count': 1,
                            'trimmed_divergent_overlaps': trimmed,
                            'disposition': disposition,
                            'seal_age_seconds': age if sealed else 0,
                            **({'proof_reason': reason} if disposition == 'proof_refused' else {}),
                            **(
                                {'tail_gap_bucket': gap}
                                if disposition == 'proof_refused' and reason == 'tail_lagging'
                                else {}
                            ),
                        }
                    )
            if active:
                pause(0.05)
    finally:
        for process, _, _ in active:
            stop(process)
    return {
        'dispositions': dict(sorted(counts.items())),
        'proof_reasons': dict(sorted(reasons.items())),
        'tail_gap_buckets': dict(sorted(gaps.items())),
        'rows': sum(counts.values()),
        'oldest_unsealed_seconds': max_age,
        'oldest_seal_age_seconds': sealed_age,
    }


def row_main(payload):
    from utils.batch_pipeline.record_seal_budget import BudgetExhausted, SweepBudget

    result = 'error'
    reason = {}
    try:
        if not config.enabled():
            return {'disposition': 'disabled'}
        config.require_runtime()
        if not 0 < payload['seconds'] <= 270 or payload['mode'] not in {'plan', 'apply'}:
            raise ValueError('invalid row controls')
        with silent_dependencies():
            from database.batch_pipeline_store import FirestoreStore
            from utils.batch_pipeline.artifact_policy import artifacts_for
            from utils.batch_pipeline.record_seal_sweeper import read_pusher_pod_proof
            from utils.other.local_storage import create_storage_client

            budget = SweepBudget(payload['seconds'])
            with budget.interrupt_io():
                store = FirestoreStore('batch_pipeline_prod')
                result = repair_one(
                    store,
                    create_storage_client(),
                    artifacts_for(store),
                    payload['path'],
                    flags=config.server_flags(),
                    inventory=read_pusher_pod_proof,
                    budget=budget,
                    mode=payload['mode'],
                    reason_out=reason,
                )
    except BudgetExhausted:
        result = 'budget_exhausted'
    except Exception:
        pass
    return {'disposition': result, **reason}


def run(*, progress=lambda _: None):
    if not config.enabled():
        return {'event': 'record_seal_repair', 'outcome': 'disabled'}
    workers, row_seconds, run_seconds, mode = config.settings()
    config.require_runtime()
    with silent_dependencies():
        from database._client import get_firestore_client
        from utils.batch_pipeline.record_seal_budget import SweepBudget
        from utils.batch_pipeline.record_seal_repair_cursor import RepairCursor
        from utils.batch_pipeline.record_seal_sweeper import read_pusher_pod_proof, require_fresh_proof

        config.server_flags()  # No cloud access if the explicit policy map is absent.
        require_fresh_proof(read_pusher_pod_proof())
        budget = SweepBudget(60)
        with budget.interrupt_io():
            client = get_firestore_client()
            frontier = RepairCursor(client, config.cursor_secret())
            selected_cursors = {}
            rows, saturated, cursor = discover(
                client,
                budget=budget,
                after=frontier.read(budget),
                advance_rows=workers,
                selected_cursors=selected_cursors,
            )
            # Advance before slow proofs: refused, hung, deferred or killed rows
            # cannot monopolize the next run. Wrap revisits them on a later pass.
            # A preview never writes even this maintenance frontier.
            if mode == 'apply':
                frontier.write(cursor, budget)
    last_attempted = None

    def attempted(path):
        nonlocal last_attempted
        last_attempted = selected_cursors[path]

    report = coordinate(
        rows,
        workers=workers,
        row_seconds=row_seconds,
        run_seconds=run_seconds,
        mode=mode,
        progress=progress,
        attempted=attempted,
    )
    if mode == 'apply' and last_attempted:
        # Preserve exact Firestore nanoseconds, not an age reconstructed clock.
        # The second point write (lead ruling 4cbd2a) advances past ALL attempts,
        # never past a deferred row. Initial checkpoint survives interruption;
        # end-of-pass wrap revisits even the oldest chronic/interrupted row.
        budget = SweepBudget(30)
        with silent_dependencies(), budget.interrupt_io():
            frontier.write(last_attempted, budget)
    return {'event': 'record_seal_repair', 'outcome': 'ok', 'mode': mode, 'discovery_saturated': saturated, **report}
