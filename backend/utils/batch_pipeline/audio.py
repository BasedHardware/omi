"""Strict CPU decode and capture-clock packing for encrypted intake staging.

Queue units span at most one hour; model windowing remains worker-owned. Never
acknowledge a bundle with a dropped file/frame or replace capture gaps by speech.
"""

import audioop
from dataclasses import dataclass
import io
import json
import os
import struct
import wave
from collections.abc import Generator

from utils.batch_pipeline.contracts import INTAKE_CONTEXT_CHUNK, INTAKE_CONTEXT_VERSION, INTAKE_CONTEXT_LIMIT
from utils.sync.files import MAX_SYNC_FRAME_BYTES, decode_files_to_wav, get_timestamp_from_path

RATE = 16000
UNIT_FRAMES = 3600 * RATE
MAX_JOIN_GAP_FRAMES = 30 * RATE


@dataclass(frozen=True)
class AudioUnit:
    capture_at: float
    wav: bytes
    duration_seconds: float


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


def _unit(capture_at: float, pcm: bytes) -> AudioUnit:
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
        stream.writeframes(pcm)
    return AudioUnit(capture_at, output.getvalue(), len(pcm) / (2 * RATE))


def decode_units(paths: list[str], *, max_seconds: float = 3600) -> Generator[AudioUnit, None, None]:
    unit_frames = min(UNIT_FRAMES, int(max_seconds * RATE))
    if unit_frames < 1 or max_seconds > 7200:
        raise ValueError('invalid dedicated capture-unit ceiling')
    expected = {path.replace('.bin', '.wav'): _frame_count(path) for path in paths}
    frames: dict[str, list[int]] = {}
    wavs = []
    try:
        wavs = decode_files_to_wav(paths, frames)
        if set(wavs) != set(expected) or any(len(frames.get(path, [])) != count for path, count in expected.items()):
            raise ValueError('sync decode did not preserve every uploaded frame')
        pending = bytearray()
        start = 0.0
        for path in sorted(wavs, key=lambda value: (get_timestamp_from_path(value), value)):
            capture = float(get_timestamp_from_path(path))
            pcm = _canonical(path)
            if not pcm:
                raise ValueError('empty decoded sync audio')
            end = start + len(pending) / (2 * RATE)
            gap = round((capture - end) * RATE)
            if pending and (gap < 0 or gap > MAX_JOIN_GAP_FRAMES or len(pending) + gap * 2 >= unit_frames * 2):
                yield _unit(start, bytes(pending))
                pending.clear()
            if not pending:
                start = capture
            elif gap > 0:
                pending.extend(b'\0' * (gap * 2))
            offset = 0
            while offset < len(pcm):
                take = min(unit_frames * 2 - len(pending), len(pcm) - offset)
                pending.extend(pcm[offset : offset + take])
                offset += take
                if len(pending) == unit_frames * 2:
                    yield _unit(start, bytes(pending))
                    pending.clear()
                    start = capture + offset / (2 * RATE)
        if pending:
            yield _unit(start, bytes(pending))
    finally:
        for path in set(wavs) | set(expected):
            if os.path.exists(path):
                os.remove(path)


def with_context(wav: bytes, context: dict) -> bytes:
    """Freeze provenance inside the encrypted WAV, outside the PCM data chunk."""
    body = json.dumps(
        {**context, 'version': INTAKE_CONTEXT_VERSION}, allow_nan=False, sort_keys=True, separators=(',', ':')
    ).encode()
    if len(body) > INTAKE_CONTEXT_LIMIT or wav[:4] != b'RIFF' or wav[8:12] != b'WAVE':
        raise ValueError('invalid bounded intake context or WAV')
    chunk = INTAKE_CONTEXT_CHUNK + struct.pack('<I', len(body)) + body + (b'\0' if len(body) % 2 else b'')
    result = wav + chunk
    return result[:4] + struct.pack('<I', len(result) - 8) + result[8:]


def read_context(wav: bytes) -> dict:
    if wav[:4] != b'RIFF' or wav[8:12] != b'WAVE' or struct.unpack('<I', wav[4:8])[0] != len(wav) - 8:
        raise ValueError('invalid intake WAV envelope')
    offset, result = 12, None
    while offset + 8 <= len(wav):
        name, size = wav[offset : offset + 4], struct.unpack('<I', wav[offset + 4 : offset + 8])[0]
        offset += 8
        if offset + size > len(wav):
            raise ValueError('truncated intake WAV chunk')
        if name == INTAKE_CONTEXT_CHUNK:
            if result is not None or size > INTAKE_CONTEXT_LIMIT:
                raise ValueError('duplicate or oversized intake context')
            result = json.loads(wav[offset : offset + size])
        offset += size + (size % 2)
    if offset != len(wav) or not isinstance(result, dict) or result.get('version') != INTAKE_CONTEXT_VERSION:
        raise ValueError('authenticated intake context is required')
    return result
