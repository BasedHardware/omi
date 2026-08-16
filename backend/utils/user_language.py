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

# Picker options, in render order. Every code must survive
# normalize_user_language(); tests/unit/test_language_catalog.py enforces it.
PRIMARY_LANGUAGE_OPTIONS: Final[tuple[tuple[str, str], ...]] = (
    # Top languages first
    ('en', 'English'),
    ('en-US', 'English (US)'),
    ('en-GB', 'English (UK)'),
    ('en-AU', 'English (Australia)'),
    ('en-NZ', 'English (New Zealand)'),
    ('en-IN', 'English (India)'),
    ('es', 'Spanish'),
    ('es-419', 'Spanish (Latin America)'),
    ('zh', 'Chinese (Mandarin, Simplified)'),
    ('zh-CN', 'Chinese (Mandarin, Simplified, CN)'),
    ('zh-Hans', 'Chinese (Mandarin, Simplified, Hans)'),
    ('hi', 'Hindi'),
    ('pt', 'Portuguese'),
    ('pt-BR', 'Portuguese (Brazil)'),
    ('pt-PT', 'Portuguese (Portugal)'),
    ('ru', 'Russian'),
    ('ja', 'Japanese'),
    ('de', 'German'),
    # Other languages alphabetically
    ('ar', 'Arabic'),
    ('be', 'Belarusian'),
    ('bn', 'Bengali'),
    ('bs', 'Bosnian'),
    ('bg', 'Bulgarian'),
    ('ca', 'Catalan'),
    ('zh-TW', 'Chinese (Mandarin, Traditional)'),
    ('zh-Hant', 'Chinese (Mandarin, Traditional, Hant)'),
    ('zh-HK', 'Chinese (Cantonese, Traditional)'),
    ('hr', 'Croatian'),
    ('cs', 'Czech'),
    ('da', 'Danish'),
    ('da-DK', 'Danish (Denmark)'),
    ('nl', 'Dutch'),
    ('et', 'Estonian'),
    ('fi', 'Finnish'),
    ('nl-BE', 'Flemish'),
    ('fr', 'French'),
    ('fr-CA', 'French (Canada)'),
    ('de-CH', 'German (Switzerland)'),
    ('el', 'Greek'),
    ('he', 'Hebrew'),
    ('hu', 'Hungarian'),
    ('id', 'Indonesian'),
    ('it', 'Italian'),
    ('kn', 'Kannada'),
    ('ko', 'Korean'),
    ('ko-KR', 'Korean (Korea)'),
    ('lv', 'Latvian'),
    ('lt', 'Lithuanian'),
    ('mk', 'Macedonian'),
    ('ms', 'Malay'),
    ('mr', 'Marathi'),
    ('no', 'Norwegian'),
    ('fa', 'Persian'),
    ('pl', 'Polish'),
    ('ro', 'Romanian'),
    ('sr', 'Serbian'),
    ('sk', 'Slovak'),
    ('sl', 'Slovenian'),
    ('sv', 'Swedish'),
    ('sv-SE', 'Swedish (Sweden)'),
    ('tl', 'Tagalog'),
    ('ta', 'Tamil'),
    ('te', 'Telugu'),
    ('th', 'Thai'),
    ('th-TH', 'Thai (Thailand)'),
    ('tr', 'Turkish'),
    ('uk', 'Ukrainian'),
    ('ur', 'Urdu'),
    ('vi', 'Vietnamese'),
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
