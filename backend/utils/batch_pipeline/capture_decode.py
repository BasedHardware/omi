"""CPU-only strict WAL decoding and bounded capture-clock packing."""

import audioop
import os
import struct
import wave
from collections.abc import Generator

from utils.batch_pipeline.audio import RATE, AudioUnit, audio_unit
from utils.sync.files import MAX_SYNC_FRAME_BYTES, decode_files_to_wav, get_timestamp_from_path

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
    paths: list[str], *, max_seconds: float = 3600, coverage_context: dict | None = None
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
        pending = bytearray()
        pending_runs = []
        start = 0.0
        for path in sorted(wavs, key=lambda value: (get_timestamp_from_path(value), value)):
            capture = float(get_timestamp_from_path(path))
            pcm = _canonical(path)
            if not pcm:
                raise ValueError('empty decoded sync audio')
            end = start + len(pending) / (2 * RATE)
            gap = round((capture - end) * RATE)
            if pending and (gap < 0 or gap > MAX_JOIN_GAP_FRAMES or len(pending) + gap * 2 >= unit_frames * 2):
                yield provenance_unit(audio_unit(start, bytes(pending)), pending_runs)
                pending.clear()
                pending_runs = []
            if not pending:
                start = capture
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
                    yield provenance_unit(audio_unit(start, bytes(pending)), pending_runs)
                    pending.clear()
                    pending_runs = []
                    start = capture + offset / (2 * RATE)
        if pending:
            yield provenance_unit(audio_unit(start, bytes(pending)), pending_runs)
    finally:
        for path in set(wavs) | set(expected) | generated:
            if os.path.exists(path):
                os.remove(path)
