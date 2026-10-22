"""Content-free recovery failures and strict, in-memory silence evidence."""

import io
import wave
from collections.abc import Callable
from typing import Any

from utils.observability.reasons import (
    ReasonFamily,
    RecoveryFailureReason,
    RecoveryFailureStage,
    reason_label,
    reason_values,
)

STAGES = reason_values(RecoveryFailureStage)
REASONS = reason_values(RecoveryFailureReason)


class RecoveryFailure(ValueError):
    def __init__(self, stage: str, reason: str):
        self.stage = stage if stage in STAGES else 'provider'
        # Behaviour-neutral: unknown folds to operation_failed as before; the miss is also counted.
        self.reason = reason if reason in REASONS else 'operation_failed'
        reason_label(ReasonFamily.RECOVERY_FAILURE, reason, RecoveryFailureReason)
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
        from utils.stt.local_vad import offline_pcm_speech_segments

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
    elif outcome == 'no_recoverable_speech':
        from utils.batch_pipeline.contracts import projection_speech_spans

        if (
            payload.get('words') != []
            or payload.get('words_provider') != 'exhausted_recognizers'
            or payload.get('recognition_evidence')
            not in (EMPTY_EVIDENCE, TWO_PROVIDER_EMPTY_EVIDENCE, LANGUAGE_GUARD_EMPTY_EVIDENCE)
        ):
            raise RecoveryFailure('payload_validation', 'invalid_payload')
        at_stage(
            'payload_validation', 'invalid_payload', lambda: projection_speech_spans(payload, payload['audio_seconds'])
        )
    elif outcome != 'success':
        raise RecoveryFailure('payload_validation', 'invalid_payload')
    return outcome


EMPTY_EVIDENCE = {'gpu_padded_retry': 'empty', 'multilingual_recovery': 'empty'}
# The worker skipped the padded retry for long unknown-language speech, so two
# independent multilingual recognizers stand in for it.
TWO_PROVIDER_EMPTY_EVIDENCE = {
    'gpu_padded_retry': 'skipped_long_speech',
    'multilingual_recovery': 'empty',
    'second_multilingual_recovery': 'empty',
}
LANGUAGE_GUARD_EMPTY_EVIDENCE = {
    'gpu_language_guard': 'unsupported_language',
    'multilingual_recovery': 'empty',
    'second_multilingual_recovery': 'empty',
}


class MultilingualEmpty(RecoveryFailure):
    """Affirmative positive VAD and a validated empty multilingual response, no content."""

    def __init__(self, duration, spans):
        super().__init__('response_validation', 'empty_asr')
        self.duration, self.spans = duration, spans


def padded_empty(job):
    return job.get('worker_empty_evidence') == {'padded_retry': 'empty', 'version': 1}


def padded_skipped(job):
    return job.get('worker_empty_evidence') in (
        {'padded_retry': 'skipped_oversize', 'version': 1},
        {'padded_retry': 'skipped_long_speech', 'version': 1},
    )


def padded_long_speech(job):
    return job.get('worker_empty_evidence') == {'padded_retry': 'skipped_long_speech', 'version': 1}


def terminal_empty_payload(duration, spans, evidence=EMPTY_EVIDENCE):
    payload = {
        'audio_seconds': duration,
        'speech_seconds': sum(s['end'] - s['start'] for s in spans),
        'speech_spans': spans,
        'words': [],
        'diarization': {'turns': [], 'outcome': 'no_recoverable_speech'},
        'words_provider': 'exhausted_recognizers',
        'recovery_version': 1,
        'outcome': 'no_recoverable_speech',
        'recognition_evidence': dict(evidence),
    }
    result_outcome(payload)
    return payload
