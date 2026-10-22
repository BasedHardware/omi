"""S1 adapters for WAL intake: trim before STT, record only after commit."""

from __future__ import annotations

import logging

from config import refactor_modes
from models.capture_coverage import CaptureKey, CoverageRecord, CoverageOrigin, FrameRange
from utils.capture import coverage
from utils.capture.coverage_metrics import SECONDS
from utils.capture_evidence import source_coordinate
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def legacy_audio_trim(uid):
    """Energy/clock heuristics are retained only for the legacy serving path."""
    return not refactor_modes.serving_for(coverage.FLAG, uid)


def key_for_claim(claim: dict, device_id=None, recording_session_id=None) -> CaptureKey:
    return CaptureKey(
        capture_root=claim['capture_root'],
        channel=claim['channel'],
        clock_epoch=str(claim['clock_epoch']),
        device_id=device_id,
        recording_session_id=recording_session_id,
    )


def failed(check: str, error: Exception) -> None:
    logger.warning(
        'event=refactor_shadow lane=L1 check=%s outcome=error exception_type=%s', check, type(error).__name__
    )
    record_fallback(
        component='sync_dispatch', from_mode='none', to_mode='none', reason='other', outcome='degraded', log=logger
    )


def trim_maps(uid, paths, maps, *, device_id=None, recording_session_id=None, origin: CoverageOrigin = 'sync'):
    """Uses the S1 materializer without decoding, joining or inferring frames."""
    from utils.sync.wal_audio_coverage import apply_wal_audio_coverage
    from utils.sync.audio_coverage import plan_unreceived_frames

    output, mapped, generated = [], {}, set()
    serving = refactor_modes.serving_for(coverage.FLAG, uid)
    for path in paths:
        mapping = maps.get(path)
        if mapping is None:
            output.append(path)
            continue
        claim, offsets = mapping['claim'], mapping['offsets']
        start = claim['source_frame_start']
        samples = [b - a for a, b in zip(offsets, offsets[1:])]
        try:
            decision = coverage.admit(
                uid,
                key_for_claim(claim, device_id, recording_session_id),
                [FrameRange(start=start, end=start + len(samples))],
                origin=origin,
            )
            covered = [(r.start, r.end) for r in decision.covered]
            keep = plan_unreceived_frames(
                samples, covered, frame_start=start, sample_rate=claim['rate_hz'], context_seconds=0
            )
            dropped = (
                sum(offsets[r.end - start] - offsets[r.start - start] for r in decision.covered) / claim['rate_hz']
            )
            materialized = apply_wal_audio_coverage(path, claim, samples, keep, frame_map=mapping) if serving else None
            if serving and materialized is None:
                failed('audio_materialize', ValueError('coverage materialization abstained'))
            if dropped and (not serving or materialized is not None):
                SECONDS.labels(origin=origin, outcome='skipped' if serving else 'would_skip').inc(dropped)
                logger.info(
                    'event=refactor_shadow lane=L1 check=audio_admit outcome=disagree covered_seconds=%.3f', dropped
                )
        except Exception as error:
            failed('audio_admit', error)
            materialized = None
        if materialized is None:
            output.append(path)
            mapped[path] = mapping
        else:
            output.extend(materialized['wav_paths'])
            mapped.update(materialized['frame_maps'])
            generated.update(materialized['generated_paths'])
    return output, mapped, generated


async def apply_sync_coverage(
    uid,
    source,
    should_lock,
    client_device_id,
    recording_session_id,
    capture_evidence_claims,
    wav_paths,
    decoded_frames,
    cleanup_paths: set[str] | None = None,
    **dependencies,
):
    from utils.sync.wal_audio_coverage import apply_sync_wal_audio_coverage, build_sync_source_frame_maps

    if refactor_modes.shadow_or_serve(coverage.FLAG):
        original = list(wav_paths)
        maps = build_sync_source_frame_maps(capture_evidence_claims, wav_paths, decoded_frames)
        wav_paths, maps, generated = await dependencies['run_blocking'](
            dependencies['db_executor'],
            trim_maps,
            uid,
            wav_paths,
            maps,
            device_id=client_device_id,
            recording_session_id=recording_session_id,
        )
        if refactor_modes.serving_for(coverage.FLAG, uid):
            # Retired originals and generated WAVs remain owned by the job cleanup.
            if cleanup_paths is not None:
                cleanup_paths.update(original)
                cleanup_paths.update(generated)
            # Keep the S1-trimmed derivative maps intact; old lookup must not rebuild them.
            return wav_paths, maps, bool(original and not wav_paths)
    # refactor: superseded by utils.capture.coverage when CAPTURE_COVERAGE_MODE=serve
    return await apply_sync_wal_audio_coverage(
        uid,
        source,
        should_lock,
        client_device_id,
        recording_session_id,
        capture_evidence_claims,
        wav_paths,
        decoded_frames,
        **dependencies,
    )


