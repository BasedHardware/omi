"""Language eligibility before new sync batch custody; independent of legacy mode."""

import os

from config.refactor_switches import default_on
from config.stt_provider_policy import (
    MODULATE_SUPPORTED_LANGUAGES,
    PARAKEET_MODEL_BY_SURFACE,
    PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL,
    STTServingSurface,
    normalized_stt_language,
)


def admission_language_exclusion_enabled() -> bool:
    """Ship-on; explicit false restores the former admission and LID inputs."""
    return default_on(
        'BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED',
        os.getenv('BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED', 'true').strip().lower() != 'false',
    )


def batch_admission_language(user: dict, conversation: dict) -> tuple[str | None, str | None]:
    """Return the declared language or a bounded exclusion reason.

    A non-single-language preference requires a supported bound conversation.
    Recognized conversation context outranks the user's preference, matching
    language inheritance. Unknown strings never establish model capability.
    """
    parakeet = PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL[PARAKEET_MODEL_BY_SURFACE[STTServingSurface.PRERECORDED]] - {
        'multi'
    }

    def code(value):
        return normalized_stt_language(value.strip()) if isinstance(value, str) else ''

    conversation_language = code(conversation.get('language'))
    user_language = code(user.get('language'))
    known = (MODULATE_SUPPORTED_LANGUAGES | parakeet) - {'multi'}
    effective = next((value for value in (conversation_language, user_language) if value in known), '')
    if effective and effective not in parakeet:
        return None, 'known_unsupported_language'
    single = (user.get('transcription_preferences') or {}).get('single_language_mode')
    if not single or user_language not in known:
        if conversation_language not in parakeet:
            return None, 'unknown_multilingual_conversation'
        return conversation_language, None
    return effective or user_language, None
