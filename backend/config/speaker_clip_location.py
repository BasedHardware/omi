"""Manual teaching relocation rollout. Disabled unless explicitly enabled."""

import os

SPEAKER_TEXT_ANCHORED_CLIPS_ENV = 'SPEAKER_TEXT_ANCHORED_CLIPS_ENABLED'


def text_anchored_clips_enabled() -> bool:
    return os.getenv(SPEAKER_TEXT_ANCHORED_CLIPS_ENV, 'false').strip().lower() == 'true'
