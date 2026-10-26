"""Durable dispatch and recovery for listen conversation finalization.

The Firestore job is the source of truth.  Cloud Tasks wakes a worker for
platform-key conversations; it is never allowed to carry content or BYOK
credentials.  BYOK jobs remain explicitly blocked until a live request again
presents its request-scoped keys.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timedelta, timezone
from functools import partial
from concurrent.futures import as_completed
from typing import Any

from google.api_core.exceptions import InvalidArgument
from prometheus_client import Counter, Gauge

from database import conversation_finalization_jobs as jobs_db
from database import conversation_quiet_checks as quiet_checks_db
from database._client import is_document_size_limit_error
from services.conversation_selfheal import STALE_AFTER, run_selfheal_tick
from utils.conversations import quiet_finalization
from utils.executors import quiet_replay_executor, submit_with_context
from utils.cloud_tasks import (
    enqueue_listen_finalization_job,
    get_listen_finalization_tasks_max_attempts,
    is_listen_finalization_dispatch_enabled,
)
from utils.metrics import (
    CONVERSATION_ORPHANED_UNFINALIZED,
    LISTEN_FINALIZATION_BYOK_ABANDONMENTS_TOTAL,
    LISTEN_FINALIZATION_DEAD_LETTER_TOTAL,
    LISTEN_FINALIZATION_DURABLE_JOBS,
    LISTEN_FINALIZATION_JOB_STATUS,
    LISTEN_FINALIZATION_OLDEST_NONTERMINAL_AGE_SECONDS,
    LISTEN_FINALIZATION_OLDEST_BLOCKED_BYOK_AGE_SECONDS,
    LISTEN_FINALIZATION_SUMMARY_LAST_SUCCESS_TIMESTAMP_SECONDS,
    LISTEN_FINALIZATION_RETRIES_TOTAL,
    LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL,
    register_listen_finalization_summary_metrics,
)
from utils.observability.fallback import record_fallback
from utils.observability.journeys import (
    record_capture_finalization_reconciliation,
    record_capture_finalization_terminal,
    record_conversation_finalization_client_terminal,
)

logger = logging.getLogger(__name__)

REPLAY_OLDEST_OVERDUE_AGE = Gauge(
    'listen_finalization_replay_oldest_overdue_age_seconds',
    'Age of the oldest overdue replay obligation; aggregate replicas with max(), not sum()',
    ['queue'],
)
REPLAY_OUTCOMES = Counter('listen_finalization_replay_outcomes_total', 'Finalization replay outcomes', ['outcome'])
# Closed literal labels keep aggregate outcome cardinality fixed.
REPLAY_OUTCOME_METRICS = {
    'requeued': REPLAY_OUTCOMES.labels(outcome='requeued'),
    'skipped': REPLAY_OUTCOMES.labels(outcome='skipped'),
    'enqueue_failed': REPLAY_OUTCOMES.labels(outcome='enqueue_failed'),
    'stale': REPLAY_OUTCOMES.labels(outcome='stale'),
    'no_progress': REPLAY_OUTCOMES.labels(outcome='no_progress'),
    'retired': REPLAY_OUTCOMES.labels(outcome='retired'),
    'advanced': REPLAY_OUTCOMES.labels(outcome='advanced'),
    'error': REPLAY_OUTCOMES.labels(outcome='error'),
}


def _skip_capture_wedge(**_: Any) -> dict[str, int]:
    """The API reconciler owns conversation GC, not user-notification nudges."""

    return {'nudged': 0, 'undeliverable': 0, 'errors': 0}


def reconcile_stale_in_progress_conversations(*, firestore_client: Any = None) -> dict[str, Any]:
    """Admit stale content-bearing ``in_progress`` rows to durable finalization.

    This is the always-on owner for the recovery primitive otherwise exposed by
    the optional conversation-selfheal job. It deliberately reuses that
    primitive's bounded scan, persisted CAS cursor, SERVER_RECOVERY admission
    fences, per-tick cap, and next-tick verification. Capture-wedge notification
    work remains owned by the dedicated job and is skipped here.
    """

    if not is_listen_finalization_dispatch_enabled():
        return {'scanned': 0, 'enqueued': 0, 'verified': 0, 'refused': 0, 'errors': 0, 'mode': 'off'}
    if not quiet_finalization.enabled():
        return run_selfheal_tick(
            firestore_client=firestore_client,
            mode='heal',
            dry_run=False,
            use_configured_uid_allowlist=False,
            wedge_runner=_skip_capture_wedge,
            stale_after=STALE_AFTER,
            content_due_scan=False,
        )
    result = run_selfheal_tick(
        firestore_client=firestore_client,
        mode='heal',
        dry_run=False,
        use_configured_uid_allowlist=False,
        wedge_runner=_skip_capture_wedge,
        stale_after=timedelta(minutes=5),
        content_due_scan=True,
        cursor_getter=partial(jobs_db.get_in_progress_content_sweep_cursor, quiet=True),
        cursor_advancer=partial(jobs_db.advance_in_progress_content_sweep_cursor, quiet=True),
    )
    CONVERSATION_ORPHANED_UNFINALIZED.inc(result.get('enqueued', 0))
    # The indexed fast path cannot see markerless photo/transcript rows and
    # deliberately refuses unknown leases. Keep their existing two-hour
    # recovery on its own cursor and previous five-minute scan cadence.
    legacy_cursor = jobs_db.get_in_progress_content_sweep_cursor(firestore_client=firestore_client)
    updated_at = legacy_cursor.get('updated_at')
    if isinstance(updated_at, datetime):
        updated_at = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - updated_at < timedelta(minutes=5):
            return result | {'legacy': {'mode': 'cooldown'}}
    legacy = run_selfheal_tick(
        firestore_client=firestore_client,
        mode='heal',
        dry_run=False,
        use_configured_uid_allowlist=False,
        wedge_runner=_skip_capture_wedge,
        stale_after=STALE_AFTER,
        content_due_scan=False,
    )
    CONVERSATION_ORPHANED_UNFINALIZED.inc(legacy.get('enqueued', 0))
    combined = result | {'legacy': legacy}
    for key in ('scanned', 'enqueued', 'verified', 'refused', 'errors'):
        combined[key] = int(result.get(key, 0)) + int(legacy.get(key, 0))
    return combined


def _reconcile_quiet_candidate(candidate: dict[str, Any], *, firestore_client: Any = None) -> str:
    """One independent transaction/admission chain; no shared executor children."""
    job_id = candidate['job_id']
    outcome = 'error'
    try:
        status = quiet_finalization.run(
            job_id, int(candidate['dispatch_generation']), firestore_client=firestore_client
        )
        if status == 'stale':
            outcome = 'stale'
        else:
            # Verify persisted progress rather than trusting a successful
            # return string: the incident's old counter did exactly that.
            current = jobs_db.get_finalization_job(job_id, firestore_client=firestore_client)
            if current is None or current.get('status') == 'quiet_done':
                outcome = 'retired'
            elif current.get('dispatch_generation') != candidate.get('dispatch_generation'):
                outcome = 'requeued' if status == 'queued' else 'advanced'
            else:
                outcome = 'no_progress'
    except Exception:
        logger.exception('quiet finalization reconciliation failed')
        try:
            quiet_checks_db.ensure_quiet_check_progress(job_id, firestore_client=firestore_client)
        except Exception:
            logger.exception('quiet finalization progress repair failed')
    if outcome in {'stale', 'no_progress', 'error'}:
        try:
            jobs_db.defer_finalization_replay(candidate, firestore_client=firestore_client)
        except Exception:
            logger.exception('quiet finalization replay backoff failed')
    return outcome


def reconcile_listen_finalization_jobs(
    limit: int | None = None, *, firestore_client: Any = None
) -> dict[str, int | float]:
    """Replay stale queued/leased platform-key jobs and publish backlog signals."""
    result: dict[str, int | float] = {
        'requeued': 0,
        'skipped': 0,
        'enqueue_failed': 0,
        'stale': 0,
        'no_progress': 0,
        'retired': 0,
        'advanced': 0,
        'error': 0,
    }
    try:
        recovery = jobs_db.recover_stranded_byok_jobs(firestore_client=firestore_client)
        if recovery['blocked']:
            logger.info('listen BYOK ownership reclaim: %s', recovery)
        if recovery['errors']:
            logger.error('listen BYOK ownership reclaim failed rows=%s', recovery['errors'])
    except Exception:
        logger.exception('listen BYOK ownership reclaim scan failed')
    if not is_listen_finalization_dispatch_enabled():
        _publish_job_metrics(firestore_client=firestore_client)
        return result

    oldest_overdue_age = 0.0
    try:
        oldest_overdue_age = jobs_db.get_finalization_replay_oldest_overdue_age_seconds(
            firestore_client=firestore_client
        )
        REPLAY_OLDEST_OVERDUE_AGE.labels(queue='conversation_finalization_jobs').set(oldest_overdue_age)
    except Exception:
        logger.exception('listen finalization overdue-age query failed')
    if limit is None:
        # A 100/min ceiling cannot recover when obligations arrive at 110/min.
        # Grow only while there is an aged backlog; explicit limits remain the
        # operator rollback and do not depend on a temporary revision env.
        default_limit = 500 if oldest_overdue_age >= 300 else 100
        try:
            limit = max(1, min(2000, int(os.getenv('LISTEN_FINALIZATION_RECONCILE_LIMIT', str(default_limit)))))
        except ValueError:
            limit = default_limit
    stale_after = jobs_db.get_finalization_reconcile_stale_after()
    try:
        candidates = jobs_db.get_finalization_replay_candidates(limit=limit, firestore_client=firestore_client)
    except Exception:
        logger.exception('listen finalization reconciliation query failed')
        _publish_job_metrics(firestore_client=firestore_client)
        return result | {'error': 1}

    quiet_candidates = [
        candidate
        for candidate in candidates
        if candidate.get('kind') == 'listen_quiet_check'
        and isinstance(candidate.get('job_id'), str)
        and candidate['job_id']
    ]
    if quiet_candidates:
        try:
            concurrency = max(1, min(16, int(os.getenv('LISTEN_QUIET_REPLAY_CONCURRENCY', '16'))))
        except ValueError:
            concurrency = 16
        # The synchronous FSR callback owns one db_executor slot. Its bounded
        # leaf pool never submits to that shared pool, so saturated shared DB
        # workers cannot deadlock this fan-out. Joining drains all in-flight
        # checks before the pass releases its FSR admission.
        if concurrency == 1 or len(quiet_candidates) == 1:
            for candidate in quiet_candidates:
                result[_reconcile_quiet_candidate(candidate, firestore_client=firestore_client)] += 1
        else:
            # Keep at most concurrency submissions outstanding, rather than
            # queueing the entire (up to 2000-row) page into the shared pool.
            remaining = iter(quiet_candidates)
            futures = set()
            try:
                for _ in range(min(concurrency, len(quiet_candidates))):
                    futures.add(
                        submit_with_context(
                            quiet_replay_executor,
                            _reconcile_quiet_candidate,
                            next(remaining),
                            firestore_client=firestore_client,
                        )
                    )
                while futures:
                    for future in as_completed(futures):
                        futures.remove(future)
                        result[future.result()] += 1
                        candidate = next(remaining, None)
                        if candidate is not None:
                            futures.add(
                                submit_with_context(
                                    quiet_replay_executor,
                                    _reconcile_quiet_candidate,
                                    candidate,
                                    firestore_client=firestore_client,
                                )
                            )
                        break
            finally:
                # Even a rejected submission cannot detach already-owned work.
                for future in as_completed(futures):
                    future.result()

    for candidate in candidates:
        try:
            job_id = candidate.get('job_id')
            if not isinstance(job_id, str) or not job_id:
                result['skipped'] += 1
                continue
            if candidate.get('kind') == 'conversation_merge':
                try:
                    from utils.conversations import lifecycle

                    lifecycle.merge_jobs.reconcile(job_id, firestore_client=firestore_client)
                    result['requeued'] += 1
                except Exception:
                    logger.warning('event=conversation_merge outcome=reconciliation_error')
                    result['enqueue_failed'] += 1
                continue
            if candidate.get('kind') == 'listen_quiet_check':
                continue
            try:
                claimed = jobs_db.claim_finalization_replay(
                    job_id,
                    stale_after=stale_after,
                    firestore_client=firestore_client,
                )
            except Exception:
                logger.exception('listen finalization reconciliation claim failed job=%s', job_id)
                result['skipped'] += 1
                continue
            if not claimed.get('created') or claimed['status'] != 'queued' or claimed['dispatch_generation'] is None:
                result['skipped'] += 1
                continue
            try:
                enqueue_listen_finalization_job(job_id, int(claimed['dispatch_generation']))
            except Exception:
                record_capture_finalization_reconciliation('enqueue_failed')
                record_fallback(
                    component='pusher',
                    from_mode='cloud_tasks',
                    to_mode='durable_queued',
                    reason='enqueue_failed',
                    outcome='degraded',
                    log=logger,
                )
                logger.exception('listen finalization reconciliation enqueue failed job=%s', job_id)
                result['enqueue_failed'] += 1
                continue
            result['requeued'] += 1
            record_capture_finalization_reconciliation('requeued')
            LISTEN_FINALIZATION_RETRIES_TOTAL.inc()
        finally:
            if (
                candidate.get('kind') != 'listen_quiet_check'
                and isinstance(candidate.get('job_id'), str)
                and candidate['job_id']
            ):
                try:
                    jobs_db.defer_finalization_replay(candidate, firestore_client=firestore_client)
                except Exception:
                    logger.exception('listen finalization replay backoff failed')

    for outcome, count in result.items():
        REPLAY_OUTCOME_METRICS[outcome].inc(count)
    if candidates:
        logger.info('event=listen_finalization_replay result=%s', result)

    _publish_job_metrics(firestore_client=firestore_client)
    return result


def reconcile_stale_processing_conversations(limit: int = 100, *, firestore_client: Any = None) -> dict[str, int]:
    """Close bare-`processing` conversations stranded by a synchronous-route crash.

    The durable replay sweep (``reconcile_listen_finalization_jobs``) only covers
    rows with a finalization job. A bare-`processing` row admitted by the
    synchronous legacy route (or a server/merge create) and then lost to a hard
    crash has no job, so it is never replayed and the recording never resolves.

    Eligibility is bounded by the authoritative, server-owned admission fence
    ``processing_admitted_at`` (never caller-controlled ``created_at``), so a live
    synchronous run whose admission is still under the conservative threshold can
    never be terminalized. A legacy row predating the fence is migrated by
    stamping the fence and deferred to a later sweep rather than completed on
    sight. Each aged orphan is driven through the truthful terminal ownership CAS
    (``complete_orphan_conversation``): a row already completed, discarded,
    superseded by a newer generation, or since bound to a durable job is fenced
    out, so the orphan reaches exactly one terminal and its recording stays
    retrievable. Re-enrichment is a separate follow-up; this safety net only ends
    the stuck lifecycle. It needs no durable dispatch, so it runs in every
    deployment mode.

    Eventual discovery is guaranteed by a persisted, rotated sweep cursor: each
    periodic invocation resumes a bounded window from the cursor and wraps to the
    top once the collection is exhausted, so a stable excluded prefix larger than
    the per-invocation bound cannot permanently hide a later orphan.

    Outcomes are recorded on ``LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL``
    (privacy-safe: aggregate counts only, no user identifiers in success logs).
    Unexpected per-row failures are counted as ``error``; an expected CAS fencing
    (the row moved on) is ``skipped``.
    """
    result: dict[str, int] = {'completed': 0, 'migrated': 0, 'skipped': 0, 'error': 0}
    stale_after = jobs_db.get_stale_processing_orphan_after()
    try:
        cursor = jobs_db.get_stale_processing_sweep_cursor(firestore_client=firestore_client)
    except Exception:
        logger.exception('stale processing sweep cursor read failed; sweeping from the top')
        cursor = {'resume_after_path': None, 'generation': 0}
    _path = cursor.get('resume_after_path')
    resume_after_path: str | None = _path if isinstance(_path, str) else None
    expected_generation: int = int(cursor.get('generation') or 0)
    try:
        sweep = jobs_db.get_stale_processing_orphan_candidates(
            stale_after=stale_after, limit=limit, resume_after_path=resume_after_path, firestore_client=firestore_client
        )
    except Exception:
        logger.exception('stale processing conversation reconciliation query failed')
        LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='error').inc()
        return result | {'error': 1}
    next_cursor = None if sweep['exhausted'] else sweep['resume_after_path']
    try:
        jobs_db.advance_stale_processing_sweep_cursor(
            expected_generation, next_cursor, firestore_client=firestore_client
        )
    except Exception:
        logger.exception('stale processing sweep cursor advance failed; coverage is still guaranteed')
    for candidate in sweep['candidates']:
        uid = candidate.get('uid')
        conversation_id = candidate.get('conversation_id')
        if not isinstance(uid, str) or not isinstance(conversation_id, str):
            result['skipped'] += 1
            LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='skipped').inc()
            continue
        try:
            if candidate.get('legacy'):
                # A stranded pre-fence row: stamp the server-owned admission
                # instant so a later sweep bounds recovery by admission age. Never
                # terminalize on first sight.  Only a successful stamp counts as
                # ``migrated``; a CAS loss (already stamped / status changed /
                # absent) is an expected ``skipped`` fencing, never a migration.
                try:
                    stamped = jobs_db.stamp_processing_admission_if_absent(
                        uid, conversation_id, firestore_client=firestore_client
                    )
                except InvalidArgument as error:
                    if not is_document_size_limit_error(error):
                        raise
                    # The row is at Firestore's 1 MiB document ceiling, so the
                    # fence can never be stamped: migration would fail on every
                    # future sweep and the conversation would stay `processing`
                    # for good. Terminalize it on the server-owned last-write
                    # instant instead — that shrinking write is the one update
                    # the document still accepts.
                    record_fallback(
                        component='pusher',
                        from_mode='admission_stamp',
                        to_mode='unstampable_terminal',
                        reason='other',
                        outcome='degraded',
                        log=logger,
                    )
                    if jobs_db.complete_unstampable_orphan_conversation(
                        uid, conversation_id, stale_after=stale_after, firestore_client=firestore_client
                    ):
                        result['completed'] += 1
                        LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='completed').inc()
                    else:
                        result['skipped'] += 1
                        LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='skipped').inc()
                    continue
                if stamped:
                    result['migrated'] += 1
                    LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='migrated').inc()
                else:
                    result['skipped'] += 1
                    LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='skipped').inc()
                continue
            completed = jobs_db.complete_orphan_conversation(
                uid,
                conversation_id,
                expected_admitted_at=candidate.get('processing_admitted_at'),
                firestore_client=firestore_client,
            )
        except Exception:
            # An unexpected per-row failure (e.g. Firestore unavailable) is an
            # error, distinct from an expected CAS fencing skip below.
            logger.exception('stale processing conversation reconciliation failed for one row')
            result['error'] += 1
            LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='error').inc()
            continue
        if completed:
            result['completed'] += 1
            LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='completed').inc()
        else:
            result['skipped'] += 1
            LISTEN_FINALIZATION_STALE_PROCESSING_RECONCILIATIONS_TOTAL.labels(outcome='skipped').inc()
    if result['completed'] or result['migrated']:
        logger.info('stale processing conversation reconciliation: %s', result)
    return result


def is_byok_abandonment_sweep_enabled() -> bool:
    """Gate the BYOK abandonment sweep; on by default.

    A resumed BYOK job is reachable by no consumer -- the Cloud Tasks worker
    refuses ``requires_byok`` and the reconciler filters on a
    ``reconcile_after_at`` those paths delete -- so leaving the sweep off does
    not hold the row in a recoverable state, it only defers its disposition
    while the conversation stays in ``processing``. There is also no
    environment that can rehearse it: dev holds zero BYOK jobs, so shipping
    this dark would buy delay rather than evidence. The bounded age in
    ``get_byok_abandoned_after`` is the real safety control; this switch exists
    to stop the sweep, not to stage it.
    """
    return os.getenv('LISTEN_FINALIZATION_BYOK_ABANDONMENT_ENABLED', 'true').strip().lower() in {
        '1',
        'true',
        'yes',
        'on',
    }


def _record_byok_abandonment_journey(job: dict[str, Any]) -> None:
    """Terminalize the journey for a job that will never be attempted again."""
    try:
        created_at = job.get('created_at')
        record_capture_finalization_terminal('failure', created_at if isinstance(created_at, datetime) else None)
        record_conversation_finalization_client_terminal('failure', job, issue_class='incomplete_attempt')
    except Exception:
        # The durable terminal is authoritative; a best-effort metric must never
        # change it.
        logger.exception('listen finalization byok abandonment metric failed')


def reconcile_abandoned_byok_finalization_jobs(limit: int = 100, *, firestore_client: Any = None) -> dict[str, int]:
    """Give stranded BYOK finalization jobs an owner and a truthful terminal.

    Prompt reclaim returns lost live-session ownership to ``blocked_byok`` so a
    reconnect can resume it. Waiting is bounded: this sweep covers queued,
    leased (without a live lease), and blocked_byok jobs whose last live activity
    exceeds ``get_byok_abandoned_after()``. Reclaim does not refresh that age.

    This sweep is **disposition and visibility only**. It never replays a BYOK
    finalization or substitutes platform credentials. Eligible jobs become
    ``dead_letter`` with the distinct ``byok_session_abandoned`` failure code;
    a still-bound ``processing`` conversation closes in the same transaction.
    Reconnect or claim changes to status, epoch, or activity fence stale scans.

    Work is bounded per invocation (fixed page size, capped scan) and eventual
    coverage comes from a persisted, rotated CAS cursor, exactly like the stale
    bare-``processing`` sweep. Terminal transitions move the projection shard
    deltas, so the metric source of truth stays correct.
    """
    result: dict[str, int] = {'abandoned': 0, 'conversations_closed': 0, 'skipped': 0, 'error': 0}
    if not is_byok_abandonment_sweep_enabled():
        return result

    abandoned_after = jobs_db.get_byok_abandoned_after()
    try:
        cursor = jobs_db.get_byok_abandonment_sweep_cursor(firestore_client=firestore_client)
    except Exception:
        logger.exception('byok abandonment sweep cursor read failed; sweeping from the top')
        cursor = {'resume_after_path': None, 'generation': 0}
    _path = cursor.get('resume_after_path')
    resume_after_path: str | None = _path if isinstance(_path, str) else None
    expected_generation = int(cursor.get('generation') or 0)

    try:
        sweep = jobs_db.get_abandoned_byok_job_candidates(
            abandoned_after=abandoned_after,
            limit=limit,
            resume_after_path=resume_after_path,
            firestore_client=firestore_client,
        )
    except Exception:
        logger.exception('byok abandonment query failed')
        LISTEN_FINALIZATION_BYOK_ABANDONMENTS_TOTAL.labels(outcome='error').inc()
        return result | {'error': 1}

    try:
        jobs_db.advance_byok_abandonment_sweep_cursor(
            expected_generation,
            None if sweep['exhausted'] else sweep['resume_after_path'],
            firestore_client=firestore_client,
        )
    except Exception:
        logger.exception('byok abandonment sweep cursor advance failed; coverage is still guaranteed')

    for candidate in sweep['candidates']:
        job_id = candidate.get('job_id')
        if not isinstance(job_id, str) or not job_id:
            result['skipped'] += 1
            LISTEN_FINALIZATION_BYOK_ABANDONMENTS_TOTAL.labels(outcome='skipped').inc()
            continue
        try:
            disposition = jobs_db.abandon_byok_finalization_job(
                job_id,
                expected_status=str(candidate.get('status') or ''),
                expected_dispatch_generation=int(candidate.get('dispatch_generation') or 1),
                expected_lease_epoch=int(candidate.get('lease_epoch') or 0),
                abandoned_after=abandoned_after,
                firestore_client=firestore_client,
            )
        except Exception:
            # An unexpected per-row failure is an error, distinct from the
            # expected CAS fencing skip below.
            logger.exception('byok abandonment failed for one job')
            result['error'] += 1
            LISTEN_FINALIZATION_BYOK_ABANDONMENTS_TOTAL.labels(outcome='error').inc()
            continue
        if disposition['status'] != 'abandoned':
            result['skipped'] += 1
            LISTEN_FINALIZATION_BYOK_ABANDONMENTS_TOTAL.labels(outcome='skipped').inc()
            continue
        result['abandoned'] += 1
        if disposition['conversation_outcome'] == 'closed':
            result['conversations_closed'] += 1
            LISTEN_FINALIZATION_BYOK_ABANDONMENTS_TOTAL.labels(outcome='abandoned_conversation_closed').inc()
        else:
            LISTEN_FINALIZATION_BYOK_ABANDONMENTS_TOTAL.labels(outcome='abandoned_bookkeeping').inc()
        _record_byok_abandonment_journey(candidate)

    if result['abandoned']:
        logger.info('byok finalization abandonment sweep: %s', result)
    return result


def final_attempt_failed(
    job_id: str,
    dispatch_generation: int,
    lease_epoch: int,
    retry_count: int,
    *,
    failure_code: str = 'final_attempt_failed',
    firestore_client: Any = None,
) -> bool:
    dead_letter_kwargs = {'firestore_client': firestore_client}
    if failure_code != 'final_attempt_failed':
        dead_letter_kwargs['failure_code'] = failure_code
    marked = jobs_db.mark_finalization_dead_letter(
        job_id,
        dispatch_generation,
        lease_epoch,
        retry_count,
        **dead_letter_kwargs,
    )
    if marked:
        LISTEN_FINALIZATION_DEAD_LETTER_TOTAL.inc()
        try:
            job = jobs_db.get_finalization_job(job_id, firestore_client=firestore_client)
            accepted_at = job.get('created_at') if job else None
            record_capture_finalization_terminal('failure', accepted_at)
            if job is not None:
                record_conversation_finalization_client_terminal('failure', job, issue_class='unknown')
        except Exception:
            # Dead-lettering is authoritative; a best-effort metric lookup must
            # never change its terminal outcome.
            logger.exception('listen finalization terminal metric lookup failed job=%s', job_id)
        # Dead-lettering closes the bound conversation inside its own
        # transaction, bypassing the update hooks; converge the search
        # projection. Fail-open: never change the terminal outcome.
        try:
            job = jobs_db.get_finalization_job(job_id, firestore_client=firestore_client)
            if job:
                uid = job.get('uid')
                conversation_id = job.get('conversation_id')
                if isinstance(uid, str) and uid and isinstance(conversation_id, str) and conversation_id:
                    from utils.conversations.typesense_index import sync_conversation_index_after_write

                    sync_conversation_index_after_write(uid, conversation_id)
        except Exception:
            logger.warning('listen finalization dead-letter index sync failed job=%s', job_id)
    return marked


def get_listen_finalization_tasks_max_attempts_for_worker() -> int:
    return get_listen_finalization_tasks_max_attempts()


def _publish_job_metrics(*, firestore_client: Any = None) -> None:
    try:
        summary = jobs_db.get_finalization_job_summary(firestore_client=firestore_client)
    except Exception:
        logger.exception('listen finalization metrics query failed')
        return
    LISTEN_FINALIZATION_OLDEST_NONTERMINAL_AGE_SECONDS.set(float(summary['oldest_nonterminal_age_seconds']))
    LISTEN_FINALIZATION_OLDEST_BLOCKED_BYOK_AGE_SECONDS.set(float(summary['oldest_blocked_byok_age_seconds']))
    for state in ('accepted', 'success', 'failure', 'stale', 'nonterminal', 'blocked_byok', 'terminal_unknown'):
        LISTEN_FINALIZATION_DURABLE_JOBS.labels(state=state).set(float(summary[state]))
    for status in ('queued', 'leased', 'blocked_byok', 'dead_letter'):
        LISTEN_FINALIZATION_JOB_STATUS.labels(status=status).set(float(summary[status]))
    LISTEN_FINALIZATION_SUMMARY_LAST_SUCCESS_TIMESTAMP_SECONDS.set(time.time())
    register_listen_finalization_summary_metrics()
