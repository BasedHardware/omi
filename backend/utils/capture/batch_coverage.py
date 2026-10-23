"""Source-frame provenance across batch packing, without capture-clock inference."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from dataclasses import replace
import logging

from config import refactor_modes
from models.capture_coverage import CaptureKey, CoverageRecord, FrameRange
from utils.capture import coverage
from utils.capture.sync_coverage import failed, key_for_claim, trim_maps

logger = logging.getLogger(__name__)
MAX_RUNS = 32


def prepare(uid, wavs, frames, context):
    from utils.sync.wal_audio_coverage import build_sync_source_frame_maps

    if not refactor_modes.shadow_or_serve(coverage.FLAG) or not context:
        return wavs, {}, set()
    maps = build_sync_source_frame_maps(context.get('capture_evidence_claims'), wavs, frames)
    paths, maps, generated = trim_maps(
        uid,
        wavs,
        maps,
        device_id=context.get('client_device_id'),
        recording_session_id=context.get('recording_session_id'),
        origin='batch',
    )
    # Caller owns cleanup of every derivative, including on early generator close.
    return paths, maps, generated


def piece_runs(mapping, source_start, count, unit_start, context):
    """Only full source frames in canonical mono 16k audio have a projection."""
    if not mapping or mapping['claim']['rate_hz'] != 16000:
        return []
    offsets, claim = mapping['offsets'], mapping['claim']
    first = bisect_left(offsets, source_start)
    last = bisect_right(offsets, source_start + count) - 1
    runs = []
    for index in range(first, last):
        samples = offsets[index + 1] - offsets[index]
        frame = claim['source_frame_start'] + index
        if runs and runs[-1]['end'] == frame and runs[-1]['samples_per_frame'] == samples:
            runs[-1]['end'] = frame + 1
        else:
            runs.append(
                {
                    'key': key_for_claim(
                        claim, context.get('client_device_id'), context.get('recording_session_id')
                    ).model_dump(),
                    'start': frame,
                    'end': frame + 1,
                    'sample_start': unit_start + offsets[index] - source_start,
                    'samples_per_frame': samples,
                }
            )
        if len(runs) > MAX_RUNS:
            return []
    return runs


def provenance_unit(unit, runs):
    return replace(unit, coverage_runs=tuple(runs) if len(runs) <= MAX_RUNS else ())


def decode_for_intake(paths, max_seconds, uid, context, *, decoder):
    if not context or not context.get('capture_evidence_claims') or not refactor_modes.shadow_or_serve(coverage.FLAG):
        return decoder(paths, max_seconds=max_seconds)
    return decoder(paths, max_seconds=max_seconds, coverage_context={**context, 'uid': uid})


def covered_response():
    from fastapi.responses import JSONResponse

    # No job was admitted and no paid call was made: the committed frame ledger
    # is already the durable receipt. Retries independently reproduce this ACK.
    return JSONResponse(
        status_code=200,
        content={
            'new_memories': [],
            'updated_memories': [],
            'failed_segments': 0,
            'total_segments': 0,
            'errors': [],
            'outcome': 'success',
        },
    )


def claims_for_segments(incoming, manifest, *, capture_at):
    """Receipts for frame interiors actually represented by projected words."""
    if not manifest:
        return []
    runs = manifest.get('capture_coverage_runs') or []
    if len(runs) > MAX_RUNS:
        return []
    claims = []
    for segment in incoming.get('transcript_segments', []):
        a = round((incoming['started_at'].timestamp() - capture_at + segment['start']) * 16000)
        b = round((incoming['started_at'].timestamp() - capture_at + segment['end']) * 16000)
        for run in runs:
            step = run['samples_per_frame']
            if type(step) is not int or step <= 0:
                continue
            first = max(run['start'], run['start'] + max(0, (a - run['sample_start'] + step - 1) // step))
            last = min(run['end'], run['start'] + (b - run['sample_start']) // step)
            if first < last:
                claims.append((CaptureKey.model_validate(run['key']), FrameRange(start=first, end=last), segment))
    return claims


def admit_projection(uid, incoming, manifest, *, capture_at):
    """Projection race recheck. Never drops a partially covered segment."""
    if not refactor_modes.shadow_or_serve(coverage.FLAG):
        return
    try:
        from utils.capture_evidence import merge_track_receipts

        receipts, proven = [], set()
        for segment in incoming.get('transcript_segments', []):
            a = round((incoming['started_at'].timestamp() - capture_at + segment['start']) * 16000)
            b = round((incoming['started_at'].timestamp() - capture_at + segment['end']) * 16000)
            for run in (manifest or {}).get('capture_coverage_runs') or []:
                step = run['samples_per_frame']
                if (
                    step <= 0
                    or not run['sample_start'] <= a < b <= run['sample_start'] + (run['end'] - run['start']) * step
                ):
                    continue
                key = CaptureKey.model_validate(run['key'])
                start, start_offset = divmod(a - run['sample_start'], step)
                end, end_offset = divmod(b - run['sample_start'], step)
                start, end = start + run['start'], end + run['start']
                decision = coverage.admit(
                    uid, key, [FrameRange(start=start, end=end + bool(end_offset))], origin='batch'
                )
                if not decision.uncovered:
                    proven.add(id(segment))
                receipts.append(
                    {
                        'segment_id': segment['id'],
                        'capture_root': key.capture_root,
                        'channel': key.channel,
                        'clock_epoch': int(key.clock_epoch),
                        'source_start_frame': start,
                        'source_start_offset': start_offset,
                        'source_end_frame': end,
                        'source_end_offset': end_offset,
                        'rate_hz': 16000,
                        'producer_revision': 'batch_projection_v1',
                    }
                )
                break
        if receipts and refactor_modes.serving_for(coverage.FLAG, uid):
            incoming['capture_evidence'] = merge_track_receipts([], receipts)
            incoming['capture_evidence'].update(
                client_device_id=manifest.get('client_device_id'),
                recording_session_id=manifest.get('recording_session_id'),
            )
        if proven:
            logger.info(
                'event=refactor_shadow lane=L1 check=batch_projection outcome=disagree covered_segments=%d', len(proven)
            )
        if refactor_modes.serving_for(coverage.FLAG, uid):
            incoming['transcript_segments'] = [s for s in incoming['transcript_segments'] if id(s) not in proven]
    except Exception as error:
        failed('batch_projection', error)


def record_projection(uid, incoming, assigned, manifest, *, capture_at, survivors=None):
    if not refactor_modes.shadow_or_serve(coverage.FLAG):
        return
    try:
        committed = {s['id'] for s in (survivors if survivors is not None else incoming.get('transcript_segments', []))}
        for key, span, segment in claims_for_segments(incoming, manifest, capture_at=capture_at):
            if segment['id'] not in committed:
                continue
            coverage.record(uid, key, CoverageRecord(conversation_id=assigned['id'], origin='batch', ranges=[span]))
    except Exception as error:
        failed('batch_record', error)


def optional_manifest(projector, item, hint):
    """Provider units carry the same authenticated context as GPU units."""
    if not refactor_modes.shadow_or_serve(coverage.FLAG):
        return None
    from utils.batch_pipeline.audio import read_context

    try:
        prefetched = hint.prefetched if hint is not None else None
        if prefetched is not None and prefetched.manifest is not None:
            return prefetched.manifest
        # Shadow may reuse work already paid for, never download a whole WAV.
        if not refactor_modes.serving_for(coverage.FLAG, item.owner_id) or projector.fetch_audio is None:
            return None
        return read_context(projector.fetch_audio(item))
    except Exception as error:
        failed('batch_manifest', error)
        return None
