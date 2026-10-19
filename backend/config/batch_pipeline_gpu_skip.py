"""Ship-on kill switches for skipping batch GPU work that cannot change output.

Read at the call boundary; set a flag to ``false`` to restore the full stage.
"""

import os


def diarize_speech_only_enabled() -> bool:
    """Diarize padded VAD/word evidence only, mapped back to capture clocks."""
    return os.getenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'true').strip().lower() != 'false'


def short_speech_single_enabled() -> bool:
    """One short contiguous speech region takes the existing skipped_single result."""
    return os.getenv('BATCH_PIPELINE_SHORT_SPEECH_SINGLE_ENABLED', 'true').strip().lower() != 'false'
