"""One bounded tick of the conversation self-heal sweep.

``SELFHEAL_MODE`` selects ``off | detect | nudge | heal`` (default ``off``; an
unrecognized value fails closed to ``off``). ``detect`` scans and reports
only, ``nudge`` adds the wedge pushes, ``heal`` also admits at most
``MAX_HEAL_ADMISSIONS_PER_TICK`` durable SERVER_RECOVERY finalizations.
``SELFHEAL_DRY_RUN=true`` suppresses every user-data mutation and push while
logging the action preview each row would have produced, and never advances
the persisted sweep cursor.

The scan is a fixed ``status == 'in_progress'`` collection-group window of at
most ``MAX_SCAN`` rows rotating on a Firestore CAS cursor. Every reported
count describes that scanned window, never the whole fleet.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

import database.conversation_finalization_jobs as jobs_db
import database.conversations as conversations_db
from services.capture_wedge import run_capture_wedge_check
from utils.conversations import lifecycle
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.conversations.recovery import raw_transcript_bytes, recovery_audio_file_ids, structured_is_rich

logger = logging.getLogger(__name__)

SELFHEAL_MODES = frozenset({'off', 'detect', 'nudge', 'heal'})
STALE_AFTER = timedelta(hours=2)
PAGE_AGE = timedelta(hours=12)
PAGE_SIZE = 100
MAX_SCAN = 2000
MAX_ELIGIBLE_PER_TICK = 25
MAX_HEAL_ADMISSIONS_PER_TICK = 10
_ENQUEUED_ROUTES = frozenset({'cloud_tasks', 'queued'})
_ADMISSION_REFUSAL_REASONS = frozenset(
    {
        'missing',
        'no_content',
        'deferred',
        'completed',
        'dead_letter',
        'terminal',
        'duplicate_finalization',
        'already_finalizing',
        'restart_replays_state',
        'reprocess_requires_new_generation',
        'invalid_transition',
        'refused_no_cutoff',
        'refused_status',
        'refused_tombstoned',
        'refused_deferred',
        'refused_locked',
        'refused_local_pending',
        'refused_terminal_no_derived',
        'refused_source',
        'refused_protected_content',
        'refused_has_job',
        'refused_no_finished_at',
        'refused_not_stale',
        'refused_no_content',
        'refused_oversized_audio_files',
    }
)


def selfheal_mode() -> str:
    """Configured sweep mode; an unrecognized value fails closed to ``off``."""
    mode = (os.getenv('SELFHEAL_MODE') or 'off').strip().lower()
    return mode if mode in SELFHEAL_MODES else 'off'


def selfheal_dry_run() -> bool:
    return (os.getenv('SELFHEAL_DRY_RUN') or '').strip().lower() in {'1', 'true', 'yes'}


def selfheal_uid_allowlist() -> frozenset[str] | None:
    """UID allowlist restricting nudge/heal; ``None`` when unset (detect scans all)."""
    raw = os.getenv('SELFHEAL_UID_ALLOWLIST') or ''
    entries = frozenset(part.strip() for part in raw.split(',') if part.strip())
    return entries or None


def _emit(event: str, **fields: Any) -> None:
    sys.stdout.write(json.dumps({'event': event, **fields}, default=str) + '\n')
    sys.stdout.flush()


def _log_action(outcome: str, *, reason: str, uid: str, conversation_id: str | None = None) -> None:
    fields: dict[str, Any] = {'outcome': outcome, 'reason': reason, 'uid': uid}
    if conversation_id is not None:
        fields['conversation_id'] = conversation_id
    _emit('selfheal_action', **fields)


def _row_has_content(uid: str, data: Mapping[str, Any]) -> bool:
    return bool(data.get('audio_files') or conversations_db.raw_conversation_has_content(uid, dict(data)))


def _verify_pending_attempts(
    pending: list[dict[str, Any]],
    *,
    firestore_client: Any,
    conversation_reader: Callable[[str, str], dict[str, Any] | None],
    job_reader: Callable[..., dict[str, Any] | None] = jobs_db.get_finalization_job,
    counters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Re-check prior-tick admissions; return the still-in-flight entries.

    A completed job must land on a completed, non-deleted conversation still
    bound to this job id, with no transcript shrinkage and every audio id
    recorded at admission still present, and rich structured output. Benign
    growth (appended segments, extra audio ids) passes. Any deviation is a
    refused verification — logged critical for paging — and the entry is
    dropped with no re-admission; a conversation that has not reached
    ``completed`` stays pending for the next tick.
    """
    remaining: list[dict[str, Any]] = []
    for entry in pending:
        uid = entry['uid']
        conversation_id = entry['conversation_id']
        job_id = entry['job_id']
        try:
            job = job_reader(job_id, firestore_client=firestore_client)
        except Exception as error:
            counters['errors'] += 1
            remaining.append(entry)
            logger.error('selfheal verify job read failed type=%s', type(error).__name__)
            continue
        if job is None:
            _log_action('skipped', reason='missing_job', uid=uid, conversation_id=conversation_id)
            counters['skipped'] += 1
            continue
        status = str(job.get('status') or '')
        if status in {'queued', 'leased', 'blocked_byok'}:
            remaining.append(entry)
            continue
        if status != 'completed':
            _refuse_verification(entry, 'dead_letter', counters)
            continue
        try:
            conversation = conversation_reader(uid, conversation_id)
        except Exception as error:
            counters['errors'] += 1
            remaining.append(entry)
            logger.error('selfheal verify conversation read failed type=%s', type(error).__name__)
            continue
        if conversation is None:
            _log_action('skipped', reason='missing_conversation', uid=uid, conversation_id=conversation_id)
            counters['skipped'] += 1
            continue
        if conversation.get('deleted'):
            _refuse_verification(entry, 'verify_deleted', counters)
            continue
        conv_status = getattr(conversation.get('status'), 'value', conversation.get('status'))
        if conv_status != 'completed':
            remaining.append(entry)
            _log_action('skipped', reason='verify_not_completed', uid=uid, conversation_id=conversation_id)
            counters['skipped'] += 1
            continue
        if str(conversation.get('finalization_job_id') or '') != job_id:
            _refuse_verification(entry, 'verify_job_binding', counters)
            continue
        recorded_ids = {str(value) for value in job.get('selfheal_audio_file_ids') or []}
        current_ids = set(recovery_audio_file_ids(conversation) or [])
        preserved = (
            raw_transcript_bytes(conversation) >= int(job.get('selfheal_transcript_bytes') or 0)
            and recorded_ids <= current_ids
        )
        if preserved and structured_is_rich(conversation.get('structured')):
            _log_action('verified', reason='ok', uid=uid, conversation_id=conversation_id)
            counters['verified'] += 1
        else:
            _refuse_verification(entry, 'verify_content_mismatch' if not preserved else 'verify_not_rich', counters)
    return remaining


