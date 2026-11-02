"""GPU-independent canonical WAV and authenticated capture-context envelope."""

from dataclasses import dataclass
import io
import json
import struct
import wave

from utils.batch_pipeline.contracts import INTAKE_CONTEXT_CHUNK, INTAKE_CONTEXT_VERSION, INTAKE_CONTEXT_LIMIT

RATE = 16000


@dataclass(frozen=True)
class AudioUnit:
    capture_at: float
    wav: bytes
    duration_seconds: float
    coverage_runs: tuple[dict, ...] = ()


def audio_unit(capture_at: float, pcm: bytes) -> AudioUnit:
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
        stream.writeframes(pcm)
    return AudioUnit(capture_at, output.getvalue(), len(pcm) / (2 * RATE))


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
