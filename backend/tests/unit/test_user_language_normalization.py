"""PATCH /v1/users/language must not persist a value no consumer can read."""

import pytest

from utils.user_language import ACCEPTED_BASE_LANGUAGES, normalize_user_language

# Every code the mobile picker can send (app/lib/providers/home_provider.dart).
CLIENT_SENT_CODES = (
    'en',
    'en-US',
    'en-GB',
    'en-AU',
    'en-NZ',
    'en-IN',
    'es',
    'es-419',
    'zh',
    'zh-CN',
    'zh-Hans',
    'hi',
    'pt',
    'pt-BR',
    'pt-PT',
    'ru',
    'ja',
    'de',
    'ar',
    'be',
    'bn',
    'bs',
    'bg',
    'ca',
    'zh-TW',
    'zh-Hant',
    'zh-HK',
    'hr',
    'cs',
    'da',
    'da-DK',
    'nl',
    'et',
    'fi',
    'nl-BE',
    'fr',
    'fr-CA',
    'de-CH',
    'el',
    'he',
    'hu',
    'id',
    'it',
    'kn',
    'ko',
    'ko-KR',
    'lv',
    'lt',
    'mk',
    'ms',
    'mr',
    'no',
    'fa',
    'pl',
    'ro',
    'sr',
    'sk',
    'sl',
    'sv',
    'sv-SE',
    'tl',
    'ta',
    'te',
    'th',
    'th-TH',
    'tr',
    'uk',
    'vi',
)


@pytest.mark.parametrize('code', CLIENT_SENT_CODES)
def test_a_code_a_client_can_send_is_preserved_exactly(code):
    assert normalize_user_language(code) == code


@pytest.mark.parametrize(
    'name,expected',
    [
        ('japanese', 'ja'),
        ('Japanese', 'ja'),
        ('JAPANESE', 'ja'),
        ('  japanese  ', 'ja'),
        ('russian', 'ru'),
        ('portuguese', 'pt'),
        ('brazilian portuguese', 'pt'),
        ('mandarin', 'zh'),
        ('simplified chinese', 'zh'),
        ('flemish', 'nl'),
        ('farsi', 'fa'),
        ('filipino', 'tl'),
    ],
)
def test_a_language_name_resolves_to_its_code(name, expected):
    """Desktop onboarding sent names; those clients must keep working."""
    assert normalize_user_language(name) == expected


@pytest.mark.parametrize('value', ['', '   ', None, 'not-a-language', 'klingon', 'xx', 'zz-ZZ', 'en_US_extra_junk'])
def test_an_unresolvable_value_is_rejected(value):
    assert normalize_user_language(value) is None


def test_underscore_separators_are_normalized():
    assert normalize_user_language('zh_Hans') == 'zh-Hans'
    assert normalize_user_language('pt_BR') == 'pt-BR'


def test_multi_is_accepted_as_the_auto_detect_preference():
    assert normalize_user_language('multi') == 'multi'


def test_accepted_set_is_derived_from_provider_capability():
    for code in ('multi', 'en', 'ja', 'hi', 'tr', 'mt'):
        assert code in ACCEPTED_BASE_LANGUAGES
    assert 'klingon' not in ACCEPTED_BASE_LANGUAGES


def test_every_mapped_name_resolves_to_an_accepted_base():
    from utils.user_language import LANGUAGE_NAME_TO_BASE

    unserviceable = {name: base for name, base in LANGUAGE_NAME_TO_BASE.items() if base not in ACCEPTED_BASE_LANGUAGES}
    assert unserviceable == {}
