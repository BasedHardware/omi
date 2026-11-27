"""Language eligibility before new sync batch custody; independent of legacy mode."""

import os

from config.batch_language_recovery import inherited_language
from config.prerecorded_language import language_class
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


# A live session counts as unsupported speech when at least this many of its classified transcript
# segments, and this share of them, are in languages batch Parakeet cannot transcribe. The projection counts
# segments (utils/stt/language_policy.py increments once per classified segment), not words. A stray
# segment or two (one 'vi' in 172 'en') is classifier noise, not a speaker of that language.
PROFILE_MIN_UNSUPPORTED_SEGMENTS = 10
PROFILE_MIN_UNSUPPORTED_SHARE = 0.2
# Sessions out of the rolling projection (database/live_language_profile.py keeps the last 20).
PROFILE_MIN_SESSIONS = 2
PROFILE_FIELD = 'live_stt_language_sessions'
# The admission reason for this rule: intake samples it like unknown_multilingual_conversation, and the record
# lane gives it to legacy multilingual STT like any exclusion. Distinct so logs and readbacks can attribute it.
MULTILINGUAL_PROFILE = 'multilingual_profile'


def _parakeet_batch_languages() -> frozenset[str]:
    return PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL[PARAKEET_MODEL_BY_SURFACE[STTServingSurface.PRERECORDED]] - {'multi'}


def _profile_class(code: str) -> str:
    """'unsupported', 'unknown' or 'supported' for one profile code, by the codebase's own ``language_class``.

    Unknown codes ('und') are not evidence. Live profiles store canonical codes, and a canonical code can stand
    for languages on both sides ('sr' is Serbian, Croatian or Bosnian; only Croatian is Parakeet's). Such a code
    counts as unsupported: the cost is a sampled check for a Croatian speaker, never Serbian sent to Parakeet.
    """
    cls = language_class(code)
    return cls if cls in ('unsupported', 'unknown') else 'supported'


def profile_speaks_unsupported(user: dict) -> bool:
    """Whether the user's own recent live speech shows a language batch Parakeet cannot transcribe.

    Reads only the user document the caller already loaded (no I/O). Malformed rows count as nothing.
    """
    sessions = user.get(PROFILE_FIELD)
    if not isinstance(sessions, list):
        return False
    hits = 0
    for counts in sessions:
        if not isinstance(counts, dict):
            continue
        valid = {code: n for code, n in counts.items() if isinstance(code, str) and type(n) is int and n > 0}
        # Unknown codes ('und') are not evidence either way: they count in neither the numerator nor the share.
        classes = {code: _profile_class(normalized_stt_language(code)) for code in valid}
        total = sum(n for code, n in valid.items() if classes[code] != 'unknown')
        other = sum(n for code, n in valid.items() if classes[code] == 'unsupported')
        if other >= PROFILE_MIN_UNSUPPORTED_SEGMENTS and other >= PROFILE_MIN_UNSUPPORTED_SHARE * total:
            hits += 1
    return hits >= PROFILE_MIN_SESSIONS


def pin_untrusted(user: dict) -> bool:
    """A multi-language user whose live speech shows a language Parakeet cannot transcribe (switch on).

    For such a user a supported conversation pin is usually the app language, not evidence. Either kill switch
    (this rule's, or the admission exclusion's) restores the former admission and input selection."""
    single = (user.get('transcription_preferences') or {}).get('single_language_mode')
    return (
        not single
        and admission_language_exclusion_enabled()
        and multilingual_profile_routing_enabled()
        and profile_speaks_unsupported(user)
    )


def profile_inherited_language(target: dict, user: dict, inherit: bool) -> str | None:
    """``inherited_language`` when inheritance is on, except a multilingual-profile user's pin is never inherited.

    Serving intake and shadow intake both use this, so the two stages stay in step. It covers every legacy mode
    and an existing ``batch_sync_v1`` owner, which skips admission: such units are classified per unit as
    ``multi``."""
    if not inherit or pin_untrusted(user):
        return None
    return inherited_language(target.get('language'), user.get('language'))


def batch_admission_language(user: dict, conversation: dict) -> tuple[str | None, str | None]:
    """Return the declared language or a bounded exclusion reason.

    A non-single-language preference requires a supported bound conversation.
    Recognized conversation context outranks the user's preference, matching
    language inheritance. Unknown strings never establish model capability.

    For a multi-language user whose own live speech shows a language Parakeet cannot
    transcribe, a supported conversation pin is not evidence either: it is usually the
    app language, stamped on every conversation. Such uploads return ``multilingual_profile``:
    sync intake classifies them on audio (the sampled LID path) and the record lane gives a new
    owner to legacy multilingual STT, instead of either going straight to Parakeet.
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
        if pin_untrusted(user):
            return None, MULTILINGUAL_PROFILE
        return conversation_language, None
    return effective or user_language, None
