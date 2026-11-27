"""Flagged sync admission. Failures never fall through to the legacy dispatcher."""

import asyncio
from dataclasses import replace
from functools import partial
import hashlib
import io
import logging
import os
import shutil
import tempfile
import time
import wave

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from config.batch_pipeline import Priority, known_unsupported_batch_language, language_inheritance_enabled, priority_for
from config.batch_pipeline_language import (
    MULTILINGUAL_PROFILE,
    admission_language_exclusion_enabled,
    admission_language_sample_enabled,
    batch_admission_language,
    pin_untrusted,
    profile_inherited_language,
)
from config.batch_pipeline_vendor_overflow import (
    legacy_capacity_fallback_enabled,
    overflow_enabled,
    overflow_priorities,
)
from config.policy import BatchUnitPolicy, resolve_batch_policy
from config.batch_pipeline_coverage_wait import decode_failure_memo_enabled
from config.batch_pipeline_providers import provider_config
from config.firestore_read_levers import lever_enabled
from config.prerecorded_language import language_guard_enabled, language_class
from config.reliability_experiments import enabled as experiment
from config.request_clock import context_fields
from config.stt_cap_dispatch import offline_enforcement_enabled
from config.stt_provider_policy import normalized_stt_language, PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL
from database import batch_pipeline_allowance_hold as allowance_hold
from database import record_wal_duplicate as wal_duplicate
from database import record_wal_handoff as wal_receipts
from database.batch_pipeline_intake import admit, cache_completed
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.privacy_check_metrics import STATUS_SKIP
from database.batch_pipeline_recovery_fence import RecoveryFence
from database.batch_pipeline_store import FirestoreStore
from database.batch_pipeline_shadow_hook import shadow_from_env
from database.sync_record_wait_cache import cached_decode_failure, remember_decode_failure
from database.sync_ledger import (
    BATCH_PARTIAL_STATUS,
    is_valid_completed_sync_content_result,
    is_valid_partial_sync_content_result,
)
from utils.batch_pipeline.artifact_policy import artifacts_for
from utils.batch_pipeline.audio import with_context
from utils.batch_pipeline import frame_outcomes
from utils.batch_pipeline.capture_decode import decode_units, is_deterministic_decode_failure
from utils.batch_pipeline.future_capture_decode import decode_future_units
from utils.sync import future_capture_request
from utils.sync.future_capture_request import Outcome as FutureCaptureOutcome
from utils.sync.receipt_clock import (
    POLICY as FUTURE_CLOCK_POLICY,
    ESTIMATED_POLICY,
    FutureCaptureRefused,
    FutureCaptureRetry,
)
from utils.batch_pipeline.repair_lineage import language_proof, lineage_record
from utils.batch_pipeline.packing_counterfactual import IntakePacking
from utils.capture.batch_coverage import covered_response
from utils.sync.source_reuse_decode import decode_for_intake
from config.refactor_modes import serving_for
from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem
from utils.batch_pipeline.intake_outcome import IntakeRouteEvidence
from database.outbox import OutboxKind, outbox_for
from utils.batch_pipeline import gpu_overflow
from utils.batch_pipeline.provider_stt_admission import provider_enqueue
from utils.batch_pipeline.route_selection import select_route
from utils.sync import legacy_dark
from utils.sync.legacy_dark import LegacySyncMode
from utils.batch_pipeline.language_metrics import record_admission_exclusion, record_route, record_sample_window
from utils.batch_pipeline.retention import batch_artifact_authorize
from utils.batch_pipeline.scheduler import Scheduler, owner_key
from utils.executors import db_executor, run_blocking, storage_executor, sync_executor
from utils.metrics import OMI_PIPELINE_RECORD_WAIT_ANSWERS_TOTAL, OMI_PIPELINE_RECORD_WAIT_MEMO_HITS_TOTAL
from utils.observability.fallback import record_fallback
from utils.observability.stt_cap_dispatch import BATCH_ADMISSION_STAGE_SECONDS
from utils.sync.admission_responses import sync_content_in_progress_response
from utils.sync.stage import current_stage
from utils.sync.capture import chunk_identity
from utils.sync.deleted_conversation import (
    CONVERSATION_DELETED_REASON_CODE,
    confirm_only_user_deletions,
    deleted_conversation_result,
    is_conversation_deleted,
)

logger = logging.getLogger(__name__)
JOB_PREFIX = 'bp_'
# Every failed unit settled its one paid recovery without words and waits for a
# reviewed operator decision server-side. Released apps ACK `completed`.
HELD_REASON_CODE = 'batch_unit_held'


SAMPLE_SCAN_SECONDS = 600  # a sampled upload is held and classified whole up to this much audio; larger stays legacy
INTAKE_PROBE_SECONDS = 1.0


def _speech_windows(wav: bytes) -> list[bytes] | None:
    """All strict-VAD speech of a unit's first SAMPLE_SCAN_SECONDS as 30 s WAVs; None when silent.

    The first window is the vendor sample. Further windows cover the rest of the speech, the last
    overlapping its predecessor so every window is a full 30 s.
    """
    from utils.stt.local_vad import offline_pcm_speech_segments

    with wave.open(io.BytesIO(wav), 'rb') as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (1, 2, 16000):
            raise ValueError('speech sample requires 16kHz mono PCM16')
        pcm = source.readframes(SAMPLE_SCAN_SECONDS * 16000)
    speech = b''.join(
        pcm[int(span['start'] * 16000) * 2 : int(span['end'] * 16000) * 2] for span in offline_pcm_speech_segments(pcm)
    )
    if not speech:
        return None
    step = 30 * 32000
    windows = []
    for start in [0, *(min(start, len(speech) - step) for start in range(step, len(speech), step))]:
        output = io.BytesIO()
        with wave.open(output, 'wb') as target:
            target.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            target.writeframes(speech[start : start + step])
        windows.append(output.getvalue())
    return windows


def _batch_admission(user: dict, target: dict) -> tuple[str | None, str | None]:
    """``batch_admission_language``, with a multilingual-profile upload classified on audio like an unknown one.

    Its admission language is 'multi' (never the conversation's supported pin) where legacy draining or dark
    admits it unsampled. Outside ``accept_upload``, which is at the type checker's complexity limit."""
    language, reason = batch_admission_language(user, target)
    if reason != MULTILINGUAL_PROFILE:
        return language, reason
    logger.info('event=batch_admission_language outcome=reclassified reason=%s', reason)
    return 'multi', 'unknown_multilingual_conversation'


def _declared_language(target: dict, user: dict) -> str:
    """The conversation-or-user declaration; 'multi' for a multilingual-profile user, whose pin is not evidence."""
    if pin_untrusted(user):
        return 'multi'
    return normalized_stt_language(target.get('language') or user.get('language'))


def _sampled_refusal(target: dict, user: dict, evidence, reason: str = 'unknown_multilingual_conversation') -> None:
    """An unsafe, silent, refused-to-legacy or unclassified sample (or an admission exclusion) keeps legacy."""
    record_admission_exclusion(target.get('language') or user.get('language'), reason, legacy_available=True)
    if evidence is not None:
        evidence.language_excluded = True
    return None


def _next_unit(iterator):
    # StopIteration cannot cross asyncio Future boundaries.
    return next(iterator, None)


def _private_sample_paths(paths: list[str]) -> tuple[str, list[str]]:
    """Link the caller's uploads under their own names for a decode that may refuse.

    WAL decode deletes its inputs; a sampled refusal hands the upload back to legacy,
    which must still stage these exact files (else FileNotFoundError -> 503 loop).
    """
    if len(set(paths)) != len(paths):
        # The router wrote every body under one repeated name to one file, so
        # an earlier body is already gone. Never acknowledge it; the phone keeps
        # its audio (the same fail-closed answer as an unsampled batch decode).
        raise ValueError('sampled upload repeats a filename')
    directory = tempfile.mkdtemp(prefix='omi-batch-sample-')
    try:
        linked = []
        for path in paths:
            target = os.path.join(directory, os.path.basename(path))
            try:
                os.link(path, target)
            except OSError:
                shutil.copy2(path, target)
            linked.append(target)
        return directory, linked
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise


def _open_operator_intent(job: dict) -> bool:
    """A reviewed redrive/disposition is preparing or running for this unit."""
    # `completed` and an operator call that itself settled `failed_held` are closed;
    # prepared, running and any unknown state stay open.
    return any(
        isinstance(job.get(key), dict) and job[key].get('state') not in {'completed', 'failed_held'}
        for key in ('speech_redrive', 'terminal_disposition', 'silence_disposition')
    )


def _terminally_held(job: dict) -> bool:
    """The unit's one paid recovery settled without words; nothing automatic follows.

    Its encrypted artifacts stay server-side for a reviewed operator redrive, so
    a re-upload can neither change the outcome nor add a recovery path.
    """
    return (job.get('state') == 'quarantined' and job.get('recovery_state') == 'failed_held') or (
        job.get('state') == 'dead' and job.get('dead_letter_reason') == 'held_expired'
    )


def _held_status(jobs: list[dict]) -> tuple[str, str | None] | None:
    """Terminal or waiting answer for uploads whose failures are all held units."""
    from config.batch_pipeline import held_terminal_status_enabled

    failed = [
        job
        for job in jobs
        if _terminally_held(job)
        or (job.get('state') == 'quarantined' and job.get('recovery_state') not in {'held', 'prepared', 'running'})
    ]
    if not failed or not all(_terminally_held(job) for job in failed) or not held_terminal_status_enabled():
        return None
    # An operator intent or a sibling still in flight (including a quarantined
    # sibling whose own recovery is held/prepared/running) can still change
    # this upload; wait rather than sending the phone into a re-upload loop.
    if any(_open_operator_intent(job) for job in failed) or any(
        job.get('state') != 'committed' and not _terminally_held(job) for job in jobs
    ):
        return 'processing', None
    # Retained server audio is not a successful transcription receipt. Keep
    # the phone's only independent copy until every unit actually completes.
    return 'processing', HELD_REASON_CODE


def _deleted_conversation_status(ledger: dict, intake: dict, job_id: str) -> dict | None:
    result = ledger.get('result')
    if not isinstance(result, dict) or not (
        ledger.get('status') == 'completed' and is_valid_completed_sync_content_result(result)
    ):
        return None
    total = result['total_segments']
    return {
        'job_id': job_id,
        'status': 'completed',
        'completed_at': ledger.get('completed_at'),
        'lane': intake['lane'],
        'total_files': intake['total_files'],
        'total_segments': total,
        'processed_segments': total,
        'successful_segments': total,
        'failed_segments': 0,
        'errors': [],
        'result': deleted_conversation_result(total),
        'reason_code': CONVERSATION_DELETED_REASON_CODE,
        'poll_after_ms': 0,
    }


def _only_deleted_total(tx, uid: str, content_id: str) -> int | None:
    """Total segments of a completed receipt whose only privacy denials are user deletions."""
    ledger = tx.get('content', f'{uid}/{content_id}')
    result = ledger.get('result')
    if (
        ledger.get('status') != 'completed'
        or not isinstance(result, dict)
        or not is_valid_completed_sync_content_result(result)
    ):
        return None
    ids = [*(result.get('new_memories') or []), *(result.get('updated_memories') or [])]
    confirm_only_user_deletions(lambda one: tx.check_privacy(uid, one), ids)
    return result['total_segments']


def durable_status(store, uid: str, job_id: str, *, poll: bool = False) -> dict | None:
    if job_id.startswith(wal_receipts.JOB_PREFIX):
        authority_store = getattr(store, 'store', store)
        return wal_receipts.read_status(authority_store.client, authority_store.namespace, uid, job_id, poll=poll)
    from database.batch_pipeline_artifact_missing import artifact_missing, REASON_CODE
    from utils.batch_pipeline.upload_coalescing import member_status

    spent_redrives: list[str] = []

    def read(tx):
        spent_redrives.clear()  # a retried transaction reports only its own commit
        intake = tx.get('intakes', job_id)
        if not intake:
            return None
        if intake['owner_id'] != uid:
            raise HTTPException(status_code=403, detail='Not authorized to view this sync job')
        if intake.get('coalesce_group'):
            return {'_coalescing_intake': intake}
        ledger = tx.get('content', f"{uid}/{intake['content_id']}")
        jobs = [tx.get('jobs', segment) for segment in intake['segment_ids']]
        # Polling sometimes redrives a job in this transaction, and partial or
        # complete results may expose conversation IDs. Keep both paths fenced.
        may_redrive = any(job.get('state') == 'dead' and job.get('merge_pending') for job in jobs)
        skip = poll and lever_enabled('bpp_status_skip', uid) and not ledger.get('result') and not may_redrive
        if not skip:
            sources = {
                value
                for job in jobs
                for value in (job.get('conversation_id'), job.get('capture_source_conversation_id'))
                if value
            }
            result_ids = ledger.get('result') or {}
            sources.update(result_ids.get('new_memories') or [])
            sources.update(result_ids.get('updated_memories') or [])
            try:
                tx.check_privacy(uid, sources, jobs[0].get('privacy_generation') if jobs else None)
            except BatchPrivacyBlocked as error:
                # Completed content whose conversation the user deleted is final:
                # ACK without IDs so the phone stops re-uploading deleted audio.
                # Unfinished work and every other denial keep the 409.
                terminal = (
                    _deleted_conversation_status(ledger, intake, job_id)
                    if is_conversation_deleted(error) and not any(artifact_missing(job) for job in jobs)
                    else None
                )
                if terminal is None:
                    raise
                generation = jobs[0].get('privacy_generation') if jobs else None
                confirm_only_user_deletions(lambda one: tx.check_privacy(uid, one, generation), sources)
                logger.info('event=batch_intake_status outcome=conversation_deleted_terminal')
                return terminal
        else:
            STATUS_SKIP.labels('batch_job').inc()
        result = ledger.get('result')
        from utils.batch_pipeline.input_retention import input_expiring

        expiring = sum(input_expiring(job) for job in jobs)
        if expiring:
            # Existing failed-upload UI keeps local custody and offers retry.
            # This precedes completion/partial receipts and the legacy polling redrive.
            projected = sum(job.get('state') == 'committed' for job in jobs)
            return {
                'job_id': job_id,
                'status': 'failed',
                'reason_code': REASON_CODE,
                'lane': intake['lane'],
                'total_files': intake['total_files'],
                'total_segments': len(jobs),
                'processed_segments': projected,
                'successful_segments': projected,
                'failed_segments': expiring,
                'errors': ['batch_worker_quarantined'],
                'result': result if is_valid_partial_sync_content_result(result) else None,
                'poll_after_ms': 0,
            }
        missing = sum(artifact_missing(job) for job in jobs)
        if missing:
            # Must precede both all-success and held-partial completion. Phones
            # acknowledge only `completed`; missing bytes remain in custody.
            projected = sum(job.get('state') == 'committed' for job in jobs)
            return {
                'job_id': job_id,
                'status': 'failed',
                'reason_code': REASON_CODE,
                'lane': intake['lane'],
                'total_files': intake['total_files'],
                'total_segments': len(jobs),
                'processed_segments': projected,
                'successful_segments': projected,
                'failed_segments': missing,
                'errors': [],
                'result': result if is_valid_partial_sync_content_result(result) else None,
                'poll_after_ms': 0,
            }
        completed = ledger.get('status') == 'completed' and is_valid_completed_sync_content_result(result)
        if not completed:
            # FirestoreTransaction buffers every put until this callback returns;
            # later units may still read their fences before the shared flush.
            for index, job in enumerate(jobs):
                outcome = Scheduler.redrive_in_transaction(tx, job, time.time(), checked=RecoveryFence(store).checked)
                if outcome is not None:
                    # The fence requeues a checked copy. Use that written value
                    # without another transactional read after staging writes.
                    jobs[index] = outcome.job
                    if outcome.spent:
                        spent_redrives.append(job['segment_id'])
        if ledger.get('status') == BATCH_PARTIAL_STATUS and is_valid_partial_sync_content_result(result):
            # Siblings are already visible independently. A partial ledger must
            # never ACK custody of unresolved units, including after 30 minutes.
            held_count, total = result['held_segments'], result['total_segments']
            return {
                'job_id': job_id,
                'status': 'processing',
                'lane': intake['lane'],
                'total_files': intake['total_files'],
                'total_segments': total,
                'processed_segments': total - held_count,
                'successful_segments': total - held_count,
                'failed_segments': held_count,
                'errors': [],
                'result': result,
                'reason_code': HELD_REASON_CODE,
                'poll_after_ms': 300000,
            }
        recovering = any(
            job.get('state') == 'quarantined' and job.get('recovery_state') in {'held', 'prepared', 'running'}
            for job in jobs
        )
        failed = sum(
            _terminally_held(job)
            or (job.get('state') == 'quarantined' and job.get('recovery_state') not in {'held', 'prepared', 'running'})
            for job in jobs
        )
        held = None if completed else _held_status(jobs)
        if held is not None:
            held_state, reason_code = held
            committed = sum(job.get('state') == 'committed' for job in jobs)
            status = {
                'job_id': job_id,
                'status': held_state,
                'lane': intake['lane'],
                'total_files': intake['total_files'],
                'total_segments': len(jobs),
                'processed_segments': committed,
                'successful_segments': committed if reason_code else 0,
                'failed_segments': failed,
                'errors': [],
                # Committed siblings are already projected; never name
                # conversations from an upload whose completion is held.
                'result': (
                    {
                        'new_memories': [],
                        'updated_memories': [],
                        'failed_segments': failed,
                        'total_segments': len(jobs),
                        'errors': [],
                    }
                    if reason_code
                    else None
                ),
                'poll_after_ms': 300000 if reason_code else 3000,
            }
            if reason_code:
                status['reason_code'] = reason_code
            return status
        status = (
            'failed'
            if failed
            else (
                'completed'
                if completed
                else (
                    'processing'
                    if recovering or any(job.get('state') in {'leased', 'result_ready', 'committed'} for job in jobs)
                    else 'queued'
                )
            )
        )
        if status == 'completed' and experiment('batch_frame_outcomes', uid):
            # Experiment batch_frame_outcomes: the completed result also names which source
            # frames became text and which were evaluated and are empty. Computed from the
            # intake and unit rows this read already holds; a held, failed or unattributable
            # unit gets no verdict, and a copy keeps the ledger's own result untouched.
            result = frame_outcomes.attach(result, intake, jobs)
        return {
            'job_id': job_id,
            'status': status,
            'lane': intake['lane'],
            'total_files': intake['total_files'],
            'total_segments': result.get('total_segments', len(jobs)) if completed else len(jobs),
            'processed_segments': sum(job.get('state') == 'committed' for job in jobs),
            'successful_segments': result.get('total_segments', len(jobs)) if completed else 0,
            'failed_segments': failed,
            'errors': ['batch_worker_quarantined'] if failed else [],
            'result': result if completed and not failed else None,
            'completed_at': ledger.get('completed_at') if completed else None,
            'poll_after_ms': 0 if completed or failed else 3000,
        }

    status = store.run(read)
    if status is not None and '_coalescing_intake' in status:
        if experiment('batch_frame_outcomes', uid):
            # Experiment batch_frame_outcomes: a coalesced member stores its target's result as
            # its own receipt. The target's verdicts span every member, so they stay out of it.
            return member_status(
                store, uid, status['_coalescing_intake'], partial(_status_without_frame_outcomes, poll=poll)
            )
        return member_status(store, uid, status['_coalescing_intake'], partial(durable_status, poll=poll))
    if spent_redrives:
        # Class 6 counter: same signal as the nightly scan, once per committed poll re-drive.
        from utils.backlog_metrics import record_transition

        record_transition('held_redrive_budget_spent', len(spent_redrives))
    return status


