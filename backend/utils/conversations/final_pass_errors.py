"""Bounded code-owned diagnostics: never log arbitrary exception messages."""

from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]

_ALIASES = {
    'word_shape': 'projection_word_shape',
    'word_clock': 'projection_word_clock',
    'word_sequence': 'projection_word_sequence',
    'result audio duration differs from admitted capture': 'projection_duration',
    'original VAD speech_spans required': 'projection_vad_missing',
    'invalid VAD span': 'projection_vad_shape',
    'numeric VAD span required': 'projection_vad_numeric',
    'finite VAD span required': 'projection_vad_nonfinite',
    'ordered nonoverlapping VAD spans required': 'projection_vad_order',
    'validated speech_seconds required': 'projection_speech_missing',
    'VAD union disagrees with speech accounting': 'projection_speech_accounting',
    'successful batch result must contain words': 'projection_no_words',
    'successful batch result produced no transcript': 'projection_no_segments',
    'bounded projection part count required': 'projection_part_count',
    'privacy_generation_changed': 'generation_mismatch',
    'account_deleted': 'erasure',
    'conversation_deleted': 'erasure',
}

REFERENCE_REASONS = frozenset(
    {
        'no_job',
        'no_result',
        'job_owner_mismatch',
        'job_unit_mismatch',
        'binding_owner_mismatch',
        'receipt_missing',
        'artifact_row_missing',
        'artifact_cleaned',
        'artifact_kind_mismatch',
        'artifact_owner_mismatch',
        'artifact_unit_mismatch',
        'generation_mismatch',
        'erasure',
        'uri_mismatch',
        'projection_segment_missing',
        'projection_text_mismatch',
        'projection_point_words',
        'projection_unassigned_words',
        'projection_coverage_partial',
    }
)

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
        'unit_duration',
        'unit_pcm_format',
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
        'skipped_shared_unit',
        'retry_custody_required',
        'batch artifact encryption secret must contain at least 32 bytes',
        'durable batch staging bucket is not configured',
    }
)


def error_details(error):
    # Inspect only a literal code string; never format provider objects or user
    # payloads through a custom exception __str__ implementation.
    message = error.args[0] if len(error.args) == 1 and type(error.args[0]) is str else None
    location = 'unavailable'
    frame = error.__traceback__
    while frame is not None:
        filename = Path(frame.tb_frame.f_code.co_filename).resolve()
        if filename.is_relative_to(_BACKEND) and filename.is_file():
            location = f'{filename.relative_to(_BACKEND).as_posix()}:{frame.tb_lineno}:{frame.tb_frame.f_code.co_name}'
        frame = frame.tb_next
    return {
        'exception_type': type(error).__name__,
        'reason': (
            _ALIASES.get(message, message if message in _REASONS | REFERENCE_REASONS else 'unclassified')
            if message is not None
            else 'unclassified'
        ),
        'location': location,
    }
