"""Content-free recovery failures and strict, in-memory silence evidence."""

import io
import wave
from collections.abc import Callable
from typing import Any

STAGES = frozenset({'audio_validation', 'strict_vad', 'provider', 'response_validation', 'payload_validation'})
REASONS = frozenset(
    {
        'invalid_audio',
        'vad_failed',
        'invalid_vad',
        'no_speech',
        'provider_failed',
        'invalid_response',
        'empty_asr',
        'invalid_payload',
        'operation_failed',
        'abandoned_running',
    }
)


class RecoveryFailure(ValueError):
    def __init__(self, stage: str, reason: str):
        self.stage = stage if stage in STAGES else 'provider'
        self.reason = reason if reason in REASONS else 'operation_failed'
        super().__init__(self.reason)


def at_stage(stage: str, reason: str, operation: Callable[[], Any]):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    try:
        return operation()
    except (RecoveryFailure, BatchPrivacyBlocked):
        raise
    except Exception:
        raise RecoveryFailure(stage, reason) from None


def inspect_audio(item, audio, *, vad=None):
    """Return canonical PCM and validated strict VAD; failures never mean silence."""

    def decode():
        with wave.open(io.BytesIO(audio), 'rb') as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 16000):
                raise ValueError('shape')
            duration = wav.getnframes() / 16000
            if not 0 < duration <= 7200 or abs(duration - item.duration_seconds) > 0.1:
                raise ValueError('duration')
            pcm = wav.readframes(wav.getnframes())
            if len(pcm) != wav.getnframes() * 2:
                raise ValueError('truncated')
            return pcm, duration

    pcm, duration = at_stage('audio_validation', 'invalid_audio', decode)
    if vad is None:
        from utils.stt.vad import offline_pcm_speech_segments

        vad = offline_pcm_speech_segments
    raw = at_stage('strict_vad', 'vad_failed', lambda: vad(pcm))

    def validate():
        from utils.batch_pipeline.contracts import projection_speech_spans

        if not isinstance(raw, list):
            raise ValueError('VAD result')
        spans = [{'start': s['start'], 'end': s['end']} for s in raw]
        if spans:
            projection_speech_spans(
                {'speech_spans': spans, 'speech_seconds': sum(s['end'] - s['start'] for s in spans)}, duration
            )
        return spans

    spans = at_stage('strict_vad', 'invalid_vad', validate)
    return pcm, duration, spans


def silence_payload(duration):
    return {
        'audio_seconds': duration,
        'speech_seconds': 0.0,
        'speech_spans': [],
        'words': [],
        'diarization': {'turns': [], 'outcome': 'silence'},
        'words_provider': 'strict_local_vad',
        'recovery_version': 1,
        'outcome': 'silence',
    }


def result_outcome(payload):
    """Only an explicit, fully empty strict-VAD payload can authorize silence."""
    outcome = payload.get('outcome', 'success')
    if outcome == 'silence':
        if (
            payload.get('words') != []
            or payload.get('speech_spans') != []
            or payload.get('speech_seconds') != 0
            or payload.get('words_provider') != 'strict_local_vad'
        ):
            raise RecoveryFailure('payload_validation', 'invalid_payload')
    elif outcome != 'success':
        raise RecoveryFailure('payload_validation', 'invalid_payload')
    return outcome
