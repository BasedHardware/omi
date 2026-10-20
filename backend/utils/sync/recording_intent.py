"""Native filename policy for an explicit Process Now keep choice."""

import os
import re


def user_selected_recording(raw_paths: list[str]) -> bool:
    # LocalRecordingsProvider uploads one selected native recording at a time.
    # The exact phone marker excludes automatic offline fallback in released
    # clients; the Watch marker identifies manually processed recovery files.
    # Mixed/bulk uploads do not establish an explicit keep choice.
    if len(raw_paths) != 1:
        return False
    name = os.path.basename(raw_paths[0]).lower()
    return name.startswith('audio_omibatchphone_') or (
        re.fullmatch(r'audio_omibatchwatch[0-9a-f]{32}s\d+_pcm16_16000_1_fs160_\d+\.bin', name) is not None
    )