def _refuse_verification(entry: dict[str, Any], reason: str, counters: dict[str, Any]) -> None:
    _log_action('refused', reason=reason, uid=entry['uid'], conversation_id=entry['conversation_id'])
    counters['refused'] += 1
    logger.critical(
        'selfheal verification failed uid=%s conversation=%s reason=%s',
        entry['uid'],
        entry['conversation_id'],
        reason,
    )


def _evaluate_row(
    row: Mapping[str, Any],
    *,
    now: datetime,
    stale_cutoff: datetime,
    page_cutoff: datetime,
    counters: dict[str, Any],
) -> str | None:
    """Update window counters and return the bounded eligibility reason or None.

    ``None`` means the row is a recovery candidate. Age is evaluated before any
    transcript decode: only stale (>=2h) rows pay for the content check, and
    the backlog counters describe stale content-bearing rows exclusively —
    a young row or an empty stub never moves ``content_holding`` or
    ``oldest_age_seconds``.
    """
    uid = row['uid']
    data = row['data']
    finished_at = data.get('finished_at')
    if isinstance(finished_at, datetime):
        if finished_at.tzinfo is None:
            finished_at = finished_at.replace(tzinfo=timezone.utc)
    stale = isinstance(finished_at, datetime) and finished_at <= stale_cutoff
    has_content = False
    if stale:
        has_content = _row_has_content(uid, data)
        if has_content:
            counters['content_holding'] += 1
            counters['oldest_age_seconds'] = max(
                counters['oldest_age_seconds'], max(0.0, (now - finished_at).total_seconds())
            )
            if finished_at <= page_cutoff:
                counters['content_holding_over_12h'] += 1
    refusal = jobs_db.recovery_admission_refusal(uid, data, stale_cutoff)
    if refusal is None:
        return None
    if has_content and refusal not in {'not_stale', 'no_finished_at', 'status', 'no_content'}:
        counters['skipped'] += 1
        _log_action('skipped', reason=refusal, uid=uid, conversation_id=row['conversation_id'])
    return refusal


