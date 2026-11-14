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
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any

from google.api_core.exceptions import FailedPrecondition
from google.cloud.firestore_v1 import FieldFilter

from utils.batch_pipeline import record_seal_profile
from config import refactor_modes
from config import record_seal_repair as config
from config import record_partial as partial_config
from config.record_audio import record_identity
from config import record_seal_rules as lease
from database import record_custody_receipts
from database.batch_pipeline_store import promote_record_recoveries
from utils.batch_pipeline.record_producer_proof import leases_would_release
from database.firestore_read_origin import read_origin
from database.record_partial import finish_partial
from utils.batch_pipeline.record_seal_reasons import PROOF_REASONS, TAIL_GAP_BUCKETS
from utils.observability.firestore_probe_export import collect_child_probe, launch_with_probe, REPAIR_OLDEST
from utils.observability.fallback import record_fallback

MAX_ROWS = 1024
MAX_SCAN = 10000
CUSTODY_MAINTENANCE_SECONDS = 30  # Per phase, independent of the audio-repair budget.
# Final day of the stored 14-day barrier deadline gets priority over recency.
NEAR_DEAD_LETTER_SECONDS = 86400
_age_order_index_warned = False
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
        'partial_eligible',
        'partial_finished',
        'already_partial',
        'not_aged',
        'byok_refused',
        'missing_cancel_eligible',
        'missing_cancelled',
        'missing_cancelled_fenced',
    }
)


