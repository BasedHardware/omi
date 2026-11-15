"""Strict future-only decoding; main's early-clock decoder remains untouched."""

import os
from dataclasses import replace

from utils.batch_pipeline.audio import RATE, audio_unit
from utils.batch_pipeline.capture_decode import canonical_pcm, validated_frame_count
from utils.sync.files import decode_files_to_wav
from utils.capture.batch_coverage import prepare, piece_runs, provenance_unit
from utils.sync.files import get_timestamp_from_path
from utils.sync.receipt_clock import receipt_clock_offsets, require_future_run


def decode_future_units(paths, *, uid, device_id, received_at, max_seconds=3600, coverage_context=None):
    require_future_run(paths, received_at=received_at)
    frames_per_unit = int(max_seconds * RATE)
    if frames_per_unit < 1 or max_seconds > 7200:
        raise ValueError('invalid dedicated capture-unit ceiling')
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
        )
        for source in sorted(wavs, key=get_timestamp_from_path):
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
                    yield replace(unit, stored_capture_at=start - offsets[source])
    finally:
        for path in set(wavs) | set(expected) | generated:
            if os.path.exists(path):
                os.remove(path)