def run_selfheal_tick(
    *,
    firestore_client: Any = None,
    now: datetime | None = None,
    mode: str | None = None,
    dry_run: bool | None = None,
    uid_allowlist: frozenset[str] | None = None,
    scan_fn: Callable[..., dict[str, Any]] = jobs_db.scan_in_progress_conversations,
    cursor_getter: Callable[..., dict[str, Any]] = jobs_db.get_in_progress_content_sweep_cursor,
    cursor_advancer: Callable[..., bool] = jobs_db.advance_in_progress_content_sweep_cursor,
    request_finalization_fn: Callable[..., dict[str, Any]] = lifecycle.request_finalization,
    conversation_reader: Callable[[str, str], dict[str, Any] | None] | None = None,
    job_reader: Callable[..., dict[str, Any] | None] = jobs_db.get_finalization_job,
    wedge_runner: Callable[..., dict[str, int]] | None = None,
) -> dict[str, Any]:
    """Run one bounded sweep plus the wedge check; return the emitted counters."""
    now = now or datetime.now(timezone.utc)
    mode = mode if mode is not None else selfheal_mode()
    dry_run = selfheal_dry_run() if dry_run is None else dry_run
    allowlist = selfheal_uid_allowlist() if uid_allowlist is None else uid_allowlist
    wedge = wedge_runner or run_capture_wedge_check
    reader = conversation_reader or (
        lambda uid, cid: conversations_db.get_conversation_raw_snapshot(uid, cid, firestore_client=firestore_client)
    )
    counters: dict[str, Any] = {
        'scanned': 0,
        'content_holding': 0,
        'oldest_age_seconds': 0.0,
        'content_holding_over_12h': 0,
        'skipped': 0,
        'enqueued': 0,
        'verified': 0,
        'refused': 0,
        'errors': 0,
        'nudged': 0,
        'undeliverable': 0,
    }
    exhausted = False

    if mode != 'off':
        stale_cutoff = now - STALE_AFTER
        page_cutoff = now - PAGE_AGE
        try:
            cursor = cursor_getter(firestore_client=firestore_client)
            pending = _verify_pending_attempts(
                list(cursor.get('pending_verifications') or []),
                firestore_client=firestore_client,
                conversation_reader=reader,
                job_reader=job_reader,
                counters=counters,
            )
            scan = scan_fn(
                page_size=PAGE_SIZE,
                max_scan=MAX_SCAN,
                resume_after_path=cursor.get('resume_after_path'),
                firestore_client=firestore_client,
            )
            counters['scanned'] = int(scan.get('scanned') or 0)
            exhausted = bool(scan.get('exhausted'))
            eligible: list[Mapping[str, Any]] = []
            for row in scan.get('rows') or []:
                if (
                    _evaluate_row(row, now=now, stale_cutoff=stale_cutoff, page_cutoff=page_cutoff, counters=counters)
                    is None
                ):
                    if len(eligible) < MAX_ELIGIBLE_PER_TICK:
                        eligible.append(row)
            pending_before = len(pending)
            pending = _act_on_eligible(
                eligible,
                pending,
                mode=mode,
                dry_run=dry_run,
                uid_allowlist=allowlist,
                stale_cutoff=stale_cutoff,
                request_finalization_fn=request_finalization_fn,
                firestore_client=firestore_client,
                counters=counters,
            )
            if not dry_run:
                try:
                    advanced = cursor_advancer(
                        int(cursor.get('generation') or 0),
                        scan.get('resume_after_path'),
                        pending_verifications=pending,
                        firestore_client=firestore_client,
                    )
                    if not advanced:
                        new_jobs = [entry['job_id'] for entry in pending[pending_before:]]
                        if new_jobs:
                            counters['errors'] += 1
                            logger.critical(
                                'selfheal sweep cursor CAS lost with %d unverified jobs; '
                                'manual audit required job_ids=%s',
                                len(new_jobs),
                                new_jobs,
                            )
                        else:
                            logger.warning('selfheal sweep cursor CAS lost; another tick advanced it')
                except Exception as error:
                    counters['errors'] += 1
                    logger.error('selfheal sweep cursor advance failed type=%s', type(error).__name__)
        except Exception as error:
            counters['errors'] += 1
            logger.exception('selfheal sweep failed type=%s', type(error).__name__)

        try:
            wedge_counts = wedge(
                mode=mode,
                dry_run=dry_run,
                uid_allowlist=allowlist,
                now=now,
                firestore_client=firestore_client,
            )
            counters['nudged'] += int(wedge_counts.get('nudged') or 0)
            counters['undeliverable'] += int(wedge_counts.get('undeliverable') or 0)
            counters['errors'] += int(wedge_counts.get('errors') or 0)
        except Exception as error:
            counters['errors'] += 1
            logger.exception('selfheal wedge check failed type=%s', type(error).__name__)

    _emit(
        'selfheal_tick',
        scanned=counters['scanned'],
        content_holding=counters['content_holding'],
        oldest_age_seconds=counters['oldest_age_seconds'],
        content_holding_over_12h=counters['content_holding_over_12h'],
        skipped=counters['skipped'],
        enqueued=counters['enqueued'],
        verified=counters['verified'],
        refused=counters['refused'],
        errors=counters['errors'],
        nudged=counters['nudged'],
        undeliverable=counters['undeliverable'],
        mode=mode,
        exhausted=exhausted,
        dry_run=dry_run,
    )
    counters['mode'] = mode
    counters['exhausted'] = exhausted
    counters['dry_run'] = dry_run
    return counters


