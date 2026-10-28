"""Flagged sync admission. Failures never fall through to the legacy dispatcher."""

from dataclasses import replace
import hashlib
import logging
import time

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from config.batch_pipeline import known_unsupported_batch_language, language_inheritance_enabled, priority_for
from config.batch_language_recovery import inherited_language
from config.batch_pipeline_language import admission_language_exclusion_enabled, batch_admission_language
from config.policy import BatchUnitPolicy, resolve_batch_policy
from config.batch_pipeline_providers import provider_config
from config.prerecorded_language import language_guard_enabled, language_class
from config.stt_provider_policy import normalized_stt_language, PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL
from database.batch_pipeline_intake import admit, cache_completed
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_store import FirestoreStore
from database.batch_pipeline_shadow_hook import shadow_from_env
from database.sync_ledger import (
    BATCH_PARTIAL_STATUS,
    is_valid_completed_sync_content_result,
    is_valid_partial_sync_content_result,
)
from utils.batch_pipeline.artifact_policy import artifacts_for
from utils.batch_pipeline.audio import with_context
from utils.batch_pipeline.capture_decode import decode_units
from utils.capture.batch_coverage import decode_for_intake, covered_response
from config.refactor_modes import serving_for
from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem
from database.outbox import OutboxKind, outbox_for
from utils.batch_pipeline.provider_stt import provider_enqueue, resolve_route
from utils.sync import legacy_dark
from utils.sync.legacy_dark import LegacySyncMode
from utils.batch_pipeline.language_metrics import record_admission_exclusion, record_route
from utils.batch_pipeline.retention import batch_artifact_authorize
from utils.batch_pipeline.scheduler import Scheduler, owner_key
from utils.executors import db_executor, run_blocking, storage_executor, sync_executor
from utils.observability.fallback import record_fallback
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


def _next_unit(iterator):
    # StopIteration cannot cross asyncio Future boundaries.
    return next(iterator, None)


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
    return job.get('state') == 'quarantined' and job.get('recovery_state') == 'failed_held'


