"""Execute the batch adapter with synthetic provider replies, without network."""

from unittest.mock import MagicMock

import pytest

from utils.stt import pre_recorded as stt


def utterance(text, language, duration=1000):
    return {'text': text, 'language': language, 'duration_ms': duration, 'start_ms': 0, 'speaker': 1}


@pytest.fixture
def reply(monkeypatch):
    monkeypatch.setenv('MODULATE_API_KEY', 'synthetic-test-key')
    response = MagicMock()
    client = MagicMock()
    client.__enter__.return_value = client
    client.post.return_value = response
    client.get.return_value.content = b'synthetic-wave'
    monkeypatch.setattr(stt.httpx, 'Client', lambda **kwargs: client)
    return response


@pytest.mark.parametrize(
    'utterances,expected',
    [
        ([utterance('We should review this synthetic draft today', 'en'), utterance('one two three', 'it')], 'en'),
        ([utterance('one two three', 'en', 2000), utterance('uno dos tres', 'es', 1000)], 'en'),
        ([utterance('one two three', 'en', 1000), utterance('uno dos tres', 'es', 2000)], 'es'),
        ([utterance('one two three', 'en')] * 2 + [utterance('uno dos tres cuatro cinco', 'es')], 'en'),
        ([utterance('We will review tomorrow', 'en')] + [utterance('si', 'es', 10000)] * 10, 'en'),
        ([utterance('Xin chao ban toi', 'vi'), utterance('okay', 'en')], 'vi'),
        ([utterance('yes', 'en'), utterance('si claro', 'es')], 'es'),
        (
            [utterance('one two three', 'en-US'), utterance('four five six', 'en_GB'), utterance('uno dos tres', 'es')],
            'en',
        ),
        ([utterance('one two three', None), utterance('yes', 'en')], 'multi'),
    ],
)
def test_word_majority_duration_ties_and_short_noise(reply, utterances, expected):
    reply.json.return_value = {'utterances': utterances}
    words, language = stt.modulate_prerecorded_from_bytes(b'wave', return_language=True)
    assert language == expected
    assert len(words) == len(utterances)
    assert words[0]['speaker'] == 'SPEAKER_00'


@pytest.mark.parametrize('utterances', [[], [utterance('  ', 'en')], [utterance('words without detection', None)]])
@pytest.mark.parametrize('requested,expected', [(None, 'multi'), ('multi', 'multi'), ('vi', 'vi')])
def test_no_detection_never_fabricates_english(reply, utterances, requested, expected):
    reply.json.return_value = {'utterances': utterances}
    _, language = stt.modulate_prerecorded_from_bytes(b'wave', return_language=True, language=requested)
    assert language == expected


@pytest.mark.parametrize('use_url', [True, False])
def test_provider_forwards_requested_language_on_url_and_bytes_paths(reply, use_url):
    reply.json.return_value = {'utterances': []}
    provider = stt.ModulatePrerecordedProvider()
    transcribe = provider.transcribe_url if use_url else provider.transcribe_bytes
    assert transcribe(
        'https://synthetic.invalid/wave' if use_url else b'wave', return_language=True, language='vi-VN'
    ) == ([], 'vi')
    assert transcribe('https://synthetic.invalid/wave' if use_url else b'wave', return_language=True) == ([], 'multi')


def test_retry_preserves_requested_language(reply):
    reply.json.side_effect = [ValueError('synthetic malformed reply'), {'utterances': []}]
    assert stt.modulate_prerecorded_from_bytes(b'wave', return_language=True, language='vi') == ([], 'vi')
