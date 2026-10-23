"""Quality boundary for Parakeet's fixed European-language batch model."""

from config.refactor_switches import default_on as rollout_default_on

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
    if not rollout_default_on(
        'STT_PRERECORDED_SHORT_LID_GUARD_ENABLED',
        not (os.getenv('STT_PRERECORDED_SHORT_LID_GUARD_ENABLED', 'true').strip().lower() == 'false'),
    ):
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
    return rollout_default_on(
        'STT_PRERECORDED_LANGUAGE_GUARD_ENABLED',
        os.getenv('STT_PRERECORDED_LANGUAGE_GUARD_ENABLED', 'true').strip().lower() != 'false',
    )


def language_class(language: str | None) -> str:
    code = normalized_stt_language(language.strip() if isinstance(language, str) else None)
    if code in {'', 'und', 'multi', 'unknown'}:
        return 'unknown'
    return 'supported' if parakeet_supports_language(STTServingSurface.PRERECORDED, code) else 'unsupported'


def requires_multilingual(language: str | None) -> bool:
    return language_guard_enabled() and language_class(language) != 'supported'


# Self-hosted gate (Parakeet /v2/language, Whisper-base). The statistic is
# P(supported) summed over the Parakeet-25 languages, not a vendor's top-1.
# Offline maxima on unsupported speech: 0.922 at >=6 s, 0.978 for 3 s crops.
SELF_LID_CONFIDENCE = 0.95
SELF_LID_SHORT_CONFIDENCE = 0.985
SELF_LID_SHORT_SECONDS = 6.0
SELF_LID_MIN_SECONDS = 1.0


def self_lid_confidence_floor(probe_seconds: float | None) -> float | None:
    """None means too short or unmeasured: never Parakeet on the self gate's word alone."""
    if (
        isinstance(probe_seconds, bool)
        or not isinstance(probe_seconds, (int, float))
        or not math.isfinite(probe_seconds)
        or probe_seconds < SELF_LID_MIN_SECONDS
    ):
        return None
    return SELF_LID_CONFIDENCE if probe_seconds >= SELF_LID_SHORT_SECONDS else SELF_LID_SHORT_CONFIDENCE


def language_gate_shadow_enabled() -> bool:
    """Kill switch for the shadow self-gate call beside the vendor probe; default on."""
    return rollout_default_on(
        'STT_PRERECORDED_LANGUAGE_GATE_SHADOW',
        os.getenv('STT_PRERECORDED_LANGUAGE_GATE_SHADOW', 'true').strip().lower() != 'false',
    )


def language_gate_percent() -> int:
    """Share of cohorts whose prerecorded route uses the self gate instead of the vendor probe.

    Default 0. Malformed values mean 0, so a typo can never widen enforcement.
    """
    raw = os.getenv('STT_PRERECORDED_LANGUAGE_GATE_PERCENT', '0').strip()
    try:
        value = int(raw)
    except ValueError:
        return 0
    return min(max(value, 0), 100)
