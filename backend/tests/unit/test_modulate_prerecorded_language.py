"""Execute the batch adapter with synthetic provider replies, without network."""

from unittest.mock import MagicMock

import pytest

from utils.stt import pre_recorded as stt


def utterance(text, language, duration=1000):
    return {'text': text, 'language': language, 'duration_ms': duration, 'start_ms': 0, 'speaker': 1}


def silence():
    """Velma's documented no-speech reply: every required field present, text and utterances empty."""
    return {'text': '', 'duration_ms': 120, 'utterances': []}


@pytest.fixture
def http(monkeypatch):
    monkeypatch.setenv('MODULATE_API_KEY', 'synthetic-test-key')
    response = MagicMock()
    response.status_code = 200
    client = MagicMock()
    client.__enter__.return_value = client
    client.post.return_value = response
    client.get.return_value.content = b'synthetic-wave'
    monkeypatch.setattr(stt.httpx, 'Client', lambda **kwargs: client)
    return client


@pytest.fixture
def reply(http):
    return http.post.return_value


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
    reply.json.return_value = {**silence(), 'utterances': utterances}
    _, language = stt.modulate_prerecorded_from_bytes(b'wave', return_language=True, language=requested)
    assert language == expected


@pytest.mark.parametrize('use_url', [True, False])
def test_provider_forwards_requested_language_on_url_and_bytes_paths(reply, use_url):
    reply.json.return_value = silence()
    provider = stt.ModulatePrerecordedProvider()
    transcribe = provider.transcribe_url if use_url else provider.transcribe_bytes
    assert transcribe(
        'https://synthetic.invalid/wave' if use_url else b'wave', return_language=True, language='vi-VN'
    ) == ([], 'vi')
    assert transcribe('https://synthetic.invalid/wave' if use_url else b'wave', return_language=True) == ([], 'multi')


def test_retry_preserves_requested_language(reply):
    reply.json.side_effect = [ValueError('synthetic malformed reply'), silence()]
    assert stt.modulate_prerecorded_from_bytes(b'wave', return_language=True, language='vi') == ([], 'vi')


# A 2xx body that is not the success shape (a JSON error envelope, a null, a bare
# string) must not be mapped to "no speech": sync would mark the segment silent,
# and held-piece recovery would checkpoint it as a completed empty reply and purge
# the audio. See #23081.
@pytest.mark.parametrize(
    'body',
    [
        {},
        {'error': 'quota exceeded'},
        {'detail': 'model loading'},
        {'utterances': None},
        {'utterances': 'none'},
        {'utterances': {}},
        [],
        None,
        'ok',
    ],
)
def test_response_without_utterances_list_raises_after_retries(monkeypatch, http, reply, body):
    # Legacy retry contract, retained behind the kill switch; fail-fast ON bounds
    # the same case to 2 POSTs (see test_prerecorded_vendor_fail_fast.py).
    monkeypatch.setenv('STT_PRERECORDED_VENDOR_FAIL_FAST', 'false')
    reply.json.return_value = body
    with pytest.raises(RuntimeError, match='Modulate transcription failed after 3 attempts'):
        stt.modulate_prerecorded_from_bytes(b'wave', return_language=True)
    assert http.post.call_count == 3


# {"utterances": []} on its own is not the documented silence reply, which also
# carries text ("" for no speech) and duration_ms; with neither sibling present the
# body could be any unrelated 2xx envelope. See #23081.
@pytest.mark.parametrize(
    'body',
    [
        {'utterances': []},
        {'utterances': [], 'text': None, 'duration_ms': None},
        {'utterances': [], 'text': 0},
        {'utterances': [], 'duration_ms': '120'},
        {'utterances': [], 'duration_ms': True},
        {'utterances': [], 'text': 'hello'},
        {'utterances': [], 'text': 'hello', 'duration_ms': 120},
        {'utterances': [{'text': ' ', 'language': 'en', 'duration_ms': 120, 'start_ms': 0}], 'text': 'hello'},
    ],
)
def test_empty_utterances_without_text_or_duration_raises_after_retries(monkeypatch, http, reply, body):
    # Legacy retry contract, retained behind the kill switch; fail-fast ON bounds
    # the same case to 2 POSTs (see test_prerecorded_vendor_fail_fast.py).
    monkeypatch.setenv('STT_PRERECORDED_VENDOR_FAIL_FAST', 'false')
    reply.json.return_value = body
    with pytest.raises(RuntimeError, match='Modulate transcription failed after 3 attempts'):
        stt.modulate_prerecorded_from_bytes(b'wave', return_language=True)
    assert http.post.call_count == 3


@pytest.mark.parametrize('body', [{'error': 'quota exceeded'}, {'utterances': None}, {'utterances': []}])
def test_held_dispatch_raises_on_malformed_body_after_one_call(http, reply, body):
    reply.json.return_value = body
    with stt.held_single_attempt(), pytest.raises(RuntimeError, match='failed after 1 attempts'):
        stt.modulate_prerecorded_from_bytes(b'wave', return_language=True)
    assert http.post.call_count == 1


@pytest.mark.parametrize('use_url', [True, False])
def test_malformed_body_raises_through_the_provider_on_url_and_bytes_paths(http, reply, use_url):
    reply.json.return_value = {'error': 'quota exceeded'}
    provider = stt.ModulatePrerecordedProvider()
    transcribe = provider.transcribe_url if use_url else provider.transcribe_bytes
    with pytest.raises(RuntimeError, match='Modulate transcription'):
        transcribe('https://synthetic.invalid/wave' if use_url else b'wave', return_language=True)


@pytest.mark.parametrize(
    'body',
    [
        silence(),
        {'utterances': [], 'text': ''},
        {'utterances': [], 'duration_ms': 120},
        {'utterances': [], 'duration_ms': 0},
        {'utterances': [], 'duration_ms': 120.0},
    ],
)
def test_well_formed_silence_is_still_no_speech(http, reply, body):
    reply.json.return_value = body
    assert stt.modulate_prerecorded_from_bytes(b'wave') == []
    assert stt.modulate_prerecorded_from_bytes(b'wave', return_language=True, language='vi') == ([], 'vi')
    assert http.post.call_count == 2


def test_non_empty_utterances_need_no_sibling_field(reply):
    reply.json.return_value = {'utterances': [utterance('one two three', 'en')]}
    assert [word['text'] for word in stt.modulate_prerecorded_from_bytes(b'wave')] == ['one two three']