def annotate_identity(incoming, device_id=None, recording_session_id=None):
    evidence = incoming.get('capture_evidence')
    if refactor_modes.shadow_or_serve(coverage.FLAG) and isinstance(evidence, dict):
        # Unpositioned legacy uploads have no envelope. Missing optional identity
        # must not turn a successful upload into an exception or rewrite its row.
        if device_id:
            evidence['client_device_id'] = device_id
        if recording_session_id:
            evidence['recording_session_id'] = recording_session_id


def covering_target(uid, source_position_map, path, *, device_id=None, recording_session_id=None):
    """A committed same-key owner is a binding hint, revalidated by assignment."""
    if not refactor_modes.shadow_or_serve(coverage.FLAG) or source_position_map is None:
        return None
    import wave

    mapping, sample_start = source_position_map
    try:
        with wave.open(path, 'rb') as audio:
            count = audio.getnframes()
        start, end = source_coordinate(mapping, sample_start), source_coordinate(mapping, sample_start + count)
        if start is None or end is None:
            return None
        first, last = start[0], end[0] + bool(end[1])
        if first >= last:
            return None
        result = coverage.query(
            uid, key_for_claim(mapping['claim'], device_id, recording_session_id), [FrameRange(start=first, end=last)]
        )
        return result.covering_conversation_id if refactor_modes.serving_for(coverage.FLAG, uid) else None
    except Exception as error:
        failed('binding', error)
        return None


def record_sync(
    uid, incoming, assigned, source_position_map, path, *, device_id=None, recording_session_id=None, survivors=None
):
    if not refactor_modes.shadow_or_serve(coverage.FLAG) or source_position_map is None:
        return
    mapping, _ = source_position_map
    try:
        committed_ids = {
            str(s['id']) for s in (survivors if survivors is not None else incoming.get('transcript_segments', []))
        }
        ranges = []
        for receipt in (incoming.get('capture_evidence') or {}).get('receipts') or []:
            if receipt.get('segment_id') not in committed_ids:
                continue
            first = receipt['source_start_frame'] + bool(receipt['source_start_offset'])
            last = receipt['source_end_frame']
            if first < last:
                ranges.append(FrameRange(start=first, end=last))
        if ranges:
            coverage.record(
                uid,
                key_for_claim(mapping['claim'], device_id, recording_session_id),
                CoverageRecord(conversation_id=assigned['id'], origin='sync', ranges=ranges),
            )
    except Exception as error:
        failed('record', error)


def held_segment(uid, path, meta):
    """Recheck an old VAD hold before paying for its recovery transcription."""
    position = meta.get('source_position_map')
    original = ({path}, {path: tuple(position) if position else None}, {}, {})
    if not position or not refactor_modes.shadow_or_serve(coverage.FLAG):
        return original
    import wave

    try:
        mapping, sample_start = position
        with wave.open(path, 'rb') as audio:
            count = audio.getnframes()
        first, last = source_coordinate(mapping, sample_start), source_coordinate(mapping, sample_start + count)
        # Splitting through a source frame needs a richer sample receipt; abstain.
        if first is None or last is None or first[1] or last[1]:
            return original
        frame_start = mapping['claim']['source_frame_start']
        offsets = mapping['offsets'][first[0] - frame_start : last[0] - frame_start + 1]
        claim = {**mapping['claim'], 'source_frame_start': first[0], 'frame_count': last[0] - first[0]}
        subset = {**mapping, 'claim': claim, 'offsets': [value - sample_start for value in offsets]}
        paths, maps, _ = trim_maps(
            uid,
            [path],
            {path: subset},
            device_id=meta.get('client_device_id'),
            recording_session_id=meta.get('recording_session_id'),
        )
        return set(paths), {p: (m, 0) for p, m in maps.items()}, {}, {}
    except Exception as error:
        failed('held_admit', error)
        return original
