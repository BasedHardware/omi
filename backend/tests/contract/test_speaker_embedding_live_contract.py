"""Live contract test: speaker embedding through the backend client against the diarizer (WP5, ADR-0035).

Exercises the backend's own client — utils.stt.speaker_embedding.extract_embedding_from_bytes,
which POSTs to {HOSTED_SPEAKER_EMBEDDING_API_URL}/v2/embedding — against a running diarizer
(pyannote/wespeaker on GPU or CPU). Proves the on-prem diarization wiring end to end.

Gated on HOSTED_SPEAKER_EMBEDDING_API_URL (skips in CI). Reaches the server on loopback under
--network host. Run:

  docker run --rm --network host \
    -e HOSTED_SPEAKER_EMBEDDING_API_URL=http://127.0.0.1:8080 \
    -v /work/omi/src/omi:/repo -w /repo/backend omi-onprem-backend-test:v2 \
    python -m pytest tests/contract/test_speaker_embedding_live_contract.py -q -p no:cacheprovider
"""

import io
import math
import os
import struct
import wave

import numpy as np
import pytest

from utils.stt.speaker_embedding import extract_embedding_from_bytes

pytestmark = pytest.mark.skipif(
    not os.getenv('HOSTED_SPEAKER_EMBEDDING_API_URL', '').strip(),
    reason='HOSTED_SPEAKER_EMBEDDING_API_URL not set — live diarizer server required',
)


def _tone_wav(freq: float, seconds: float = 2.0, sr: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = b''.join(
            struct.pack('<h', int(12000 * math.sin(2 * math.pi * freq * i / sr))) for i in range(int(sr * seconds))
        )
        w.writeframes(frames)
    return buf.getvalue()


def _cos(a, b) -> float:
    a = np.ravel(a).astype(float)
    b = np.ravel(b).astype(float)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def test_extract_embedding_returns_real_vector():
    # The diarizer returns a numpy array of shape (1, D) — flatten to inspect it.
    vec = np.ravel(extract_embedding_from_bytes(_tone_wav(180.0)))
    assert vec.size > 0
    assert np.any(vec != 0.0), 'expected a non-trivial embedding'


def test_embedding_is_deterministic_and_discriminative():
    a1 = np.ravel(extract_embedding_from_bytes(_tone_wav(180.0)))
    a2 = np.ravel(extract_embedding_from_bytes(_tone_wav(180.0)))
    b = np.ravel(extract_embedding_from_bytes(_tone_wav(330.0)))
    assert a1.size == a2.size == b.size
    # Same audio -> same embedding; different audio -> different embedding.
    assert _cos(a1, a2) > 0.999
    assert _cos(a1, b) < _cos(a1, a2)