def _status_without_frame_outcomes(store, uid: str, job_id: str, *, poll: bool = False) -> dict | None:
    status = durable_status(store, uid, job_id, poll=poll)
    if not status:
        return status
    result = status.get('result')
    if isinstance(result, dict) and frame_outcomes.FIELD in result:
        return {**status, 'result': {key: value for key, value in result.items() if key != frame_outcomes.FIELD}}
    return status


def start_response(status: dict) -> JSONResponse:
    return JSONResponse(
        status_code=202,
        content={
            key: status[key] for key in ('job_id', 'status', 'total_files', 'total_segments', 'poll_after_ms', 'lane')
        },
    )


def upload_decoder(uid, device_id, context):
    if (context or {}).get('capture_clock_policy') in {FUTURE_CLOCK_POLICY, ESTIMATED_POLICY}:
        return partial(
            decode_future_units,
            uid=uid,
            device_id=device_id,
            retained_offsets_by_name=(context or {}).get('retained_capture_offsets_by_name'),
        )
    return decode_units


def upload_capture_trust(context):
    return (
        'untrusted' if (context or {}).get('capture_clock_policy') in {FUTURE_CLOCK_POLICY, ESTIMATED_POLICY} else None
    )


def _sync_unavailable_response() -> JSONResponse:
    """Today's single retryable intake answer; every failure path returns exactly this."""
    return JSONResponse(
        status_code=503,
        headers={'Retry-After': '30'},
        content={'code': 'sync_batch_unavailable', 'detail': 'Sync is temporarily unavailable; retain local audio'},
    )


def _decode_failure_key(uid: str, content_id: str, paths: list[str]) -> str | None:
    """Upload identity only: owner, content hash, file count and total bytes.

    ``content_id`` already HMACs each basename and the SHA-256 of its bytes, so
    this key cannot move to different audio. Neither the key nor its log line
    carries a path, file name, uid or id.
    """
    try:
        sizes = [os.path.getsize(path) for path in paths]
    except OSError:
        return None
    payload = f'{uid}\n{content_id}\n{len(paths)}\n{sum(sizes)}'
    return hashlib.sha256(payload.encode()).hexdigest()


async def _probe_upload_allowance(
    store, uid, policy, lane, items, source_aliases
) -> allowance_hold.IntakeRefusal | None:
    """Recognize the funded gate's monthly refusal using a verified usage total."""
    if not (
        policy.stt_route == 'parakeet'
        and policy.provider_reason != 'byok'
        and lane in {'fresh', 'backfill'}
        and any(item.requires_compute_admission and item.segment_id not in source_aliases for item in items)
        and offline_enforcement_enabled('batch')
        and lever_enabled('usage_month_total', uid)
    ):
        return None

    deadline = time.monotonic() + INTAKE_PROBE_SECONDS

    def probe():
        if time.monotonic() >= deadline or not allowance_hold.intake_enabled():
            return None
        from utils import funded_processing
        from utils.stt_cap_dispatch import funded_allowance

        if time.monotonic() >= deadline or not funded_processing.consent_allows(uid):
            return None
        key = owner_key(uid)
        fence = store.run(lambda tx: allowance_hold.release_fence(tx.get(allowance_hold.OWNERS, key)))
        if fence is None or time.monotonic() >= deadline:
            return None
        observed_at = time.time()
        # The GPU gate uses the same monthly allowance for both lanes. Sync
        # upload enforces the independent Unlimited V2 backfill day cap.
        allowance = funded_allowance(uid, lane='batch', ready_usage_only=True)
        if time.monotonic() < deadline and not allowance.managed and allowance.reason == 'plan_allowance_exhausted':
            return allowance_hold.IntakeRefusal(observed_at, fence)
        return None

    try:
        with BATCH_ADMISSION_STAGE_SECONDS.labels(stage='intake_funding').time():
            return await asyncio.wait_for(run_blocking(db_executor, probe), timeout=INTAKE_PROBE_SECONDS)
    except Exception as error:
        logger.warning('event=batch_allowance_intake outcome=unevaluated exception_type=%s', type(error).__name__)
        return None


