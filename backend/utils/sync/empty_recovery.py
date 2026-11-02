"""Strict local silence evidence and one multilingual attempt for legacy sync."""

import io
import math
import os
import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from pydub import AudioSegment

from config.prerecorded_stt import TranscriptionOutcome
from utils.batch_pipeline.recovery_disposition import inspect_audio
from utils.stt.outcomes import TranscriptionFailure


def enabled() -> bool:
    return os.getenv('SYNC_EMPTY_MULTILINGUAL_RECOVERY_ENABLED', 'false').lower() == 'true'


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


def recover(
    path: str | Path,
    *,
    transcribe: Callable[..., Any],
    authorize: Callable[[], None],
    observe: Callable[[float | None, list[dict] | None], None] | None = None,
) -> tuple[list[dict], str, float, list[dict]]:
    """Only validated zero-span VAD authorizes silence; all uncertainty fails closed.

    The input is the existing local segment. Canonicalize supported legacy PCM
    formats, rejecting truncated input before conversion. Provider metadata never
    receives the source WAV's ancillary chunks. The caller owns funded admission.
    """
    try:
        pcm, duration, spans = inspect_strict(path)
    except Exception:
        if observe is not None:
            observe(None, None)
        raise
    # Observe every strict verdict before admission/provider/result handling can
    # fail. Logging only successful recovery would bias the speech-loss sample.
    if observe is not None:
        observe(duration, spans)
    if not spans:
        return [], '', duration, spans
    authorize()
    clean = io.BytesIO()
    with wave.open(clean, 'wb') as wav:
        wav.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        wav.writeframes(pcm)
    response = transcribe(clean.getvalue(), return_language=True, language='multi', attempts=2)
    try:
        if not isinstance(response, tuple) or len(response) != 2:
            raise ValueError('response shape')
        words, language = response
        if not isinstance(words, list) or not isinstance(language, str) or not language:
            raise ValueError('response shape')
        previous = -1.0
        for word in words:
            start, end = map(float, word['timestamp'])
            if (
                not all(math.isfinite(v) for v in (start, end))
                or not 0 <= start <= end <= duration + 0.01
                or start < previous
                or not isinstance(word['text'], str)
                or not word['text'].strip()
            ):
                raise ValueError('word shape')
            previous = start
    except Exception:
        raise RuntimeError('sync empty recovery response invalid') from None
    if not words:
        raise TranscriptionFailure(TranscriptionOutcome.EMPTY_UNEXPECTED, provider='modulate')
    return words, language, duration, spans