def _act_on_eligible(
    eligible: list[Mapping[str, Any]],
    pending: list[dict[str, Any]],
    *,
    mode: str,
    dry_run: bool,
    uid_allowlist: frozenset[str] | None,
    stale_cutoff: datetime,
    request_finalization_fn: Callable[..., dict[str, Any]],
    firestore_client: Any,
    counters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Admit eligible rows in heal mode; preview or skip them otherwise.

    Returns the pending-verification list to persist on the sweep cursor.
    """
    if mode != 'heal':
        for row in eligible:
            _log_action('skipped', reason=f'mode_{mode}', uid=row['uid'], conversation_id=row['conversation_id'])
            counters['skipped'] += 1
        return pending

    admitted = 0
    for row in eligible:
        if admitted >= MAX_HEAL_ADMISSIONS_PER_TICK:
            _log_action(
                'skipped',
                reason='admission_cap',
                uid=row['uid'],
                conversation_id=row['conversation_id'],
            )
            counters['skipped'] += 1
            continue
        if uid_allowlist is not None and row['uid'] not in uid_allowlist:
            _log_action('skipped', reason='allowlist', uid=row['uid'], conversation_id=row['conversation_id'])
            counters['skipped'] += 1
            continue
        if dry_run:
            _log_action(
                'dry_run',
                reason='would_admit',
                uid=row['uid'],
                conversation_id=row['conversation_id'],
            )
            continue
        if len(pending) >= jobs_db.SELFHEAL_MAX_PENDING_VERIFICATIONS:
            _log_action(
                'skipped',
                reason='verification_capacity',
                uid=row['uid'],
                conversation_id=row['conversation_id'],
            )
            counters['skipped'] += 1
            continue
        try:
            result = request_finalization_fn(
                row['uid'],
                row['conversation_id'],
                has_byok_keys=False,
                trigger=ProcessingTrigger.SERVER_RECOVERY,
                require_cloud_tasks=True,
                recovery_cutoff=stale_cutoff,
                firestore_client=firestore_client,
            )
        except lifecycle.FinalizationDispatchUnavailable:
            _log_action(
                'refused',
                reason='dispatch_unavailable',
                uid=row['uid'],
                conversation_id=row['conversation_id'],
            )
            counters['refused'] += 1
            continue
        except Exception as error:
            counters['errors'] += 1
            _log_action(
                'refused',
                reason='admission_error',
                uid=row['uid'],
                conversation_id=row['conversation_id'],
            )
            logger.error(
                'selfheal admission failed uid=%s conversation=%s type=%s',
                row['uid'],
                row['conversation_id'],
                type(error).__name__,
            )
            continue
        route = str(result.get('route') or '')
        status = str(result.get('status') or '')
        if result.get('created') and result.get('job_id') and route in _ENQUEUED_ROUTES:
            admitted += 1
            counters['enqueued'] += 1
            _log_action('enqueued', reason='ok', uid=row['uid'], conversation_id=row['conversation_id'])
            pending.append({'uid': row['uid'], 'conversation_id': row['conversation_id'], 'job_id': result['job_id']})
        elif route == 'noop':
            reason = status if status in _ADMISSION_REFUSAL_REASONS else 'unknown'
            _log_action('refused', reason=reason, uid=row['uid'], conversation_id=row['conversation_id'])
            counters['refused'] += 1
        else:
            _log_action(
                'skipped',
                reason='route',
                uid=row['uid'],
                conversation_id=row['conversation_id'],
            )
            counters['skipped'] += 1
    return pending