def valid_metric_clock(started):
    """Finite positive clock for metrics and stored urgent-deadline validation."""
    return (
        isinstance(started, (int, float)) and not isinstance(started, bool) and math.isfinite(started) and started > 0
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

    record_seal_profile.enter('proof')
    budget.check()
    uid, cid = nojob.conversation_path(path)
    _, job_id = record_identity(uid, cid)
    job = store.run(lambda tx: tx.get('jobs', job_id))
    budget.check()
    row = store.run(lambda tx: tx.get('conversations', f'{uid}/{cid}'))
    budget.check()
    if row.get('record_audio_partial') and not job.get('partial_coordinator'):
        from database.batch_pipeline_record_lease_recovery import recovery_segment

        continuation_id = recovery_segment(uid, cid)
        continuation = store.run(lambda tx: tx.get('jobs', continuation_id))
        if continuation.get('partial_coordinator'):
            job_id, job = continuation_id, continuation
    blocker = pending_blocker(row)
    if reason_out is not None:
        reason_out['blocker'] = blocker
    if job and not row and config.jobs_enabled():
        from database.record_pending_repair import cancel_missing

        record_seal_profile.enter('apply')
        return cancel_missing(store, uid, cid, now=time.time(), preview=mode == 'plan')
    partial = bool(job.get('partial_coordinator') or config.jobs_enabled() and row.get('record_audio_partial'))
    if partial:
        # Aged pending/retired barriers retry only with the rollback switch on
        # and fresh transactional proof; age never clears the barrier.
        if partial_config.partial_barrier(row) and (
            not config.jobs_enabled()
            or job.get('state') not in {'record_pending', 'partial_retired'}
            or not partial_config.repair_due(row, time.time())
        ):
            return 'already_partial'
    proof = inventory()
    require_fresh_proof(proof)  # Required for every attempted seal or rearm.
    if partial:
        if (
            reason_out is not None
            and lease.token_lease_mode() == 'shadow'
            and leases_would_release(
                row.get('record_upload_sessions'),
                proof,
                uid=uid,
                row=row,
                job=job,
            )
        ):
            reason_out['lease_reason'] = 'lease_would_expire'
        if reason_out is not None:
            reason = job.get('partial_reason')
            reason_out['partial_reason'] = reason if reason in partial_config.REASONS else 'tail_lost_or_unproven'
        record_seal_profile.enter('apply')
        return finish_partial(
            store,
            path,
            reason='tail_lagging',
            proof=proof,
            now=time.time(),
            preview=mode == 'plan',
            retry_aged=config.jobs_enabled(),
        )
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
            repair_closed=True,
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
    if reason_out is not None and entries[0].get('lease_reason') == 'lease_would_expire':
        reason_out['lease_reason'] = 'lease_would_expire'
    if (
        not row.get('record_audio_closed')
        and partial_config.enabled()
        and (
            disposition == 'proof_refused'
            and entries[0].get('proof_reason') in partial_config.REASONS
            or disposition == 'read_error'
            and entries[0].get('proof_reason') == 'budget_limit'
        )
    ):
        require_fresh_proof(proof)
        record_seal_profile.enter('apply')
        partial_result = finish_partial(
            store,
            path,
            reason=entries[0]['proof_reason'],
            proof=proof,
            now=time.time(),
            preview=mode == 'plan',
            register=lambda tx, uid, cid, row: nojob.registration(tx, uid, cid, row, flags),
        )
        if partial_result != 'not_aged':
            if reason_out is not None:
                reason_out['partial_reason'] = entries[0]['proof_reason']
            return partial_result
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
    record_seal_profile.enter('apply')
    result = apply(store, plan, plan['plan_sha256'])
    if sum(result.values()) != 1 or len(result) != 1:
        return 'unknown'
    disposition = next(iter(result))
    return disposition if disposition in DISPOSITIONS else 'unknown'


def settled(data):
    """Rows a repair attempt can only refuse until their state changes.

    A recent valid partial barrier is repair's `already_partial`; a deleted, discarded
    or sync-disabled row is `privacy_refused`. Both used to take a worker slot
    on every pass (207 of 208 attempts in prod 2026-11-04), so the cursor
    crawled while recent stuck captures waited. Any change to the mark, upload
    revision or privacy fields makes the row eligible again on the next pass.
    """
    if data.get('deleted') or data.get('discarded') or data.get('private_cloud_sync_enabled') is False:
        return True
    return (
        bool(data.get('record_audio_partial'))
        and partial_config.partial_barrier(data)
        and (not config.jobs_enabled() or not partial_config.repair_due(data, time.time()))
    )


def discover(
    client, *, budget, after=None, max_rows=MAX_ROWS, max_scan=MAX_SCAN, advance_rows=MAX_ROWS, selected_cursors=None
):
    """Page past closed rows; newest finished first within each bounded pass.

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
    resume = after
    while scanned < max_scan and len(rows) < max_rows:
        budget.check()
        query = (
            client.collection_group('conversations')
            .where(filter=FieldFilter('record_lane_owner', 'in', ['batch_live_v1', 'batch_sync_v1']))
            .where(filter=FieldFilter('status', '==', 'completed'))
            .where(filter=FieldFilter('finished_at', '<=', horizon))
            .order_by('finished_at', direction='DESCENDING')
            .order_by('__name__', direction='DESCENDING')
            .select(
                (
                    'finished_at',
                    'record_audio_closed',
                    'record_audio_partial',
                    'record_upload_revision',
                    'deleted',
                    'discarded',
                    'private_cloud_sync_enabled',
                )
            )
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
            if (
                (not data.get('record_audio_closed') or data.get('record_audio_partial'))
                and isinstance(finished, datetime)
                and finished.tzinfo is not None
                and not settled(data)
            ):
                stamp = finished.timestamp()
                age = max(0, int(time.time() - stamp)) if valid_metric_clock(stamp) else None
                rows.append((doc.reference.path, age))
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


BLOCKERS = frozenset(
    {
        'partial_barrier',
        'producer_pending_tokens',
        'upload_failed',
        'already_closed_job_pending',
        'conversation_missing',
        'seal_eligible',
    }
)


def pending_blocker(row):
    if not row:
        return 'conversation_missing'
    if row.get('record_audio_partial'):
        return 'partial_barrier'
    if row.get('record_upload_sessions'):
        return 'producer_pending_tokens'
    if row.get('record_upload_failed'):
        return 'upload_failed'
    if row.get('record_audio_closed'):
        return 'already_closed_job_pending'
    return 'seal_eligible'


@read_origin('job:record_seal_cluster_repair:discover_jobs')
def discover_jobs(
    client,
    *,
    budget,
    after=None,
    max_rows=8,
    max_scan=128,
    selected_cursors=None,
    progress=lambda _: None,
    metric_ages=None,
    urgent=False,
    invalid_clock_counts=None,
):
    """Newest pending jobs, or earliest near-dead-letter deadline, with bounded cursors.

    Missing/non-finite/non-numeric enqueue clocks were already ineligible in
    the name scan; the age query does not remove any eligible record. Keep the
    local age/identity filters in both modes. Never use mutable available_at.
    """
    global _age_order_index_warned
    if not 1 <= max_rows <= MAX_ROWS or not 1 <= max_scan <= MAX_SCAN:
        raise ValueError('invalid jobs discovery limits')
    budget.check()
    age_order = refactor_modes.record_seal_repair_age_order()
    if urgent and not age_order:
        return [], False, None
    order_field = 'record_dead_letter_deadline_at' if urgent else 'enqueued_at'
    hash_after = after if after and 'enqueued_at' not in after else None
    # A cursor from the other ordering cannot be resumed safely. Restart at
    # that order's head (also upgrades the legacy hash frontier without loss).
    if after and ('enqueued_at' in after) != age_order:
        after = None
    # Deadline order can safely expand its tail as new rows enter the final day.
    # Recency passes freeze their head so continuous inflow cannot prevent wrap.
    horizon = (
        datetime.now(timezone.utc)
        if urgent
        else (after or {}).get('horizon' if age_order else 'finished_at') or datetime.now(timezone.utc)
    )

    def page_for(age_order, after):
        budget.check()
        query = client.collection('batch_pipeline_prod_jobs').where(filter=FieldFilter('state', '==', 'record_pending'))
        if age_order:
            cutoff = horizon.timestamp() + (NEAR_DEAD_LETTER_SECONDS if urgent else 0)
            if urgent:
                query = query.where(filter=FieldFilter(order_field, '>', 0))
            query = query.where(filter=FieldFilter(order_field, '<=', cutoff)).order_by(
                order_field, direction='ASCENDING' if urgent else 'DESCENDING'
            )
        query = (
            query.order_by('__name__', direction='DESCENDING')
            if age_order and not urgent
            else query.order_by('__name__')
        )
        query = query.select(
            ('owner_id', 'conversation_id', 'enqueued_at', 'record_content_id')
            + (('record_dead_letter_deadline_at',) if urgent else ())
        ).limit(min(128, max_scan))
        if after:
            values = {'__name__': client.document(after['path'])}
            if age_order:
                values[order_field] = after['enqueued_at']
            query = query.start_after(values)
        return list(query.stream(timeout=budget.timeout(), retry=None))

    try:
        page = page_for(age_order, after)
    except FailedPrecondition as error:
        message = str(error).lower()
        if (
            urgent
            or not age_order
            or not (
                'requires an index' in message
                or ('index' in message and ('not ready' in message or 'building' in message))
            )
        ):
            raise
        if not _age_order_index_warned:
            _age_order_index_warned = True
            record_fallback(
                component='firestore_read',
                from_mode='record_seal_age_order',
                to_mode='record_seal_hash_order',
                reason='other',
                outcome='degraded',
            )
            # The coordinator suppresses dependency logging; its explicit
            # aggregate channel remains visible. Never emit the SDK message.
            progress({'event': 'record_seal_repair_age_order', 'outcome': 'missing_index_hash_order'})
        age_order = False
        # An age cursor's position has no meaning in hash order.
        horizon = (hash_after or {}).get('finished_at') or datetime.now(timezone.utc)
        page = page_for(False, hash_after)
    budget.check()
    rows, cursor = [], None
    for doc in page:
        budget.check()
        job = doc.to_dict() or {}
        uid, cid, enqueued = job.get('owner_id'), job.get('conversation_id'), job.get('enqueued_at')
        # Checkpoint every examined query position before eligibility checks:
        # a malformed page must not pin later urgent jobs. Frontiers are separate.
        cursor = (
            {'path': doc.reference.path, 'enqueued_at': job.get(order_field), 'horizon': horizon}
            if age_order
            else {'path': doc.reference.path, 'finished_at': horizon}
        )
        if urgent and not valid_metric_clock(job.get(order_field)):
            if invalid_clock_counts is not None:
                invalid_clock_counts['invalid_clock_rows'] += 1
            continue
        if not isinstance(uid, str) or not uid or '/' in uid or not isinstance(cid, str) or not cid or '/' in cid:
            continue
        if doc.id != record_identity(uid, cid)[1] or not job.get('record_content_id'):
            continue
        if not isinstance(enqueued, (int, float)) or isinstance(enqueued, bool) or not math.isfinite(enqueued):
            continue
        if urgent:
            deadline = job.get(order_field)
            if (
                not isinstance(deadline, (int, float))
                or not valid_metric_clock(deadline)
                or deadline > horizon.timestamp() + NEAR_DEAD_LETTER_SECONDS
            ):
                continue
        age = horizon.timestamp() - enqueued
        if age < config.JOBS_MIN_AGE_SECONDS:
            continue
        path = f'users/{uid}/conversations/{cid}'
        # Preserve selection/cursors even for zero or negative clocks. Only the metric is absent.
        rows.append((path, max(0, int(age)) if valid_metric_clock(enqueued) else None))
        # Keep invalid-clock jobs eligible and preserve their exact cursor.
        # Only the exported gauge excludes them; future clocks already fail
        # the unchanged minimum-age check above.
        if metric_ages is not None and valid_metric_clock(enqueued):
            metric_ages.append(max(0, int(age)))
        if selected_cursors is not None:
            selected_cursors[path] = cursor
        if len(rows) >= max_rows:
            return rows, True, cursor
    saturated = len(page) >= min(128, max_scan)
    return rows, saturated, cursor if saturated else None


class RowProcess(subprocess.Popen):
    """Own the row's session, including any ffmpeg decoder descendants."""

    def kill(self) -> None:
        try:
            os.killpg(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def launch_row(path, seconds, mode):
    script = Path(__file__).resolve().parents[2] / 'scripts/record_seal_repair_job.py'
    started = time.monotonic()
    process = launch_with_probe(
        RowProcess,
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
        payload = json.dumps({'path': path, 'seconds': seconds, 'mode': mode, 'started': started}).encode()
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
    collect_child_probe(process)
    process.stdout.close()


class RowOutput:
    """Drain bounded JSON lines without waiting for a live child to close stdout."""

    def __init__(self, process):
        self.process, self.buffer = process, b''
        self.result: dict[str, Any] = {}
        self.profile: dict[str, Any] = {'stage': 'unknown'}
        self.oversized = False
        try:
            self.fd = process.stdout.fileno()
            os.set_blocking(self.fd, False)
        except (AttributeError, OSError):
            self.fd = None  # In-memory/old child adapters are read after exit only.

    def accept(self, line):
        try:
            value = json.loads(line)
            if not isinstance(value, dict):
                return
            if 'disposition' in value:
                self.result = value
            stage = value.get('stage')
            if isinstance(stage, str) and stage in record_seal_profile.STAGES:
                self.profile['stage'] = stage
            timings = value.get('stage_ms', {})
            if isinstance(timings, dict):
                self.profile['stage_ms'] = {
                    key: val
                    for key, val in timings.items()
                    if key in record_seal_profile.STAGES and type(val) is int and 0 <= val <= 3600000
                }
            for key in ('chunks', 'bytes', 'metadata_reloads'):
                val = value.get(key)
                if type(val) is int and 0 <= val <= 2**53:
                    self.profile[key] = val
        except (ValueError, TypeError):
            pass

    def drain(self, finished=False):
        # A row sends only stage transitions and its final result. Bound work and
        # memory even if an unexpected dependency writes to the private pipe.
        for _ in range(16):
            try:
                data = (
                    os.read(self.fd, 1025)
                    if self.fd is not None
                    else (self.process.stdout.read(1025) if finished else b'')
                )
            except BlockingIOError:
                break
            if not data:
                break
            for part in data.splitlines(keepends=True):
                self.buffer += part
                self.oversized |= len(self.buffer.rstrip(b'\n')) > 1024
                if part.endswith(b'\n'):
                    if not self.oversized:
                        self.accept(self.buffer)
                    self.buffer, self.oversized = b'', False
                elif self.oversized:
                    self.buffer = b''
        if finished and self.buffer:
            if not self.oversized:
                self.accept(self.buffer)
            self.buffer = b''


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
    gaps, partial_reasons, blocker_outcomes = Counter(), Counter(), Counter()
    started = clock()
    deadline = started + run_seconds
    max_age, sealed_age, invalid_clock_rows = 0, 0, 0
    elapsed_by_disposition = Counter()
    try:
        while pending or active:
            now = clock()
            if now >= deadline:
                counts['deferred'] += len(pending)
                if pending:
                    elapsed_by_disposition['deferred'] += 0
                pending.clear()
            while pending and len(active) < workers and now < deadline:
                path, age = pending.popleft()
                attempted(path)
                if age is None:
                    invalid_clock_rows += 1
                else:
                    max_age = max(max_age, age)
                seconds = min(row_seconds, deadline - now)
                try:
                    process = launch(path, seconds, mode)
                    active.append((process, now + seconds, age, now, RowOutput(process)))
                except Exception:
                    counts['error'] += 1
                    elapsed_by_disposition['error'] += max(0, round((clock() - now) * 1000))
            for process, expires, age, row_started, output in active[:]:
                finished = process.poll() is not None
                output.drain(finished)
                disposition = None
                reason = 'other'
                gap = 'negative_or_unknown'
                blocker = None
                trimmed = 0
                lease_reason = None
                partial_reason = 'tail_lost_or_unproven'
                if finished:
                    try:
                        result = output.result
                        candidate = result.get('trimmed_divergent_overlaps', 0)
                        trimmed = candidate if type(candidate) is int and 0 <= candidate <= 4096 else 0
                        disposition = result.get('disposition')
                        if result.get('lease_reason') == 'lease_would_expire':
                            lease_reason = 'lease_would_expire'
                        candidate = result.get('blocker')
                        blocker = candidate if candidate in BLOCKERS else None
                        candidate = result.get('proof_reason')
                        reason = candidate if candidate in PROOF_REASONS else 'other'
                        candidate = result.get('tail_gap_bucket')
                        gap = candidate if candidate in TAIL_GAP_BUCKETS else 'negative_or_unknown'
                        candidate = result.get('partial_reason')
                        partial_reason = candidate if candidate in partial_config.REASONS else 'tail_lost_or_unproven'
                    except Exception:
                        disposition = 'error'
                    if process.returncode != 0 or not isinstance(disposition, str) or disposition not in DISPOSITIONS:
                        disposition = 'error'
                elif clock() >= expires:
                    disposition = 'budget_exhausted'
                if disposition:
                    row_elapsed = max(0, round((clock() - row_started) * 1000))
                    stop(process)
                    active.remove((process, expires, age, row_started, output))
                    elapsed_by_disposition[disposition] += row_elapsed
                    counts[disposition] += 1
                    if blocker:
                        blocker_outcomes[f'{blocker}:{disposition}'] += 1
                    if disposition == 'partial_finished':
                        partial_reasons[partial_reason] += 1
                    if disposition == 'proof_refused':
                        reasons[reason] += 1
                        if reason == 'tail_lagging':
                            gaps[gap] += 1
                    if age is not None:
                        age += max(0, int(clock() - started))
                    sealed = disposition in {'sealed', 'sealed_registered', 'upload_failed_cleared'}
                    if sealed and age is not None:
                        sealed_age = max(sealed_age, age)
                    progress(
                        {
                            'event': 'record_seal_repair_row',
                            'elapsed_ms': row_elapsed,
                            **output.profile,
                            'count': 1,
                            **({'blocker': blocker} if blocker else {}),
                            'trimmed_divergent_overlaps': trimmed,
                            'disposition': disposition,
                            **({'lease_reason': lease_reason} if lease_reason else {}),
                            **({'partial_reason': partial_reason} if disposition == 'partial_finished' else {}),
                            **({'seal_age_seconds': age if sealed else 0} if age is not None else {}),
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
        for process, *_ in active:
            stop(process)
    return {
        'dispositions': dict(sorted(counts.items())),
        'disposition_elapsed_ms': dict(sorted(elapsed_by_disposition.items())),
        'proof_reasons': dict(sorted(reasons.items())),
        'tail_gap_buckets': dict(sorted(gaps.items())),
        'partial_finishes': dict(sorted(partial_reasons.items())),
        'blocker_outcomes': dict(sorted(blocker_outcomes.items())),
        'rows': sum(counts.values()),
        'oldest_unsealed_seconds': max_age,
        'oldest_seal_age_seconds': sealed_age,
        'invalid_clock_rows': invalid_clock_rows,
    }


def row_main(payload, *, progress=lambda _: None):
    profile = record_seal_profile.RowProfile(payload.get('started', time.monotonic()), progress)
    profile.enter('clients')
    from utils.batch_pipeline.record_seal_budget import BudgetExhausted, SweepBudget

    result = 'error'
    reason = {}
    try:
        if not config.enabled():
            return {'disposition': 'disabled', **profile.snapshot()}
        config.require_runtime()
        if not 0 < payload['seconds'] <= 270 or payload['mode'] not in {'plan', 'apply'}:
            raise ValueError('invalid row controls')
        with silent_dependencies(), profile.install():
            from database.batch_pipeline_store import FirestoreStore
            from utils.batch_pipeline.artifact_policy import artifacts_for
            from utils.batch_pipeline.record_seal_sweeper import read_pusher_pod_proof
            from utils.other.local_storage import create_storage_client

            budget = SweepBudget(payload['seconds'])
            with budget.interrupt_io():
                store = FirestoreStore('batch_pipeline_prod')
                storage = create_storage_client()
                artifacts = artifacts_for(store, storage_client=storage)
                result = repair_one(
                    store,
                    storage,
                    artifacts,
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
    return {'disposition': result, **reason, **profile.snapshot()}


def run(*, progress=lambda _: None):
    if not config.enabled():
        return {'event': 'record_seal_repair', 'outcome': 'disabled'}
    workers, row_seconds, run_seconds, mode = config.settings()
    config.require_runtime()
    with silent_dependencies():
        from database._client import get_firestore_client
        from utils.batch_pipeline.record_seal_budget import BudgetExhausted, SweepBudget
        from utils.batch_pipeline.record_seal_repair_cursor import RepairCursor
        from utils.batch_pipeline.record_seal_sweeper import read_pusher_pod_proof, require_fresh_proof

        config.server_flags()  # No cloud access if the explicit policy map is absent.
        require_fresh_proof(read_pusher_pod_proof())
        budget = SweepBudget(60)
        with budget.interrupt_io():
            client = get_firestore_client()
            frontier = RepairCursor(client, config.cursor_secret())
            selected_cursors, job_cursors = {}, {}
            job_rows, jobs_saturated, jobs_cursor = [], False, None
            job_metric_ages = []
            jobs_frontier, urgent_frontier = None, None
            urgent_rows, urgent_cursors, urgent_cursor = [], {}, None
            invalid_clock_counts = Counter()
            if config.jobs_enabled():
                jobs_frontier = RepairCursor(client, config.cursor_secret(), jobs=True)
                allocation = max(1, workers // 2)
                # Scan ordinary jobs every run, even under continuous urgency.
                job_rows, jobs_saturated, jobs_cursor = discover_jobs(
                    client,
                    budget=budget,
                    after=jobs_frontier.read(budget),
                    max_rows=allocation,
                    selected_cursors=job_cursors,
                    progress=progress,
                    metric_ages=job_metric_ages,
                )
                ordinary_reserve = min(len(job_rows), max(1, allocation // 4))
                if refactor_modes.record_seal_repair_age_order() and allocation > ordinary_reserve:
                    urgent_frontier = RepairCursor(client, config.cursor_secret(), jobs=True, urgent=True)
                    try:
                        urgent_rows, urgent_saturated, urgent_cursor = discover_jobs(
                            client,
                            budget=budget,
                            after=urgent_frontier.read(budget),
                            max_rows=allocation - ordinary_reserve,
                            selected_cursors=urgent_cursors,
                            urgent=True,
                            invalid_clock_counts=invalid_clock_counts,
                            metric_ages=job_metric_ages,
                        )
                        jobs_saturated = jobs_saturated or urgent_saturated
                    except FailedPrecondition:
                        # Fail only the urgent leg; never emit the SDK message.
                        record_fallback(
                            component='firestore_read',
                            from_mode='record_seal_age_order',
                            to_mode='none',
                            reason='other',
                            outcome='degraded',
                        )
                        progress({'event': 'record_seal_repair_urgent', 'outcome': 'index_unavailable'})
                remaining = allocation - len(urgent_rows)
                job_rows = [(path, age) for path, age in job_rows if path not in urgent_cursors]
                if len(job_rows) > remaining:
                    jobs_saturated = True
                    # Candidates held for the next run must stay ahead of the
                    # ordinary frontier, even if discovery exhausted its page.
                    jobs_cursor = job_cursors[job_rows[remaining - 1][0]]
                    job_rows = job_rows[:remaining]
                job_cursors = {path: job_cursors[path] for path, _ in job_rows}
                # Keep the existing half-worker reservation for the conversation leg.
                job_rows = urgent_rows + job_rows
            rows, saturated, cursor = discover(
                client,
                budget=budget,
                after=frontier.read(budget),
                advance_rows=workers - len(job_rows),
                max_rows=MAX_ROWS - len(job_rows),
                max_scan=MAX_SCAN - (128 if jobs_frontier else 0) - (128 if urgent_frontier else 0),
                selected_cursors=selected_cursors,
            )
            # Advance before slow proofs: refused, hung, deferred or killed rows
            # cannot monopolize the next run. Wrap revisits them on a later pass.
            # A preview never writes even this maintenance frontier.
            if mode == 'apply':
                frontier.write(cursor, budget)
                if jobs_frontier:
                    jobs_frontier.write(jobs_cursor, budget)
                if urgent_frontier:
                    urgent_frontier.write(urgent_cursor, budget)
            metric_ages = job_metric_ages + [age for path, age in rows if age is not None and path not in job_cursors]
            rows = job_rows + [
                (path, age) for path, age in rows if path not in job_cursors and path not in urgent_cursors
            ]
            saturated = saturated or jobs_saturated
    # Reuse discovery's bounded, content-free age sample. No additional query
    # and no activation of the idle seal worker's scanner are needed.
    REPAIR_OLDEST.set(max(metric_ages, default=0))
    if mode == 'apply':
        # The checked-in production seal worker is idle. The active repair
        # CronJob must resume parked accepted bytes in off/shadow/serve too.
        try:
            with silent_dependencies():
                promotion_budget = SweepBudget(CUSTODY_MAINTENANCE_SECONDS)
                with promotion_budget.interrupt_io():
                    promoted = promote_record_recoveries(
                        client, 'batch_pipeline_prod', time.time(), budget=promotion_budget
                    )
            progress({'event': 'record_token_recovery_promotion', 'outcome': 'completed', 'promoted': promoted})
        except BudgetExhausted:
            progress({'event': 'record_token_recovery_promotion', 'outcome': 'budget_exhausted'})
        except Exception:
            progress({'event': 'record_token_recovery_promotion', 'outcome': 'error'})
        try:
            with silent_dependencies():
                expiry_budget = SweepBudget(CUSTODY_MAINTENANCE_SECONDS)
                with expiry_budget.interrupt_io():
                    expired = record_custody_receipts.prune(client, now=time.time(), budget=expiry_budget)
            progress(
                {
                    'event': 'record_custody_receipts_expiry',
                    'outcome': 'saturated' if expired >= record_custody_receipts.MAX_PER_RUN else 'completed',
                    'deleted': expired,
                }
            )
        except BudgetExhausted:
            progress({'event': 'record_custody_receipts_expiry', 'outcome': 'budget_exhausted'})
        except Exception:
            progress({'event': 'record_custody_receipts_expiry', 'outcome': 'error'})
    last_attempted, last_job_attempted, last_urgent_attempted = None, None, None

    def attempted(path):
        nonlocal last_attempted, last_job_attempted, last_urgent_attempted
        if path in urgent_cursors:
            last_urgent_attempted = urgent_cursors[path]
        elif path in job_cursors:
            last_job_attempted = job_cursors[path]
        else:
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
    report['invalid_clock_rows'] = report.get('invalid_clock_rows', 0) + invalid_clock_counts['invalid_clock_rows']
    if mode == 'apply' and (last_attempted or last_job_attempted or last_urgent_attempted):
        # Preserve exact Firestore nanoseconds, not an age reconstructed clock.
        # The second point write (lead ruling 4cbd2a) advances past ALL attempts,
        # never past a deferred row. Initial checkpoint survives interruption;
        # end-of-pass wrap revisits even the oldest chronic/interrupted row.
        budget = SweepBudget(30)
        with silent_dependencies(), budget.interrupt_io():
            if last_attempted:
                frontier.write(last_attempted, budget)
            if last_job_attempted and jobs_frontier is not None:
                jobs_frontier.write(last_job_attempted, budget)
            if last_urgent_attempted and urgent_frontier is not None:
                urgent_frontier.write(last_urgent_attempted, budget)
    return {'event': 'record_seal_repair', 'outcome': 'ok', 'mode': mode, 'discovery_saturated': saturated, **report}
