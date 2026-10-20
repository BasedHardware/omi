"""Flagged sync admission. Failures never fall through to the legacy dispatcher."""

from dataclasses import replace
import hashlib
import logging
import os
import time

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from config.batch_pipeline import priority_for
from config.policy import BatchUnitPolicy, resolve_batch_policy
from config.batch_pipeline_providers import provider_config
from config.stt_provider_policy import normalized_stt_language, PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL
from database.batch_pipeline_intake import admit, cache_completed
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_store import FirestoreStore
from database.sync_ledger import is_valid_completed_sync_content_result
from utils.batch_pipeline.artifacts import ArtifactStore
from utils.batch_pipeline.artifact_policy import create_artifact_store
from utils.batch_pipeline.audio import with_context
from utils.batch_pipeline.capture_decode import decode_units
from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem
from database.outbox import OutboxKind, outbox_for
from utils.batch_pipeline.provider_stt import provider_enqueue, resolve_route
from utils.sync import legacy_dark
from utils.sync.legacy_dark import LegacySyncMode
from utils.batch_pipeline.retention import batch_artifact_authorize
from utils.batch_pipeline.scheduler import Scheduler, owner_key
from utils.executors import db_executor, run_blocking, storage_executor, sync_executor
from utils.other.local_storage import create_storage_client
from utils.observability.fallback import record_fallback
from utils.sync.admission_responses import sync_content_in_progress_response
from utils.sync.stage import current_stage
from utils.sync.capture import chunk_identity

logger = logging.getLogger(__name__)
JOB_PREFIX = 'bp_'


def artifacts_for(store: FirestoreStore) -> ArtifactStore:
    bucket = os.getenv('BUCKET_BATCH_PIPELINE', '').strip()
    if not bucket:
        raise RuntimeError('durable batch staging bucket is not configured')
    return create_artifact_store(store, create_storage_client(), bucket, os.getenv('ENCRYPTION_SECRET', '').encode())


def _next_unit(iterator):
    # StopIteration cannot cross asyncio Future boundaries.
    return next(iterator, None)


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
        tx.check_privacy(uid, sources, jobs[0].get('privacy_generation') if jobs else None)
        result = ledger.get('result')
        completed = ledger.get('status') == 'completed' and is_valid_completed_sync_content_result(result)
        if not completed:
            for job in jobs:
                Scheduler.redrive_in_transaction(tx, job, time.time())
        recovering = any(
            job.get('state') == 'quarantined' and job.get('recovery_state') in {'held', 'prepared', 'running'}
            for job in jobs
        )
        failed = sum(
            job.get('state') == 'quarantined' and job.get('recovery_state') not in {'held', 'prepared', 'running'}
            for job in jobs
        )
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
        store = await run_blocking(db_executor, FirestoreStore, f'batch_pipeline_{current_stage()}')
        previous = await run_blocking(db_executor, store.run, lambda tx: tx.get('content', f'{uid}/{content_id}'))
        if previous.get('dispatch_protocol') == 'batch_v1':
            status = await run_blocking(db_executor, durable_status, store, uid, previous['job_id'])
            return start_response(status) if status else sync_content_in_progress_response(previous['job_id'])
        if previous.get('status') == 'completed':
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
        if target.get('record_lane_owner') == 'legacy_final_pass_v1':
            if mode is LegacySyncMode.ON:
                return None
            # The in-flight legacy final pass owns this recording (h, invariant 4).
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
            and normalized_stt_language(target.get('language'))
            in PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL['nvidia/parakeet-tdt-0.6b-v3']
        )
        artifacts = await run_blocking(storage_executor, artifacts_for, store)
        config = provider_config()
        if config.pool_kind != 'dedicated_batch':
            raise ValueError('serving intake requires a dedicated batch GPU pool')
        iterator = (
            decode(config.max_unit_seconds)
            if decode is not None
            else decode_units(paths, max_seconds=config.max_unit_seconds)
        )
        items = []
        while unit := await run_blocking(sync_executor, _next_unit, iterator):
            if len(items) >= 128:
                raise ValueError('capture bundle exceeds bounded conversation-unit limit')
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
                    # Resolved conversation/user STT language ('' when unknown).
                    # The worker skips a Parakeet-only retry for other languages.
                    'stt_language': language,
                },
            )
            uri = await run_blocking(storage_executor, artifacts.stage_audio, item, frozen)
            # Provider units are funded by the provider stage, not GPU compute admission.
            items.append(replace(item, audio_uri=uri, requires_compute_admission=not provider))
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
            language=target.get('language'),
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
    status = durable_status(FirestoreStore(f'batch_pipeline_{current_stage()}'), uid, job_id)
    if status is None:
        raise HTTPException(status_code=404, detail='Sync job not found')
    return status
