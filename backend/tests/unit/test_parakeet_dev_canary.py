"""Hermetic assertions for the dev Parakeet post-deploy canary."""

import pytest

from scripts.parakeet_dev_canary import MANIFESTS, check_result, load_fixture


@pytest.mark.parametrize('manifest_name', MANIFESTS)
def test_canary_fixtures_are_short_verified_speech(manifest_name):
    manifest, audio = load_fixture(manifest_name)
    assert manifest['language'] in {'en', 'pt'}
    assert audio


@pytest.mark.parametrize(
    'text,detected_language,latency',
    [
        ('', 'pt', 1.0),
        ('The wizard spoke English.', 'en', 1.0),
        ('A música está bonita.', 'pt', 31.0),
        ('English words in another language.', 'pt', 1.0),
    ],
)
def test_canary_rejects_empty_wrong_language_wrong_words_and_slow_output(text, detected_language, latency):
    with pytest.raises(AssertionError):
        check_result({'language': 'pt'}, {'text': text, 'detected_language': detected_language}, latency)


def test_canary_accepts_portuguese_diacritics():
    check_result({'language': 'pt'}, {'text': 'Vamos ouvir música amanhã.', 'detected_language': 'pt'}, 2.0)