async def accept_upload(
    *,
    uid: str,
    job_id: str,
    content_id: str,
    paths: list[str],
    lane: str,
    recording_age_seconds: float | None,
    source: str,
    should_lock: bool,
    conversation_id: str | None,
    client_device_id: str | None,
    client_platform: str | None,
    byok_enabled: bool = False,
    intake_context: dict | None = None,
    record_router=None,
    decode=None,
    policy: BatchUnitPolicy | None = None,
    usage_period: str | None = None,
    evidence: IntakeRouteEvidence | None = None,
    repair_job_id: str | None = None,
    vendor_table: bool = True,
    release: str | None = None,
    _coalescing_group: dict | None = None,
) -> JSONResponse | None:
    """None preserves a prior legacy receipt; batch outcomes never fall through.

    ``decode(max_seconds)`` replaces WAL decoding of ``paths`` for server-held audio
    (the cap-hold adapter); it must yield the same ``AudioUnit`` shape. ``evidence``
    records this request's language-exclusion declines for the caller's intake
    outcome counter; declines that follow a prior owner carry no fresh decision.
    """
    policy = policy or resolve_batch_policy(uid)
    public_job_id = JOB_PREFIX + job_id
    iterator = None
    sample_directory = None
    deterministic_key = None
    phase = 'receipt_read'
    started = time.monotonic()
    try:
        # A2 seam: the sync upload admission (intakes, jobs, owners, queues, control) is mirrored in shadow mode.
        store = await run_blocking(
            db_executor, lambda: shadow_from_env(FirestoreStore(f'batch_pipeline_{current_stage()}'))
        )
        previous = await run_blocking(db_executor, store.run, lambda tx: tx.get('content', f'{uid}/{content_id}'))
        previous = await _coalescing_previous(store, previous, public_job_id, _coalescing_group)
        refused = await _repair_prior_upload(
            store,
            previous,
            uid,
            content_id,
            paths,
            repair_job_id,
            decode,
            {
                'source': source,
                'should_lock': should_lock,
                'conversation_id': conversation_id,
                'client_device_id': client_device_id,
                'client_platform': client_platform,
                'intake_context': intake_context,
            },
        )
        if refused is not None:
            future_capture_request.mark(FutureCaptureOutcome.PREFLIGHT_REFUSED)
            return refused
        if previous.get('dispatch_protocol') == 'batch_v1':
            status = await run_blocking(db_executor, durable_status, store, uid, previous['job_id'])
            future_capture_request.mark(FutureCaptureOutcome.PRIOR_CUSTODY)
            return start_response(status) if status else sync_content_in_progress_response(previous['job_id'])
        if previous.get('status') == 'completed':
            try:
                cached = await run_blocking(
                    db_executor,
                    cache_completed,
                    store,
                    uid,
                    content_id,
                    public_job_id,
                    {
                        'owner_key': owner_key(uid),
                        'conversation_id': conversation_id,
                        'total_files': len(paths),
                        'lane': lane,
                    },
                    time.time(),
                )
            except BatchPrivacyBlocked as error:
                # cache_completed checks privacy only after proving a valid
                # completed receipt. The user deleted its conversation: answer
                # the synchronous all-success shape (no IDs, no intake write) so
                # the phone ACKs instead of looping on a 409.
                if not is_conversation_deleted(error):
                    raise
                # Re-prove in one transaction that every denial is a deletion;
                # any other denial raises here and keeps the 409.
                total = await run_blocking(db_executor, store.run, lambda tx: _only_deleted_total(tx, uid, content_id))
                if total is None:
                    raise error
                future_capture_request.mark(FutureCaptureOutcome.PRIOR_CUSTODY)
                logger.info('event=batch_intake outcome=conversation_deleted_terminal')
                return JSONResponse(status_code=200, content=deleted_conversation_result(total))
            if cached:
                status = await run_blocking(db_executor, durable_status, store, uid, public_job_id)
                if status:
                    future_capture_request.mark(FutureCaptureOutcome.PRIOR_CUSTODY)
                    return start_response(status)
        phase = 'ownership_fence'
        mode = await run_blocking(db_executor, legacy_dark.current_mode, uid)
        adopt = None
        if previous:
            if mode is LegacySyncMode.ON:
                # Existing legacy ownership includes capped/retryable/missing-Redis
                # recovery. Its original claimant remains the sole authority.
                future_capture_request.mark(FutureCaptureOutcome.PRIOR_CUSTODY)
                return None
            # Contract (h) invariant 4: legacy-owned content is acknowledged, never
            # re-admitted; only a row legacy can no longer finish is adopted, by a
            # ledger CAS inside the admission transaction.
            # The Redis owner's existence decides a fresh-looking claim, as in
            # claim_sync_content; a live repeat-failure pause stays 409 (fence).
            owner_job_present = await run_blocking(db_executor, legacy_dark.legacy_owner_job_present, previous)
            decision = legacy_dark.fence_decision(
                previous, mode, owner_job_present=owner_job_present, batch_adopts_stranded=True
            )
            if decision.action is not legacy_dark.FenceAction.ADMIT_BATCH:
                future_capture_request.mark(FutureCaptureOutcome.PRIOR_CUSTODY)
                return legacy_dark.fence_response(decision, total_files=len(paths), lane=lane)
            adopt = stranded_adopter(previous, owner_job_present=owner_job_present)
        if not policy.batch_enabled:
            # Main's owner-load filter (ramp narrowing) applies only after durable
            # dispatch ownership checks; accepted batch receipts above always drain.
            if mode is LegacySyncMode.ON:
                future_capture_request.mark(FutureCaptureOutcome.ROUTE_DECLINED)
                return None
            # Legacy draining/dark cannot take a narrowed owner back (contract (h)),
            # so the upload stays on batch rather than being refused.
            policy = replace(policy, batch_enabled=True)
        # BYOK uploads are admitted like every other upload (David, 10-19); the
        # stage never needs request-scoped keys and enrichment runs on Omi's keys.
        seed = WorkItem(
            hashlib.sha256(f'{content_id}:0'.encode()).hexdigest(),
            uid,
            0,
            'intake:pending',
            1,
            priority_for(lane, recording_age_seconds),
            requires_compute_admission=True,
            conversation_id=conversation_id,
            privacy_generation=_coalescing_generation(_coalescing_group),
            capture_source_conversation_id=(intake_context or {}).get('capture_source_conversation_id'),
        )
        phase = 'authorization'
        snapshots = {}
        context = await run_blocking(db_executor, batch_artifact_authorize, store, seed, snapshots=snapshots)
        user = snapshots['user']
        target = snapshots.get('conversations', {}).get(conversation_id) or {}
        user, target = _coalescing_language(user, target, _coalescing_group)
        # Privacy authorization already loaded this row. Rollback may drain a
        # native owner here without adding an ownership-discovery read to dark
        # uploads, or accidentally admitting a second GPU job.
        if target.get('record_lane_owner') == 'batch_live_v1':
            future_capture_request.mark(FutureCaptureOutcome.PRIOR_CUSTODY)
            phase = 'record_routing'
            if record_router is None:
                OMI_PIPELINE_RECORD_WAIT_ANSWERS_TOTAL.labels(reason='record_router_missing').inc()
                logger.info('event=sync_record_upload outcome=pending reason=record_router_missing')
                return JSONResponse(status_code=503, content={'code': 'record_capture_pending'})
            return await record_router(
                uid=uid,
                conversation_id=conversation_id,
                content_id=content_id,
                paths=paths,
                source=source,
                client_device_id=client_device_id,
                byok_enabled=byok_enabled,
                loaded_conversation=target,
                policy=policy,
                evidence=evidence,
            )
        phase = 'route_selection'
        admission_language = None
        sampled = False
        if admission_language_exclusion_enabled() and target.get('record_lane_owner') != 'batch_sync_v1':
            admission_language, exclusion_reason = _batch_admission(user, target)
            # Exclusion is safe only while this owner still has legacy. Once its
            # legacy is draining/dark the upload is admitted (C8's provider route
            # serves it) instead of being refused by both lanes; a supported
            # conversation keeps its pinned input language in every mode.
            if (
                exclusion_reason == 'unknown_multilingual_conversation'
                and mode is LegacySyncMode.ON
                and admission_language_sample_enabled()
            ):
                # Decide on audio, not the declaration: the first unit's LID runs below,
                # before any staging, and an unsafe answer keeps the upload on legacy.
                sampled = True
            elif exclusion_reason and mode is LegacySyncMode.ON:
                _sampled_refusal(target, user, evidence, exclusion_reason)
                future_capture_request.mark(FutureCaptureOutcome.ROUTE_DECLINED)
                return None
        fresh = seed.priority == Priority.FRESH
        if (
            fresh
            and mode is LegacySyncMode.ON
            and target.get('record_lane_owner') != 'batch_sync_v1'
            and legacy_capacity_fallback_enabled()
            and gpu_overflow.saturated(store)
        ):
            # Capacity fallback: the GPU ring is past its fresh-backlog SLO and this owner still
            # has legacy sync, which serves the upload now instead of queueing it (same exit as
            # heavy-owner exclusion; nothing was written). Backfill waits for the ring.
            record_fallback(
                component='sync_dispatch',
                from_mode='batch',
                to_mode='legacy',
                reason='capacity_full',
                outcome='recovered',
            )
            future_capture_request.mark(FutureCaptureOutcome.ROUTE_DECLINED)
            return None
        if isinstance(conversation_id, str) and target.get('record_lane_owner') == 'legacy_final_pass_v1':
            if mode is LegacySyncMode.ON:
                future_capture_request.mark(FutureCaptureOutcome.PRIOR_CUSTODY)
                return None
            # Legacy can no longer serve this conversation: move its route to batch
            # (the same revision-fenced CAS as every owner transition) and admit
            # below. A held re-home (a live legacy job for the uid, a lost CAS)
            # keeps the in-flight owner's ACK (h, invariant 4); the client retries.
            from utils.sync import final_pass_rehome

            rehome = await run_blocking(db_executor, final_pass_rehome.upload_rehome, mode, uid, conversation_id)
            if not final_pass_rehome.rehomes_to_batch(rehome):
                future_capture_request.mark(FutureCaptureOutcome.PRIOR_CUSTODY)
                return legacy_dark.fence_response(
                    legacy_dark.FenceDecision(
                        legacy_dark.FenceAction.ACK,
                        legacy_dark.LegacyDarkReason.LEGACY_ACTIVE,
                        legacy_dark.LegacyOwnership.ACTIVE,
                    ),
                    total_files=len(paths),
                    lane=lane,
                )
        language = _declared_language(target, user)
        # Switch-off retains legacy sync's input; new custody inherits known
        # context. Previous batch receipts above always keep their original lane.
        prefs = user.get('transcription_preferences') or {}
        input_language = normalized_stt_language(user.get('language')) if prefs.get('single_language_mode') else 'multi'
        inherit = language_inheritance_enabled()
        inherited = profile_inherited_language(target, user, inherit)
        if inherited:
            language = inherited
            if language_class(inherited) == 'supported':
                # Bound supported context outranks a later user single-mode
                # preference, including in the legacy eligibility guard.
                input_language = inherited
        elif inherit:
            # Unknown declarations are classification inputs, not capability
            # proof, even if single-language mode was selected.
            language = input_language = 'multi'
        if admission_language is not None:
            language = input_language = admission_language
        if sampled or admission_language == 'multi':
            # The user's declared language (or a multilingual profile's supported pin, admitted unsampled
            # while legacy drains or is dark) is not capability proof without single-language mode.
            inherited = None
            language = input_language = 'multi'
        if mode is LegacySyncMode.ON and language_guard_enabled() and language_class(input_language) == 'unsupported':
            # Main's prerecorded language guard; with legacy draining or dark the C8
            # provider-STT route below serves unsupported speech instead of legacy.
            record_route('intake', input_language, 'multilingual')
            record_fallback(
                component='stt_selection', from_mode='batch', to_mode='modulate', reason='other', outcome='recovered'
            )
            if evidence is not None:
                evidence.language_excluded = True
            future_capture_request.mark(FutureCaptureOutcome.ROUTE_DECLINED)
            return None
        if (
            mode is LegacySyncMode.ON
            and target.get('record_lane_owner') != 'batch_sync_v1'
            and known_unsupported_batch_language(language)
        ):
            # Batch eligibility (lead 41e13b, scope 304254): the conversation-or-user
            # language names a language the batch Parakeet model cannot serve, so the
            # worker guard would quarantine its speech. Keep it on legacy sync before
            # any custody or probe spend. Blank, 'multi' and unknown languages are not
            # known-unsupported and stay admitted exactly as before. A conversation
            # with a durable batch-sync owner never falls through to legacy here.
            record_route('intake', language, 'multilingual')
            logger.info('event=batch_language_eligibility outcome=legacy reason=known_unsupported_language')
            if evidence is not None:
                evidence.language_excluded = True
            future_capture_request.mark(FutureCaptureOutcome.ROUTE_DECLINED)
            return None
        if inherited:
            input_language = inherited
        # All-vendor routing: outside its cohort, with its kill switch off, or while this
        # owner's legacy is on, this is resolve_route exactly (today's routing). Configured
        # priorities may overflow only when their own GPU backlog is past its SLO.
        route = select_route(
            language,
            byok=byok_enabled,
            uid=uid,
            batch_percent=policy.batch_percent,
            vendor_eligible=vendor_table and mode is not LegacySyncMode.ON,
            gpu_saturated=(
                (lambda: overflow_enabled() and gpu_overflow.saturated(store, int(seed.priority)))
                if int(seed.priority) in overflow_priorities()
                else None
            ),
        ).route
        # C8: with legacy draining or dark, a language Parakeet cannot serve goes
        # to the batch provider-STT stage instead of the legacy fallback; inside the
        # vendor-routing cohort a supported language may also take a vendor route.
        provider = mode is not LegacySyncMode.ON and route.stt_route == 'provider'
        # Contract (c): admission records the route it actually takes. A unit that
        # stays on Parakeet keeps only the BYOK funding decision (lane 6's dispatch
        # re-check reads job['policy']['provider_reason']).
        policy = replace(
            policy,
            stt_route='provider' if provider else 'parakeet',
            provider_reason=route.provider_reason if provider else ('byok' if byok_enabled else 'none'),
            provider_service=route.provider_service if provider else 'none',
        )
        # legacy_sync 'on' keeps today's fallback exactly, including unknown and
        # 'multi' languages.
        if (
            mode is LegacySyncMode.ON
            and policy.live_record_enabled
            and (route.stt_route == 'provider' or language in {'', 'multi'})
        ):
            # Keep the supported existing provider route. Never silently send
            # an unsupported language to the record worker's fixed Parakeet.
            record_fallback(
                component='stt_selection', from_mode='none', to_mode='none', reason='other', outcome='recovered'
            )
            future_capture_request.mark(FutureCaptureOutcome.ROUTE_DECLINED)
            return None
        record_origin = bool(
            not provider
            and target
            and source == 'desktop'
            and policy.live_record_enabled
            and not target.get('uses_custom_stt')
            and user.get('private_cloud_sync_enabled', True)
            # The same conversation-or-user language as the escape above: a blank
            # conversation language must replace, not append beside provisional text.
            and language in PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL['nvidia/parakeet-tdt-0.6b-v3']
        )
        phase = 'artifact_setup'
        artifacts = await run_blocking(storage_executor, artifacts_for, store)
        upload_arguments = {
            'uid': uid,
            'job_id': job_id,
            'content_id': content_id,
            'paths': paths,
            'lane': lane,
            'recording_age_seconds': recording_age_seconds,
            'source': source,
            'should_lock': should_lock,
            'conversation_id': conversation_id,
            'client_device_id': client_device_id,
            'client_platform': client_platform,
            'byok_enabled': byok_enabled,
            'intake_context': intake_context,
        }
        held_response = await _coalescing_try_offer(
            store,
            artifacts,
            seed,
            context,
            language,
            policy,
            (
                _coalescing_group,
                previous,
                adopt,
                provider,
                sampled,
                record_origin,
                decode,
                repair_job_id,
                release,
                usage_period,
                uid,
                language,
                input_language,
            ),
            upload_arguments,
            evidence,
        )
        if held_response is not None:
            return held_response
        config = provider_config()
        if config.pool_kind != 'dedicated_batch':
            raise ValueError('serving intake requires a dedicated batch GPU pool')
        deterministic_key, memo_hit = await _cached_decode_refusal(uid, content_id, paths, decode)
        if memo_hit:
            future_capture_request.mark(FutureCaptureOutcome.DECODE_MEMO_HIT)
            return _sync_unavailable_response()
        # A sampled upload is held whole before staging, so no single unit may exceed the hold bound.
        max_unit_seconds = min(config.max_unit_seconds, SAMPLE_SCAN_SECONDS) if sampled else config.max_unit_seconds
        decode_paths = paths
        if sampled and decode is None:
            sample_directory, decode_paths = await run_blocking(sync_executor, _private_sample_paths, paths)
        iterator = (
            decode(max_unit_seconds)
            if decode is not None
            else decode_for_intake(
                decode_paths,
                max_unit_seconds,
                uid,
                _source_decode_context(
                    intake_context,
                    client_device_id,
                    source,
                    should_lock,
                    record_origin,
                    conversation_id,
                    sampled,
                    _coalescing_group,
                ),
                decoder=upload_decoder(uid, client_device_id, intake_context),
            )
        )
        items = []
        source_aliases = {}

        # Experiment batch_frame_outcomes: the source frames each unit holds, kept for the status read.
        frame_runs: dict[str, tuple] = {}

        def unit_item(unit, index):
            item = unit_work_item(unit, index)
            frame_runs[item.segment_id] = getattr(unit, 'coverage_runs', ())
            return item

        def unit_work_item(unit, index):
            return replace(
                seed,
                segment_id=hashlib.sha256(f'{content_id}:{index}'.encode()).hexdigest(),
                capture_at=(
                    unit.stored_capture_at if getattr(unit, 'stored_capture_at', None) is not None else unit.capture_at
                ),
                duration_seconds=unit.duration_seconds,
                unit_kind='conversation' if conversation_id else 'capture_span',
                conversation_id=conversation_id
                or getattr(unit, 'recovery_id', None)
                or chunk_identity(uid, source, client_device_id, should_lock, unit.capture_at),
                privacy_generation=context.generation,
                # The built-in decoder times WAL PCM from sync filenames.
                # Alternate adapters (for example held WAV) have no such proof.
                timing_store='sync' if decode is None else None,
                source_reuse_key=getattr(unit, 'source_reuse_key', None),
                capture_time_trust='untrusted' if getattr(unit, 'recovery_id', None) else None,
            )

        from utils.stt.batch_language import resolve_language
        from utils.batch_pipeline.language_probe_authorization import ServingLanguageProbeGuard

        # A sampled upload is decided whole before anything is staged: every unit's strict-VAD
        # speech must be Parakeet-safe vendor audio LID, and every further 30 s of it a Parakeet
        # language to the self gate, so no admitted unit meets the worker's language barrier or
        # sends later speech in another language to Parakeet. Strict-silent units keep today's own
        # per-unit LID (an unknown answer preserves the barrier for speech the worker VAD finds);
        # no unit inherits another's language.
        queue, decisions = [], {}
        if sampled:

            def set_sample_phase(value):
                nonlocal phase
                phase = value

            sample = await _sample_language_units(
                iterator, unit_item, store, input_language, uid, target, user, evidence, set_sample_phase
            )
            if sample is None:
                future_capture_request.mark(FutureCaptureOutcome.ROUTE_DECLINED)
                return None
            queue, decisions = sample
        # A missing-input repair replays these exact decisions; it never probes again.
        repair_languages: dict[str, dict] = {}
        packing = IntakePacking(upload_arguments, canonical_decode=decode is None)
        phase = 'decode'
        while unit := (
            queue.pop(0) if queue else None if sampled else await run_blocking(sync_executor, _next_unit, iterator)
        ):
            if len(items) >= 128:
                raise ValueError('capture bundle exceeds bounded conversation-unit limit')
            item = unit_item(unit, len(items))
            if item.source_reuse_key:
                from utils.batch_pipeline.source_reuse_intake import stage_alias

                alias = await stage_alias(
                    store,
                    artifacts,
                    item,
                    unit,
                    {
                        **(intake_context or {}),
                        'owner_id': uid,
                        'job_id': public_job_id,
                        'content_id': content_id,
                        'segment_id': item.segment_id,
                        'capture_at': item.capture_at,
                        'source': source,
                        'should_lock': should_lock,
                        'client_device_id': client_device_id,
                        'client_platform': client_platform,
                    },
                )
                if alias is not None:
                    staged, proposal = alias
                    items.append(staged)
                    source_aliases[item.segment_id] = proposal
                    packing.note_alias(item.segment_id)
                    continue
            if len(items) in decisions:
                # This unit was classified above under fresh authority (silent units on their own audio).
                language_decision = decisions[len(items)]
            else:
                phase = 'language_probe'
                probe_guard = ServingLanguageProbeGuard(store, item, authorize=batch_artifact_authorize)
                # Every self/vendor classification gets fresh dispatch authority on CPU.
                language_decision = await run_blocking(
                    sync_executor,
                    resolve_language,
                    input_language,
                    unit.wav,
                    surface='batch',
                    cohort_key=uid,
                    before_probe=probe_guard,
                    before_self_probe=probe_guard,
                )
                # Refusal preserves the caller's source; never acknowledge or admit it.
                probe_guard.raise_if_denied()
            proof = _frozen_language_proof(input_language, language_decision)
            repair_languages[item.segment_id] = proof
            packing.note(item.segment_id, unit, proof)
            phase = 'freeze_audio'
            frozen = await run_blocking(
                sync_executor,
                with_context,
                unit.wav,
                {
                    **(intake_context or {}),
                    'owner_id': uid,
                    'job_id': public_job_id,
                    'content_id': content_id,
                    'segment_id': item.segment_id,
                    'capture_at': item.capture_at,
                    'source': source,
                    'should_lock': should_lock,
                    'client_device_id': client_device_id,
                    'client_platform': client_platform,
                    'conversation_id': conversation_id,
                    'capture_coverage_runs': list(getattr(unit, 'coverage_runs', ())),
                    **proof,
                },
            )
            phase = 'stage_audio'
            uri = await run_blocking(storage_executor, artifacts.stage_audio, item, frozen)
            # Provider units are funded by the provider stage, not GPU compute admission.
            items.append(replace(item, audio_uri=uri, requires_compute_admission=not provider))
            phase = 'decode'
        if not items and serving_for('CAPTURE_COVERAGE_MODE', uid):
            return covered_response()
        binding = ProjectionBinding(
            owner_id=uid,
            job_id=public_job_id,
            content_id=content_id,
            segment_ids=tuple(item.segment_id for item in items),
            source=source,
            client_device_id=client_device_id,
            client_platform=client_platform,
            is_locked=should_lock,
            private_cloud_sync_enabled=bool(user.get('private_cloud_sync_enabled', True)),
            data_protection_level=context.level,
            target_conversation_id=conversation_id,
            privacy_generation=context.generation,
            language=inherited or target.get('language'),
            record_origin=record_origin,
        )
        wakes: dict[str, str] = {}
        phase = 'admit'
        outbox = await run_blocking(db_executor, outbox_for, OutboxKind.PROVIDER_STT) if provider else None
        intake_refusal = await _probe_upload_allowance(store, uid, policy, lane, items, source_aliases)
        accepted_at = time.time()
        packing_observations = packing.observations(
            subscription=user.get('subscription'),
            protection=context,
            policy=policy,
            priority=seed.priority,
            release=release,
            now=accepted_at,
            excluded=(provider, sampled, record_origin, repair_job_id, _coalescing_group, adopt, usage_period),
            input_language=input_language,
            language=language,
        )
        outcome = await run_blocking(
            db_executor,
            admit,
            store,
            items,
            binding,
            accepted_at,
            namespace=store.namespace,
            policy=policy,
            require_artifacts=True,
            intake={
                'owner_id': uid,
                'owner_key': owner_key(uid),
                'content_id': content_id,
                'conversation_id': conversation_id,
                'segment_ids': list(binding.segment_ids),
                'total_files': len(paths),
                'total_audio_seconds': sum(item.duration_seconds for item in items),
                'lane': lane,
                'repair_lineage': lineage_record(intake_context),
                'repair_languages': repair_languages,
                **context_fields(intake_context),
                # Funded period the owner's choice was made in (cap-hold re-entry); projection
                # attributes usage to it across a month rollover (lane 6, Subscription ruling B).
                **({'usage_period': usage_period} if usage_period else {}),
                # An automatic release (trial or conversion) is backfill the owner did not tap for;
                # its rows carry the source so hard-3 and the 2h alarm can count it apart.
                **({'release': release} if release else {}),
                # Experiment batch_frame_outcomes: that mapping otherwise exists only inside the
                # encrypted staged audio, which the status route cannot read. Off, nothing is added.
                **frame_outcomes.intake_fields(uid, frame_runs),
            },
            enqueue=provider_enqueue(route, outbox, wakes) if provider else None,
            adopt=adopt,
            coalescing_group=_coalescing_group,
            source_aliases=source_aliases,
            packing_observations=packing_observations,
            intake_refusal=intake_refusal,
        )
        phase = 'wake'
        for row_id, wake_token in wakes.items():
            try:
                await run_blocking(db_executor, outbox.wake, row_id, wake_token)  # type: ignore[union-attr]
            except Exception as error:
                # The row is durable; the outbox sweep re-wakes it (contract (b), invariant 4).
                logger.warning(
                    'event=batch_provider_stt action=wake outcome=deferred exception_type=%s', type(error).__name__
                )
        if adopt is not None and outcome['outcome'] == 'batch' and outcome.get('job_id') == public_job_id:
            legacy_dark.record_dark_ack(legacy_dark.LegacyDarkReason.LEGACY_STRANDED_ADOPTED)
        if outcome['outcome'] == 'batch':
            # Only this request's own admission is fresh work: a concurrent
            # winner commits the same content and admit returns its existing
            # job (Luna r2), which is a re-ACK, not a new admission.
            if evidence is not None and outcome.get('job_id') == public_job_id:
                evidence.batch_accepted = True
            phase = 'status_read'
            status = await run_blocking(db_executor, durable_status, store, uid, outcome['job_id'])
            return start_response(status) if status else sync_content_in_progress_response(outcome['job_id'])
        return sync_content_in_progress_response(outcome.get('job_id'))
    except BatchPrivacyBlocked:
        future_capture_request.mark(FutureCaptureOutcome.PREFLIGHT_REFUSED)
        return privacy_blocked_response()
    except Exception as error:
        return await _upload_failure_response(
            error, phase, started, decode is None, deterministic_key, uid, content_id, paths
        )
    finally:
        if iterator is not None:
            await run_blocking(sync_executor, iterator.close)
        if sample_directory is not None:
            await run_blocking(sync_executor, shutil.rmtree, sample_directory, True)


