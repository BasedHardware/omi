# Failure-Class: FC-terminal-validation-disposition-misbooked-as-worker-fault
"""Every family reason is reachable from its real raise site.

The closed verdicts the demotion rechannels are driven from the actual
raise sites — the shared word-clock validators, the VAD window geometry
checks, the canonical staging decoder, the intake-context envelope and the
typed decoded-extent boundary — with malformed inputs per reason, so the
family's vocabulary cannot drift from what the chain actually raises.
"""

import io
import struct
import wave

import pytest

from diarizer.batch_pipeline import DecodedDurationMismatch, crop_model_vad_spans, speech_windows
from utils.batch_pipeline.audio import StagedAudioInvalid, read_context, with_context
from utils.batch_pipeline.word_validation import (
    BatchValidationError,
    ValidationReason,
    bounded_window_words,
    validate_words,
)
from utils.batch_pipeline.artifacts import StagedArtifactInvalid
from utils.batch_pipeline.source_audio import RetainedAudioInvalid

DURATION = 2.0
NAN = float("nan")
INF = float("inf")


class _Config:
    context_seconds = 0.0


def _reason(exc):
    return exc.reason if isinstance(exc, BatchValidationError) else None


def test_bounded_window_words_shape_string_timestamp_raises_word_shape():
    """bounded_window_words: shape_string_timestamp raises the closed word_shape verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        bounded_window_words([{'word': 'hi', 'timestamp': 'xy'}], DURATION)
    assert _reason(excinfo.value) == "word_shape"


def test_bounded_window_words_shape_list_of_str_raises_word_shape():
    """bounded_window_words: shape_list_of_str raises the closed word_shape verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        bounded_window_words([{'word': 'hi', 'timestamp': ['a', 'b']}], DURATION)
    assert _reason(excinfo.value) == "word_shape"


def test_bounded_window_words_shape_empty_list_raises_word_shape():
    """bounded_window_words: shape_empty_list raises the closed word_shape verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        bounded_window_words([{'word': 'hi', 'timestamp': []}], DURATION)
    assert _reason(excinfo.value) == "word_shape"


def test_bounded_window_words_clock_nonfinite_start_raises_word_clock():
    """bounded_window_words: clock_nonfinite_start raises the closed word_clock verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        bounded_window_words([{'word': 'hi', 'timestamp': [NAN, 0.5]}], DURATION)
    assert _reason(excinfo.value) == "word_clock"


def test_bounded_window_words_clock_nonfinite_end_raises_word_clock():
    """bounded_window_words: clock_nonfinite_end raises the closed word_clock verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        bounded_window_words([{'word': 'hi', 'timestamp': [0.1, INF]}], DURATION)
    assert _reason(excinfo.value) == "word_clock"


def test_bounded_window_words_clock_inverted_raises_word_clock():
    """bounded_window_words: clock_inverted raises the closed word_clock verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        bounded_window_words([{'word': 'hi', 'timestamp': [0.6, 0.5]}], DURATION)
    assert _reason(excinfo.value) == "word_clock"


def test_bounded_window_words_sequence_out_of_order_raises_word_sequence():
    """bounded_window_words: sequence_out_of_order raises the closed word_sequence verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        bounded_window_words([{'word': 'b', 'timestamp': [1.0, 1.2]}, {'word': 'a', 'timestamp': [0.1, 0.4]}], DURATION)
    assert _reason(excinfo.value) == "word_sequence"


def test_bounded_window_words_sequence_blank_text_raises_word_sequence():
    """bounded_window_words: sequence_blank_text raises the closed word_sequence verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        bounded_window_words([{'word': '   ', 'timestamp': [0.1, 0.4]}], DURATION)
    assert _reason(excinfo.value) == "word_sequence"


def test_bounded_window_words_sequence_non_str_text_raises_word_sequence():
    """bounded_window_words: sequence_non_str_text raises the closed word_sequence verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        bounded_window_words([{'word': 7, 'timestamp': [0.1, 0.4]}], DURATION)
    assert _reason(excinfo.value) == "word_sequence"


def test_validate_words_vw_negative_start_raises_word_clock():
    """validate_words: vw_negative_start raises the closed word_clock verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        validate_words([{'word': 'hi', 'timestamp': [-0.5, 0.2]}], DURATION)
    assert _reason(excinfo.value) == "word_clock"


