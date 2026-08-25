"""Normalization for the user's stored primary-language preference.

``PATCH /v1/users/language`` accepted any string, so clients that sent a language
*name* persisted values like ``"japanese"``. No STT capability map can match a name,
and every consumer reads this field expecting an ISO code.
"""

from __future__ import annotations

from typing import Final, Optional

from config.stt_provider_policy import (
    MODULATE_SUPPORTED_LANGUAGES,
    PARAKEET_MODEL_BY_SURFACE,
    PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL,
    STTServingSurface,
)

# A stored value must be serviceable by some provider, so the accepted set is the
# union of provider capability rather than a second list that can drift from policy.
ACCEPTED_BASE_LANGUAGES: Final[frozenset[str]] = MODULATE_SUPPORTED_LANGUAGES | frozenset(
    PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL[PARAKEET_MODEL_BY_SURFACE[STTServingSurface.PRERECORDED]]
)

# English names for every accepted code, plus the aliases clients have actually sent.
LANGUAGE_NAME_TO_BASE: Final[dict[str, str]] = {
    'afrikaans': 'af',
    'albanian': 'sq',
    'arabic': 'ar',
    'azerbaijani': 'az',
    'basque': 'eu',
    'belarusian': 'be',
    'bengali': 'bn',
    'bosnian': 'bs',
    'brazilian portuguese': 'pt',
    'bulgarian': 'bg',
    'cantonese': 'zh',
    'catalan': 'ca',
    'chinese': 'zh',
    'chinese simplified': 'zh',
    'chinese traditional': 'zh',
    'croatian': 'hr',
    'czech': 'cs',
    'danish': 'da',
    'dutch': 'nl',
    'english': 'en',
    'estonian': 'et',
    'farsi': 'fa',
    'filipino': 'tl',
    'finnish': 'fi',
    'flemish': 'nl',
    'french': 'fr',
    'galician': 'gl',
    'german': 'de',
    'greek': 'el',
    'gujarati': 'gu',
    'hebrew': 'he',
    'hindi': 'hi',
    'hungarian': 'hu',
    'indonesian': 'id',
    'italian': 'it',
    'japanese': 'ja',
    'kannada': 'kn',
    'kazakh': 'kk',
    'korean': 'ko',
    'latvian': 'lv',
    'lithuanian': 'lt',
    'macedonian': 'mk',
    'malay': 'ms',
    'malayalam': 'ml',
    'maltese': 'mt',
    'mandarin': 'zh',
    'marathi': 'mr',
    'norwegian': 'no',
    'persian': 'fa',
    'polish': 'pl',
    'portuguese': 'pt',
    'punjabi': 'pa',
    'romanian': 'ro',
    'russian': 'ru',
    'serbian': 'sr',
    'simplified chinese': 'zh',
    'slovak': 'sk',
    'slovenian': 'sl',
    'spanish': 'es',
    'swahili': 'sw',
    'swedish': 'sv',
    'tagalog': 'tl',
    'tamil': 'ta',
    'telugu': 'te',
    'thai': 'th',
    'turkish': 'tr',
    'ukrainian': 'uk',
    'urdu': 'ur',
    'vietnamese': 'vi',
    'welsh': 'cy',
}


def normalize_user_language(raw: Optional[str]) -> Optional[str]:
    """Return a storable language preference, or None when it cannot be resolved.

    Region qualifiers survive (``pt-BR`` stays ``pt-BR``) because only the base code
    drives provider capability. A recognized language name resolves to its base code
    so older clients keep working instead of persisting an unusable value.
    """
    candidate = (raw or '').strip()
    if not candidate:
        return None

    base, _, subtag = candidate.replace('_', '-').partition('-')
    if base.lower() in ACCEPTED_BASE_LANGUAGES and _is_region_subtag(subtag):
        return f'{base.lower()}-{subtag}' if subtag else base.lower()

    return LANGUAGE_NAME_TO_BASE.get(candidate.lower())


def _is_region_subtag(subtag: str) -> bool:
    """Accept one region/script qualifier (``US``, ``419``, ``Hans``), never a tail of junk."""
    return not subtag or (subtag.isalnum() and 2 <= len(subtag) <= 4)