async def _upload_failure_response(
    error: Exception,
    phase: str,
    started: float,
    uses_wal_decoder: bool,
    deterministic_key: str | None,
    uid: str,
    content_id: str,
    paths: list[str],
) -> JSONResponse:
    if isinstance(error, (FutureCaptureRefused, FutureCaptureRetry)):
        return JSONResponse(status_code=error.status_code, headers=error.headers, content=error.detail)
    # A transaction may have committed even when its reply was lost. Keep
    # the staging outbox for reconciliation; never release/re-route content.
    # The sampled path advances the same decoder over the same bytes under
    # its own phase (`sample_decode`) before anything is staged; its probe
    # phase classifies already-decoded audio, so a decoder fault can only
    # surface while the sample itself is being decoded.
    deterministic = phase in ('decode', 'sample_decode') and uses_wal_decoder and is_deterministic_decode_failure(error)
    if deterministic and decode_failure_memo_enabled():
        # These bytes cannot decode however often they are retried. Remember
        # the proven failure so the next retry answers the same 503 without
        # decoding or staging again. The response never changes.
        try:
            key = deterministic_key or await run_blocking(sync_executor, _decode_failure_key, uid, content_id, paths)
            if key:
                await run_blocking(db_executor, remember_decode_failure, key)
                logger.info('event=batch_intake_decode_memo outcome=stored')
        except Exception:
            # A memo is an optimization: never let it replace the 503.
            logger.info('event=batch_intake_decode_memo outcome=degraded')
    logger.error(
        'event=batch_intake outcome=retry exception_type=%s phase=%s deterministic=%s elapsed_ms=%d',
        type(error).__name__,
        phase,
        'yes' if deterministic else 'no',
        round((time.monotonic() - started) * 1000),
    )
    return _sync_unavailable_response()


