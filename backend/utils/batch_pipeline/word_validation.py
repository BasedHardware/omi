"""Pure batch word-clock validation shared by GPU workers and CPU projections."""

import math
from enum import Enum


class ValidationReason(Enum):
    UNSUPPORTED_LANGUAGE = 'unsupported_language'
    WORD_SHAPE = 'word_shape'
    WORD_CLOCK = 'word_clock'
    WORD_SEQUENCE = 'word_sequence'
    VAD_NONFINITE = 'vad_nonfinite'
    VAD_ORDER = 'vad_order'
    VAD_BOUNDS = 'vad_bounds'
    EMPTY_ASR = 'empty_asr'
    NO_OWNED_WORDS = 'no_owned_words'


class BatchValidationError(ValueError):
    """A closed reason code, never a provider exception message."""

    def __init__(self, reason: object):
        if not isinstance(reason, ValidationReason):
            raise ValueError('invalid batch validation reason')
        self.reason = reason.value
        super().__init__(reason.value)


def validate_words(words, duration):
    result = []
    previous = -1.0
    for word in words:
        try:
            start, end = map(float, word['timestamp'])
        except ValueError:
            raise BatchValidationError(ValidationReason.WORD_SHAPE) from None
        if not all(math.isfinite(v) for v in (start, end)) or not 0 <= start <= end <= duration + 0.01:
            raise BatchValidationError(ValidationReason.WORD_CLOCK)
        if start < previous or not isinstance(word['word'], str) or not word['word'].strip():
            raise BatchValidationError(ValidationReason.WORD_SEQUENCE)
        previous = start
        result.append({**word, 'timestamp': [start, end]})
    return result
