"""Optional lossless representation for new custody PCM; never a retention policy."""

import os
import subprocess
import threading

from prometheus_client import Counter

DECISIONS = Counter('omi_audio_pcm_storage_total', 'New PCM representation attempts', ['result'])
INPUT_BYTES = Counter('omi_audio_pcm_storage_input_bytes_total', 'PCM bytes considered for new writes')
SAVED_BYTES = Counter('omi_audio_pcm_storage_saved_bytes_total', 'Bytes saved by verified encoding attempts')
_ENCODERS = threading.BoundedSemaphore(2)
_TIMEOUT_SECONDS = 2
_MIN_BYTES = 32000
_MAX_BYTES = 16 * 1024 * 1024


def compact_pcm(pcm: bytes, sample_rate: int, channels: int) -> tuple[bytes, str]:
    """Return FLAC only when smaller and independently decoded byte-for-byte.

    Existing FLAC readers need no new container/version. Missing ffmpeg, busy
    workers, timeouts, codec errors and incompressible data all retain PCM.
    Limits bound optional work before the existing durable commit barrier.
    """
    result = 'disabled'
    payload, codec = pcm, 'pcm16'
    if os.getenv('AUDIO_CUSTODY_PCM_COMPRESSION_ENABLED', 'true').strip().lower() != 'true':
        DECISIONS.labels(result).inc()
        return payload, codec
    INPUT_BYTES.inc(len(pcm))
    if not (_MIN_BYTES <= len(pcm) <= _MAX_BYTES) or channels != 1 or len(pcm) % 2:
        result = 'ineligible'
    elif not _ENCODERS.acquire(blocking=False):
        result = 'busy'
    else:
        try:
            common = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-threads', '1']
            encoded = subprocess.run(
                common
                + [
                    '-f',
                    's16le',
                    '-ar',
                    str(sample_rate),
                    '-ac',
                    '1',
                    '-i',
                    'pipe:0',
                    '-map_metadata',
                    '-1',
                    '-fflags',
                    '+bitexact',
                    '-flags:a',
                    '+bitexact',
                    '-c:a',
                    'flac',
                    '-compression_level',
                    '0',
                    '-threads',
                    '1',
                    '-f',
                    'flac',
                    'pipe:1',
                ],
                input=pcm,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=_TIMEOUT_SECONDS,
            ).stdout
            result = 'not_smaller'
            if encoded and len(encoded) * 100 <= len(pcm) * 95:
                decoded = subprocess.run(
                    common + ['-f', 'flac', '-i', 'pipe:0', '-f', 's16le', '-c:a', 'pcm_s16le', 'pipe:1'],
                    input=encoded,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    check=True,
                    timeout=_TIMEOUT_SECONDS,
                ).stdout
                result = 'mismatch'
                if decoded == pcm:
                    payload, codec, result = encoded, 'flac', 'flac'
                    SAVED_BYTES.inc(len(pcm) - len(encoded))
        except (OSError, subprocess.SubprocessError):
            result = 'encoder_error'
        finally:
            _ENCODERS.release()
    DECISIONS.labels(result).inc()
    return payload, codec