async def _sample_language_units(
    iterator, unit_item, store, input_language, uid, target, user, evidence, set_phase
) -> tuple[list, dict] | None:
    """Decide a sampled upload whole before staging, preserving phase and privacy fences."""
    from utils.stt.batch_language import resolve_language, self_language_class
    from utils.batch_pipeline.language_probe_authorization import ServingLanguageProbeGuard

    queue, decisions, first = [], {}, None
    set_phase('sample_decode')
    speeches = []
    while unit := await run_blocking(sync_executor, _next_unit, iterator):
        if len(queue) >= 128 or sum(u.duration_seconds for u in queue) + unit.duration_seconds > (SAMPLE_SCAN_SECONDS):
            return _sampled_refusal(target, user, evidence)
        queue.append(unit)
        try:
            speeches.append(await run_blocking(sync_executor, _speech_windows, unit.wav))
        except Exception:
            return _sampled_refusal(target, user, evidence)  # a VAD failure is not silence
    if all(speech is None for speech in speeches):
        # No strict-VAD speech to sample: nothing was probed or staged; the upload keeps legacy.
        return _sampled_refusal(target, user, evidence)
    for index, (unit, speech) in enumerate(zip(queue, speeches)):
        set_phase('language_probe')
        # Every probe of the upload runs here, so any refusal happens before anything is staged.
        # Authorize each as the exact unit it will replay as (index, derived conversation).
        probe_guard = ServingLanguageProbeGuard(store, unit_item(unit, index), authorize=batch_artifact_authorize)
        decision = await run_blocking(
            sync_executor,
            resolve_language,
            input_language,
            speech[0] if speech is not None else unit.wav,
            surface='batch',
            cohort_key=uid,
            before_probe=probe_guard,
            before_self_probe=probe_guard,
        )
        probe_guard.raise_if_denied()
        decisions[index] = decision
        if speech is None:
            continue
        # Only vendor audio LID admits: worker self-LID evidence is bound to the unit's first 30 s.
        if not decision.parakeet_safe or decision.evidence != 'audio_lid':
            return _sampled_refusal(target, user, evidence)
        # The vendor heard only this unit's first 30 s of speech; the rest is frozen with it.
        for window in speech[1:]:
            capability = await run_blocking(sync_executor, self_language_class, window, before_probe=probe_guard)
            probe_guard.raise_if_denied()
            record_sample_window(capability)
            if capability != 'supported':
                return _sampled_refusal(target, user, evidence)
        first = first or decision
    if first is not None:  # always set here: at least one speech unit passed above
        record_route('intake', first.language, 'parakeet')
    return queue, decisions


