"""Default-off speech compaction for stored-audio final passes."""

from config.refactor_switches import default_off as rollout_default_off

import os


def final_pass_vad_compaction_enabled():
    return rollout_default_off(
        'TRANSCRIPTION_FINAL_PASS_VAD_COMPACTION_ENABLED',
        os.getenv('TRANSCRIPTION_FINAL_PASS_VAD_COMPACTION_ENABLED', 'false').lower() == 'true',
    )
