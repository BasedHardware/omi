"""Exact-content missing-input repair, without a new projection or ledger owner."""

from dataclasses import fields
import logging
import math
from pathlib import Path
import time

from database.batch_pipeline_artifact_missing import ArtifactMissingStore
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from utils.batch_pipeline.audio import with_context
from utils.batch_pipeline.contracts import WorkItem
from utils.batch_pipeline.capture_decode import decode_units
from utils.batch_pipeline.repair_lineage import LANGUAGE_KEYS, LINEAGE_KEYS, recorded_lineage
from utils.executors import run_blocking, db_executor, storage_executor, sync_executor

logger = logging.getLogger(__name__)


def _repair_plan(store, uid, content_id, source, should_lock, conversation_id, client_device_id, client_platform):
    protocol = ArtifactMissingStore(store)
    plan = protocol.reupload_snapshot(uid, content_id)
    if plan is None:
        return protocol, None
    binding, _, _ = plan
    if (
        source != binding.source
        or should_lock != binding.is_locked
        or conversation_id != binding.target_conversation_id
        or client_device_id != binding.client_device_id
        or client_platform != binding.client_platform
    ):
        raise ProjectionBlocked('re-upload cannot change original projection binding')
    return protocol, plan


def _hold(reason):
    logger.warning('event=batch_artifact_repair outcome=held reason=%s', reason)
    error = ProjectionBlocked(f'missing-input repair held: {reason}')
    setattr(error, 'block_reason', reason)
    return error


def _repair_evidence(store, binding, snapshots, intake_context):
    """The original projection inputs, from the durable intake record only; holds when absent.

    Admission records the frozen lineage fields and each unit's language decision
    (lead 6d0246). Repair restages with both as recorded: the retried request's
    lineage fields are discarded, and no unit is probed again. A legacy intake
    has neither, so it holds with phone custody and its audio intact.
    """
    intake = store.run(lambda tx: tx.get('intakes', binding.job_id)) or {}
    record = intake.get('repair_lineage')
    if record is None:
        raise _hold('legacy_lineage_unproven')
    try:
        lineage = recorded_lineage(record)
    except (TypeError, ValueError):
        raise _hold('lineage_unreadable') from None
    context = {key: value for key, value in (intake_context or {}).items() if key not in LINEAGE_KEYS}
    languages = {}
    for sid in snapshots:
        proof = (intake.get('repair_languages') or {}).get(sid)
        if not isinstance(proof, dict) or not isinstance(proof.get('stt_language'), str):
            raise _hold('language_unproven')
        languages[sid] = {key: proof.get(key) for key in LANGUAGE_KEYS}
    return {**context, **lineage}, languages


def _original_unit(jobs, index, unit):
    if index >= len(jobs):
        raise ProjectionBlocked('re-upload unit count changed')
    job = jobs[index]
    if not math.isclose(unit.capture_at, job['capture_at'], rel_tol=0, abs_tol=1 / 16000) or not math.isclose(
        unit.duration_seconds, job['duration_seconds'], rel_tol=0, abs_tol=1 / 16000
    ):
        raise ProjectionBlocked('re-upload capture boundaries changed')
    return job


def _commit_restore(protocol, uid, content_id, snapshots, uris, count, expected):
    if count != expected or set(uris) != set(snapshots):
        raise ProjectionBlocked('complete original upload required for repair')
    return protocol.restore_reupload(uid, content_id, snapshots, uris, time.time())


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
    Projected siblings are not staged, and no unit is language-probed. Staged repair
    inputs stay in the ordinary durable outbox after an uncertain CAS reply.
    """
    protocol, plan = await run_blocking(
        db_executor,
        _repair_plan,
        store,
        uid,
        content_id,
        source,
        should_lock,
        conversation_id,
        client_device_id,
        client_platform,
    )
    if plan is None:
        return None
    binding, jobs, snapshots = plan
    context, languages = await run_blocking(db_executor, _repair_evidence, store, binding, snapshots, intake_context)
    ceiling = max(job['duration_seconds'] for job in jobs)
    iterator = decode(ceiling) if decode is not None else decode_units(paths, max_seconds=ceiling)
    uris, count = {}, 0
    try:
        while (unit := await run_blocking(sync_executor, next, iterator, None)) is not None:
            job = await run_blocking(sync_executor, _original_unit, jobs, count, unit)
            count += 1
            sid = job['segment_id']
            if sid not in snapshots:
                continue
            item = WorkItem(**{f.name: job[f.name] for f in fields(WorkItem) if f.name in job})
            frozen = await run_blocking(
                sync_executor,
                with_context,
                unit.wav,
                {
                    **context,
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
                    **languages[sid],
                },
            )
            uris[sid] = await run_blocking(storage_executor, artifacts.stage_audio, item, frozen)
        return await run_blocking(
            db_executor, _commit_restore, protocol, uid, content_id, snapshots, uris, count, len(jobs)
        )
    finally:
        close = getattr(iterator, 'close', None)
        if close is not None:
            await run_blocking(sync_executor, close)
