"""Exact-content missing-input repair, without a new projection or ledger owner."""

from dataclasses import fields
import math
from pathlib import Path
import time

from database.batch_pipeline_artifact_missing import ArtifactMissingStore
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from utils.batch_pipeline.retention import batch_artifact_authorize
from utils.batch_pipeline.audio import with_context
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.capture_decode import decode_units
from utils.batch_pipeline.language_probe_authorization import ServingLanguageProbeGuard
from utils.executors import run_blocking, db_executor, storage_executor, sync_executor
from utils.stt.batch_language import resolve_language
from config.prerecorded_language import language_class


async def restore_upload(
    store,
    uid,
    content_id,
    paths,
    *,
    source,
    should_lock,
    conversation_id,
    client_device_id,
    client_platform,
    intake_context,
    artifacts,
    decode=None,
):
    """Only the metadata-proven missing spans enter compute again.

    `content_id` is the router's HMAC of the complete original bytes/names. Every
    decoded unit must match the original ordered capture/duration boundaries;
    decoder drift or changed binding fails closed, retaining phone custody.
    Projected siblings are neither staged nor language-probed. Staged repair
    inputs stay in the ordinary durable outbox after an uncertain CAS reply.
    """
    protocol = ArtifactMissingStore(store)
    plan = await run_blocking(db_executor, protocol.reupload_snapshot, uid, content_id)
    if plan is None:
        return None
    binding, jobs, snapshots = plan
    if (
        source != binding.source
        or should_lock != binding.is_locked
        or conversation_id != binding.target_conversation_id
        or client_device_id != binding.client_device_id
        or client_platform != binding.client_platform
    ):
        raise ProjectionBlocked('re-upload cannot change original projection binding')
    ceiling = max(job['duration_seconds'] for job in jobs)
    iterator = decode(ceiling) if decode is not None else decode_units(paths, max_seconds=ceiling)
    uris, count = {}, 0
    try:
        while (unit := await run_blocking(sync_executor, next, iterator, None)) is not None:
            if count >= len(jobs):
                raise ProjectionBlocked('re-upload unit count changed')
            job = jobs[count]
            count += 1
            if not math.isclose(unit.capture_at, job['capture_at'], rel_tol=0, abs_tol=1 / 16000) or not math.isclose(
                unit.duration_seconds, job['duration_seconds'], rel_tol=0, abs_tol=1 / 16000
            ):
                raise ProjectionBlocked('re-upload capture boundaries changed')
            sid = job['segment_id']
            if sid not in snapshots:
                continue
            item = WorkItem(**{f.name: job[f.name] for f in fields(WorkItem) if f.name in job})
            guard = ServingLanguageProbeGuard(store, item, authorize=batch_artifact_authorize)
            decision = await run_blocking(
                sync_executor,
                resolve_language,
                binding.language,
                unit.wav,
                surface='batch',
                cohort_key=uid,
                before_probe=guard,
                before_self_probe=guard,
            )
            guard.raise_if_denied()
            language = (
                decision.language
                if decision.parakeet_safe or language_class(decision.language) == 'unsupported'
                else 'und'
            )
            frozen = await run_blocking(
                sync_executor,
                with_context,
                unit.wav,
                {
                    **(intake_context or {}),
                    'owner_id': uid,
                    'job_id': binding.job_id,
                    'content_id': content_id,
                    'segment_id': sid,
                    'capture_at': item.capture_at,
                    'source': binding.source,
                    'should_lock': binding.is_locked,
                    'client_device_id': binding.client_device_id,
                    'client_platform': binding.client_platform,
                    'conversation_id': binding.target_conversation_id,
                    'filenames': [Path(path).name for path in paths],
                    'capture_coverage_runs': list(unit.coverage_runs),
                    'stt_language': language,
                    'stt_language_evidence': decision.evidence,
                    'stt_language_confidence': decision.confidence,
                    'stt_language_probe_seconds': decision.probe_seconds,
                },
            )
            uris[sid] = await run_blocking(storage_executor, artifacts.stage_audio, item, frozen)
        if count != len(jobs) or set(uris) != set(snapshots):
            raise ProjectionBlocked('complete original upload required for repair')
        return await run_blocking(db_executor, protocol.restore_reupload, uid, content_id, snapshots, uris, time.time())
    finally:
        close = getattr(iterator, 'close', None)
        if close is not None:
            await run_blocking(sync_executor, close)
