"""Bounded code-owned diagnostics: never log arbitrary exception messages."""

_REASONS = frozenset(
    {
        'audio too long',
        'conversation_unavailable',
        'word_shape',
        'word_clock',
        'word_sequence',
        'unit limit',
        'unit unavailable',
        'unit PCM format',
        'unit duration',
        'audio timeline too long',
        'conflicting capture clocks',
        'no units',
        'unplaced segments',
        'invalid turn',
        'turns must be exclusive',
        'invalid word clock',
        'result audio duration differs from admitted capture',
        'original VAD speech_spans required',
        'invalid VAD span',
        'numeric VAD span required',
        'finite VAD span required',
        'ordered nonoverlapping VAD spans required',
        'validated speech_seconds required',
        'VAD union disagrees with speech accounting',
        'artifact read deadline',
        'artifact object limit',
        'artifact byte limit',
        'diarizer_unconfigured',
        'diarizer_backend_mismatch',
        'diarizer_attempt_budget',
        'skipped_expired',
        'skipped_merged',
        'batch artifact encryption secret must contain at least 32 bytes',
        'durable batch staging bucket is not configured',
    }
)


def error_details(error):
    message = str(error)
    return {'exception_type': type(error).__name__, 'reason': message if message in _REASONS else 'unclassified'}
