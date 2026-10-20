"""Model-free process fencing shared by the worker and lease coordinator."""

WORKER_VALIDATION_STAGES = frozenset({'vad_windows', 'word_clocks', 'assemble_words', 'asr_recovery'})
WORKER_VALIDATION_REASONS = frozenset(
    {
        'word_shape',
        'word_clock',
        'word_sequence',
        'vad_nonfinite',
        'vad_order',
        'vad_bounds',
        'empty_asr',
        'no_owned_words',
    }
)


def validate_worker_failure(failure):
    """Durable diagnostics accept closed codes only, never an exception message."""
    if (
        not isinstance(failure, dict)
        or set(failure) != {'stage', 'reason'}
        or failure['stage'] not in WORKER_VALIDATION_STAGES
        or failure['reason'] not in WORKER_VALIDATION_REASONS
    ):
        raise ValueError('closed worker validation failure required')


class FatalGpuError(RuntimeError):
    """GPU process must restart; never turn this flight into a segment failure."""
