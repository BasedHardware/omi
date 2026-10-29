import pytest
from diarizer.batch_pipeline import validate_words, BatchValidationError, ValidationReason
from diarizer.batch_pipeline import padded_retry_seconds, near_empty_words, padded_retry_fits, crop_model_vad_spans, vad_speech_spans
import numpy as np
from diarizer.batch_pipeline import speech_windows
from unittest.mock import MagicMock
from diarizer.batch_pipeline import is_fatal_cuda_error, FatalGpuError

def test_validate_words_valid():
    words = [
        {'word': 'hello', 'timestamp': [0.0, 1.0]},
        {'word': 'world', 'timestamp': [1.1, 2.0]}
    ]
    duration = 3.0
    result = validate_words(words, duration)
    assert result == words

def test_validate_words_invalid_shape():
    words = [
        {'word': 'hello', 'timestamp': [0.0]}
    ]
    duration = 3.0
    with pytest.raises(BatchValidationError) as exc_info:
        validate_words(words, duration)
    assert exc_info.value.reason == ValidationReason.WORD_SHAPE.value

def test_validate_words_invalid_clock():
    words = [
        {'word': 'hello', 'timestamp': [1.0, 0.0]}
    ]
    duration = 3.0
    with pytest.raises(BatchValidationError) as exc_info:
        validate_words(words, duration)
    assert exc_info.value.reason == ValidationReason.WORD_CLOCK.value

def test_validate_words_invalid_sequence():
    words = [
        {'word': 'world', 'timestamp': [1.1, 2.0]},
        {'word': 'hello', 'timestamp': [0.0, 1.0]}
    ]
    duration = 3.0
    with pytest.raises(BatchValidationError) as exc_info:
        validate_words(words, duration)
    assert exc_info.value.reason == ValidationReason.WORD_SEQUENCE.value


def test_validate_words_inf():
    words = [
        {'word': 'hello', 'timestamp': [0.0, float('inf')]}
    ]
    duration = 3.0
    with pytest.raises(BatchValidationError) as exc_info:
        validate_words(words, duration)
    assert exc_info.value.reason == ValidationReason.WORD_CLOCK.value


def test_padded_retry_seconds():
    # SAMPLE_RATE = 16000
    # left = 32000
    # right = max(32000, 128000 - len(samples) - 32000)
    samples = np.zeros(16000) # 1 second
    # len(samples) = 16000
    # right = max(32000, 128000 - 16000 - 32000) = max(32000, 80000) = 80000
    # result = (16000 + 32000 + 80000) / 16000 = 128000 / 16000 = 8.0
    assert padded_retry_seconds(samples) == 8.0

    samples_long = np.zeros(16000 * 10) # 10 seconds
    # len = 160000
    # right = max(32000, 128000 - 160000 - 32000) = 32000
    # result = (160000 + 32000 + 32000) / 16000 = 224000 / 16000 = 14.0
    assert padded_retry_seconds(samples_long) == 14.0

def test_near_empty_words():
    words = [{'word': 'a'}, {'word': '.'}]
    assert near_empty_words(words, 2.0) == True

    words2 = [{'word': 'hi'}, {'word': 'there'}]
    assert near_empty_words(words2, 2.0) == False

def test_padded_retry_fits():
    samples = np.zeros(16000)
    # padded = 8.0
    assert padded_retry_fits(samples, 10.0) == True
    assert padded_retry_fits(samples, 5.0) == False

def test_crop_model_vad_spans():
    spans = [(0.0, 1.0), (1.5, 3.5)]
    duration = 3.0
    result = crop_model_vad_spans(spans, duration)
    assert result == [(0.0, 1.0), (1.5, 3.0)]

def test_crop_model_vad_spans_invalid():
    spans = [(0.0, 1.0), (2.0, 1.0)]
    duration = 3.0
    with pytest.raises(BatchValidationError) as exc_info:
        crop_model_vad_spans(spans, duration)
    assert exc_info.value.reason == ValidationReason.VAD_ORDER.value

def test_crop_model_vad_spans_out_of_bounds():
    spans = [(4.0, 5.0)]
    duration = 3.0
    with pytest.raises(BatchValidationError) as exc_info:
        crop_model_vad_spans(spans, duration)
    assert exc_info.value.reason == ValidationReason.VAD_BOUNDS.value

def test_vad_speech_spans():
    spans = [(0.0, 1.5), (1.0, 2.0), (3.0, 4.0)]
    total_samples = 16000 * 5 # 5 seconds
    result = vad_speech_spans(spans, total_samples)
    assert result == [{'start': 0.0, 'end': 2.0}, {'start': 3.0, 'end': 4.0}]


def test_speech_windows():
    item = MagicMock()
    item.segment_id = 'seg1'
    samples = np.zeros(16000 * 10) # 10 seconds
    spans = [(1.0, 2.0), (3.0, 4.0)]
    config = MagicMock()
    config.context_seconds = 0.5
    config.window_seconds = 5.0

    windows = list(speech_windows(item, samples, spans, config))
    assert len(windows) == 1
    assert windows[0].segment_id == 'seg1'
    assert windows[0].start == 0.0
    assert windows[0].core_start == 0.5
    assert windows[0].core_end == 4.5

def test_speech_windows_invalid():
    item = MagicMock()
    samples = np.zeros(16000 * 10)
    spans = [(1.0, float('nan'))]
    config = MagicMock()

    with pytest.raises(BatchValidationError) as exc_info:
        list(speech_windows(item, samples, spans, config))
    assert exc_info.value.reason == ValidationReason.VAD_NONFINITE.value

def test_speech_windows_order():
    item = MagicMock()
    samples = np.zeros(16000 * 10)
    spans = [(2.0, 1.0)]
    config = MagicMock()

    with pytest.raises(BatchValidationError) as exc_info:
        list(speech_windows(item, samples, spans, config))
    assert exc_info.value.reason == ValidationReason.VAD_ORDER.value

def test_speech_windows_bounds():
    item = MagicMock()
    samples = np.zeros(16000 * 10)
    spans = [(9.0, 11.0)]
    config = MagicMock()

    with pytest.raises(BatchValidationError) as exc_info:
        list(speech_windows(item, samples, spans, config))
    assert exc_info.value.reason == ValidationReason.VAD_BOUNDS.value


def test_is_fatal_cuda_error():
    assert is_fatal_cuda_error(Exception("worker cuda graph policy violated")) == True
    assert is_fatal_cuda_error(Exception("cuda out of memory")) == True
    assert is_fatal_cuda_error(Exception("something else")) == False

    class AcceleratorError(Exception): pass
    assert is_fatal_cuda_error(AcceleratorError()) == True

    assert is_fatal_cuda_error(FatalGpuError()) == True

    # Check chaining
    exc = Exception("outer")
    exc.__cause__ = Exception("cuda out of memory")
    assert is_fatal_cuda_error(exc) == True
