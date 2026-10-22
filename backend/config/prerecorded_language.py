"""Quality boundary for Parakeet's fixed European-language batch model."""

import math
import os

from config.stt_provider_policy import STTServingSurface, normalized_stt_language, parakeet_supports_language

MIN_AUDIO_LID_CONFIDENCE = 0.8
MIN_SHORT_AUDIO_LID_CONFIDENCE = 0.9
SHORT_AUDIO_LID_SECONDS = 10.0


def audio_lid_confidence_floor(probe_seconds: float | None) -> float:
    """Six-second Chinese TTS was mislabeled English at 0.804–0.839 confidence.

    Treat a short or unmeasured sample conservatively. Duration comes from the
    decoded audio, not the detector's response or the user's primary language.
    This floor is not a claim that longer or higher-confidence LID is infallible.
    """
    if os.getenv('STT_PRERECORDED_SHORT_LID_GUARD_ENABLED', 'true').strip().lower() == 'false':
        return MIN_AUDIO_LID_CONFIDENCE
    if (
        isinstance(probe_seconds, bool)
        or not isinstance(probe_seconds, (int, float))
        or not math.isfinite(probe_seconds)
        or probe_seconds < SHORT_AUDIO_LID_SECONDS
    ):
        return MIN_SHORT_AUDIO_LID_CONFIDENCE
    return MIN_AUDIO_LID_CONFIDENCE


def language_guard_enabled() -> bool:
    # Only the explicit kill value restores the old route; malformed values stay safe.
    return os.getenv('STT_PRERECORDED_LANGUAGE_GUARD_ENABLED', 'true').strip().lower() != 'false'


def language_class(language: str | None) -> str:
    code = normalized_stt_language(language.strip() if isinstance(language, str) else None)
    if code in {'', 'und', 'multi', 'unknown'}:
        return 'unknown'
    return 'supported' if parakeet_supports_language(STTServingSurface.PRERECORDED, code) else 'unsupported'


def requires_multilingual(language: str | None) -> bool:
    return language_guard_enabled() and language_class(language) != 'supported'
