"""Default-off speech compaction for stored-audio final passes."""

import os


def final_pass_vad_compaction_enabled():
    return os.getenv('TRANSCRIPTION_FINAL_PASS_VAD_COMPACTION_ENABLED', 'false').lower() == 'true'
