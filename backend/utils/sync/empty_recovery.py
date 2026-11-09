"""Strict local silence evidence and one multilingual attempt for legacy sync."""

import io
import wave
from pathlib import Path
from types import SimpleNamespace

from pydub import AudioSegment

from utils.batch_pipeline.recovery_disposition import inspect_audio


def inspect_strict(path: str | Path) -> tuple[bytes, float, list[dict]]:
    """Canonicalize the local segment and run the strict local VAD.

    Shared by the paid multilingual recovery and the (free) empty-success guard.
    Raises RuntimeError on any inspection failure; a failure is never silence
    evidence.
    """
    try:
        audio = Path(path).read_bytes()
        with wave.open(io.BytesIO(audio), 'rb') as original:
            frames = original.getnframes()
            if (
                original.getnchannels() not in (1, 2)
                or original.getsampwidth() not in (1, 2)
                or not 0 < original.getframerate() <= 48000
                or not 0 < frames / original.getframerate() <= 7200
                or len(original.readframes(frames)) != frames * original.getnchannels() * original.getsampwidth()
            ):
                raise ValueError('invalid audio')
        segment = AudioSegment.from_wav(io.BytesIO(audio)).set_channels(1).set_sample_width(2).set_frame_rate(16000)
        output = io.BytesIO()
        segment.export(output, format='wav')
        return inspect_audio(SimpleNamespace(duration_seconds=len(segment.raw_data) / 32000), output.getvalue())
    except Exception:
        # RecoveryFailure is a ValueError; don't misclassify VAD uncertainty as
        # permanent bad user input in the legacy public failure classifier.
        raise RuntimeError('sync empty recovery inspection failed') from None
