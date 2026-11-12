"""GPU-independent canonical WAV and authenticated capture-context envelope.

Every fault this module raises is deterministic on the pinned stored bytes
(the same envelope re-parses and re-authenticates identically on every
attempt), so every raise site carries the family type ``StagedAudioInvalid``
-- the same doctrine as ``decode_pcm16_wav``, ``capture_decode`` and the
retained-audio decoder wrap sites. ``read_context`` was the last intake
envelope reader whose raise sites stayed anonymous: a bare ``ValueError``
here collapsed the whole cohort into the anonymous fault vocabulary prod
books as ``error_class=ValueError stage=fetch_decode`` and walked the
bounded retry ladder on bytes no retry can repair.

Failure-Class: FC-sync-decode-fault-anonymous-at-typed-boundaries
"""

from dataclasses import dataclass
import io
import json
import struct
import wave

from utils.batch_pipeline.contracts import INTAKE_CONTEXT_CHUNK, INTAKE_CONTEXT_VERSION, INTAKE_CONTEXT_LIMIT

RATE = 16000


class StagedAudioInvalid(ValueError):
    """Staged or derived audio that can never decode from these pinned bytes.

    Deterministic on the stored bytes and frozen intake context: a retry
    re-reads the same bytes, re-validates the same envelope and fails the
    same way, so the failure must end the GPU chain at the fetch_decode
    boundary instead of walking the bounded retry ladder. Raise sites carry
    the type and the worker boundary reads the type — never an exception
    message — so a new deterministic decode fault cannot silently drift
    back onto the ladder.
    """


@dataclass(frozen=True)
class AudioUnit:
    capture_at: float
    wav: bytes
    duration_seconds: float
    coverage_runs: tuple[dict, ...] = ()
    stored_capture_at: float | None = None


def audio_unit(capture_at: float, pcm: bytes) -> AudioUnit:
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
        stream.writeframes(pcm)
    return AudioUnit(capture_at, output.getvalue(), len(pcm) / (2 * RATE))


def with_context(wav: bytes, context: dict) -> bytes:
    """Freeze provenance inside the encrypted WAV, outside the PCM data chunk."""
    try:
        body = json.dumps(
            {**context, 'version': INTAKE_CONTEXT_VERSION}, allow_nan=False, sort_keys=True, separators=(',', ':')
        ).encode()
    except ValueError as error:
        # A NaN/Infinity float in the stored context is deterministic on the
        # pinned manifest: re-serializing it can never succeed.
        raise StagedAudioInvalid('invalid bounded intake context or WAV') from error
    if len(body) > INTAKE_CONTEXT_LIMIT or wav[:4] != b'RIFF' or wav[8:12] != b'WAVE':
        raise StagedAudioInvalid('invalid bounded intake context or WAV')
    chunk = INTAKE_CONTEXT_CHUNK + struct.pack('<I', len(body)) + body + (b'\0' if len(body) % 2 else b'')
    result = wav + chunk
    return result[:4] + struct.pack('<I', len(result) - 8) + result[8:]


def read_context(wav: bytes) -> dict:
    if wav[:4] != b'RIFF' or wav[8:12] != b'WAVE' or struct.unpack('<I', wav[4:8])[0] != len(wav) - 8:
        raise StagedAudioInvalid('invalid intake WAV envelope')
    offset, result = 12, None
    while offset + 8 <= len(wav):
        name, size = wav[offset : offset + 4], struct.unpack('<I', wav[offset + 4 : offset + 8])[0]
        offset += 8
        if offset + size > len(wav):
            raise StagedAudioInvalid('truncated intake WAV chunk')
        if name == INTAKE_CONTEXT_CHUNK:
            if result is not None or size > INTAKE_CONTEXT_LIMIT:
                raise StagedAudioInvalid('duplicate or oversized intake context')
            try:
                result = json.loads(wav[offset : offset + size])
            except (ValueError, RecursionError) as error:
                # Corrupt or pathological JSON in the stored chunk is
                # deterministic on the pinned bytes: re-parsing it can never
                # succeed, so it joins the family like the envelope faults.
                raise StagedAudioInvalid('authenticated intake context is required') from error
        offset += size + (size % 2)
    if offset != len(wav) or not isinstance(result, dict) or result.get('version') != INTAKE_CONTEXT_VERSION:
        raise StagedAudioInvalid('authenticated intake context is required')
    return result
