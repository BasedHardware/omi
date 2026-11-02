"""Replay ordinary WAL coverage, VAD and lineage planning for a held capture."""

from pathlib import Path

from config.sync_live_dedupe import sync_lineage_resolve_active_for
from config.sync_safety_wal import sync_safety_wal_enabled
from utils.executors import run_blocking, db_executor, storage_executor, sync_executor
from utils.sync import recording_lineage
from utils.sync.files import get_timestamp_from_path, get_wav_duration
from utils.sync.pipeline import retrieve_vad_segments, cleanup_recovered_sync_files
from utils.sync.safety_wal_coverage import apply_safety_wal_coverage
from utils.capture.sync_coverage import (
    apply_sync_coverage as apply_sync_wal_audio_coverage,
    held_segment,
    legacy_audio_trim,
)


async def prepare(uid: str, path: str, meta: dict) -> tuple[set, dict, dict, dict]:
    if meta.get('origin') == 'live':
        segments, errors, offsets = set(), [], {}
        await run_blocking(
            sync_executor,
            retrieve_vad_segments,
            path,
            segments,
            errors,
            keep_short=True,
            source_frame_map={'live_source_slice': True} if meta.get('live_custody_version') == 4 else None,
            segment_source_maps=offsets,
        )
        if errors:
            raise RuntimeError('held live VAD failed')
        return segments, offsets, {}, {}
    if not meta.get('full_capture'):
        return await run_blocking(db_executor, held_segment, uid, path, meta)
    mapping = meta.get('source_frame_map') or {}
    offsets = mapping.get('offsets') or []
    frames = [end - start for start, end in zip(offsets, offsets[1:])]
    claims = {Path(path).name.replace('.wav', '.bin'): mapping['claim']} if mapping else None
    paths, source_maps, _ = await apply_sync_wal_audio_coverage(
        uid,
        meta['source'],
        False,
        meta.get('client_device_id'),
        meta.get('recording_session_id'),
        claims,
        [path],
        {path: frames},
        run_blocking=run_blocking,
        db_executor=db_executor,
        storage_executor=storage_executor,
        cleanup_files=cleanup_recovered_sync_files,
    )
    # refactor: superseded by utils.capture.coverage when CAPTURE_COVERAGE_MODE=serve
    if sync_safety_wal_enabled() and legacy_audio_trim(uid):
        inputs = list(paths)
        paths, _ = await apply_safety_wal_coverage(
            uid,
            paths,
            meta.get('target_conversation_id'),
            run_blocking=run_blocking,
            db_executor=db_executor,
            storage_executor=storage_executor,
            job_ref='cap_recovery',
            protected_paths=source_maps,
            capture_partition={
                'source': meta['source'],
                'client_device_id': meta.get('client_device_id'),
                'is_locked': False,
            },
        )
        if inputs and not paths:
            paths = inputs  # Same conservative envelope fallback as ordinary sync.
    segments, segment_maps, errors = set(), {}, []
    for wav_path in paths:
        await run_blocking(
            sync_executor,
            retrieve_vad_segments,
            wav_path,
            segments,
            errors,
            source_frame_map=source_maps.get(wav_path),
            segment_source_maps=segment_maps,
        )
    if errors:
        raise RuntimeError('held capture VAD failed')
    targets, bindings = {}, {}
    origin = meta.get('recording_session_id')
    if origin and sync_lineage_resolve_active_for(uid):
        targets = await run_blocking(
            db_executor,
            recording_lineage.plan_segment_targets,
            sorted(segments, key=get_timestamp_from_path),
            get_timestamp_from_path,
            get_wav_duration,
            uid,
            origin,
            meta.get('target_conversation_id'),
            meta['source'],
            meta.get('client_device_id'),
            False,
            meta.get('job_id'),
            bindings,
            segment_source_maps=segment_maps,
        )
    return segments, segment_maps, targets, bindings