async def _coalescing_try_offer(
    store,
    artifacts,
    seed,
    context,
    language,
    policy,
    eligibility: tuple,
    arguments: dict,
    evidence: IntakeRouteEvidence | None,
) -> JSONResponse | None:
    if upload_capture_trust(arguments.get('intake_context')) == 'untrusted':
        return None  # Do not pack independent unknown-date sources together.
    if not _coalescing_eligible(*eligibility):
        return None
    from utils.batch_pipeline.upload_coalescing import offer

    response = await offer(
        store, artifacts, seed, context=context, language=language, policy=policy, arguments=arguments
    )
    if response is not None and response.status_code == 202 and evidence is not None:
        evidence.batch_accepted = True
    return response


async def _coalescing_previous(store, previous, public_job_id, group) -> dict:
    """A reentry owns only this exact held receipt, under its drain lease."""
    if group is None:
        return previous
    from database.batch_pipeline_coalescing import guard

    await run_blocking(db_executor, store.run, lambda tx: guard(tx, group, time.time()))
    if group['mode'] == 'individual' and previous.get('job_id') == public_job_id:
        held = await run_blocking(db_executor, store.run, lambda tx: tx.get('intakes', public_job_id))
        if held.get('coalesce_group') == group['id'] and not held.get('coalesce_target'):
            return {}
    return previous


