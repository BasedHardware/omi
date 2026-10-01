"""Pure fields for a published person voice sample, independent of transaction machinery."""

from typing import Optional


def voice_learning_fields(state: str, outcome: str, speech_seconds: Optional[float]) -> dict:
    return {
        'voice_learning_state': state,
        'voice_learning_outcome': outcome,
        'voice_speech_seconds': speech_seconds,
        'voice_needed_seconds': None,
    }
