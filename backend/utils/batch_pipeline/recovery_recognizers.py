"""Validated single-call recognizers for fenced CPU batch recovery."""

import io
import wave

from config.batch_pipeline import empty_asr_disposition_enabled
from config.policy import RecoveryPolicy
from utils.batch_pipeline.contracts import projection_speech_spans
from utils.batch_pipeline.recovery_disposition import (
    inspect_audio,
    silence_payload,
    at_stage,
    RecoveryFailure,
    MultilingualEmpty,
)


def transcribe(item, binding, audio, *, multilingual=None):
    """Use the sync client directly, with no whole-upload coordinator or retries."""
    # Preserve the existing deferred STT boundary: its transitive encryption
    # module requires runtime secrets and cannot join credential-free imports.
    from utils.stt.pre_recorded import prerecorded_from_bytes, modulate_prerecorded_from_bytes
    from utils.stt.parakeet_request_metrics import parakeet_caller

    pcm, duration, spans = inspect_audio(item, audio)
    if not spans:
        if empty_asr_disposition_enabled():
            return silence_payload(duration)
        raise RecoveryFailure('strict_vad', 'no_speech')
    output = canonical_wav(pcm)
    # attempts=2 disables all existing client retry branches. An uncertain call
    # must remain held, never be silently reissued by the recovery dispatcher.
    use_multilingual = RecoveryPolicy().speech_empty_multilingual if multilingual is None else multilingual
    if use_multilingual:
        # Unknown intake language currently selects Parakeet again. Its European
        # language model cannot recover unsupported-language speech by repadding.
        # Use an independent multilingual provider within the SAME paid intent;
        # attempts=2 disables Modulate's recursive retry branches too.
        dispatch = lambda: modulate_prerecorded_from_bytes(
            output, language=binding.language, return_language=True, attempts=2
        )
    else:
        dispatch = lambda: prerecorded_from_bytes(output, language=binding.language, return_language=True, attempts=2)
    with parakeet_caller('batch_recovery'):
        response = at_stage('provider', 'provider_failed', dispatch)
    words, language = at_stage(
        'response_validation',
        'invalid_response',
        lambda: validate_response(response, duration, spans, multilingual=use_multilingual),
    )
    return words_payload(duration, spans, words, language)


def second_transcribe(item, audio, empty):
    """One independent Soniox async call after Modulate's validated empty response."""
    from utils.stt.soniox_batch import transcribe as soniox_transcribe

    # Reuse the first call's strict VAD instead of running it again.
    pcm, duration, spans = inspect_audio(item, audio, vad=lambda _: empty.spans)
    output = canonical_wav(pcm)
    response = at_stage(
        'provider',
        'provider_failed',
        lambda: soniox_transcribe(output, duration),
    )
    words, language = at_stage(
        'response_validation',
        'invalid_response',
        lambda: validate_response(response, duration, spans, multilingual=True),
    )
    return {**words_payload(duration, spans, words, language), 'words_provider': 'soniox'}


def canonical_wav(pcm):
    # Keep the authenticated intake manifest in the original artifact only;
    # third-party STT receives canonical audio without ancillary provenance.
    output = io.BytesIO()
    with wave.open(output, 'wb') as clean:
        clean.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        clean.writeframes(pcm)
    return output.getvalue()


def validate_response(response, duration, spans, *, multilingual):
    from diarizer.batch_pipeline import validate_words

    if not isinstance(response, tuple) or len(response) != 2:
        raise ValueError('response shape')
    raw, language = response
    if not isinstance(language, str) or not language:
        raise ValueError('response language')
    words = validate_words([{**word, 'word': word['text']} for word in raw], duration)
    if not words:
        if multilingual:
            raise MultilingualEmpty(duration, spans)
        raise RecoveryFailure('response_validation', 'empty_asr')
    return words, language


def words_payload(duration, spans, words, language):
    # Preserve legacy speaker labels directly in build_incoming. Exclusive batch
    # diarization turns cannot represent overlapping legacy utterances.
    payload = {
        'audio_seconds': duration,
        'speech_seconds': sum(s['end'] - s['start'] for s in spans),
        'speech_spans': spans,
        'words': words,
        'diarization': {'turns': []},
        'words_provider': 'legacy_sync',
        'language': language,
        'recovery_version': 1,
    }
    at_stage('payload_validation', 'invalid_payload', lambda: projection_speech_spans(payload, duration))
    return payload