def _held_status(jobs: list[dict]) -> tuple[str, str | None] | None:
    """Terminal or waiting answer for uploads whose failures are all held units."""
    from config.batch_pipeline import held_terminal_status_enabled

    failed = [
        job
        for job in jobs
        if job.get('state') == 'quarantined' and job.get('recovery_state') not in {'held', 'prepared', 'running'}
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
    return 'completed', HELD_REASON_CODE


def _deleted_conversation_status(ledger: dict, intake: dict, job_id: str) -> dict | None:
    result = ledger.get('result')
    if not isinstance(result, dict) or not (
        (ledger.get('status') == 'completed' and is_valid_completed_sync_content_result(result))
        or (ledger.get('status') == BATCH_PARTIAL_STATUS and is_valid_partial_sync_content_result(result))
    ):
        return None
    total = result['total_segments']
    return {
        'job_id': job_id,
        'status': 'completed',
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


def durable_status(store, uid: str, job_id: str) -> dict | None:
    def read(tx):
        intake = tx.get('intakes', job_id)
        if not intake:
            return None
        if intake['owner_id'] != uid:
            raise HTTPException(status_code=403, detail='Not authorized to view this sync job')
        ledger = tx.get('content', f"{uid}/{intake['content_id']}")
        jobs = [tx.get('jobs', segment) for segment in intake['segment_ids']]
        sources = {job.get('conversation_id') for job in jobs if job.get('conversation_id')}
        result_ids = ledger.get('result') or {}
        sources.update(result_ids.get('new_memories') or [])
        sources.update(result_ids.get('updated_memories') or [])
        try:
            tx.check_privacy(uid, sources, jobs[0].get('privacy_generation') if jobs else None)
        except BatchPrivacyBlocked as error:
            # Completed content whose conversation the user deleted is final:
            # ACK without IDs so the phone stops re-uploading deleted audio.
            # Unfinished work and every other denial keep the 409.
            terminal = _deleted_conversation_status(ledger, intake, job_id) if is_conversation_deleted(error) else None
            if terminal is None:
                raise
            generation = jobs[0].get('privacy_generation') if jobs else None
            confirm_only_user_deletions(lambda one: tx.check_privacy(uid, one, generation), sources)
            logger.info('event=batch_intake_status outcome=conversation_deleted_terminal')
            return terminal
        result = ledger.get('result')
        completed = ledger.get('status') == 'completed' and is_valid_completed_sync_content_result(result)
        if not completed:
            for job in jobs:
                Scheduler.redrive_in_transaction(tx, job, time.time())
        if ledger.get('status') == BATCH_PARTIAL_STATUS and is_valid_partial_sync_content_result(result):
            # Terminal for the phone: projected siblings are published, the held
            # units' audio stays server-side, and a later recovery upgrades the
            # ledger. Released apps ACK `completed`.
            held_count, total = result['held_segments'], result['total_segments']
            return {
                'job_id': job_id,
                'status': 'completed',
                'lane': intake['lane'],
                'total_files': intake['total_files'],
                'total_segments': total,
                'processed_segments': total - held_count,
                'successful_segments': total - held_count,
                'failed_segments': held_count,
                'errors': [],
                'result': result,
                'reason_code': HELD_REASON_CODE,
                'poll_after_ms': 0,
            }
        recovering = any(
            job.get('state') == 'quarantined' and job.get('recovery_state') in {'held', 'prepared', 'running'}
            for job in jobs
        )
        failed = sum(
            job.get('state') == 'quarantined' and job.get('recovery_state') not in {'held', 'prepared', 'running'}
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
                'poll_after_ms': 0 if reason_code else 3000,
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
            'poll_after_ms': 0 if completed or failed else 3000,
        }

    return store.run(read)


def start_response(status: dict) -> JSONResponse:
    return JSONResponse(
        status_code=202,
        content={
            key: status[key] for key in ('job_id', 'status', 'total_files', 'total_segments', 'poll_after_ms', 'lane')
        },
    )


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
) -> JSONResponse | None:
    """None preserves a prior legacy receipt; batch outcomes never fall through.

    ``decode(max_seconds)`` replaces WAL decoding of ``paths`` for server-held audio
    (the cap-hold adapter); it must yield the same ``AudioUnit`` shape.
    """
    policy = policy or resolve_batch_policy(uid)
    public_job_id = JOB_PREFIX + job_id
    iterator = None
    try:
        # A2 seam: the sync upload admission (intakes, jobs, owners, queues, control) is mirrored in shadow mode.
        store = await run_blocking(
            db_executor, lambda: shadow_from_env(FirestoreStore(f'batch_pipeline_{current_stage()}'))
        )
        previous = await run_blocking(db_executor, store.run, lambda tx: tx.get('content', f'{uid}/{content_id}'))
        if previous.get('dispatch_protocol') == 'batch_v1':
            status = await run_blocking(db_executor, durable_status, store, uid, previous['job_id'])
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
                logger.info('event=batch_intake outcome=conversation_deleted_terminal')
                return JSONResponse(status_code=200, content=deleted_conversation_result(total))
            if cached:
                status = await run_blocking(db_executor, durable_status, store, uid, public_job_id)
                if status:
                    return start_response(status)
        mode = await run_blocking(db_executor, legacy_dark.current_mode)
        adopt = None
        if previous:
            if mode is LegacySyncMode.ON:
                # Existing legacy ownership includes capped/retryable/missing-Redis
                # recovery. Its original claimant remains the sole authority.
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
                return legacy_dark.fence_response(decision, total_files=len(paths), lane=lane)
            adopt = stranded_adopter(previous, owner_job_present=owner_job_present)
        if not policy.batch_enabled:
            # Main's owner-load filter (ramp narrowing) applies only after durable
            # dispatch ownership checks; accepted batch receipts above always drain.
            if mode is LegacySyncMode.ON:
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
        )
        snapshots = {}
        context = await run_blocking(db_executor, batch_artifact_authorize, store, seed, snapshots=snapshots)
        user = snapshots['user']
        target = snapshots.get('conversations', {}).get(conversation_id) or {}
        # Privacy authorization already loaded this row. Rollback may drain a
        # native owner here without adding an ownership-discovery read to dark
        # uploads, or accidentally admitting a second GPU job.
        if target.get('record_lane_owner') == 'batch_live_v1':
            if record_router is None:
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
            )
        admission_language = None
        if admission_language_exclusion_enabled() and target.get('record_lane_owner') != 'batch_sync_v1':
            admission_language, exclusion_reason = batch_admission_language(user, target)
            if exclusion_reason:
                # This is before re-home, decode, LID or custody. The caller's
                # legacy-dark fence still refuses new legacy work outside ON.
                record_admission_exclusion(
                    target.get('language') or user.get('language'),
                    exclusion_reason,
                    legacy_available=mode is LegacySyncMode.ON,
                )
                return None
        if isinstance(conversation_id, str) and target.get('record_lane_owner') == 'legacy_final_pass_v1':
            if mode is LegacySyncMode.ON:
                return None
            # Legacy can no longer serve this conversation: move its route to batch
            # (the same revision-fenced CAS as every owner transition) and admit
            # below. A held re-home (a live legacy job for the uid, a lost CAS)
            # keeps the in-flight owner's ACK (h, invariant 4); the client retries.
            from utils.sync import final_pass_rehome

            rehome = await run_blocking(db_executor, final_pass_rehome.upload_rehome, mode, uid, conversation_id)
            if not final_pass_rehome.rehomes_to_batch(rehome):
                return legacy_dark.fence_response(
                    legacy_dark.FenceDecision(
                        legacy_dark.FenceAction.ACK,
                        legacy_dark.LegacyDarkReason.LEGACY_ACTIVE,
                        legacy_dark.LegacyOwnership.ACTIVE,
                    ),
                    total_files=len(paths),
                    lane=lane,
                )
        language = normalized_stt_language(target.get('language') or user.get('language'))
        # Switch-off retains legacy sync's input; new custody inherits known
        # context. Previous batch receipts above always keep their original lane.
        prefs = user.get('transcription_preferences') or {}
        input_language = normalized_stt_language(user.get('language')) if prefs.get('single_language_mode') else 'multi'
        inherit = language_inheritance_enabled()
        inherited = inherited_language(target.get('language'), user.get('language')) if inherit else None
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
        if mode is LegacySyncMode.ON and language_guard_enabled() and language_class(input_language) == 'unsupported':
            # Main's prerecorded language guard; with legacy draining or dark the C8
            # provider-STT route below serves unsupported speech instead of legacy.
            record_route('intake', input_language, 'multilingual')
            record_fallback(
                component='stt_selection', from_mode='batch', to_mode='modulate', reason='other', outcome='recovered'
            )
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
            return None
        if inherited:
            input_language = inherited
        route = resolve_route(language, byok=byok_enabled)
        # C8: with legacy draining or dark, a language Parakeet cannot serve goes
        # to the batch provider-STT stage instead of the legacy fallback.
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
        artifacts = await run_blocking(storage_executor, artifacts_for, store)
        config = provider_config()
        if config.pool_kind != 'dedicated_batch':
            raise ValueError('serving intake requires a dedicated batch GPU pool')
        iterator = (
            decode(config.max_unit_seconds)
            if decode is not None
            else decode_for_intake(
                paths,
                config.max_unit_seconds,
                uid,
                {**(intake_context or {}), 'client_device_id': client_device_id},
                decoder=decode_units,
            )
        )
        items = []
        while unit := await run_blocking(sync_executor, _next_unit, iterator):
            if len(items) >= 128:
                raise ValueError('capture bundle exceeds bounded conversation-unit limit')
            from utils.stt.batch_language import resolve_language
            from config.stt_cap_dispatch import execution_admission_enabled
            from utils.stt_cap_dispatch import sync_allowed

            # Classification runs on the CPU intake host, never under the GPU
            # lock or with vendor credentials on a worker. Cap refusal does not
            # license a probe; the worker retains uncertain speech for recovery.
            language_decision = await run_blocking(
                sync_executor,
                resolve_language,
                input_language,
                unit.wav,
                surface='batch',
                cohort_key=uid,
                before_probe=lambda duration=unit.duration_seconds: not execution_admission_enabled(uid, 'batch')
                or sync_allowed(uid, duration, 'modulate', lane='batch'),
            )
            frozen_language = (
                language_decision.language
                if language_decision.parakeet_safe or language_class(language_decision.language) == 'unsupported'
                else 'und' if language_guard_enabled() else input_language
            )
            item = replace(
                seed,
                segment_id=hashlib.sha256(f'{content_id}:{len(items)}'.encode()).hexdigest(),
                capture_at=unit.capture_at,
                duration_seconds=unit.duration_seconds,
                unit_kind='conversation' if conversation_id else 'capture_span',
                conversation_id=conversation_id
                or chunk_identity(uid, source, client_device_id, should_lock, unit.capture_at),
                privacy_generation=context.generation,
            )
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
                    'stt_language': frozen_language,
                    'capture_coverage_runs': list(getattr(unit, 'coverage_runs', ())),
                    'stt_language_evidence': language_decision.evidence,
                    'stt_language_confidence': language_decision.confidence,
                    'stt_language_probe_seconds': language_decision.probe_seconds,
                },
            )
            uri = await run_blocking(storage_executor, artifacts.stage_audio, item, frozen)
            # Provider units are funded by the provider stage, not GPU compute admission.
            items.append(replace(item, audio_uri=uri, requires_compute_admission=not provider))
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
        outbox = await run_blocking(db_executor, outbox_for, OutboxKind.PROVIDER_STT) if provider else None
        outcome = await run_blocking(
            db_executor,
            admit,
            store,
            items,
            binding,
            time.time(),
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
                # Funded period the owner's choice was made in (cap-hold re-entry); projection
                # attributes usage to it across a month rollover (lane 6, Subscription ruling B).
                **({'usage_period': usage_period} if usage_period else {}),
            },
            enqueue=provider_enqueue(route, outbox, wakes) if provider else None,
            adopt=adopt,
        )
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
            status = await run_blocking(db_executor, durable_status, store, uid, outcome['job_id'])
            return start_response(status) if status else sync_content_in_progress_response(outcome['job_id'])
        return sync_content_in_progress_response(outcome.get('job_id'))
    except BatchPrivacyBlocked:
        return privacy_blocked_response()
    except Exception as error:
        # A transaction may have committed even when its reply was lost. Keep
        # the staging outbox for reconciliation; never release/re-route content.
        logger.error('event=batch_intake outcome=retry exception_type=%s', type(error).__name__)
        return JSONResponse(
            status_code=503,
            headers={'Retry-After': '30'},
            content={
                'code': 'sync_batch_unavailable',
                'detail': 'Sync is temporarily unavailable; retain local audio',
            },
        )
    finally:
        if iterator is not None:
            await run_blocking(sync_executor, iterator.close)


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


def get_durable_job_status(job_id: str, uid: str) -> dict | None:
    if not job_id.startswith(JOB_PREFIX):
        return None
    if len(job_id) > 128 or '/' in job_id:
        raise HTTPException(status_code=404, detail='Sync job not found')
    # A2 seam: durable_status may redrive a dead job (writes jobs/queues/control).
    status = durable_status(shadow_from_env(FirestoreStore(f'batch_pipeline_{current_stage()}')), uid, job_id)
    if status is None:
        raise HTTPException(status_code=404, detail='Sync job not found')
    return status
