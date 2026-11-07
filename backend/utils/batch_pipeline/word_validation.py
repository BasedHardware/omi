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


def bounded_window_words(words, duration):
    """Own recognition clocks by midpoint; wholly-outside clocks are unowned.

    Shared by the GPU worker's window seam, the padded-retry adapter and the
    CPU provider/recovery response validators. Model and vendor frames may
    extend past either edge of the captured window, and TDT start-state
    ghosts can anchor a clock entirely before it. A word whose whole span
    lies outside the capture can never be owned by it — the midpoint rule
    below would reject it — so it drops instead of failing an
    already-paid hypothesis whose kept words are real: the fenced second
    recognition cannot recover a word the capture never contained, and the
    quarantine it used to cause discarded every kept word with it. Clocks
    that are malformed inside the window's domain — inverted bounds,
    non-finite values, unparsable shapes — still fail closed; clamping must
    never turn them into plausible captured speech.
    """
    result = []
    previous = -math.inf
    for word in words:
        try:
            start, end = map(float, word['timestamp'])
        except ValueError:
            raise BatchValidationError(ValidationReason.WORD_SHAPE) from None
        if not all(math.isfinite(v) for v in (start, end)) or start > end:
            raise BatchValidationError(ValidationReason.WORD_CLOCK)
        if end < 0 or (end == 0 and start < 0):
            # Wholly before the window: the same unowned-ghost rule as the
            # post-window tail below. A clock inverted across zero still
            # raised above; only ordering-legal, entirely pre-window words
            # drop, and the drop must precede the sequence check so a ghost
            # trailing real words cannot fail their ordering.
            continue
        if start >= duration:
            # A word that begins at or after the window's captured extent can
            # never be owned: the midpoint rule below would drop it, and so
            # does the window's own duration. Failing the unit here discarded
            # the already-paid hypothesis for every kept word and quarantined
            # the capture for a fenced second recognition that cannot recover
            # a word this window never contained. Drop the tail word and keep
            # the window's real transcript; malformed clocks above still fail.
            continue
        if start < previous or not isinstance(word['word'], str) or not word['word'].strip():
            raise BatchValidationError(ValidationReason.WORD_SEQUENCE)
        previous = start
        if 0 <= (start + end) / 2 < duration:
            result.append({**word, 'timestamp': [max(0, start), min(duration, end)]})
    return validate_words(result, duration)


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