def _coalescing_generation(group) -> int | None:
    return group['privacy_generation'] if group is not None else None


def _coalescing_language(user, target, group) -> tuple[dict, dict]:
    if group is None:
        return user, target
    # Freeze only the initially declared supported language. All privacy and
    # consent fields continue to come from the current authoritative snapshots.
    language = group['members'][0]['language']
    return (
        {
            **user,
            'language': language,
            'transcription_preferences': {
                **(user.get('transcription_preferences') or {}),
                'single_language_mode': True,
            },
        },
        {**target, 'language': language},
    )


def _coalescing_eligible(
    group,
    previous,
    adopt,
    provider,
    sampled,
    record_origin,
    decode,
    repair_job_id,
    release,
    usage_period,
    uid,
    language,
    input_language,
):
    return (
        group is None
        and not previous
        and adopt is None
        and not provider
        and not sampled
        and not record_origin
        and decode is None
        and repair_job_id is None
        and not release
        and not usage_period
        and not serving_for('CAPTURE_COVERAGE_MODE', uid)
        and language in PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL['nvidia/parakeet-tdt-0.6b-v3']
        and language not in {'', 'multi'}
        and input_language == language
    )


def stranded_adopter(observed: dict, *, owner_job_present: bool | None = None):
    """admit() ``adopt`` hook: take over only the legacy row we classified, still stranded, unchanged.

    ``owner_job_present`` is the Redis probe made for ``observed``; the field
    match pins the same owner job id, so it still applies inside the CAS.
    """
    fields = ('dispatch_protocol', 'status', 'job_id', 'updated_at', 'repeat_failure_pause_until')
    expected = tuple(observed.get(name) for name in fields)

    def adopt(existing: dict) -> bool:
        return (
            tuple(existing.get(name) for name in fields) == expected
            and legacy_dark.classify_ledger_row(existing, owner_job_present=owner_job_present)
            is legacy_dark.LegacyOwnership.STRANDED
        )

    return adopt


def privacy_blocked_response() -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            'code': 'sync_batch_privacy_blocked',
            'detail': 'Capture is unavailable for server processing',
        },
    )


async def _repair_prior_upload(
    store, previous: dict, uid: str, content_id: str, paths, repair_job_id: str | None, decode, binding: dict
) -> JSONResponse | None:
    """The original batch owner's missing-span repair; a 409 when the retry is not that upload.

    Kept out of ``accept_upload`` so that function stays within the type checker's complexity bound.
    """
    if repair_job_id is not None and not _repair_owner_matches(previous, repair_job_id):
        # A regrouped/subset retry must never enter fresh admission. The
        # client retains every surviving file and the original repair tag.
        return JSONResponse(
            status_code=409,
            content={
                'code': 'sync_repair_bundle_changed',
                'detail': 'The original complete upload is required; retain local audio',
            },
        )
    if previous.get('dispatch_protocol') == 'batch_v1' and previous.get('artifact_missing_units'):
        # A fresh owner would lose batch checkpoint identities. Repair
        # only missing spans under the original content/job binding.
        from utils.batch_pipeline.artifact_reupload import restore_upload

        repair_artifacts = await run_blocking(storage_executor, artifacts_for, store)
        await restore_upload(store, uid, content_id, paths, artifacts=repair_artifacts, decode=decode, **binding)
    return None


def _repair_owner_matches(ledger: dict, job_id: object) -> bool:
    return (
        isinstance(job_id, str)
        and job_id.startswith(JOB_PREFIX)
        and len(job_id) <= 128
        and '/' not in job_id
        and ledger.get('dispatch_protocol') == 'batch_v1'
        and ledger.get('job_id') == job_id
    )


def repair_upload_owner_matches(uid: str, content_id: str, job_id: str) -> bool:
    """Read-only original-owner proof before archiving or waiving new-upload age.

    Admission rechecks this row and every privacy/binding fence transactionally;
    this lookup cannot grant a fresh owner, processing, completion or a write.
    """
    store = shadow_from_env(FirestoreStore(f'batch_pipeline_{current_stage()}'))
    return store.run(lambda tx: _repair_owner_matches(tx.get('content', f'{uid}/{content_id}'), job_id))


def _wal_receipt_status(uid: str, job_id: str) -> dict | None:
    # WAL receipts are Firestore-owned and independent of ordinary jobstore
    # shadow/index modes, including released clients' headerless status polls.
    return durable_status(FirestoreStore(f'batch_pipeline_{current_stage()}'), uid, job_id, poll=True)


def get_durable_job_status(job_id: str, uid: str, *, artifact_retry: bool = False) -> dict | None:
    if not job_id.startswith(JOB_PREFIX):
        return None
    if len(job_id) > 128 or '/' in job_id:
        raise HTTPException(status_code=404, detail='Sync job not found')
    if job_id.startswith(wal_receipts.JOB_PREFIX):
        status = _wal_receipt_status(uid, job_id)
    else:
        store = FirestoreStore(f'batch_pipeline_{current_stage()}')
        witnessed, status = wal_duplicate.terminal_status(store, uid, job_id)
        # A2 seam: durable_status may redrive a dead job (writes jobs/queues/control).
        if not witnessed:
            status = durable_status(shadow_from_env(store), uid, job_id, poll=True)
    if status is None:
        raise HTTPException(status_code=404, detail='Sync job not found')
    if status.get('reason_code') == 'batch_artifact_missing' and not artifact_retry:
        # Released clients regroup terminal failures and cannot preserve the
        # original content identity. Only a capable exact-bundle client retries.
        return {**status, 'status': 'processing', 'poll_after_ms': 300000}
    return status


def _frozen_language_proof(input_language, decision):
    frozen = (
        decision.language
        if decision.parakeet_safe or language_class(decision.language) == 'unsupported'
        else 'und' if language_guard_enabled() else input_language
    )
    return language_proof(frozen, decision)


def _source_decode_context(context, device, source, locked, record_origin, conversation_id, sampled, group):
    return {
        **(context or {}),
        'client_device_id': device,
        'source': source,
        'should_lock': locked,
        'source_reuse_excluded': bool(record_origin or conversation_id or sampled or group),
    }


async def _cached_decode_refusal(uid, content_id, paths, decode):
    if decode is not None or not decode_failure_memo_enabled():
        return None, False
    # Identical bytes and decoder faults keep the existing retryable response.
    key = await run_blocking(sync_executor, _decode_failure_key, uid, content_id, paths)
    if key and await run_blocking(db_executor, cached_decode_failure, key):
        OMI_PIPELINE_RECORD_WAIT_MEMO_HITS_TOTAL.labels(memo='decode_failure').inc()
        logger.info('event=batch_intake_decode_memo outcome=hit')
        return key, True
    return key, False