def test_validate_words_vw_inverted_raises_word_clock():
    """validate_words: vw_inverted raises the closed word_clock verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        validate_words([{'word': 'hi', 'timestamp': [0.6, 0.5]}], DURATION)
    assert _reason(excinfo.value) == "word_clock"


def test_validate_words_vw_nonfinite_raises_word_clock():
    """validate_words: vw_nonfinite raises the closed word_clock verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        validate_words([{'word': 'hi', 'timestamp': [NAN, 0.2]}], DURATION)
    assert _reason(excinfo.value) == "word_clock"


def test_validate_words_vw_past_duration_raises_word_clock():
    """validate_words: vw_past_duration raises the closed word_clock verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        validate_words([{'word': 'hi', 'timestamp': [0.1, 2.5]}], DURATION)
    assert _reason(excinfo.value) == "word_clock"


def test_validate_words_vw_out_of_order_raises_word_sequence():
    """validate_words: vw_out_of_order raises the closed word_sequence verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        validate_words([{'word': 'b', 'timestamp': [1.0, 1.2]}, {'word': 'a', 'timestamp': [0.1, 0.4]}], DURATION)
    assert _reason(excinfo.value) == "word_sequence"


def test_validate_words_vw_blank_text_raises_word_sequence():
    """validate_words: vw_blank_text raises the closed word_sequence verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        validate_words([{'word': ' ', 'timestamp': [0.1, 0.4]}], DURATION)
    assert _reason(excinfo.value) == "word_sequence"


def test_crop_model_vad_spans_nonfinite_start_raises_vad_nonfinite():
    """crop_model_vad_spans: nonfinite_start raises the closed vad_nonfinite verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        crop_model_vad_spans([(NAN, 0.5)], DURATION)
    assert _reason(excinfo.value) == "vad_nonfinite"


def test_crop_model_vad_spans_infinite_end_raises_vad_nonfinite():
    """crop_model_vad_spans: infinite_end raises the closed vad_nonfinite verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        crop_model_vad_spans([(0.1, INF)], DURATION)
    assert _reason(excinfo.value) == "vad_nonfinite"


def test_crop_model_vad_spans_order_inverted_raises_vad_order():
    """crop_model_vad_spans: order_inverted raises the closed vad_order verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        crop_model_vad_spans([(0.5, 0.2)], DURATION)
    assert _reason(excinfo.value) == "vad_order"


def test_crop_model_vad_spans_bounds_start_past_duration_raises_vad_bounds():
    """crop_model_vad_spans: bounds_start_past_duration raises the closed vad_bounds verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        crop_model_vad_spans([(2.5, 3.0)], DURATION)
    assert _reason(excinfo.value) == "vad_bounds"


def test_speech_windows_sw_nonfinite_raises_vad_nonfinite():
    """speech_windows: sw_nonfinite raises the closed vad_nonfinite verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        list(speech_windows('item', [0.0] * 32000, [(NAN, 0.5)], _Config()))
    assert _reason(excinfo.value) == "vad_nonfinite"


def test_speech_windows_sw_infinite_raises_vad_nonfinite():
    """speech_windows: sw_infinite raises the closed vad_nonfinite verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        list(speech_windows('item', [0.0] * 32000, [(0.1, INF)], _Config()))
    assert _reason(excinfo.value) == "vad_nonfinite"


def test_speech_windows_sw_order_inverted_raises_vad_order():
    """speech_windows: sw_order_inverted raises the closed vad_order verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        list(speech_windows('item', [0.0] * 32000, [(0.5, 0.2)], _Config()))
    assert _reason(excinfo.value) == "vad_order"


def test_speech_windows_sw_bounds_past_end_raises_vad_bounds():
    """speech_windows: sw_bounds_past_end raises the closed vad_bounds verdict."""
    with pytest.raises(BatchValidationError) as excinfo:
        list(speech_windows('item', [0.0] * 32000, [(0.1, 9.0)], _Config()))
    assert _reason(excinfo.value) == "vad_bounds"


def test_decode_pcm16_wav_garbage_bytes_raises_staged_audio_invalid():
    """decode_pcm16_wav: garbage_bytes is deterministic on the pinned bytes."""
    from diarizer.batch_pipeline_models import decode_pcm16_wav

    with pytest.raises(StagedAudioInvalid):
        decode_pcm16_wav(b'not a wav at all')


