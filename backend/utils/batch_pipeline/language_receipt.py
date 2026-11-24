"""Content-free language/script observations; never recognizer routing authority."""

import unicodedata
from typing import Any, cast

from config.stt_provider_policy import PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL, normalized_stt_language

SUPPORTED = PARAKEET_SUPPORTED_LANGUAGES_BY_MODEL['nvidia/parakeet-tdt-0.6b-v3'] - {'multi'}
SCRIPTS = frozenset({'latin', 'cyrillic', 'greek', 'other'})
ROUTES = frozenset({'parakeet', 'modulate', 'soniox', 'live_record', 'multilingual_recovery', 'none', 'other'})
EVIDENCE = frozenset({'audio_lid', 'declared', 'unavailable'})
FIELDS = frozenset({'version', 'language', 'route', 'word_count', 'letters', 'incompatible_letters', 'scripts'})
ADMISSION_FIELDS = frozenset({'version', 'language', 'evidence'})


def bounded_language(value):
    if not isinstance(value, str):
        return 'und'
    language = normalized_stt_language(value)
    return language if language in SUPPORTED else 'und' if language in {'', 'multi', 'auto', 'und'} else 'unsupported'


def expected_script(language):
    if language not in SUPPORTED:
        return None
    return 'cyrillic' if language in {'bg', 'ru', 'uk'} else 'greek' if language == 'el' else 'latin'


def script_counts(words):
    counts = {script: 0 for script in sorted(SCRIPTS)}
    for word in words:
        text = word.get('word', '')
        if not isinstance(text, str):
            raise ValueError('word text required')
        for char in text:
            if not char.isalpha():
                continue
            name = unicodedata.name(char, '')
            script = next((script for script in ('latin', 'cyrillic', 'greek') if script.upper() in name), 'other')
            counts[script] += 1
    return counts


def observation(language, route, words):
    language = bounded_language(language)
    route = route if isinstance(route, str) and route in ROUTES else 'other'
    counts = script_counts(words)
    letters = sum(counts.values())
    expected = expected_script(language)
    receipt = {
        'version': 1,
        'language': language,
        'route': route,
        'word_count': len(words),
        'letters': letters,
        # None means language has no supported-script comparison. Never call
        # unknown-language output a clean script match.
        'incompatible_letters': letters - counts[expected] if expected else None,
        'scripts': counts,
    }
    validate(receipt)
    return receipt


def admission(context):
    evidence = context.get('stt_language_evidence')
    receipt = {
        'version': 1,
        'language': bounded_language(context.get('stt_language')),
        'evidence': evidence if isinstance(evidence, str) and evidence in {'audio_lid', 'declared'} else 'unavailable',
    }
    validate_admission(receipt)
    return receipt


def auto_language_cohort(*, server_batch_only, client_platform, native_record, language):
    return (
        server_batch_only is True
        and client_platform in {'ios', 'android'}
        and native_record is True
        and language in {'multi', 'auto', ''}
    )


def validate_admission(value):
    if not isinstance(value, dict):
        raise ValueError('closed language admission receipt required')
    receipt = cast(dict[str, Any], value)
    if len(receipt) != len(ADMISSION_FIELDS) or not ADMISSION_FIELDS.issubset(receipt):
        raise ValueError('closed language admission receipt required')
    if type(receipt['version']) is not int or receipt['version'] != 1:
        raise ValueError('unsupported language admission receipt version')
    if not isinstance(receipt['language'], str) or receipt['language'] not in SUPPORTED | {'und', 'unsupported'}:
        raise ValueError('closed language admission labels required')
    if not isinstance(receipt['evidence'], str) or receipt['evidence'] not in EVIDENCE:
        raise ValueError('closed language evidence labels required')


def validate(value):
    if not isinstance(value, dict):
        raise ValueError('closed language receipt required')
    receipt = cast(dict[str, Any], value)
    if len(receipt) != len(FIELDS) or not FIELDS.issubset(receipt):
        raise ValueError('closed language receipt required')
    if type(receipt['version']) is not int or receipt['version'] != 1:
        raise ValueError('unsupported language receipt version')
    if (
        not isinstance(receipt['language'], str)
        or receipt['language'] not in SUPPORTED | {'und', 'unsupported'}
        or not isinstance(receipt['route'], str)
        or receipt['route'] not in ROUTES
    ):
        raise ValueError('closed language receipt labels required')
    counts = receipt['scripts']
    if not isinstance(counts, dict) or len(counts) != len(SCRIPTS) or not SCRIPTS.issubset(counts):
        raise ValueError('closed script counts required')
    counts = cast(dict[str, Any], counts)
    numbers = [receipt['word_count'], receipt['letters'], *counts.values()]
    if any(type(number) is not int or not 0 <= number <= 100_000_000 for number in numbers):
        raise ValueError('bounded language receipt counts required')
    if sum(counts.values()) != receipt['letters']:
        raise ValueError('script counts disagree with total')
    expected = expected_script(receipt['language'])
    incompatible = receipt['letters'] - counts[expected] if expected else None
    if incompatible is None:
        if receipt['incompatible_letters'] is not None:
            raise ValueError('incompatible script count must be absent without a supported script')
    elif (
        type(receipt['incompatible_letters']) is not int
        or not 0 <= receipt['incompatible_letters'] <= receipt['letters']
        or receipt['incompatible_letters'] != incompatible
    ):
        raise ValueError('incompatible script count disagrees with language')
