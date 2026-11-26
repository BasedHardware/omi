"""A multi-language user whose own live speech shows a language Parakeet cannot transcribe is classified on audio.

The conversation's supported pin (usually the app language, 'en') is not capability proof for that user:
the sampled LID path decides instead of admitting the upload straight to Parakeet.
"""

import pytest

from config.batch_pipeline_language import (
    MULTILINGUAL_PROFILE,
    PROFILE_FIELD,
    batch_admission_language,
    multilingual_profile_routing_enabled,
    profile_speaks_unsupported,
)

# Shape of a real multilingual owner's rolling projection: Mandarin is classified 'ja' by live STT, plus 'vi'.
MULTILINGUAL = [
    {'en': 8, 'vi': 1},
    {'ja': 33},
    {'en': 4, 'ja': 21},
    {'en': 172, 'vi': 1},
    {'en': 17, 'ja': 30},
    {'vi': 28},
]
# English speaker with classifier noise: stray single words never reach the per-session floor.
ENGLISH_WITH_NOISE = [{'en': 172, 'vi': 1}, {'en': 99, 'de': 2}, {'en': 45, 'vi': 1}, {'ja': 1}, {'ja': 1}]
# European languages are Parakeet's own; a German/English speaker keeps Parakeet.
EUROPEAN = [{'en': 40, 'de': 60}, {'de': 80}, {'fr': 50, 'en': 10}]


@pytest.fixture(autouse=True)
def defaults(monkeypatch):
    monkeypatch.delenv('BATCH_MULTILINGUAL_PROFILE_ROUTING_ENABLED', raising=False)


def multi_user(sessions):
    return {'language': 'en', 'transcription_preferences': {'single_language_mode': False}, PROFILE_FIELD: sessions}


@pytest.mark.parametrize(
    'sessions, expected',
    [
        (MULTILINGUAL, True),
        (ENGLISH_WITH_NOISE, False),
        (EUROPEAN, False),
        ([], False),
        (None, False),
        ('not-a-list', False),
        ([{'ja': 33}], False),  # one session is not a pattern
        ([{'ja': 9}, {'ja': 9}], False),  # under the per-session word floor
        ([{'en': 100, 'zh': 15}, {'en': 100, 'zh': 15}], False),  # under the per-session share
        ([{'en': 40, 'zh': 15}, {'en': 40, 'zh': 15}], True),
        ([{'zh': 'many'}, {'zh': True}, {7: 30}, 'row'], False),  # malformed rows count as nothing
        ([{'und': 30}, {'und': 30}], False),  # an unknown language is not evidence
        ([{'sr': 30}, {'sr': 30}], False),  # canonical 'sr' also stands for Parakeet's 'hr'
        ([{'hi': 30}, {'ko': 30}], True),
    ],
)
def test_profile_speaks_unsupported(sessions, expected):
    assert profile_speaks_unsupported({PROFILE_FIELD: sessions}) is expected


def test_multilingual_profile_does_not_trust_the_en_pin():
    assert batch_admission_language(multi_user(MULTILINGUAL), {'language': 'en'}) == (None, MULTILINGUAL_PROFILE)


@pytest.mark.parametrize('sessions', [ENGLISH_WITH_NOISE, EUROPEAN, None])
def test_other_multi_language_users_keep_the_pinned_route(sessions):
    assert batch_admission_language(multi_user(sessions), {'language': 'en'}) == ('en', None)


def test_single_language_mode_is_an_explicit_choice_and_wins():
    user = {**multi_user(MULTILINGUAL), 'transcription_preferences': {'single_language_mode': True}}
    assert batch_admission_language(user, {'language': 'en'}) == ('en', None)


def test_known_unsupported_conversation_is_unchanged():
    assert batch_admission_language(multi_user(MULTILINGUAL), {'language': 'zh'}) == (
        None,
        'known_unsupported_language',
    )


@pytest.mark.parametrize(
    'value, enabled', [(None, True), ('true', True), ('', True), ('false', False), ('FALSE', False)]
)
def test_kill_switch(monkeypatch, value, enabled):
    if value is not None:
        monkeypatch.setenv('BATCH_MULTILINGUAL_PROFILE_ROUTING_ENABLED', value)
    assert multilingual_profile_routing_enabled() is enabled
    expected = (None, MULTILINGUAL_PROFILE) if enabled else ('en', None)
    assert batch_admission_language(multi_user(MULTILINGUAL), {'language': 'en'}) == expected
