"""CPU-only strict WAL decoding and bounded capture-clock packing."""

import audioop
import os
import struct
import wave
from dataclasses import replace
from collections.abc import Generator

from utils.batch_pipeline.audio import RATE, AudioUnit, audio_unit
from utils.sync.files import MAX_SYNC_FRAME_BYTES, decode_files_to_wav, get_timestamp_from_path
from utils.sync.capture_clock import is_early_capture_time

UNIT_FRAMES = 3600 * RATE
MAX_JOIN_GAP_FRAMES = 30 * RATE


def _frame_count(path: str) -> int:
    count = 0
    with open(path, 'rb') as stream:
        while header := stream.read(4):
            if len(header) != 4:
                raise ValueError('truncated sync audio frame')
            size = struct.unpack('<I', header)[0]
            if not 0 < size <= MAX_SYNC_FRAME_BYTES or len(stream.read(size)) != size:
                raise ValueError('invalid sync audio frame')
            count += 1
    if count == 0:
        raise ValueError('empty sync audio')
    return count


def _canonical(path: str) -> bytes:
    with wave.open(path, 'rb') as stream:
        channels, width, rate = stream.getnchannels(), stream.getsampwidth(), stream.getframerate()
        if channels not in {1, 2} or width not in {1, 2, 3, 4} or not 8000 <= rate <= 48000:
            raise ValueError('unsupported sync PCM format')
        pcm = stream.readframes(stream.getnframes())
    if width == 1:
        pcm = audioop.bias(pcm, 1, -128)
    if width != 2:
        pcm = audioop.lin2lin(pcm, width, 2)
    if channels == 2:
        pcm = audioop.tomono(pcm, 2, 0.5, 0.5)
    if rate != RATE:
        pcm, _ = audioop.ratecv(pcm, 2, 1, rate, RATE, None)
    return pcm


# Server-held WAV (the cap-hold adapter) takes the same canonicalization as uploads.
canonical_pcm = _canonical


def decode_units(
    paths: list[str],
    *,
    max_seconds: float = 3600,
    coverage_context: dict | None = None,
    received_at: float | None = None,
) -> Generator[AudioUnit, None, None]:
    unit_frames = min(UNIT_FRAMES, int(max_seconds * RATE))
    if unit_frames < 1 or max_seconds > 7200:
        raise ValueError('invalid dedicated capture-unit ceiling')
    expected = {path.replace('.bin', '.wav'): _frame_count(path) for path in paths}
    frames: dict[str, list[int]] = {}
    wavs = []
    generated = set()
    try:
        wavs = decode_files_to_wav(paths, frames)
        if set(wavs) != set(expected) or any(len(frames.get(path, [])) != count for path, count in expected.items()):
            raise ValueError('sync decode did not preserve every uploaded frame')
        from utils.capture.batch_coverage import prepare, piece_runs, provenance_unit

        wavs, source_maps, generated = prepare((coverage_context or {}).get('uid'), wavs, frames, coverage_context)
        early_paths = {
            path
            for path in wavs
            if received_at is not None
            and is_early_capture_time(
                (source_maps.get(path) or {}).get('capture_clock_at', get_timestamp_from_path(path))
            )
        }
        # Count canonical samples before streaming the units. Untrusted clock
        # gaps cannot place siblings years before receipt or overlap them.
        early_frames = sum(len(_canonical(path)) // 2 for path in wavs if path in early_paths)
        early_committed_frames = 0

        def packed_unit(start, pcm, runs, early):
            nonlocal early_committed_frames
            unit = provenance_unit(audio_unit(start, pcm), runs)
            if early and received_at is not None:
                unit = replace(unit, stored_capture_at=received_at - (early_frames - early_committed_frames) / RATE)
                early_committed_frames += len(pcm) // 2
            return unit

        pending = bytearray()
        pending_runs = []
        start = 0.0
        pending_early = False
        for path in sorted(
            wavs,
            key=lambda value: (
                (source_maps.get(value) or {}).get('capture_clock_at', get_timestamp_from_path(value)),
                get_timestamp_from_path(value),
                value,
            ),
        ):
            capture = float(get_timestamp_from_path(path))
            pcm = _canonical(path)
            if not pcm:
                raise ValueError('empty decoded sync audio')
            end = start + len(pending) / (2 * RATE)
            gap = round((capture - end) * RATE)
            early = path in early_paths
            if early and pending_early:
                gap = 0  # Invalid wall-clock gaps are not silence or timing proof.
            if pending and (
                early != pending_early
                or gap < 0
                or gap > MAX_JOIN_GAP_FRAMES
                or len(pending) + gap * 2 >= unit_frames * 2
            ):
                yield packed_unit(start, bytes(pending), pending_runs, pending_early)
                pending.clear()
                pending_runs = []
            if not pending:
                start = capture
                pending_early = early
            elif gap > 0:
                pending.extend(b'\0' * (gap * 2))
            offset = 0
            while offset < len(pcm):
                take = min(unit_frames * 2 - len(pending), len(pcm) - offset)
                pending_runs.extend(
                    piece_runs(source_maps.get(path), offset // 2, take // 2, len(pending) // 2, coverage_context or {})
                )
                pending.extend(pcm[offset : offset + take])
                offset += take
                if len(pending) == unit_frames * 2:
                    yield packed_unit(start, bytes(pending), pending_runs, pending_early)
                    pending.clear()
                    pending_runs = []
                    start = capture + offset / (2 * RATE)
        if pending:
            yield packed_unit(start, bytes(pending), pending_runs, pending_early)
    finally:
        for path in set(wavs) | set(expected) | generated:
            if os.path.exists(path):
                os.remove(path)
