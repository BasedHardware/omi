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


def admission_language_sample_enabled() -> bool:
    """Ship-on; an unknown-multilingual upload is admitted only after its first unit's LID is Parakeet-safe.

    Explicit false restores the full exclusion (every such upload stays on legacy).
    """
    return default_on(
        'BATCH_ADMISSION_LANGUAGE_SAMPLE_ENABLED',
        os.getenv('BATCH_ADMISSION_LANGUAGE_SAMPLE_ENABLED', 'true').strip().lower() != 'false',
    )


def multilingual_profile_routing_enabled() -> bool:
    """Ship-on kill switch; false trusts a supported conversation pin for every multi-language user again."""
    return default_on(
        'BATCH_MULTILINGUAL_PROFILE_ROUTING_ENABLED',
        os.getenv('BATCH_MULTILINGUAL_PROFILE_ROUTING_ENABLED', 'true').strip().lower() != 'false',
    )


# A live session counts as unsupported speech when at least this many of its confidently classified
# words, and this share of them, are in languages batch Parakeet cannot transcribe. A stray word or two
# (one 'vi' in 172 'en') is classifier noise, not a speaker of that language.
PROFILE_MIN_UNSUPPORTED_WORDS = 10
PROFILE_MIN_UNSUPPORTED_SHARE = 0.2
# Sessions out of the rolling projection (database/live_language_profile.py keeps the last 20).
PROFILE_MIN_SESSIONS = 2
PROFILE_FIELD = 'live_stt_language_sessions'


def _parakeet_batch_languages() -> frozenset[str]:
    return PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL[PARAKEET_MODEL_BY_SURFACE[STTServingSurface.PRERECORDED]] - {'multi'}


def profile_speaks_unsupported(user: dict) -> bool:
    """Whether the user's own recent live speech shows a language batch Parakeet cannot transcribe.

    Reads only the user document the caller already loaded (no I/O). Malformed rows count as nothing.
    """
    sessions = user.get(PROFILE_FIELD)
    if not isinstance(sessions, list):
        return False
    parakeet = _parakeet_batch_languages()
    hits = 0
    for counts in sessions:
        if not isinstance(counts, dict):
            continue
        valid = {code: n for code, n in counts.items() if isinstance(code, str) and type(n) is int and n > 0}
        total = sum(valid.values())
        other = sum(n for code, n in valid.items() if normalized_stt_language(code) not in parakeet)
        if other >= PROFILE_MIN_UNSUPPORTED_WORDS and other >= PROFILE_MIN_UNSUPPORTED_SHARE * total:
            hits += 1
    return hits >= PROFILE_MIN_SESSIONS


def batch_admission_language(user: dict, conversation: dict) -> tuple[str | None, str | None]:
    """Return the declared language or a bounded exclusion reason.

    A non-single-language preference requires a supported bound conversation.
    Recognized conversation context outranks the user's preference, matching
    language inheritance. Unknown strings never establish model capability.

    For a multi-language user whose own live speech shows a language Parakeet cannot
    transcribe, a supported conversation pin is not evidence either: it is usually the
    app language, stamped on every conversation. Such uploads are classified on audio
    (the sampled LID path) instead of going straight to Parakeet.
    """
    parakeet = _parakeet_batch_languages()

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
        if not single and multilingual_profile_routing_enabled() and profile_speaks_unsupported(user):
            return None, 'unknown_multilingual_conversation'
        return conversation_language, None
    return effective or user_language, None
