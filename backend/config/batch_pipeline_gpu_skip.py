"""Kill switches for skipping batch GPU work that cannot change output.

Read at the call boundary. Speech-only diarization ships on (unset is on; only
``false`` disables it). The short single-speaker skip ships OFF: only ``true``
enables it, after the prod-revision qualification in batch_pipeline_runtime.md.
"""

from config.refactor_switches import default_on as rollout_default_on

import os


def diarize_speech_only_enabled() -> bool:
    """Diarize padded VAD/word evidence only, mapped back to capture clocks."""
    return rollout_default_on(
        'BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED',
        os.getenv('BATCH_PIPELINE_DIARIZE_SPEECH_ONLY_ENABLED', 'true').strip().lower() != 'false',
    )