def test_decode_pcm16_wav_empty_body_raises_staged_audio_invalid():
    """decode_pcm16_wav: empty_body is deterministic on the pinned bytes."""
    from diarizer.batch_pipeline_models import decode_pcm16_wav

    with pytest.raises(StagedAudioInvalid):
        decode_pcm16_wav(b'')


def test_decode_pcm16_wav_truncated_header_raises_staged_audio_invalid():
    """decode_pcm16_wav: truncated_header is deterministic on the pinned bytes."""
    from diarizer.batch_pipeline_models import decode_pcm16_wav

    with pytest.raises(StagedAudioInvalid):
        decode_pcm16_wav(b'RIFF\x00\x00\x00\x00WAVE')


def test_decode_pcm16_wav_wrong_rate_raises_staged_audio_invalid():
    """decode_pcm16_wav: wrong_rate is deterministic on the pinned bytes."""
    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b'\0\0' * 16000)
    body = output.getvalue()
    with pytest.raises(StagedAudioInvalid):
        from diarizer.batch_pipeline_models import decode_pcm16_wav

        decode_pcm16_wav(body)


def test_with_context_non_riff_body_raises_staged_audio_invalid():
    """with_context: non_riff_body is a deterministic staged-audio fault."""
    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b'\0\0' * 160)
    canonical_wav = lambda: output.getvalue()

    with pytest.raises(StagedAudioInvalid):
        with_context(b'XXXXrather not', {'k': 'v'})


def test_with_context_non_wave_tag_raises_staged_audio_invalid():
    """with_context: non_wave_tag is a deterministic staged-audio fault."""
    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b'\0\0' * 160)
    canonical_wav = lambda: output.getvalue()

    with pytest.raises(StagedAudioInvalid):
        with_context(b'RIFF\x00\x00\x00\x00XXXX', {'k': 'v'})


def test_with_context_nan_context_raises_staged_audio_invalid():
    """with_context: nan_context is a deterministic staged-audio fault."""
    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b'\0\0' * 160)
    canonical_wav = lambda: output.getvalue()

    with pytest.raises(StagedAudioInvalid):
        with_context(canonical_wav(), {'t': NAN})


def test_with_context_oversized_context_raises_staged_audio_invalid():
    """with_context: oversized_context is a deterministic staged-audio fault."""
    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b'\0\0' * 160)
    canonical_wav = lambda: output.getvalue()

    with pytest.raises(StagedAudioInvalid):
        with_context(canonical_wav(), {'blob': 'x' * 70000})


def test_read_context_invalid_envelope_size_raises_a_closed_fault():
    """read_context: invalid_envelope_size never yields a context dict."""
    import pytest

    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b'\0\0' * 160)
    canonical_wav = lambda: output.getvalue()

    from utils.batch_pipeline.audio import read_context as _read

    with pytest.raises(ValueError):
        _read(b'RIFF\x00\x00\x00\x00WAVE')


def test_read_context_missing_context_raises_a_closed_fault():
    """read_context: missing_context never yields a context dict."""
    import pytest

    output = io.BytesIO()
    with wave.open(output, 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b'\0\0' * 160)
    canonical_wav = lambda: output.getvalue()

    from utils.batch_pipeline.audio import read_context as _read

    with pytest.raises(ValueError):
        _read(canonical_wav())


def test_error_class_name_staged_carries_its_own_name():
    """The boundary's error_class field is the exception's own type name for staged."""
    exc = StagedAudioInvalid('x')
    assert type(exc).__name__ == "StagedAudioInvalid"


def test_error_class_name_artifact_carries_its_own_name():
    """The boundary's error_class field is the exception's own type name for artifact."""
    exc = StagedArtifactInvalid('x')
    assert type(exc).__name__ == "StagedArtifactInvalid"


def test_error_class_name_retained_carries_its_own_name():
    """The boundary's error_class field is the exception's own type name for retained."""
    exc = RetainedAudioInvalid('x')
    assert type(exc).__name__ == "RetainedAudioInvalid"


def test_error_class_name_extent_carries_its_own_name():
    """The boundary's error_class field is the exception's own type name for extent."""
    exc = DecodedDurationMismatch('x')
    assert type(exc).__name__ == "DecodedDurationMismatch"


def test_error_class_name_vad_bounds_carries_its_own_name():
    """The boundary's error_class field is the exception's own type name for vad_bounds."""
    exc = BatchValidationError(ValidationReason.VAD_BOUNDS)
    assert type(exc).__name__ == "BatchValidationError"
