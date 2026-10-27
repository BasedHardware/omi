"""Validated single-call recognizers for fenced CPU batch recovery."""

import io
import wave

from config.batch_pipeline import empty_asr_disposition_enabled
from config.policy import RecoveryPolicy
from config.prerecorded_stt import missing_provider_environment
from config.stt_provider_policy import provider_is_enabled, STTServingSurface
from utils.executors import run_blocking, sync_executor
from utils.batch_pipeline.contracts import projection_speech_spans, worker_vad_word_spans
from utils.batch_pipeline.recovery_disposition import (
    inspect_audio,
    silence_payload,
    at_stage,
    RecoveryFailure,
    MultilingualEmpty,
    WordsWithoutVad,
    result_outcome,
)


def recognizer_attempt(operation):
    """A validated word response with no VAD remains billable, never silence."""
    from database.batch_pipeline_privacy import BatchPrivacyBlocked
    from database.batch_pipeline_projection_protocol import ProjectionBlocked

    try:
        payload = operation()
        result_outcome(payload)
        return payload, 'words', len(payload['words'])
    except (BatchPrivacyBlocked, ProjectionBlocked):
        raise
    except MultilingualEmpty:
        return None, 'empty', 0
    except WordsWithoutVad as error:
        return None, 'words', error.word_count
    except Exception:
        return None, 'error', None


def independent_ready():
    return provider_is_enabled('soniox', STTServingSurface.HELD_RECOVERY) and not missing_provider_environment('soniox')


def transcribe(item, binding, audio, *, multilingual=None, force_recognition=False, worker_speech=None):
    """Use the sync client directly, with no whole-upload coordinator or retries."""
    # Preserve the existing deferred STT boundary: its transitive encryption
    # module requires runtime secrets and cannot join credential-free imports.
    from utils.stt.pre_recorded import prerecorded_from_bytes, modulate_prerecorded_from_bytes
    from utils.stt.parakeet_request_metrics import parakeet_caller

    pcm, duration, spans = inspect_audio(item, audio)
    if not spans and not force_recognition:
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
    return words_payload(duration, spans, words, language, worker_speech=worker_speech)


def second_transcribe(item, audio, empty):
    """One independent Soniox async call after Modulate's validated empty response."""
    from utils.stt.soniox_batch import transcribe as soniox_transcribe

    # Reuse the first call's strict VAD instead of running it again.
    output, duration, spans = independent_audio(item, audio, empty)
    response = at_stage(
        'provider',
        'provider_failed',
        lambda: soniox_transcribe(output, duration),
    )
    return independent_payload(response, duration, spans, getattr(empty, 'worker_speech', None))


def independent_audio(item, audio, empty):
    pcm, duration, spans = inspect_audio(item, audio, vad=lambda _: empty.spans)
    return canonical_wav(pcm), duration, spans


def independent_payload(response, duration, spans, worker_speech=None):
    words, language = at_stage(
        'response_validation',
        'invalid_response',
        lambda: validate_response(response, duration, spans, multilingual=True),
    )
    return {**words_payload(duration, spans, words, language, worker_speech=worker_speech), 'words_provider': 'soniox'}


async def second_transcribe_async(item, audio, empty):
    from utils.stt.soniox_batch import transcribe_async as soniox_transcribe_async

    output, duration, spans = await run_blocking(sync_executor, independent_audio, item, audio, empty)
    try:
        response = await soniox_transcribe_async(output, duration)
    except Exception:
        raise RecoveryFailure('provider', 'provider_failed') from None
    return await run_blocking(
        sync_executor, independent_payload, response, duration, spans, getattr(empty, 'worker_speech', None)
    )


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


def words_payload(duration, spans, words, language, *, worker_speech=None):
    evidence = None
    if not spans and worker_speech:
        # Strict CPU VAD can miss short low-energy speech that the GPU worker's
        # bound VAD receipt measured. Words alone never prove speech: only with
        # that independent measurement may their clocks place it, and
        # speech_seconds stays the acoustic measure (lead ruling ef03d2).
        spans = worker_vad_word_spans(words, duration, worker_speech)
        evidence = {'speech_spans_source': 'worker_vad_word_clocks', 'worker_vad_speech_seconds': worker_speech}
    if not spans:
        raise WordsWithoutVad(len(words))
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
        **(evidence or {}),
    }
    at_stage('payload_validation', 'invalid_payload', lambda: projection_speech_spans(payload, duration))
    return payload
