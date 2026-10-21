"""Quality boundary for Parakeet's fixed European-language batch model."""

import os

from config.stt_provider_policy import STTServingSurface, normalized_stt_language, parakeet_supports_language


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
