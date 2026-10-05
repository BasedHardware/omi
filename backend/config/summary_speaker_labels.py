"""One server-owned switch for note-derived labels; no client or UID override."""

import os


def summary_speaker_labels_enabled() -> bool:
    return os.getenv('SUMMARY_SPEAKER_LABELS_ENABLED', 'off').strip().lower() in {'true', '1', 'on', 'yes'}
