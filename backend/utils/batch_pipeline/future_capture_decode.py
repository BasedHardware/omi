"""Isolated future/estimated-source decoding; main's early-clock decoder is unchanged."""

import os
from dataclasses import replace

from utils.batch_pipeline.audio import RATE, audio_unit
from utils.batch_pipeline.capture_decode import canonical_pcm, validated_frame_count, decode_units
from utils.sync.capture_clock import is_implausible_future_capture_time, is_early_capture_time
from utils.sync.clock_run import capture_clock_run_from_path
from utils.sync.content_id import compute_sync_content_id
from utils.sync.files import decode_files_to_wav
from utils.capture.batch_coverage import prepare, piece_runs, provenance_unit
from utils.sync.files import get_timestamp_from_path
from utils.sync.receipt_clock import receipt_clock_offsets, require_future_upload, retained_source_offsets


def decode_future_units(
    paths,
    *,
    uid,
    device_id,
    received_at,
    max_seconds=3600,
    coverage_context=None,
    retained_offsets_by_name=None,
):
    retained = (
        {
            path: retained_offsets_by_name[os.path.basename(path)]
            for path in paths
            if os.path.basename(path) in retained_offsets_by_name
        }
        if retained_offsets_by_name is not None
        else retained_source_offsets(paths, uid=uid, device_id=device_id, received_at=received_at)
    )
    future = [
        p
        for p in paths
        if p in retained or is_implausible_future_capture_time(get_timestamp_from_path(p), now=received_at)
    ]
    estimated = [
        p
        for p in paths
        if p not in future and capture_clock_run_from_path(p) and not is_early_capture_time(get_timestamp_from_path(p))
    ]
    if not future and not estimated:
        require_future_upload([], received_at=received_at)
    if future:
        yield from _future_units(
            future,
            uid=uid,
            device_id=device_id,
            received_at=received_at,
            max_seconds=max_seconds,
            coverage_context=coverage_context,
            retained=retained,
        )
    for path in sorted(estimated, key=lambda p: (get_timestamp_from_path(p), os.path.basename(p))):
        identity = 'receipt-' + compute_sync_content_id(uid, [path])
        # A normal estimated stamp stays unchanged. The explicit token proves
        # unknown absolute time, never adjacency to a real conversation.
        for unit in decode_units(
            [path], received_at=received_at, max_seconds=max_seconds, coverage_context=coverage_context
        ):
            yield replace(unit, recovery_id=identity)
    ordinary = [p for p in paths if p not in future and p not in estimated]
    if ordinary:
        yield from decode_units(
            ordinary, received_at=received_at, max_seconds=max_seconds, coverage_context=coverage_context
        )


def _future_units(paths, *, uid, device_id, received_at, max_seconds, coverage_context, retained):
    frames_per_unit = int(max_seconds * RATE)
    if frames_per_unit < 1 or max_seconds > 7200:
        raise ValueError('invalid dedicated capture-unit ceiling')
    source_ids = {path.replace('.bin', '.wav'): compute_sync_content_id(uid, [path]) for path in paths}
    expected = {path.replace('.bin', '.wav'): validated_frame_count(path) for path in paths}
    wavs, generated, decoded_frames = [], set(), {}
    try:
        wavs = decode_files_to_wav(paths, decoded_frames)
        if set(wavs) != set(expected) or any(len(decoded_frames.get(p, [])) != n for p, n in expected.items()):
            raise ValueError('sync decode did not preserve every uploaded frame')
        # All full-file anchors and account bounds are checked before yielding
        # even one unit. Coverage derivatives cannot create another offset.
        offsets = receipt_clock_offsets(
            [(p, get_timestamp_from_path(p), len(canonical_pcm(p)) / (2 * RATE)) for p in wavs],
            uid=uid,
            device_id=device_id,
            received_at=received_at,
            source_ids=source_ids,
            retained_offsets={p.replace('.bin', '.wav'): offset for p, offset in retained.items()},
        )
        for source in sorted(wavs, key=lambda p: (get_timestamp_from_path(p), os.path.basename(p))):
            pieces, maps, derivatives = prepare(uid, [source], decoded_frames, coverage_context)
            generated.update(derivatives)
            for path in sorted(pieces, key=get_timestamp_from_path):
                pcm = canonical_pcm(path)
                if not pcm:
                    raise ValueError('empty decoded sync audio')
                for first in range(0, len(pcm), frames_per_unit * 2):
                    payload = pcm[first : first + frames_per_unit * 2]
                    start = get_timestamp_from_path(path) + first / (2 * RATE)
                    runs = piece_runs(maps.get(path), first // 2, len(payload) // 2, 0, coverage_context or {})
                    unit = provenance_unit(audio_unit(start, payload), runs)
                    yield replace(
                        unit, stored_capture_at=start - offsets[source], recovery_id='receipt-' + source_ids[source]
                    )
    finally:
        for path in set(wavs) | set(expected) | generated:
            if os.path.exists(path):
                os.remove(path)
